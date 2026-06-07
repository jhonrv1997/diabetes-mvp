"""
Diabetes Type 2 Early Detection — CNN-LSTM Model Service

Hybrid architecture:
  • Temporal branch (CNN-1D)  – processes glucose reading sequences
  • Static branch  (Dense)    – processes 6 clinical variables
  • Concatenation → Bidirectional LSTM → sigmoid output

Risk levels:
  Low    : 0.0  – 0.4   → #47805a (green)
  Medium : 0.4  – 0.7   → #9b8048 (yellow)
  High   : >= 0.7       → #8e4f49 (red)
"""

import os
import json
import logging
from typing import Optional

import numpy as np
from sklearn.preprocessing import MinMaxScaler
import joblib

# TensorFlow is optional — the server can run with heuristic scoring
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers  # type: ignore
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    tf = None
    keras = None
    layers = None

logger = logging.getLogger(__name__)


class DiabetesRiskModel:
    """Complete CNN-LSTM model service for Type-2 Diabetes risk prediction."""

    # Risk thresholds
    RISK_LOW_THRESHOLD: float = 0.4
    RISK_HIGH_THRESHOLD: float = 0.7

    # Risk colors
    RISK_COLORS = {
        "low": "#47805a",
        "medium": "#9b8048",
        "high": "#8e4f49",
    }

    def __init__(self, model_path: Optional[str] = None):
        self.model: Optional[object] = None
        self.scaler_glucose: Optional[MinMaxScaler] = None
        self.scaler_clinical: Optional[MinMaxScaler] = None
        self.is_loaded: bool = False
        self.model_version: str = "1.0"
        self.seq_length: int = 90
        self.n_features: int = 6

        # Default ranges for initializing scalers (will be overwritten on train/load)
        self._glucose_range = np.array([[40.0, 400.0]])   # min, max
        self._clinical_ranges = np.array([
            [18.0, 100.0],    # age
            [15.0, 50.0],     # bmi
            [80.0, 200.0],    # systolic_bp
            [50.0, 130.0],    # diastolic_bp
            [0.0, 1.0],       # family_diabetes
            [0.0, 1.0],       # hypertension_history
        ])

        self._init_scalers()

        if model_path and os.path.exists(model_path):
            self.load(model_path)

    # ── Scaler helpers ─────────────────────────────────────────────────────

    def _init_scalers(self) -> None:
        """Initialize MinMaxScaler instances with known data ranges."""
        # Glucose scaler
        self.scaler_glucose = MinMaxScaler(feature_range=(0, 1))
        self.scaler_glucose.fit(self._glucose_range)

        # Clinical scaler
        self.scaler_clinical = MinMaxScaler(feature_range=(0, 1))
        self.scaler_clinical.fit(self._clinical_ranges)

    # ── Model architecture ─────────────────────────────────────────────────

    def build_model(self, seq_length: int = 90, n_features: int = 6):
        """
        Build the CNN-LSTM architecture using the Keras Functional API.

        Parameters
        ----------
        seq_length : int
            Number of time-steps in the glucose input (default 90).
        n_features : int
            Number of static clinical features (default 6).

        Returns
        -------
        keras.Model
            Compiled model ready for training.
        """
        if not TF_AVAILABLE:
            raise RuntimeError(
                "TensorFlow no esta instalado. "
                "Instalalo con: pip install tensorflow==2.15.0"
            )

        self.seq_length = seq_length
        self.n_features = n_features

        # ── Temporal branch (CNN-1D) ────────────────────────────────────
        glucose_input = keras.Input(
            shape=(seq_length, 1), name="glucose_input"
        )

        x1 = layers.Conv1D(
            64, kernel_size=3, activation="relu", padding="same"
        )(glucose_input)
        x1 = layers.BatchNormalization()(x1)

        x1 = layers.Conv1D(
            32, kernel_size=5, activation="relu", padding="same"
        )(x1)
        x1 = layers.BatchNormalization()(x1)

        x1 = layers.Conv1D(
            16, kernel_size=7, activation="relu", padding="same"
        )(x1)
        x1 = layers.BatchNormalization()(x1)
        # x1 shape: (batch, seq_length, 16)

        # ── Static branch (Dense) ───────────────────────────────────────
        clinical_input = keras.Input(
            shape=(n_features,), name="clinical_input"
        )

        x2 = layers.Dense(32, activation="relu")(clinical_input)
        x2 = layers.Dropout(0.3)(x2)
        x2 = layers.Dense(16, activation="relu")(x2)
        # x2 shape: (batch, 16)
        # Broadcast along temporal dimension
        x2 = layers.RepeatVector(seq_length)(x2)
        # x2 shape: (batch, seq_length, 16)

        # ── Concatenation ───────────────────────────────────────────────
        concat = layers.Concatenate(axis=-1)([x1, x2])
        # concat shape: (batch, seq_length, 32)

        # ── LSTM ────────────────────────────────────────────────────────
        lstm1 = layers.Bidirectional(
            layers.LSTM(64, dropout=0.3, return_sequences=True)
        )(concat)
        # lstm1 shape: (batch, seq_length, 128)

        lstm2 = layers.Bidirectional(
            layers.LSTM(32, dropout=0.2, return_sequences=False)
        )(lstm1)
        # lstm2 shape: (batch, 64)

        # ── Output ──────────────────────────────────────────────────────
        output = layers.Dense(1, activation="sigmoid")(lstm2)
        # output shape: (batch, 1)

        model = keras.Model(
            inputs=[glucose_input, clinical_input],
            outputs=output,
            name="cnn_lstm_diabetes_risk",
        )

        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=1e-3),
            loss="binary_crossentropy",
            metrics=[
                "accuracy",
                keras.metrics.AUC(name="auc"),
                keras.metrics.Precision(name="precision"),
                keras.metrics.Recall(name="recall"),
            ],
        )

        self.model = model
        logger.info(
            "Model built — total params: %d, trainable: %d",
            model.count_params(),
            sum(tf.size(w).numpy() for w in model.trainable_weights),
        )
        return model

    # ── Training ────────────────────────────────────────────────────────────

    def train(
        self,
        X_glucose: np.ndarray,
        X_clinical: np.ndarray,
        y: np.ndarray,
        epochs: int = 100,
        batch_size: int = 32,
        validation_split: float = 0.2,
        n_augment: int = 5,
        use_cross_validation: bool = True,
        n_folds: int = 5,
    ) -> dict:
        """
        Train the model with data augmentation and optional cross-validation.

        Parameters
        ----------
        X_glucose : np.ndarray
            Glucose sequences of shape (n_samples, seq_length, 1).
        X_clinical : np.ndarray
            Clinical data of shape (n_samples, n_features).
        y : np.ndarray
            Binary labels of shape (n_samples,).
        epochs : int
            Maximum number of training epochs.
        batch_size : int
            Mini-batch size.
        validation_split : float
            Fraction of training data used for validation.
        n_augment : int
            Number of augmented variants per original sample.
        use_cross_validation : bool
            Whether to perform stratified k-fold cross-validation.
        n_folds : int
            Number of CV folds.

        Returns
        -------
        dict
            Training history with keys: loss, accuracy, auc, val_loss, etc.
        """
        if not TF_AVAILABLE:
            raise RuntimeError(
                "TensorFlow no esta instalado. No se puede entrenar el modelo."
            )

        if self.model is None:
            self.build_model(
                seq_length=X_glucose.shape[1],
                n_features=X_clinical.shape[1],
            )

        # Fit scalers on training data
        self._fit_scalers(X_glucose, X_clinical)

        # Normalize inputs
        X_glucose_norm = self._normalize_glucose(X_glucose)
        X_clinical_norm = self._normalize_clinical(X_clinical)

        # Data augmentation
        X_glucose_aug, X_clinical_aug, y_aug = self._augment_dataset(
            X_glucose_norm, X_clinical_norm, y, n_variants=n_augment
        )

        # Cosine-decay learning-rate schedule
        total_steps = (len(y_aug) // batch_size) * epochs
        lr_schedule = keras.optimizers.schedules.CosineDecay(
            initial_learning_rate=1e-3,
            decay_steps=total_steps,
            alpha=1e-5,
        )
        self.model.optimizer = keras.optimizers.Adam(learning_rate=lr_schedule)

        # Callbacks
        callbacks = [
            keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=15,
                restore_best_weights=True,
                verbose=1,
            ),
        ]

        if use_cross_validation:
            history = self._cross_validate(
                X_glucose_aug, X_clinical_aug, y_aug,
                epochs=epochs, batch_size=batch_size,
                n_folds=n_folds, callbacks=callbacks,
            )
        else:
            hist = self.model.fit(
                [X_glucose_aug, X_clinical_aug],
                y_aug,
                epochs=epochs,
                batch_size=batch_size,
                validation_split=validation_split,
                callbacks=callbacks,
                verbose=1,
            )
            history = {k: [float(v) for v in vs] for k, vs in hist.history.items()}

        self.is_loaded = True
        logger.info("Training completed — model is loaded.")
        return history

    def _cross_validate(
        self,
        X_glucose: np.ndarray,
        X_clinical: np.ndarray,
        y: np.ndarray,
        epochs: int,
        batch_size: int,
        n_folds: int,
        callbacks: list,
    ) -> dict:
        """Perform stratified k-fold cross-validation, keeping the best fold model."""
        from sklearn.model_selection import StratifiedKFold

        skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
        fold_metrics: list[dict] = []
        best_val_auc = -1.0
        best_weights = None
        aggregated_history: dict[str, list[float]] = {}

        for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X_glucose, y)):
            logger.info("-- Fold %d/%d --", fold_idx + 1, n_folds)

            # Re-build model for each fold to reset weights
            self.build_model(
                seq_length=X_glucose.shape[1],
                n_features=X_clinical.shape[1],
            )

            X_g_train, X_g_val = X_glucose[train_idx], X_glucose[val_idx]
            X_c_train, X_c_val = X_clinical[train_idx], X_clinical[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            # Recompute LR schedule per fold
            total_steps = (len(y_train) // batch_size) * epochs
            lr_schedule = keras.optimizers.schedules.CosineDecay(
                initial_learning_rate=1e-3,
                decay_steps=max(total_steps, 1),
                alpha=1e-5,
            )
            self.model.optimizer = keras.optimizers.Adam(learning_rate=lr_schedule)

            hist = self.model.fit(
                [X_g_train, X_c_train], y_train,
                epochs=epochs,
                batch_size=batch_size,
                validation_data=([X_g_val, X_c_val], y_val),
                callbacks=callbacks,
                verbose=1,
            )

            # Record fold metrics
            final_metrics = {k: vs[-1] for k, vs in hist.history.items()}
            fold_metrics.append(final_metrics)
            logger.info("Fold %d metrics: %s", fold_idx + 1, final_metrics)

            # Track best fold by validation AUC
            val_auc = final_metrics.get("val_auc", 0.0)
            if val_auc > best_val_auc:
                best_val_auc = val_auc
                best_weights = self.model.get_weights()

            # Aggregate history (average across folds)
            for key, values in hist.history.items():
                if key not in aggregated_history:
                    aggregated_history[key] = []
                aggregated_history[key].extend([float(v) for v in values])

        # Restore best-fold weights
        if best_weights is not None:
            self.build_model(
                seq_length=X_glucose.shape[1],
                n_features=X_clinical.shape[1],
            )
            self.model.set_weights(best_weights)

        # Print summary
        for metric_name in fold_metrics[0]:
            vals = [fm[metric_name] for fm in fold_metrics]
            logger.info(
                "CV %s: %.4f +/- %.4f", metric_name, np.mean(vals), np.std(vals)
            )

        return aggregated_history

    # ── Inference ────────────────────────────────────────────────────────────

    def predict(
        self,
        glucose_readings: list[float],
        clinical_data: dict,
    ) -> dict:
        """
        Generate a risk prediction for a single patient.

        Parameters
        ----------
        glucose_readings : list[float]
            Glucose measurements in mg/dL (up to seq_length values).
        clinical_data : dict
            Keys: age, bmi, systolic_bp, diastolic_bp, family_diabetes, hypertension.

        Returns
        -------
        dict
            {risk_probability, risk_level, risk_color, confidence}
        """
        if self.model is None:
            raise RuntimeError("Model is not loaded. Call load() or train() first.")

        # ── Prepare glucose input ────────────────────────────────────────
        glucose_arr = np.array(glucose_readings, dtype=np.float32).reshape(-1, 1)

        # Pad or truncate to seq_length
        if len(glucose_arr) < self.seq_length:
            pad_len = self.seq_length - len(glucose_arr)
            glucose_arr = np.vstack(
                [np.zeros((pad_len, 1), dtype=np.float32), glucose_arr]
            )
        else:
            glucose_arr = glucose_arr[-self.seq_length:]

        # Normalize
        glucose_norm = self.scaler_glucose.transform(glucose_arr)
        glucose_input = glucose_norm.reshape(1, self.seq_length, 1)

        # ── Prepare clinical input ───────────────────────────────────────
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

        clinical_norm = self.scaler_clinical.transform(clinical_vector)

        # ── Run inference ────────────────────────────────────────────────
        raw_pred = self.model.predict(
            [glucose_input, clinical_norm], verbose=0
        )
        probability = float(np.clip(raw_pred[0, 0], 0.0, 1.0))

        # ── Classify risk ────────────────────────────────────────────────
        risk_level = self._classify_risk(probability)
        risk_color = self.RISK_COLORS[risk_level]

        # ── Confidence estimate ──────────────────────────────────────────
        confidence = round(abs(probability - 0.5) * 2.0, 4)

        result = {
            "risk_probability": round(probability, 4),
            "risk_level": risk_level,
            "risk_color": risk_color,
            "confidence": confidence,
        }
        return result

    # ── Feature importance (gradient-based) ─────────────────────────────────

    def get_feature_importance(
        self,
        glucose_readings: list[float],
        clinical_data: dict,
    ) -> dict:
        """
        Compute gradient-based feature importance for a single prediction.
        Requires TensorFlow.
        """
        if not TF_AVAILABLE:
            raise RuntimeError("TensorFlow is required for feature importance.")

        if self.model is None:
            raise RuntimeError("Model is not loaded.")

        # Prepare inputs (same as predict)
        glucose_arr = np.array(glucose_readings, dtype=np.float32).reshape(-1, 1)
        if len(glucose_arr) < self.seq_length:
            pad_len = self.seq_length - len(glucose_arr)
            glucose_arr = np.vstack(
                [np.zeros((pad_len, 1), dtype=np.float32), glucose_arr]
            )
        else:
            glucose_arr = glucose_arr[-self.seq_length:]

        glucose_norm = self.scaler_glucose.transform(glucose_arr)
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
        clinical_norm = self.scaler_clinical.transform(clinical_vector)

        # Convert to tensors
        glucose_tensor = tf.constant(glucose_norm.reshape(1, self.seq_length, 1))
        clinical_tensor = tf.constant(clinical_norm.reshape(1, -1))

        # Compute gradients
        with tf.GradientTape() as tape:
            tape.watch(glucose_tensor)
            tape.watch(clinical_tensor)
            output = self.model(
                [glucose_tensor, clinical_tensor], training=False
            )

        grads_glucose, grads_clinical = tape.gradient(
            output, [glucose_tensor, clinical_tensor]
        )

        # Glucose importance: aggregate over time dimension
        glucose_grads = np.abs(grads_glucose.numpy()).flatten()
        glucose_mean_importance = float(np.mean(glucose_grads))
        glucose_std_importance = float(np.std(glucose_grads))

        # Compute trend from glucose readings
        if len(glucose_readings) > 1:
            x_vals = np.arange(len(glucose_readings), dtype=np.float64)
            y_vals = np.array(glucose_readings, dtype=np.float64)
            slope = float(np.polyfit(x_vals, y_vals, 1)[0])
        else:
            slope = 0.0

        # Clinical feature importances
        clinical_grads = np.abs(grads_clinical.numpy()).flatten()

        feature_importance = {
            "glucose_avg": round(float(np.mean(glucose_arr)), 2),
            "glucose_std": round(float(np.std(glucose_arr)), 2),
            "glucose_trend": round(slope, 4),
            "glucose_importance": round(glucose_mean_importance, 6),
            "glucose_variability_importance": round(glucose_std_importance, 6),
            "age": round(float(clinical_data.get("age", 50)), 1),
            "age_importance": round(float(clinical_grads[0]), 6),
            "bmi": round(float(clinical_data.get("bmi", 25)), 1),
            "bmi_importance": round(float(clinical_grads[1]), 6),
            "systolic_bp": round(float(clinical_data.get("systolic_bp", 120)), 1),
            "systolic_bp_importance": round(float(clinical_grads[2]), 6),
            "diastolic_bp": round(float(clinical_data.get("diastolic_bp", 80)), 1),
            "diastolic_bp_importance": round(float(clinical_grads[3]), 6),
            "family_diabetes": float(clinical_data.get("family_diabetes", 0)),
            "family_diabetes_importance": round(float(clinical_grads[4]), 6),
            "hypertension": float(clinical_data.get("hypertension", 0)),
            "hypertension_importance": round(float(clinical_grads[5]), 6),
        }

        # Normalized importance (sum to 1)
        importance_keys = [
            "glucose_importance",
            "glucose_variability_importance",
            "age_importance",
            "bmi_importance",
            "systolic_bp_importance",
            "diastolic_bp_importance",
            "family_diabetes_importance",
            "hypertension_importance",
        ]
        total = sum(feature_importance[k] for k in importance_keys) + 1e-10
        normalized = {
            k.replace("_importance", "_norm"): round(feature_importance[k] / total, 4)
            for k in importance_keys
        }
        feature_importance.update(normalized)

        return feature_importance

    # ── Save / Load ─────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """
        Save model, scalers, and metadata to disk.
        Requires TensorFlow.
        """
        if not TF_AVAILABLE:
            raise RuntimeError("TensorFlow is required to save the model.")

        if self.model is None:
            raise RuntimeError("No model to save.")

        os.makedirs(path, exist_ok=True)

        # Save Keras model
        model_path = os.path.join(path, "model.keras")
        self.model.save(model_path)

        # Save scalers
        joblib.dump(self.scaler_glucose, os.path.join(path, "scaler_glucose.joblib"))
        joblib.dump(self.scaler_clinical, os.path.join(path, "scaler_clinical.joblib"))

        # Save metadata
        metadata = {
            "model_version": self.model_version,
            "seq_length": self.seq_length,
            "n_features": self.n_features,
            "risk_thresholds": {
                "low": self.RISK_LOW_THRESHOLD,
                "high": self.RISK_HIGH_THRESHOLD,
            },
        }
        with open(os.path.join(path, "metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info("Model saved to %s", path)

    def load(self, path: str) -> None:
        """
        Load model, scalers, and metadata from disk.
        Requires TensorFlow.
        """
        if not TF_AVAILABLE:
            logger.warning(
                "TensorFlow no esta instalado. No se puede cargar el modelo. "
                "El servidor usara scoring heuristico."
            )
            return

        model_path = os.path.join(path, "model.keras")
        scaler_g_path = os.path.join(path, "scaler_glucose.joblib")
        scaler_c_path = os.path.join(path, "scaler_clinical.joblib")
        meta_path = os.path.join(path, "metadata.json")

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")

        # Load model
        self.model = keras.models.load_model(model_path)

        # Load scalers
        if os.path.exists(scaler_g_path):
            self.scaler_glucose = joblib.load(scaler_g_path)
        else:
            logger.warning("Glucose scaler not found; using default.")

        if os.path.exists(scaler_c_path):
            self.scaler_clinical = joblib.load(scaler_c_path)
        else:
            logger.warning("Clinical scaler not found; using default.")

        # Load metadata
        if os.path.exists(meta_path):
            with open(meta_path, "r") as f:
                metadata = json.load(f)
            self.model_version = metadata.get("model_version", "1.0")
            self.seq_length = metadata.get("seq_length", 90)
            self.n_features = metadata.get("n_features", 6)
        else:
            # Infer from model
            input_shapes = [inp.shape for inp in self.model.inputs]
            for shape in input_shapes:
                if len(shape) == 3:
                    self.seq_length = int(shape[1])
                elif len(shape) == 2:
                    self.n_features = int(shape[1])

        self.is_loaded = True
        logger.info(
            "Model loaded from %s (version=%s, seq_length=%d, n_features=%d)",
            path, self.model_version, self.seq_length, self.n_features,
        )

    # ── Data augmentation ───────────────────────────────────────────────────

    def _data_augment(
        self,
        X: np.ndarray,
        n_variants: int = 5,
    ) -> np.ndarray:
        """Generate augmented data variants for a single glucose sequence."""
        seq = X.flatten()
        augmented = []

        for i in range(n_variants):
            strategy = i % 5

            if strategy == 0:
                # Jitter
                noise = np.random.normal(loc=0.0, scale=0.02, size=seq.shape)
                aug = seq + noise

            elif strategy == 1:
                # Scaling
                scale_factor = np.random.uniform(0.9, 1.1)
                aug = seq * scale_factor

            elif strategy == 2:
                # Window slicing
                window_ratio = np.random.uniform(0.8, 1.0)
                window_len = max(int(len(seq) * window_ratio), 1)
                start = np.random.randint(0, len(seq) - window_len + 1)
                window = seq[start: start + window_len]
                pad_before = start
                pad_after = len(seq) - start - window_len
                aug = np.concatenate(
                    [np.zeros(pad_before), window, np.zeros(pad_after)]
                )

            elif strategy == 3:
                # Permutation
                n_segments = np.random.randint(3, 7)
                seg_len = max(len(seq) // n_segments, 1)
                segments = []
                for s in range(n_segments):
                    start = s * seg_len
                    end = min(start + seg_len, len(seq))
                    segments.append(seq[start:end])
                np.random.shuffle(segments)
                aug = np.concatenate(segments)[: len(seq)]
                if len(aug) < len(seq):
                    aug = np.concatenate(
                        [aug, np.zeros(len(seq) - len(aug))]
                    )

            else:
                # Interpolation
                from scipy.interpolate import interp1d

                orig_len = len(seq)
                indices = np.arange(orig_len)
                n_keep = max(int(orig_len * np.random.uniform(0.6, 0.95)), 4)
                keep_idx = np.sort(np.random.choice(orig_len, n_keep, replace=False))
                if len(keep_idx) < 2:
                    aug = seq.copy()
                else:
                    f_interp = interp1d(
                        keep_idx, seq[keep_idx], kind="linear", fill_value="extrapolate"
                    )
                    aug = f_interp(indices)

            # Clip to valid range and reshape
            aug = np.clip(aug, 0.0, 1.0)  # Already normalized
            augmented.append(aug.reshape(-1, 1))

        return np.array(augmented, dtype=np.float32)

    def _augment_dataset(
        self,
        X_glucose: np.ndarray,
        X_clinical: np.ndarray,
        y: np.ndarray,
        n_variants: int = 5,
    ) -> tuple:
        """Apply data augmentation to the entire dataset."""
        n_samples = X_glucose.shape[0]
        aug_glucose_list = [X_glucose]
        aug_clinical_list = [X_clinical]
        aug_y_list = [y]

        for i in range(n_samples):
            aug_seqs = self._data_augment(X_glucose[i], n_variants=n_variants)
            for aug_seq in aug_seqs:
                aug_glucose_list.append(aug_seq.reshape(1, self.seq_length, 1))
                aug_clinical_list.append(X_clinical[i].reshape(1, -1))
                aug_y_list.append(np.array([y[i]]))

        X_glucose_aug = np.vstack(aug_glucose_list)
        X_clinical_aug = np.vstack(aug_clinical_list)
        y_aug = np.concatenate(aug_y_list)

        # Shuffle
        idx = np.random.permutation(len(y_aug))
        return X_glucose_aug[idx], X_clinical_aug[idx], y_aug[idx]

    # ── Normalization helpers ───────────────────────────────────────────────

    def _fit_scalers(
        self,
        X_glucose: np.ndarray,
        X_clinical: np.ndarray,
    ) -> None:
        """Fit scalers on training data."""
        all_glucose = X_glucose.reshape(-1, 1)
        self.scaler_glucose = MinMaxScaler(feature_range=(0, 1))
        self.scaler_glucose.fit(all_glucose)

        self.scaler_clinical = MinMaxScaler(feature_range=(0, 1))
        self.scaler_clinical.fit(X_clinical)

    def _normalize_glucose(self, X_glucose: np.ndarray) -> np.ndarray:
        """Normalize glucose data using the fitted scaler."""
        shape = X_glucose.shape
        flat = X_glucose.reshape(-1, 1)
        norm = self.scaler_glucose.transform(flat)
        return norm.reshape(shape)

    def _normalize_clinical(self, X_clinical: np.ndarray) -> np.ndarray:
        """Normalize clinical data using the fitted scaler."""
        return self.scaler_clinical.transform(X_clinical)

    # ── Risk classification ─────────────────────────────────────────────────

    def _classify_risk(self, probability: float) -> str:
        """Classify risk level from probability."""
        if probability >= self.RISK_HIGH_THRESHOLD:
            return "high"
        elif probability >= self.RISK_LOW_THRESHOLD:
            return "medium"
        else:
            return "low"

    # ── Model summary ───────────────────────────────────────────────────────

    def summary(self) -> str:
        """Return a string summary of the model architecture."""
        if self.model is None:
            return "Model not built yet. TensorFlow may not be installed."
        summary_parts = []
        self.model.summary(print_fn=lambda line: summary_parts.append(line))
        return "\n".join(summary_parts)