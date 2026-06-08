import json
import os
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.config import settings
from app.database import get_db
from app.models import User, Patient, GlucoseReading, ClinicalData, Prediction
from app.schemas import PredictionResponse, PredictionRequest

# Conditional imports — TensorFlow/ML may not be installed
try:
    from app.services.ml_model import DiabetesRiskModel, TF_AVAILABLE as ML_TF_AVAILABLE
    from app.services.shap_explainer import ShapExplainer
    from app.services.alert_service import AlertService
    ML_AVAILABLE = True
except ImportError as e:
    ML_AVAILABLE = False
    ML_TF_AVAILABLE = False
    DiabetesRiskModel = None
    ShapExplainer = None
    AlertService = None
    logging.getLogger(__name__).warning(
        "ML modules not fully available (%s). Using heuristic scoring.", e
    )

# Import AlertService separately since it doesn't depend on TF
try:
    from app.services.alert_service import AlertService
except ImportError:
    AlertService = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Predictions"])

# Lazy-loaded model singleton
_model_instance = None


def _get_model():
    """Load the ML model lazily (singleton pattern). Returns None if unavailable."""
    global _model_instance
    if not ML_AVAILABLE:
        return None

    if _model_instance is None or not _model_instance.is_loaded:
        model_path = settings.MODEL_PATH
        if os.path.exists(model_path):
            try:
                _model_instance = DiabetesRiskModel(model_path=model_path)
                logger.info("ML model loaded from %s", model_path)
            except Exception as exc:
                logger.warning("Failed to load ML model: %s — falling back to heuristic", exc)
                _model_instance = None
        else:
            logger.info("No trained model found at %s — using heuristic scoring", model_path)
            _model_instance = None
    return _model_instance


def _compute_risk_heuristic(
    glucose_readings: list,
    clinical: ClinicalData | None,
) -> tuple[float, str, dict | None]:
    """
    Heuristic risk scoring as a fallback when the ML model is not available.
    """
    score = 0.0
    shap: dict[str, float] = {}

    if glucose_readings:
        avg_glucose = sum(r.glucose_mg_dl for r in glucose_readings) / len(glucose_readings)
        if avg_glucose >= 200:
            g_score = 0.40
        elif avg_glucose >= 140:
            g_score = 0.25
        elif avg_glucose >= 100:
            g_score = 0.10
        else:
            g_score = 0.0
        score += g_score
        shap["avg_glucose"] = round(g_score, 4)

        if len(glucose_readings) > 1:
            mean_g = avg_glucose
            variance = sum((r.glucose_mg_dl - mean_g) ** 2 for r in glucose_readings) / len(glucose_readings)
            import math
            std_g = math.sqrt(variance)
            if std_g > 60:
                v_score = 0.10
            elif std_g > 30:
                v_score = 0.05
            else:
                v_score = 0.0
            score += v_score
            shap["glucose_variability"] = round(v_score, 4)

    if clinical:
        if clinical.bmi:
            if clinical.bmi >= 35:
                b_score = 0.15
            elif clinical.bmi >= 30:
                b_score = 0.10
            elif clinical.bmi >= 25:
                b_score = 0.05
            else:
                b_score = 0.0
            score += b_score
            shap["bmi"] = round(b_score, 4)

        if clinical.age >= 65:
            a_score = 0.10
        elif clinical.age >= 45:
            a_score = 0.05
        else:
            a_score = 0.0
        score += a_score
        shap["age"] = round(a_score, 4)

        if clinical.systolic_bp >= 140 or clinical.diastolic_bp >= 90:
            bp_score = 0.10
        elif clinical.systolic_bp >= 130 or clinical.diastolic_bp >= 80:
            bp_score = 0.05
        else:
            bp_score = 0.0
        score += bp_score
        shap["blood_pressure"] = round(bp_score, 4)

        if clinical.family_diabetes:
            score += 0.10
            shap["family_diabetes"] = 0.10

        if clinical.hypertension_history:
            score += 0.05
            shap["hypertension_history"] = 0.05
    else:
        shap["clinical_data"] = 0.0

    prob = min(score, 1.0)

    if prob >= settings.RISK_THRESHOLD_HIGH:
        level = "high"
    elif prob >= settings.RISK_THRESHOLD_LOW:
        level = "medium"
    else:
        level = "low"

    return prob, level, shap


@router.post("/predict/{patient_id}", response_model=PredictionResponse)
async def predict_patient(
    patient_id: int,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
):
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

    # Try ML model first, fall back to heuristic
    model = _get_model()
    shap_values = None
    confidence = None

    if model is not None and clinical is not None:
        try:
            # Prepare inputs for ML model
            glucose_list = [float(r.glucose_mg_dl) for r in glucose_readings]
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

            # Run SHAP explainer
            try:
                explainer = ShapExplainer(model)
                explanation = explainer.explain_prediction(glucose_list, clinical_dict, n_steps=15)
                shap_values = explanation["shap_values"]
            except Exception as shap_exc:
                logger.warning("SHAP explanation failed: %s", shap_exc)
                shap_values = {"model": "ml", "probability": risk_probability}

        except Exception as exc:
            logger.warning("ML prediction failed: %s — falling back to heuristic", exc)
            risk_probability, risk_level, shap_values = _compute_risk_heuristic(
                glucose_readings, clinical
            )
    else:
        # No model available — use heuristic
        risk_probability, risk_level, shap_values = _compute_risk_heuristic(
            glucose_readings, clinical
        )

    # Store prediction
    prediction = Prediction(
        patient_id=patient_id,
        risk_probability=risk_probability,
        risk_level=risk_level,
        confidence=confidence,
        glucose_readings_used=len(glucose_readings),
        model_version=model.model_version if model else "heuristic-1.0",
        shap_values_json=json.dumps(shap_values) if shap_values else None,
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

    return prediction


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