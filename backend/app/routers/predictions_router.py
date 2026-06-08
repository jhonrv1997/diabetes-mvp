import json
import os
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.config import settings
from app.database import get_db
from app.models import User, Patient, GlucoseReading, ClinicalData, Prediction
from app.schemas import (
    PredictionResponse,
    PredictionRequest,
    SHAPExplanation,
)

# Conditional imports — TensorFlow/ML may not be installed
try:
    from app.services.ml_model import DiabetesRiskModel, TF_AVAILABLE as ML_TF_AVAILABLE
    from app.services.shap_explainer import ShapExplainer
    ML_AVAILABLE = True
except ImportError as e:
    ML_AVAILABLE = False
    ML_TF_AVAILABLE = False
    DiabetesRiskModel = None
    ShapExplainer = None
    logging.getLogger(__name__).warning(
        "ML modules not fully available (%s). Using heuristic scoring.", e
    )

# AlertService is TF-independent, import separately
try:
    from app.services.alert_service import AlertService
except ImportError:
    AlertService = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Predictions"])

# Lazy-loaded model singleton
_model_instance = None
_model_load_attempted = False
_explainer_instance = None


def _get_model():
    """Load the ML model lazily (singleton pattern). Returns None if unavailable."""
    global _model_instance, _model_load_attempted

    if not ML_AVAILABLE:
        return None

    if _model_instance is not None and _model_instance.is_loaded:
        return _model_instance

    # Only attempt to load once to avoid repeated failures
    if _model_load_attempted and (_model_instance is None or not _model_instance.is_loaded):
        return None

    _model_load_attempted = True
    model_path = settings.MODEL_PATH
    if os.path.exists(model_path):
        try:
            _model_instance = DiabetesRiskModel(model_path=model_path)
            if _model_instance.is_loaded:
                logger.info("ML model loaded from %s", model_path)
                return _model_instance
            else:
                logger.info("Model at %s exists but could not be loaded — using heuristic", model_path)
                return None
        except Exception as exc:
            logger.warning("Failed to load ML model: %s — falling back to heuristic", exc)
            _model_instance = None
            return None
    else:
        logger.info("No trained model found at %s — using heuristic scoring", model_path)
        return None


def _get_explainer(model):
    """Get or create a ShapExplainer for the given model (singleton)."""
    global _explainer_instance
    if ShapExplainer is None:
        return None
    if _explainer_instance is None:
        _explainer_instance = ShapExplainer(model)
    return _explainer_instance


@router.post("/predict/{patient_id}", response_model=PredictionResponse)
async def predict_patient(
    patient_id: int,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
    shap_method: str = Query(
        "auto",
        description="Método de explicación: auto, shap, integrated_gradients, heuristic",
    ),
    shap_samples: int = Query(
        100,
        description="Número de muestras para SHAP KernelExplainer (mayor = más preciso pero más lento)",
    ),
):
    """
    Generate a diabetes risk prediction for a patient with full SHAP explanation.

    Parameters
    ----------
    patient_id : int
        The patient to predict for.
    shap_method : str
        Explanation method: "auto" | "shap" | "integrated_gradients" | "heuristic"
    shap_samples : int
        Number of samples for SHAP (only applies when method is "shap" or "auto").
    """
    # Verify patient exists
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    # Fetch last ~90 glucose readings (30 day window)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    glucose_result = await db.execute(
        select(GlucoseReading)
        .where(
            and_(
                GlucoseReading.patient_id == patient_id,
                GlucoseReading.measurement_timestamp >= thirty_days_ago,
            )
        )
        .order_by(desc(GlucoseReading.measurement_timestamp))
        .limit(90)
    )
    glucose_readings = list(glucose_result.scalars().all())

    if not glucose_readings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No glucose readings found for this patient in the last 30 days",
        )

    # Fetch latest clinical data
    clinical_result = await db.execute(
        select(ClinicalData)
        .where(ClinicalData.patient_id == patient_id)
        .order_by(desc(ClinicalData.created_at))
        .limit(1)
    )
    clinical = clinical_result.scalar_one_or_none()

    warnings_list = []
    if clinical is None:
        warnings_list.append("No clinical data available. Prediction may be less accurate.")
    elif clinical.created_at < datetime.utcnow() - timedelta(days=settings.CLINICAL_DATA_EXPIRY_DAYS):
        warnings_list.append(
            f"Clinical data is older than {settings.CLINICAL_DATA_EXPIRY_DAYS} days. "
            "Consider updating clinical measurements."
        )

    # Prepare common data
    glucose_list = [float(r.glucose_mg_dl) for r in glucose_readings]

    # ── ML model prediction + SHAP explanation ───────────────────────────
    model = _get_model()
    full_explanation = None
    risk_probability = None
    risk_level = None
    confidence = None
    model_version = "heuristic-1.0"

    if model is not None and model.is_loaded and clinical is not None:
        try:
            clinical_dict = {
                "age": clinical.age,
                "bmi": clinical.bmi or 25.0,
                "systolic_bp": clinical.systolic_bp,
                "diastolic_bp": clinical.diastolic_bp,
                "family_diabetes": int(clinical.family_diabetes),
                "hypertension": int(clinical.hypertension_history),
            }

            # Run ML prediction
            pred_result = model.predict(glucose_list, clinical_dict)
            risk_probability = pred_result["risk_probability"]
            risk_level = pred_result["risk_level"]
            confidence = pred_result["confidence"]
            model_version = model.model_version

            # Run SHAP explainer (full explanation)
            explainer = _get_explainer(model)
            if explainer is not None:
                try:
                    full_explanation = explainer.explain_prediction(
                        glucose_list,
                        clinical_dict,
                        n_samples=min(shap_samples, 300),
                        method=shap_method,
                    )
                except Exception as shap_exc:
                    logger.warning("SHAP explanation failed: %s", shap_exc)

        except Exception as exc:
            logger.warning("ML prediction failed: %s — falling back to heuristic", exc)

    # ── Heuristic path (no model or model failed) ────────────────────────
    if risk_probability is None:
        # Use ShapExplainer's heuristic for both prediction and explanation
        # to ensure consistency between risk_probability and explanation
        clinical_dict = None
        if clinical is not None:
            clinical_dict = {
                "age": clinical.age,
                "bmi": clinical.bmi or 25.0,
                "systolic_bp": clinical.systolic_bp,
                "diastolic_bp": clinical.diastolic_bp,
                "family_diabetes": int(clinical.family_diabetes),
                "hypertension": int(clinical.hypertension_history),
            }

        try:
            h_explainer = ShapExplainer(None)
            full_explanation = h_explainer.explain_prediction(
                glucose_list,
                clinical_dict or {},
                method="heuristic",
            )
            risk_probability = full_explanation["prediction"]
            # Classify risk from heuristic probability
            if risk_probability >= settings.RISK_THRESHOLD_HIGH:
                risk_level = "high"
            elif risk_probability >= settings.RISK_THRESHOLD_LOW:
                risk_level = "medium"
            else:
                risk_level = "low"
        except Exception as heur_exc:
            logger.warning("Heuristic explanation also failed: %s", heur_exc)
            # Ultimate fallback: simple average-based scoring
            avg_glucose = sum(glucose_list) / len(glucose_list) if glucose_list else 100
            risk_probability = min(max((avg_glucose - 70) / 330, 0.0), 1.0)
            if risk_probability >= settings.RISK_THRESHOLD_HIGH:
                risk_level = "high"
            elif risk_probability >= settings.RISK_THRESHOLD_LOW:
                risk_level = "medium"
            else:
                risk_level = "low"

    # Extract shap_values from full explanation for legacy compatibility
    shap_values = full_explanation["shap_values"] if full_explanation else None

    # ── Store prediction ─────────────────────────────────────────────────
    prediction = Prediction(
        patient_id=patient_id,
        risk_probability=risk_probability,
        risk_level=risk_level,
        confidence=confidence,
        glucose_readings_used=len(glucose_readings),
        model_version=model_version,
        shap_values_json=json.dumps(shap_values) if shap_values else None,
        shap_explanation_json=json.dumps(full_explanation) if full_explanation else None,
        shap_base_value=full_explanation.get("base_value") if full_explanation else None,
        shap_method=full_explanation.get("method_used") if full_explanation else None,
        predicted_by=current_user.id,
    )
    db.add(prediction)
    await db.flush()
    await db.refresh(prediction)

    # Create alert if risk warrants it
    if AlertService is not None:
        try:
            alert_service = AlertService(db)
            await alert_service.check_and_create_alerts(prediction)
        except Exception as alert_exc:
            logger.warning("Failed to create alert: %s", alert_exc)

    # ── Build response with full SHAP explanation ────────────────────────
    response_data = {
        "id": prediction.id,
        "patient_id": prediction.patient_id,
        "risk_probability": prediction.risk_probability,
        "risk_level": prediction.risk_level,
        "confidence": prediction.confidence,
        "glucose_readings_used": prediction.glucose_readings_used,
        "model_version": prediction.model_version,
        "shap_values": prediction.shap_values,
        "shap_explanation": full_explanation,
        "predicted_by": prediction.predicted_by,
        "created_at": prediction.created_at,
    }

    return PredictionResponse(**response_data)


@router.get("/explain/{prediction_id}", response_model=SHAPExplanation)
async def explain_prediction(
    prediction_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve the full SHAP explanation for a past prediction.

    If the explanation is cached in the database, returns it directly.
    Otherwise, returns a 404.
    """
    result = await db.execute(
        select(Prediction).where(Prediction.id == prediction_id)
    )
    prediction = result.scalar_one_or_none()
    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prediction not found",
        )

    # Return cached explanation if available
    if prediction.shap_explanation:
        return SHAPExplanation(**prediction.shap_explanation)

    # Return basic SHAP values if we have them
    if prediction.shap_values:
        return SHAPExplanation(
            shap_values=prediction.shap_values,
            base_value=prediction.shap_base_value or 0.0,
            prediction=prediction.risk_probability,
            method_used=prediction.shap_method or "unknown",
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No SHAP explanation available for this prediction",
    )


@router.get("/predictions", response_model=list[PredictionResponse])
async def list_predictions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all predictions, ordered by most recent first."""
    result = await db.execute(
        select(Prediction).order_by(desc(Prediction.created_at))
    )
    return result.scalars().all()


@router.get("/predictions/{patient_id}", response_model=list[PredictionResponse])
async def list_patient_predictions(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all predictions for a specific patient, ordered by most recent first."""
    # Verify patient exists
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    result = await db.execute(
        select(Prediction)
        .where(Prediction.patient_id == patient_id)
        .order_by(desc(Prediction.created_at))
    )
    return result.scalars().all()
