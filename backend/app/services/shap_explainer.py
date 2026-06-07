"""
SHAP-like Explainability Service for the Diabetes Risk Model.

Computes gradient-based feature importance for individual predictions
and aggregates global importance across a dataset.

Requires TensorFlow for gradient computation.
When TensorFlow is not available, provides a heuristic fallback.
"""

import logging
from typing import Optional

import numpy as np

# TensorFlow is optional
try:
    import tensorflow as tf
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    tf = None

from app.services.ml_model import DiabetesRiskModel, TF_AVAILABLE as MODEL_TF_AVAILABLE

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
        Generate a SHAP-like explanation for a single prediction.

        If TensorFlow is available, uses integrated gradients.
        Otherwise, falls back to a heuristic explanation.
        """
        if not TF_AVAILABLE:
            return self._heuristic_explanation(glucose_readings, clinical_data)

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

        # ── Baseline inputs ──────────────────────────────────────────────
        baseline_glucose = np.zeros((1, seq_length, 1), dtype=np.float32)
        baseline_clinical = np.zeros((1, 6), dtype=np.float32)

        # ── Integrated gradients ─────────────────────────────────────────
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
        glucose_orig = glucose_arr.flatten()
        glucose_avg_val = float(np.mean(glucose_orig))
        glucose_std_val = float(np.std(glucose_orig)) if len(glucose_orig) > 1 else 0.0

        if len(glucose_orig) > 1:
            x_vals = np.arange(len(glucose_orig), dtype=np.float64)
            slope = float(np.polyfit(x_vals, glucose_orig.astype(np.float64), 1)[0])
        else:
            slope = 0.0

        glucose_shap_total = float(np.sum(np.abs(ig_glucose)))
        glucose_shap_avg = glucose_shap_total * 0.4
        glucose_shap_std = glucose_shap_total * 0.35
        glucose_shap_trend = glucose_shap_total * 0.25

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

        total_shap = sum(abs(v) for v in shap_values.values()) + 1e-10
        normalized = {
            k: round(abs(v) / total_shap, 4) for k, v in shap_values.items()
        }

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

    # ── Heuristic fallback (without TensorFlow) ─────────────────────────────

    def _heuristic_explanation(
        self,
        glucose_readings: list[float],
        clinical_data: dict,
    ) -> dict:
        """
        Provide a heuristic-based explanation when TensorFlow is not available.
        """
        glucose_arr = np.array(glucose_readings, dtype=np.float32)
        glucose_avg_val = float(np.mean(glucose_arr)) if len(glucose_arr) > 0 else 0.0
        glucose_std_val = float(np.std(glucose_arr)) if len(glucose_arr) > 1 else 0.0

        if len(glucose_arr) > 1:
            x_vals = np.arange(len(glucose_arr), dtype=np.float64)
            slope = float(np.polyfit(x_vals, glucose_arr.astype(np.float64), 1)[0])
        else:
            slope = 0.0

        # Heuristic importance scores
        shap_values = {}

        # Glucose average importance
        if glucose_avg_val >= 200:
            shap_values["glucose_avg"] = 0.30
        elif glucose_avg_val >= 140:
            shap_values["glucose_avg"] = 0.20
        elif glucose_avg_val >= 100:
            shap_values["glucose_avg"] = 0.10
        else:
            shap_values["glucose_avg"] = 0.02

        # Glucose variability
        if glucose_std_val > 60:
            shap_values["glucose_std"] = 0.15
        elif glucose_std_val > 30:
            shap_values["glucose_std"] = 0.08
        else:
            shap_values["glucose_std"] = 0.02

        # Glucose trend
        if slope > 1.0:
            shap_values["glucose_trend"] = 0.10
        elif slope > 0:
            shap_values["glucose_trend"] = 0.05
        else:
            shap_values["glucose_trend"] = 0.01

        # Clinical features
        age = float(clinical_data.get("age", 50))
        bmi = float(clinical_data.get("bmi", 25))
        systolic = float(clinical_data.get("systolic_bp", 120))
        diastolic = float(clinical_data.get("diastolic_bp", 80))
        family = float(clinical_data.get("family_diabetes", 0))
        hypertension = float(clinical_data.get("hypertension", 0))

        shap_values["age"] = 0.12 if age >= 65 else (0.06 if age >= 45 else 0.02)
        shap_values["bmi"] = 0.15 if bmi >= 35 else (0.10 if bmi >= 30 else (0.05 if bmi >= 25 else 0.02))
        shap_values["systolic_bp"] = 0.10 if systolic >= 140 else (0.05 if systolic >= 130 else 0.02)
        shap_values["diastolic_bp"] = 0.08 if diastolic >= 90 else (0.04 if diastolic >= 80 else 0.01)
        shap_values["family_diabetes"] = 0.10 if family >= 1 else 0.02
        shap_values["hypertension"] = 0.08 if hypertension >= 1 else 0.01

        feature_values = {
            "glucose_avg": round(glucose_avg_val, 2),
            "glucose_std": round(glucose_std_val, 2),
            "glucose_trend": round(slope, 4),
            "age": int(age),
            "bmi": round(bmi, 1),
            "systolic_bp": int(systolic),
            "diastolic_bp": int(diastolic),
            "family_diabetes": int(family),
            "hypertension": int(hypertension),
        }

        total_shap = sum(abs(v) for v in shap_values.values()) + 1e-10
        normalized = {
            k: round(abs(v) / total_shap, 4) for k, v in shap_values.items()
        }

        direction = {}
        for feat in FEATURE_NAMES:
            val = feature_values.get(feat, 0)
            if feat == "glucose_avg":
                direction[feat] = "increases" if val > 130 else "decreases"
            elif feat == "glucose_std":
                direction[feat] = "increases" if val > 30 else "decreases"
            elif feat == "glucose_trend":
                direction[feat] = "increases" if val