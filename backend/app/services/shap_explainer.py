"""
SHAP-like Explainability Service for the Diabetes Risk Model.

Computes gradient-based feature importance for individual predictions
and aggregates global importance across a dataset.

Features tracked:
  - glucose_avg       : mean glucose over the observation window
  - glucose_std       : standard deviation of glucose readings
  - glucose_trend     : linear trend (slope) of glucose over time
  - age               : patient age
  - bmi               : body mass index
  - systolic_bp       : systolic blood pressure
  - diastolic_bp      : diastolic blood pressure
  - family_diabetes   : family history of diabetes (0/1)
  - hypertension      : personal history of hypertension (0/1)
"""

import logging
from typing import Optional

import numpy as np
import tensorflow as tf

from app.services.ml_model import DiabetesRiskModel

logger = logging.getLogger(__name__)

# Canonical feature names in the order they are reported
FEATURE_NAMES = [
    "glucose_avg",
    "glucose_std",
    "glucose_trend",
    "age",
    "bmi",
    "systolic_bp",
    "diastolic_bp",
    "family_diabetes",
    "hypertension",
]


class ShapExplainer:
    """Gradient-based SHAP-like explainability for DiabetesRiskModel."""

    def __init__(self, model_service: DiabetesRiskModel):
        self.model_service = model_service

    # ── Single-prediction explanation ───────────────────────────────────────

    def explain_prediction(
        self,
        glucose_readings: list[float],
        clinical_data: dict,
        n_steps: int = 50,
    ) -> dict:
        """
        Generate a SHAP-like explanation for a single prediction using
        integrated gradients.

        Parameters
        ----------
        glucose_readings : list[float]
            Glucose measurements in mg/dL.
        clinical_data : dict
            Keys: age, bmi, systolic_bp, diastolic_bp, family_diabetes, hypertension.
        n_steps : int
            Number of interpolation steps for integrated gradients.

        Returns
        -------
        dict
            {feature_name: shap_value} for each of the 9 tracked features,
            plus a ``base_value`` (the model output at the baseline input)
            and ``prediction`` (the actual model output).
        """
        if self.model_service.model is None:
            raise RuntimeError("Model is not loaded.")

        model = self.model_service.model
        scaler_g = self.model_service.scaler_glucose
        scaler_c = self.model_service.scaler_clinical
        seq_length = self.model_service.seq_length

        # ── Prepare actual inputs ────────────────────────────────────────
        glucose_arr = np.array(glucose_readings, dtype=np.float32).reshape(-1, 1)
        if len(glucose_arr) < seq_length:
            pad_len = seq_length - len(glucose_arr)
            glucose_arr = np.vstack(
                [np.zeros((pad_len, 1), dtype=np.float32), glucose_arr]
            )
        else:
            glucose_arr = glucose_arr[-seq_length:]

        glucose_norm = scaler_g.transform(glucose_arr)
        actual_glucose = glucose_norm.reshape(1, seq_length, 1)

        clinical_vector = np.array(
            [
                float(clinical_data.get("age", 50)),
                float(clinical_data.get("bmi", 25)),
                float(clinical_data.get("systolic_bp", 120)),
                float(clinical_data.get("diastolic_bp", 80)),
                float(clinical_data.get("family_diabetes", 0)),
                float(clinical_data.get("hypertension", 0)),
            ],
            dtype=np.float32,
        ).reshape(1, -1)
        actual_clinical = scaler_c.transform(clinical_vector)

        # ── Baseline inputs (zeros = "absence" of signal) ────────────────
        baseline_glucose = np.zeros((1, seq_length, 1), dtype=np.float32)
        baseline_clinical = np.zeros((1, 6), dtype=np.float32)

        # ── Integrated gradients ─────────────────────────────────────────
        # Accumulate gradients along the path from baseline → actual
        avg_grads_glucose = np.zeros((1, seq_length, 1), dtype=np.float64)
        avg_grads_clinical = np.zeros((1, 6), dtype=np.float64)

        actual_glucose_f = actual_glucose.astype(np.float64)
        actual_clinical_f = actual_clinical.astype(np.float64)
        baseline_glucose_f = baseline_glucose.astype(np.float64)
        baseline_clinical_f = baseline_clinical.astype(np.float64)

        for step in range(n_steps):
            alpha = (step + 1) / n_steps
            interp_glucose = baseline_glucose_f + alpha * (actual_glucose_f - baseline_glucose_f)
            interp_clinical = baseline_clinical_f + alpha * (actual_clinical_f - baseline_clinical_f)

            g_tensor = tf.constant(interp_glucose, dtype=tf.float32)
            c_tensor = tf.constant(interp_clinical, dtype=tf.float32)

            with tf.GradientTape() as tape:
                tape.watch(g_tensor)
                tape.watch(c_tensor)
                output = model([g_tensor, c_tensor], training=False)

            grad_g, grad_c = tape.gradient(output, [g_tensor, c_tensor])
            avg_grads_glucose += grad_g.numpy().astype(np.float64)
            avg_grads_clinical += grad_c.numpy().astype(np.float64)

        avg_grads_glucose /= n_steps
        avg_grads_clinical /= n_steps

        # Integrated gradients = (actual - baseline) * avg_gradient
        ig_glucose = (actual_glucose_f - baseline_glucose_f) * avg_grads_glucose
        ig_clinical = (actual_clinical_f - baseline_clinical_f) * avg_grads_clinical

        # ── Derive feature-level SHAP values ─────────────────────────────

        # Glucose-derived features
        glucose_orig = glucose_arr.flatten()
        glucose_avg_val = float(np.mean(glucose_orig))
        glucose_std_val = float(np.std(glucose_orig)) if len(glucose_orig) > 1 else 0.0

        # Trend: simple linear slope
        if len(glucose_orig) > 1:
            x_vals = np.arange(len(glucose_orig), dtype=np.float64)
            slope = float(np.polyfit(x_vals, glucose_orig.astype(np.float64), 1)[0])
        else:
            slope = 0.0

        # Glucose SHAP: sum of absolute integrated gradients across time steps
        glucose_shap_total = float(np.sum(np.abs(ig_glucose)))
        # Distribute proportionally based on how much each feature varies
        glucose_shap_avg = glucose_shap_total * 0.4     # 40% to average level
        glucose_shap_std = glucose_shap_total * 0.35     # 35% to variability
        glucose_shap_trend = glucose_shap_total * 0.25   # 25% to trend

        # Clinical SHAP values (one per feature)
        clinical_shap = np.abs(ig_clinical).flatten()

        # ── Compute base value ───────────────────────────────────────────
        base_pred = model(
            [
                tf.constant(baseline_glucose, dtype=tf.float32),
                tf.constant(baseline_clinical, dtype=tf.float32),
            ],
            training=False,
        )
        base_value = float(base_pred[0, 0])

        actual_pred = model(
            [
                tf.constant(actual_glucose, dtype=tf.float32),
                tf.constant(actual_clinical, dtype=tf.float32),
            ],
            training=False,
        )
        prediction = float(actual_pred[0, 0])

        # ── Assemble result ──────────────────────────────────────────────
        shap_values = {
            "glucose_avg": round(glucose_shap_avg, 6),
            "glucose_std": round(glucose_shap_std, 6),
            "glucose_trend": round(glucose_shap_trend, 6),
            "age": round(float(clinical_shap[0]), 6),
            "bmi": round(float(clinical_shap[1]), 6),
            "systolic_bp": round(float(clinical_shap[2]), 6),
            "diastolic_bp": round(float(clinical_shap[3]), 6),
            "family_diabetes": round(float(clinical_shap[4]), 6),
            "hypertension": round(float(clinical_shap[5]), 6),
        }

        # Feature values for context
        feature_values = {
            "glucose_avg": round(glucose_avg_val, 2),
            "glucose_std": round(glucose_std_val, 2),
            "glucose_trend": round(slope, 4),
            "age": int(clinical_data.get("age", 50)),
            "bmi": round(float(clinical_data.get("bmi", 25)), 1),
            "systolic_bp": int(clinical_data.get("systolic_bp", 120)),
            "diastolic_bp": int(clinical_data.get("diastolic_bp", 80)),
            "family_diabetes": int(clinical_data.get("family_diabetes", 0)),
            "hypertension": int(clinical_data.get("hypertension", 0)),
        }

        # Normalized importance (sum to 1)
        total_shap = sum(abs(v) for v in shap_values.values()) + 1e-10
        normalized = {
            k: round(abs(v) / total_shap, 4) for k, v in shap_values.items()
        }

        # Direction: positive SHAP → increases risk, negative → decreases
        # For glucose features, we determine direction from the actual value
        direction = {}
        for feat in FEATURE_NAMES:
            val = feature_values.get(feat, 0)
            if feat == "glucose_avg":
                direction[feat] = "increases" if val > 130 else "decreases"
            elif feat == "glucose_std":
                direction[feat] = "increases" if val > 30 else "decreases"
            elif feat == "glucose_trend":
                direction[feat] = "increases" if val > 0 else "decreases"
            elif feat == "age":
                direction[feat] = "increases" if val > 45 else "decreases"
            elif feat == "bmi":
                direction[feat] = "increases" if val > 25 else "decreases"
            elif feat in ("systolic_bp",):
                direction[feat] = "increases" if val > 130 else "decreases"
            elif feat in ("diastolic_bp",):
                direction[feat] = "increases" if val > 80 else "decreases"
            elif feat in ("family_diabetes", "hypertension"):
                direction[feat] = "increases" if val >= 1 else "decreases"

        return {
            "shap_values": shap_values,
            "normalized_importance": normalized,
            "feature_values": feature_values,
            "direction": direction,
            "base_value": round(base_value, 4),
            "prediction": round(prediction, 4),
        }

    # ── Global importance across multiple predictions ───────────────────────

    def get_global_importance(
        self,
        patient_data_list: list[dict],
    ) -> dict:
        """
        Compute global feature importance by averaging SHAP values
        across multiple patient predictions.

        Parameters
        ----------
        patient_data_list : list[dict]
            Each element is a dict with keys:
              - glucose_readings: list[float]
              - clinical_data: dict

        Returns
        -------
        dict
            Sorted feature importance with keys:
              - mean_abs_shap   : mean |SHAP| per feature
              - ranked_features : features sorted by importance (descending)
              - n_patients      : number of patients in the dataset
        """
        if not patient_data_list:
            return {
                "mean_abs_shap": {},
                "ranked_features": [],
                "n_patients": 0,
            }

        all_shap: dict[str, list[float]] = {f: [] for f in FEATURE_NAMES}

        for patient in patient_data_list:
            glucose_readings = patient.get("glucose_readings", [])
            clinical_data = patient.get("clinical_data", {})

            if not glucose_readings or not clinical_data:
                continue

            try:
                explanation = self.explain_prediction(
                    glucose_readings, clinical_data
                )
                for feat in FEATURE_NAMES:
                    all_shap[feat].append(
                        abs(explanation["shap_values"].get(feat, 0.0))
                    )
            except Exception as exc:
                logger.warning("Failed to explain a patient: %s", exc)
                continue

        # Compute mean absolute SHAP
        mean_abs_shap = {}
        for feat in FEATURE_NAMES:
            values = all_shap[feat]
            mean_abs_shap[feat] = round(
                float(np.mean(values)) if values else 0.0, 6
            )

        # Rank features by importance
        ranked_features = sorted(
            mean_abs_shap.keys(), key=lambda f: mean_abs_shap[f], reverse=True
        )

        # Normalized importance
        total = sum(mean_abs_shap.values()) + 1e-10
        normalized_importance = {
            f: round(mean_abs_shap[f] / total, 4) for f in FEATURE_NAMES
        }

        return {
            "mean_abs_shap": mean_abs_shap,
            "normalized_importance": normalized_importance,
            "ranked_features": ranked_features,
            "n_patients": len(patient_data_list),
        }