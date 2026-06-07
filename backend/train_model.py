#!/usr/bin/env python3
"""
Training script for the Diabetes Type 2 Early Detection CNN-LSTM model.

Steps:
  1. Generate ~1000 synthetic patient sequences with glucose readings
  2. Generate corresponding clinical data
  3. Assign labels based on clinical risk factors
  4. Build and train the CNN-LSTM model
  5. Save the model to ./model/cnn_lstm_diabetes/
  6. Print training metrics

Usage:
    cd backend/
    source venv/bin/activate
    python train_model.py
"""

import os
import sys
import json
import time
import logging

import numpy as np

# Ensure the backend directory is on the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.ml_model import DiabetesRiskModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────────

N_PATIENTS = 1000
SEQ_LENGTH = 90       # ~30 days × 3 readings/day
N_FEATURES = 6        # age, bmi, systolic_bp, diastolic_bp, family_diabetes, hypertension
MODEL_SAVE_PATH = os.path.join(os.path.dirname(__file__), "model", "cnn_lstm_diabetes")
RANDOM_SEED = 42


# ─── Synthetic Data Generation ──────────────────────────────────────────────

def generate_glucose_sequence(
    label: int,
    seq_length: int = 90,
) -> np.ndarray:
    """
    Generate a synthetic glucose reading sequence for a patient.

    Parameters
    ----------
    label : int
        0 = healthy, 1 = diabetic/pre-diabetic.
    seq_length : int
        Number of readings.

    Returns
    -------
    np.ndarray
        Shape (seq_length,) with glucose values in mg/dL.
    """
    if label == 0:
        # Healthy: glucose ~70-110, low variability
        baseline = np.random.uniform(75, 105)
        std = np.random.uniform(5, 15)
        trend = np.random.uniform(-0.1, 0.1)
    else:
        # At-risk/diabetic: glucose ~110-250, higher variability
        baseline = np.random.uniform(120, 200)
        std = np.random.uniform(15, 50)
        trend = np.random.uniform(0.05, 0.5)

    # Time index
    t = np.arange(seq_length, dtype=np.float64)

    # Base signal: baseline + trend + daily cyclic pattern + noise
    daily_cycle = np.random.uniform(5, 15) * np.sin(2 * np.pi * t / 3.0 + np.random.uniform(0, 2 * np.pi))
    noise = np.random.normal(0, std, seq_length)
    readings = baseline + trend * t * 0.01 + daily_cycle + noise

    # Occasional spikes for diabetic patients
    if label == 1:
        n_spikes = np.random.randint(2, 8)
        spike_indices = np.random.choice(seq_length, n_spikes, replace=False)
        for idx in spike_indices:
            readings[idx] += np.random.uniform(30, 80)

    # Clamp to realistic range
    readings = np.clip(readings, 40.0, 400.0)
    return readings.astype(np.float32)


def generate_clinical_data(
    label: int,
) -> dict:
    """
    Generate synthetic clinical variables for a patient.

    Returns
    -------
    dict
        Keys: age, bmi, systolic_bp, diastolic_bp, family_diabetes, hypertension.
    """
    if label == 0:
        # Healthy profile
        age = int(np.random.uniform(25, 55))
        bmi = round(np.random.uniform(20, 27), 1)
        systolic = int(np.random.uniform(100, 125))
        diastolic = int(np.random.uniform(60, 82))
        family_diabetes = float(np.random.choice([0, 0, 0, 0, 1]))  # 20%
        hypertension = float(np.random.choice([0, 0, 0, 0, 0, 1]))  # ~17%
    else:
        # At-risk profile
        age = int(np.random.uniform(40, 80))
        bmi = round(np.random.uniform(27, 42), 1)
        systolic = int(np.random.uniform(125, 180))
        diastolic = int(np.random.uniform(78, 110))
        family_diabetes = float(np.random.choice([0, 1, 1]))  # 67%
        hypertension = float(np.random.choice([0, 1, 1]))  # 67%

    return {
        "age": age,
        "bmi": bmi,
        "systolic_bp": systolic,
        "diastolic_bp": diastolic,
        "family_diabetes": family_diabetes,
        "hypertension": hypertension,
    }


def assign_label(clinical: dict, glucose_avg: float) -> int:
    """
    Assign a binary label (0/1) based on clinical risk factors and glucose.

    This uses a weighted scoring system — not a simple threshold — to create
    a realistic, non-linear decision boundary.
    """
    score = 0.0

    # Glucose average
    if glucose_avg >= 200:
        score += 0.30
    elif glucose_avg >= 140:
        score += 0.20
    elif glucose_avg >= 110:
        score += 0.10

    # BMI
    if clinical["bmi"] >= 35:
        score += 0.15
    elif clinical["bmi"] >= 30:
        score += 0.10
    elif clinical["bmi"] >= 25:
        score += 0.05

    # Age
    if clinical["age"] >= 65:
        score += 0.15
    elif clinical["age"] >= 45:
        score += 0.10
    elif clinical["age"] >= 35:
        score += 0.05

    # Blood pressure
    if clinical["systolic_bp"] >= 140 or clinical["diastolic_bp"] >= 90:
        score += 0.10
    elif clinical["systolic_bp"] >= 130 or clinical["diastolic_bp"] >= 80:
        score += 0.05

    # Family history
    if clinical["family_diabetes"]:
        score += 0.15

    # Hypertension
    if clinical["hypertension"]:
        score += 0.10

    # Add controlled noise to avoid perfect separation
    score += np.random.normal(0, 0.05)

    return 1 if score >= 0.5 else 0


def generate_synthetic_dataset(
    n_patients: int = 1000,
    seq_length: int = 90,
    seed: int = 42,
) -> tuple:
    """
    Generate a complete synthetic dataset for training.

    Returns
    -------
    tuple
        (X_glucose, X_clinical, y)
        X_glucose: shape (n_patients, seq_length, 1)
        X_clinical: shape (n_patients, 6)
        y: shape (n_patients,)
    """
    np.random.seed(seed)

    X_glucose = np.zeros((n_patients, seq_length, 1), dtype=np.float32)
    X_clinical = np.zeros((n_patients, 6), dtype=np.float32)
    y = np.zeros(n_patients, dtype=np.float32)

    for i in range(n_patients):
        # Pre-assign a rough label to generate correlated data
        pre_label = np.random.choice([0, 1], p=[0.55, 0.45])

        # Generate glucose and clinical data
        glucose = generate_glucose_sequence(pre_label, seq_length)
        clinical = generate_clinical_data(pre_label)

        # Compute a refined label based on actual data
        glucose_avg = float(np.mean(glucose))
        final_label = assign_label(clinical, glucose_avg)

        X_glucose[i, :, 0] = glucose
        X_clinical[i] = [
            clinical["age"],
            clinical["bmi"],
            clinical["systolic_bp"],
            clinical["diastolic_bp"],
            clinical["family_diabetes"],
            clinical["hypertension"],
        ]
        y[i] = float(final_label)

    # Print dataset statistics
    n_positive = int(np.sum(y))
    n_negative = n_patients - n_positive
    logger.info("Generated %d patients: %d positive, %d negative", n_patients, n_positive, n_negative)
    logger.info(
        "Glucose range: [%.1f, %.1f] mg/dL",
        float(X_glucose.min()),
        float(X_glucose.max()),
    )
    logger.info(
        "Age range: [%d, %d], BMI range: [%.1f, %.1f]",
        int(X_clinical[:, 0].min()),
        int(X_clinical[:, 0].max()),
        float(X_clinical[:, 1].min()),
        float(X_clinical[:, 1].max()),
    )

    return X_glucose, X_clinical, y


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    """Train the CNN-LSTM model on synthetic data and save it."""
    start_time = time.time()

    # ── 1. Generate synthetic data ──────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Step 1: Generating synthetic training data (%d patients)", N_PATIENTS)
    logger.info("=" * 60)

    X_glucose, X_clinical, y = generate_synthetic_dataset(
        n_patients=N_PATIENTS,
        seq_length=SEQ_LENGTH,
        seed=RANDOM_SEED,
    )

    # ── 2. Build the model ──────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 2: Building CNN-LSTM model")
    logger.info("=" * 60)

    model_service = DiabetesRiskModel()
    model_service.build_model(seq_length=SEQ_LENGTH, n_features=N_FEATURES)
    print(model_service.summary())

    # ── 3. Train ────────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 3: Training model")
    logger.info("=" * 60)

    history = model_service.train(
        X_glucose=X_glucose,
        X_clinical=X_clinical,
        y=y,
        epochs=50,
        batch_size=32,
        validation_split=0.2,
        n_augment=3,
        use_cross_validation=True,
        n_folds=3,
    )

    # ── 4. Print final metrics ──────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 4: Training complete — final metrics")
    logger.info("=" * 60)

    # If we have history from the aggregated CV, pick the last values
    if history:
        final_metrics = {}
        for key in ["loss", "accuracy", "auc", "val_loss", "val_accuracy", "val_auc"]:
            if key in history and history[key]:
                final_metrics[key] = history[key][-1]
        logger.info("Final training metrics:")
        for k, v in final_metrics.items():
            logger.info("  %s: %.4f", k, v)

    # ── 5. Save model ───────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 5: Saving model to %s", MODEL_SAVE_PATH)
    logger.info("=" * 60)

    model_service.save(MODEL_SAVE_PATH)

    # ── 6. Quick sanity check — predict on a sample ─────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 6: Sanity-check prediction")
    logger.info("=" * 60)

    # High-risk patient
    high_risk_glucose = generate_glucose_sequence(1, SEQ_LENGTH)
    high_risk_clinical = generate_clinical_data(1)
    result_high = model_service.predict(high_risk_glucose.tolist(), high_risk_clinical)
    logger.info("High-risk sample: %s", result_high)

    # Low-risk patient
    low_risk_glucose = generate_glucose_sequence(0, SEQ_LENGTH)
    low_risk_clinical = generate_clinical_data(0)
    result_low = model_service.predict(low_risk_glucose.tolist(), low_risk_clinical)
    logger.info("Low-risk sample: %s", result_low)

    # ── 7. Test model reload ────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("Step 7: Testing model reload from disk")
    logger.info("=" * 60)

    model_service2 = DiabetesRiskModel(model_path=MODEL_SAVE_PATH)
    result_reloaded = model_service2.predict(high_risk_glucose.tolist(), high_risk_clinical)
    logger.info("Reloaded model prediction: %s", result_reloaded)

    # Verify predictions match
    prob_diff = abs(result_high["risk_probability"] - result_reloaded["risk_probability"])
    if prob_diff < 1e-4:
        logger.info("✅ Reloaded model predictions match! (Δ=%.6f)", prob_diff)
    else:
        logger.warning("⚠️  Predictions differ: Δ=%.6f", prob_diff)

    elapsed = time.time() - start_time
    logger.info("")
    logger.info("=" * 60)
    logger.info("Done! Total time: %.1f seconds", elapsed)
    logger.info("Model saved to: %s", MODEL_SAVE_PATH)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()