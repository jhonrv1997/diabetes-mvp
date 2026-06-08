"""
SHAP-based Explainability Service for the Diabetes Risk Model.

Provides three levels of explanation:
  1. SHAP KernelExplainer (preferred) — model-agnostic, produces signed
     feature attributions for all 9 interpretable features.
  2. Integrated Gradients (secondary) — gradient-based, requires TensorFlow.
  3. Heuristic fallback — threshold-based scoring when neither SHAP nor TF
     is available.

Feature vector (9 features):
  [glucose_avg, glucose_std, glucose_trend, age, bmi,
   systolic_bp, diastolic_bp, family_diabetes, hypertension]
"""

import logging
from typing import Optional

import numpy as np

# ── Optional imports ──────────────────────────────────────────────────────
try:
    import shap as _shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    _shap = None

try:
    import tensorflow as tf
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    tf = None

from app.services.ml_model import DiabetesRiskModel

logger = logging.getLogger(__name__)


def _py(val):
    """Convert numpy scalars to native Python types for JSON serialization."""
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val

# ── Canonical feature metadata ────────────────────────────────────────────

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

# Ranges used to synthesise background data and for clinical interpretation
# (min, max, normal_low, normal_high, unit, spanish_label)
FEATURE_META = {
    "glucose_avg": {
        "min": 60, "max": 300,
        "normal_low": 70, "normal_high": 100,
        "unit": "mg/dL",
        "label": "Glucosa promedio",
    },
    "glucose_std": {
        "min": 5, "max": 80,
        "normal_low": 0, "normal_high": 30,
        "unit": "mg/dL",
        "label": "Variabilidad glucosa",
    },
    "glucose_trend": {
        "min": -3.0, "max": 3.0,
        "normal_low": -0.5, "normal_high": 0.5,
        "unit": "mg/dL/día",
        "label": "Tendencia glucosa",
    },
    "age": {
        "min": 18, "max": 100,
        "normal_low": 0, "normal_high": 45,
        "unit": "años",
        "label": "Edad",
    },
    "bmi": {
        "min": 15, "max": 50,
        "normal_low": 18.5, "normal_high": 24.9,
        "unit": "kg/m²",
        "label": "IMC",
    },
    "systolic_bp": {
        "min": 80, "max": 200,
        "normal_low": 0, "normal_high": 120,
        "unit": "mmHg",
        "label": "Presión sistólica",
    },
    "diastolic_bp": {
        "min": 50, "max": 130,
        "normal_low": 0, "normal_high": 80,
        "unit": "mmHg",
        "label": "Presión diastólica",
    },
    "family_diabetes": {
        "min": 0, "max": 1,
        "normal_low": 0, "normal_high": 0,
        "unit": "",
        "label": "Antecedentes familiares DM2",
    },
    "hypertension": {
        "min": 0, "max": 1,
        "normal_low": 0, "normal_high": 0,
        "unit": "",
        "label": "Hipertensión",
    },
}


class ShapExplainer:
    """SHAP-based explainability for DiabetesRiskModel predictions.

    Uses ``shap.KernelExplainer`` (model-agnostic) as the primary method,
    Integrated Gradients as a secondary method when TF is available but SHAP
    is not, and a heuristic fallback for environments without either.
    """

    # ── Construction ─────────────────────────────────────────────────────

    def __init__(self, model_service: Optional[DiabetesRiskModel] = None):
        self.model_service = model_service
        self._kernel_explainer = None
        self._background_data: Optional[np.ndarray] = None

    # ── Public API ───────────────────────────────────────────────────────

    def explain_prediction(
        self,
        glucose_readings: list[float],
        clinical_data: dict,
        n_samples: int = 100,
        method: str = "auto",
    ) -> dict:
        """Generate an explanation for a single prediction.

        Parameters
        ----------
        glucose_readings : list[float]
            Raw glucose measurements in mg/dL.
        clinical_data : dict
            Keys: age, bmi, systolic_bp, diastolic_bp, family_diabetes,
            hypertension.
        n_samples : int
            Number of samples for SHAP KernelExplainer (more = more accurate
            but slower).
        method : str
            ``"auto"`` | ``"shap"`` | ``"integrated_gradients"`` |
            ``"heuristic"``

        Returns
        -------
        dict
            Full explanation with shap_values, base_value, feature_values,
            direction, normalized_importance, clinical_interpretation, and
            method_used.
        """
        # Choose method
        if method == "auto":
            model_ready = (
                self.model_service is not None
                and self.model_service.model is not None
            )
            if SHAP_AVAILABLE and model_ready:
                method = "shap"
            elif TF_AVAILABLE and model_ready:
                method = "integrated_gradients"
            else:
                method = "heuristic"

        logger.info("Explanation method selected: %s", method)

        if method == "shap":
            try:
                return self._shap_explanation(
                    glucose_readings, clinical_data, n_samples
                )
            except Exception as exc:
                logger.warning(
                    "SHAP explanation failed (%s). Falling back to IG.", exc
                )
                if TF_AVAILABLE and self.model_service.model is not None:
                    return self._integrated_gradients_explanation(
                        glucose_readings, clinical_data
                    )
                return self._heuristic_explanation(
                    glucose_readings, clinical_data
                )

        if method == "integrated_gradients":
            if TF_AVAILABLE and self.model_service.model is not None:
                return self._integrated_gradients_explanation(
                    glucose_readings, clinical_data
                )
            return self._heuristic_explanation(glucose_readings, clinical_data)

        return self._heuristic_explanation(glucose_readings, clinical_data)

    # ── SHAP KernelExplainer ─────────────────────────────────────────────

    def _shap_explanation(
        self,
        glucose_readings: list[float],
        clinical_data: dict,
        n_samples: int,
    ) -> dict:
        """Explain using ``shap.KernelExplainer``."""
        feature_vector = self._compute_feature_vector(
            glucose_readings, clinical_data
        )

        # Lazy-init explainer
        self._ensure_explainer()

        # Compute SHAP values  (returns list for each output; we have 1)
        raw_shap = self._kernel_explainer.shap_values(
            feature_vector.reshape(1, -1), nsamples=n_samples
        )
        if isinstance(raw_shap, list):
            shap_arr = raw_shap[0].flatten()
        else:
            shap_arr = raw_shap.flatten()

        base_value = float(self._kernel_explainer.expected_value)
        if isinstance(base_value, (list, np.ndarray)):
            base_value = float(base_value[0])

        # Build signed SHAP dict
        shap_values = {
            name: round(float(shap_arr[i]), 6)
            for i, name in enumerate(FEATURE_NAMES)
        }

        # Feature values
        feature_values = self._build_feature_values_dict(
            glucose_readings, clinical_data
        )

        # Prediction from model
        pred_result = self.model_service.predict(glucose_readings, clinical_data)
        prediction = pred_result["risk_probability"]

        return self._assemble_explanation(
            shap_values=shap_values,
            base_value=base_value,
            prediction=prediction,
            feature_values=feature_values,
            method_used="shap_kernel",
        )

    def _ensure_explainer(self):
        """Lazily create and cache the SHAP KernelExplainer."""
        if self._kernel_explainer is not None:
            return

        if not SHAP_AVAILABLE:
            raise RuntimeError("shap library not installed")

        self._background_data = self._create_background_data(n_samples=50)
        self._kernel_explainer = _shap.KernelExplainer(
            self._predict_fn, self._background_data
        )
        logger.info("SHAP KernelExplainer initialised (50 background samples)")

    def _create_background_data(self, n_samples: int = 50) -> np.ndarray:
        """Synthesise background data for the KernelExplainer.

        Draws each feature uniformly within its clinically plausible range.
        """
        rng = np.random.RandomState(42)
        bg = np.zeros((n_samples, len(FEATURE_NAMES)))
        for i, name in enumerate(FEATURE_NAMES):
            meta = FEATURE_META[name]
            bg[:, i] = rng.uniform(meta["min"], meta["max"], n_samples)
        # Binary features
        bg[:, 7] = rng.randint(0, 2, n_samples).astype(float)
        bg[:, 8] = rng.randint(0, 2, n_samples).astype(float)
        return bg

    def _predict_fn(self, features_array: np.ndarray) -> np.ndarray:
        """Prediction wrapper for KernelExplainer.

        Maps a (batch, 9) feature array → (batch,) risk probabilities by
        reconstructing glucose sequences and calling the CNN-LSTM model.
        """
        batch_size = features_array.shape[0]
        seq_length = self.model_service.seq_length

        glucose_batch = np.zeros(
            (batch_size, seq_length, 1), dtype=np.float32
        )
        clinical_batch = np.zeros((batch_size, 6), dtype=np.float32)

        for i in range(batch_size):
            row = features_array[i]
            g_avg, g_std, g_trend = float(row[0]), float(row[1]), float(row[2])

            # Reconstruct deterministic glucose sequence
            glucose_seq = self._reconstruct_glucose(g_avg, g_std, g_trend, seq_length)
            g_arr = np.array(glucose_seq, dtype=np.float32).reshape(-1, 1)

            # Pad / truncate
            if len(g_arr) < seq_length:
                pad_len = seq_length - len(g_arr)
                g_arr = np.vstack(
                    [np.zeros((pad_len, 1), dtype=np.float32), g_arr]
                )
            else:
                g_arr = g_arr[-seq_length:]

            # Normalise glucose
            g_norm = self.model_service.scaler_glucose.transform(g_arr)
            glucose_batch[i] = g_norm.reshape(seq_length, 1)

            # Clinical vector
            clinical_batch[i] = [
                float(row[3]),   # age
                float(row[4]),   # bmi
                float(row[5]),   # systolic_bp
                float(row[6]),   # diastolic_bp
                float(row[7]),   # family_diabetes
                float(row[8]),   # hypertension
            ]

        # Normalise clinical
        clinical_norm = self.model_service.scaler_clinical.transform(
            clinical_batch
        )

        # Batch prediction
        raw = self.model_service.model.predict(
            [glucose_batch, clinical_norm], verbose=0
        )
        return raw.flatten()

    @staticmethod
    def _reconstruct_glucose(
        avg: float,
        std: float,
        trend: float,
        seq_length: int = 90,
    ) -> list[float]:
        """Deterministically reconstruct a glucose sequence from summary
        statistics.  Uses a combination of linear trend and sinusoidal
        components to simulate realistic diurnal patterns.
        """
        t = np.linspace(0, 1, seq_length)
        # Base trend line
        base = avg + trend * (t - 0.5) * seq_length * 0.5
        # Deterministic variability (sum of sinusoids at meal/circadian freqs)
        idx = np.arange(seq_length, dtype=np.float64)
        var_signal = (
            std * 0.35 * np.sin(2 * np.pi * idx / 7.0)
            + std * 0.25 * np.sin(2 * np.pi * idx / 3.5 + 1.0)
            + std * 0.20 * np.sin(2 * np.pi * idx / 14.0 + 2.0)
            + std * 0.10 * np.sin(2 * np.pi * idx / 2.0 + 0.5)
            + std * 0.10 * np.cos(2 * np.pi * idx / 5.0 + 1.5)
        )
        seq = base + var_signal
        seq = np.clip(seq, 40, 400)
        return seq.tolist()

    # ── Integrated Gradients (improved) ──────────────────────────────────

    def _integrated_gradients_explanation(
        self,
        glucose_readings: list[float],
        clinical_data: dict,
        n_steps: int = 50,
    ) -> dict:
        """Improved Integrated Gradients with proper sign attribution."""
        if not TF_AVAILABLE:
            raise RuntimeError("TensorFlow not available")
        if self.model_service.model is None:
            raise RuntimeError("Model not loaded")

        model = self.model_service.model
        scaler_g = self.model_service.scaler_glucose
        scaler_c = self.model_service.scaler_clinical
        seq_length = self.model_service.seq_length

        # ── Prepare actual inputs ─────────────────────────────────────
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

        # ── Baseline ──────────────────────────────────────────────────
        # Use the mean background as baseline instead of zero for better IG
        baseline_glucose = np.full(
            (1, seq_length, 1),
            float(scaler_g.transform(np.array([[100.0]]))[0, 0]),
            dtype=np.float32,
        )
        baseline_clinical = np.zeros((1, 6), dtype=np.float32)

        # ── Integrated gradients computation ──────────────────────────
        avg_grads_glucose = np.zeros((1, seq_length, 1), dtype=np.float64)
        avg_grads_clinical = np.zeros((1, 6), dtype=np.float64)

        actual_glucose_f = actual_glucose.astype(np.float64)
        actual_clinical_f = actual_clinical.astype(np.float64)
        baseline_glucose_f = baseline_glucose.astype(np.float64)
        baseline_clinical_f = baseline_clinical.astype(np.float64)

        for step in range(n_steps):
            alpha = (step + 1) / n_steps
            interp_glucose = baseline_glucose_f + alpha * (
                actual_glucose_f - baseline_glucose_f
            )
            interp_clinical = baseline_clinical_f + alpha * (
                actual_clinical_f - baseline_clinical_f
            )

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

        # IG = (actual - baseline) * avg_gradient  →  signed attributions
        ig_glucose = (actual_glucose_f - baseline_glucose_f) * avg_grads_glucose
        ig_clinical = (actual_clinical_f - baseline_clinical_f) * avg_grads_clinical

        # ── Decompose glucose attribution ─────────────────────────────
        # Use the gradient-weighted contributions instead of fixed ratios
        glucose_orig = glucose_arr.flatten()

        # Compute per-step contribution magnitudes
        ig_glucose_flat = ig_glucose.flatten()  # (seq_length,)
        total_glucose_ig = ig_glucose_flat  # signed per-step values

        # Split into avg / std / trend based on gradient-weighted analysis
        # avg: mean contribution (how far readings are from baseline)
        # std: variance of contributions across time steps
        # trend: correlation of contributions with time index
        mean_ig = float(np.mean(total_glucose_ig))
        std_ig = float(np.std(total_glucose_ig))
        if len(total_glucose_ig) > 1:
            t_idx = np.arange(len(total_glucose_ig), dtype=np.float64)
            t_mean = np.mean(t_idx)
            t_std = np.std(t_idx) + 1e-10
            trend_ig = float(
                np.sum(total_glucose_ig * (t_idx - t_mean)) / (len(t_idx) * t_std)
            )
        else:
            trend_ig = 0.0

        # Normalise to match total glucose attribution
        total_abs = abs(mean_ig) + abs(std_ig) + abs(trend_ig) + 1e-10
        glucose_total_ig = float(np.sum(ig_glucose))

        glucose_shap_avg = glucose_total_ig * (abs(mean_ig) / total_abs)
        glucose_shap_std = glucose_total_ig * (abs(std_ig) / total_abs)
        glucose_shap_trend = glucose_total_ig * (abs(trend_ig) / total_abs)

        # Clinical features: use signed IG values
        clinical_ig = ig_clinical.flatten()

        shap_values = {
            "glucose_avg": round(_py(glucose_shap_avg), 6),
            "glucose_std": round(_py(glucose_shap_std), 6),
            "glucose_trend": round(_py(glucose_shap_trend), 6),
            "age": round(_py(clinical_ig[0]), 6),
            "bmi": round(_py(clinical_ig[1]), 6),
            "systolic_bp": round(_py(clinical_ig[2]), 6),
            "diastolic_bp": round(_py(clinical_ig[3]), 6),
            "family_diabetes": round(_py(clinical_ig[4]), 6),
            "hypertension": round(_py(clinical_ig[5]), 6),
        }

        # Base value
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

        feature_values = self._build_feature_values_dict(
            glucose_readings, clinical_data
        )

        return self._assemble_explanation(
            shap_values=shap_values,
            base_value=base_value,
            prediction=prediction,
            feature_values=feature_values,
            method_used="integrated_gradients",
        )

    # ── Heuristic fallback ───────────────────────────────────────────────

    def _heuristic_explanation(
        self,
        glucose_readings: list[float],
        clinical_data: dict,
    ) -> dict:
        """Threshold-based heuristic explanation (no TF/SHAP required)."""
        glucose_arr = np.array(glucose_readings, dtype=np.float32)
        glucose_avg_val = (
            float(np.mean(glucose_arr)) if len(glucose_arr) > 0 else 0.0
        )
        glucose_std_val = (
            float(np.std(glucose_arr)) if len(glucose_arr) > 1 else 0.0
        )
        if len(glucose_arr) > 1:
            x_vals = np.arange(len(glucose_arr), dtype=np.float64)
            slope = float(
                np.polyfit(x_vals, glucose_arr.astype(np.float64), 1)[0]
            )
        else:
            slope = 0.0

        age = float(clinical_data.get("age", 50))
        bmi = float(clinical_data.get("bmi", 25))
        systolic = float(clinical_data.get("systolic_bp", 120))
        diastolic = float(clinical_data.get("diastolic_bp", 80))
        family = float(clinical_data.get("family_diabetes", 0))
        hypertension = float(clinical_data.get("hypertension", 0))

        # Signed heuristic: positive = increases risk, negative = decreases
        shap_values = {}

        # Glucose avg: baseline at 100 mg/dL
        if glucose_avg_val > 200:
            shap_values["glucose_avg"] = 0.30
        elif glucose_avg_val > 140:
            shap_values["glucose_avg"] = round(
                0.10 + 0.20 * (glucose_avg_val - 140) / 60, 4
            )
        elif glucose_avg_val > 100:
            shap_values["glucose_avg"] = round(
                0.02 + 0.08 * (glucose_avg_val - 100) / 40, 4
            )
        else:
            shap_values["glucose_avg"] = round(
                -0.05 + 0.07 * glucose_avg_val / 100, 4
            )

        # Glucose std: baseline at 15
        if glucose_std_val > 60:
            shap_values["glucose_std"] = 0.15
        elif glucose_std_val > 30:
            shap_values["glucose_std"] = round(
                0.03 + 0.12 * (glucose_std_val - 30) / 30, 4
            )
        elif glucose_std_val > 15:
            shap_values["glucose_std"] = round(
                0.01 + 0.02 * (glucose_std_val - 15) / 15, 4
            )
        else:
            shap_values["glucose_std"] = round(-0.01, 4)

        # Glucose trend: baseline at 0
        shap_values["glucose_trend"] = round(
            _py(np.clip(slope * 0.05, -0.10, 0.10)), 4
        )

        # Age: baseline at 40
        if age >= 65:
            shap_values["age"] = 0.12
        elif age >= 45:
            shap_values["age"] = round(0.04 + 0.08 * (age - 45) / 20, 4)
        else:
            shap_values["age"] = round(-0.02 + 0.06 * age / 45, 4)

        # BMI: baseline at 22
        if bmi >= 35:
            shap_values["bmi"] = 0.15
        elif bmi >= 30:
            shap_values["bmi"] = round(0.08 + 0.07 * (bmi - 30) / 5, 4)
        elif bmi >= 25:
            shap_values["bmi"] = round(0.03 + 0.05 * (bmi - 25) / 5, 4)
        else:
            shap_values["bmi"] = round(-0.02 + 0.05 * bmi / 25, 4)

        # Systolic BP: baseline at 120
        if systolic >= 140:
            shap_values["systolic_bp"] = 0.10
        elif systolic >= 130:
            shap_values["systolic_bp"] = round(
                0.03 + 0.07 * (systolic - 130) / 10, 4
            )
        else:
            shap_values["systolic_bp"] = round(
                -0.02 + 0.05 * systolic / 130, 4
            )

        # Diastolic BP: baseline at 80
        if diastolic >= 90:
            shap_values["diastolic_bp"] = 0.08
        elif diastolic >= 80:
            shap_values["diastolic_bp"] = round(
                0.01 + 0.07 * (diastolic - 80) / 10, 4
            )
        else:
            shap_values["diastolic_bp"] = round(
                -0.01 + 0.02 * diastolic / 80, 4
            )

        # Binary features
        shap_values["family_diabetes"] = 0.10 if family >= 1 else -0.02
        shap_values["hypertension"] = 0.08 if hypertension >= 1 else -0.01

        # Heuristic base value
        base_value = 0.12
        prediction = base_value + sum(shap_values.values())
        prediction = _py(np.clip(prediction, 0.0, 1.0))

        feature_values = {
            "glucose_avg": round(_py(glucose_avg_val), 2),
            "glucose_std": round(_py(glucose_std_val), 2),
            "glucose_trend": round(_py(slope), 4),
            "age": int(age),
            "bmi": round(_py(bmi), 1),
            "systolic_bp": int(systolic),
            "diastolic_bp": int(diastolic),
            "family_diabetes": int(family),
            "hypertension": int(hypertension),
        }

        return self._assemble_explanation(
            shap_values=shap_values,
            base_value=base_value,
            prediction=prediction,
            feature_values=feature_values,
            method_used="heuristic",
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _compute_feature_vector(
        glucose_readings: list[float],
        clinical_data: dict,
    ) -> np.ndarray:
        """Build the (9,) feature vector from raw inputs."""
        arr = np.array(glucose_readings, dtype=np.float32)
        g_avg = float(np.mean(arr)) if len(arr) > 0 else 100.0
        g_std = float(np.std(arr)) if len(arr) > 1 else 15.0
        if len(arr) > 1:
            x = np.arange(len(arr), dtype=np.float64)
            g_trend = float(np.polyfit(x, arr.astype(np.float64), 1)[0])
        else:
            g_trend = 0.0

        return np.array(
            [
                g_avg,
                g_std,
                g_trend,
                float(clinical_data.get("age", 50)),
                float(clinical_data.get("bmi", 25)),
                float(clinical_data.get("systolic_bp", 120)),
                float(clinical_data.get("diastolic_bp", 80)),
                float(clinical_data.get("family_diabetes", 0)),
                float(clinical_data.get("hypertension", 0)),
            ],
            dtype=np.float32,
        )

    @staticmethod
    def _build_feature_values_dict(
        glucose_readings: list[float],
        clinical_data: dict,
    ) -> dict:
        """Return a dict of actual feature values for display."""
        arr = np.array(glucose_readings, dtype=np.float32)
        g_avg = float(np.mean(arr)) if len(arr) > 0 else 0.0
        g_std = float(np.std(arr)) if len(arr) > 1 else 0.0
        if len(arr) > 1:
            x = np.arange(len(arr), dtype=np.float64)
            g_trend = float(np.polyfit(x, arr.astype(np.float64), 1)[0])
        else:
            g_trend = 0.0

        return {
            "glucose_avg": round(_py(g_avg), 2),
            "glucose_std": round(_py(g_std), 2),
            "glucose_trend": round(_py(g_trend), 4),
            "age": int(clinical_data.get("age", 50)),
            "bmi": round(float(clinical_data.get("bmi", 25)), 1),
            "systolic_bp": int(clinical_data.get("systolic_bp", 120)),
            "diastolic_bp": int(clinical_data.get("diastolic_bp", 80)),
            "family_diabetes": int(clinical_data.get("family_diabetes", 0)),
            "hypertension": int(clinical_data.get("hypertension", 0)),
        }

    def _assemble_explanation(
        self,
        shap_values: dict,
        base_value: float,
        prediction: float,
        feature_values: dict,
        method_used: str,
    ) -> dict:
        """Assemble the full explanation payload."""
        # Normalised importance (sum to 1)
        total_abs = sum(abs(v) for v in shap_values.values()) + 1e-10
        normalized = {
            k: round(abs(v) / total_abs, 4) for k, v in shap_values.items()
        }

        # Direction from signed SHAP values
        direction = {
            k: "increases" if v > 0 else "decreases" if v < 0 else "neutral"
            for k, v in shap_values.items()
        }

        # Clinical interpretation
        clinical_interpretation = self._generate_clinical_interpretation(
            shap_values, feature_values, base_value, prediction
        )

        # Risk contributors sorted by absolute SHAP value
        sorted_features = sorted(
            shap_values.items(), key=lambda x: abs(x[1]), reverse=True
        )
        top_risk_factors = [
            {
                "feature": feat,
                "shap_value": round(val, 6),
                "value": feature_values.get(feat),
                "direction": direction[feat],
                "importance_pct": round(normalized[feat] * 100, 1),
            }
            for feat, val in sorted_features
        ]

        return {
            "shap_values": shap_values,
            "base_value": round(base_value, 4),
            "prediction": round(prediction, 4),
            "normalized_importance": normalized,
            "feature_values": feature_values,
            "direction": direction,
            "clinical_interpretation": clinical_interpretation,
            "top_risk_factors": top_risk_factors,
            "method_used": method_used,
            "feature_names": FEATURE_NAMES,
            "feature_meta": {
                k: {
                    "label": v["label"],
                    "unit": v["unit"],
                    "normal_low": v["normal_low"],
                    "normal_high": v["normal_high"],
                }
                for k, v in FEATURE_META.items()
            },
        }

    # ── Clinical interpretation generator ────────────────────────────────

    def _generate_clinical_interpretation(
        self,
        shap_values: dict,
        feature_values: dict,
        base_value: float,
        prediction: float,
    ) -> dict:
        """Generate Spanish clinical interpretation narrative."""
        # Sort features by absolute contribution
        sorted_feats = sorted(
            shap_values.items(), key=lambda x: abs(x[1]), reverse=True
        )

        # Main risk narrative
        risk_pct = round(prediction * 100, 1)
        base_pct = round(base_value * 100, 1)
        delta_pct = round((prediction - base_value) * 100, 1)

        if prediction >= 0.7:
            risk_label = "ALTO"
        elif prediction >= 0.4:
            risk_label = "MODERADO"
        else:
            risk_label = "BAJO"

        summary = (
            f"El riesgo predicho de Diabetes Tipo 2 es {risk_pct}% "
            f"(riesgo {risk_label}), partiendo de un valor base poblacional "
            f"de {base_pct}%. Los factores del paciente {'aumentan' if delta_pct > 0 else 'reducen'} "
            f"el riesgo en {abs(delta_pct)} puntos porcentuales."
        )

        # Per-feature clinical notes
        feature_notes = []
        for feat, shap_val in sorted_feats[:5]:
            meta = FEATURE_META.get(feat, {})
            label = meta.get("label", feat)
            value = feature_values.get(feat)
            unit = meta.get("unit", "")
            normal_low = meta.get("normal_low", 0)
            normal_high = meta.get("normal_high", 100)

            direction = "aumenta" if shap_val > 0 else "reduce"
            magnitude = "significativamente" if abs(shap_val) > 0.05 else "moderadamente" if abs(shap_val) > 0.02 else "levemente"

            # Check if value is outside normal range
            is_abnormal = False
            if isinstance(value, (int, float)):
                is_abnormal = value < normal_low or value > normal_high

            if feat in ("family_diabetes", "hypertension"):
                if value and value >= 1:
                    note = (
                        f"{label}: Presente. {direction.capitalize()} {magnitude} "
                        f"el riesgo (contribución: {round(abs(shap_val)*100, 1)}%)."
                    )
                else:
                    note = (
                        f"{label}: Ausente. {direction.capitalize()} {magnitude} "
                        f"el riesgo (contribución: {round(abs(shap_val)*100, 1)}%)."
                    )
            elif feat == "glucose_trend":
                trend_dir = "ascendente" if value > 0.5 else "descendente" if value < -0.5 else "estable"
                note = (
                    f"{label}: {trend_dir.capitalize()} ({value:+.2f} {unit}). "
                    f"{direction.capitalize()} {magnitude} el riesgo "
                    f"(contribución: {round(abs(shap_val)*100, 1)}%)."
                )
            else:
                val_str = f"{value} {unit}".strip()
                abnormal_tag = " (fuera de rango normal)" if is_abnormal else ""
                note = (
                    f"{label}: {val_str}{abnormal_tag}. {direction.capitalize()} "
                    f"{magnitude} el riesgo (contribución: {round(abs(shap_val)*100, 1)}%)."
                )

            feature_notes.append(
                {
                    "feature": feat,
                    "note": note,
                    "is_abnormal": is_abnormal,
                    "contribution_pct": round(abs(shap_val) * 100, 1),
                    "direction": direction,
                }
            )

        # Clinical recommendation
        if prediction >= 0.7:
            recommendation = (
                "Se recomienda referencia inmediata a especialista en endocrinología. "
                "Iniciar protocolo de seguimiento intensivo con monitoreo continuo de "
                "glucosa y signos vitales. Evaluar intervención farmacológica."
            )
        elif prediction >= 0.4:
            recommendation = (
                "Programar consulta de seguimiento en 2-4 semanas. Reforzar medidas "
                "de estilo de vida (dieta, ejercicio). Monitoreo periódico de glucosa "
                "y factores de riesgo cardiovascular."
            )
        else:
            recommendation = (
                "Continuar con seguimiento rutinario. Promover hábitos saludables y "
                "actividad física regular. Próxima evaluación en 6 meses."
            )

        return {
            "summary": summary,
            "feature_notes": feature_notes,
            "recommendation": recommendation,
            "risk_label": risk_label,
            "base_risk_pct": base_pct,
            "predicted_risk_pct": risk_pct,
            "risk_delta_pct": delta_pct,
        }
