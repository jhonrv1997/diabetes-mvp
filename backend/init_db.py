#!/usr/bin/env python3
"""
Database Initialization Script for the Diabetes Detection MVP.

Steps:
  1. Create all tables
  2. Insert default admin user (username: admin, password: admin123)
  3. Insert a default nurse user (username: enfermera, password: enfermera123)
  4. Insert sample patients (5 patients with varying risk profiles)
  5. Insert sample clinical data for each patient
  6. Insert sample glucose readings (30 days × 2-4 readings/day for each patient)
  7. Print summary of created records

Usage:
    cd backend/
    source venv/bin/activate
    python init_db.py
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta, date
from random import Random

# Ensure the backend directory is on the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select, delete

from app.database import engine, Base, AsyncSessionLocal
from app.models import User, Patient, ClinicalData, GlucoseReading, Prediction, Alert
from app.auth import get_password_hash

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

RANDOM_SEED = 42
rng = Random(RANDOM_SEED)


# ─── Sample Data Definitions ────────────────────────────────────────────────

SAMPLE_PATIENTS = [
    {
        "first_name": "María",
        "last_name": "García López",
        "date_of_birth": date(1958, 5, 12),
        "gender": "F",
        "phone": "+52 555 100 2000",
        "address": "Av. Reforma 123, Col. Centro, CDMX",
        "emergency_contact": "Juan García +52 555 100 2001",
        "family_diabetes_history": True,
        "hypertension_history": True,
        "notes": "Patient with family history of diabetes and hypertension.",
        # Clinical data — HIGH risk profile
        "clinical": {
            "systolic_bp": 155,
            "diastolic_bp": 95,
            "weight_kg": 82.0,
            "height_cm": 158.0,
            "age": 67,
            "family_diabetes": True,
            "hypertension_history": True,
        },
        # Glucose profile — HIGH risk (elevated, variable)
        "glucose_baseline": 165,
        "glucose_std": 40,
        "glucose_trend": 0.5,
    },
    {
        "first_name": "Carlos",
        "last_name": "Hernández Ruiz",
        "date_of_birth": date(1972, 8, 23),
        "gender": "M",
        "phone": "+52 555 200 3000",
        "address": "Calle Hidalgo 456, Guadalajara, Jalisco",
        "emergency_contact": "Ana Hernández +52 555 200 3001",
        "family_diabetes_history": True,
        "hypertension_history": False,
        "notes": "Overweight, family history of diabetes.",
        # Clinical data — MEDIUM risk profile
        "clinical": {
            "systolic_bp": 132,
            "diastolic_bp": 85,
            "weight_kg": 92.0,
            "height_cm": 172.0,
            "age": 52,
            "family_diabetes": True,
            "hypertension_history": False,
        },
        # Glucose profile — MEDIUM risk (slightly elevated)
        "glucose_baseline": 125,
        "glucose_std": 25,
        "glucose_trend": 0.2,
    },
    {
        "first_name": "Rosa",
        "last_name": "Martínez Flores",
        "date_of_birth": date(1985, 2, 14),
        "gender": "F",
        "phone": "+52 555 300 4000",
        "address": "Paseo de la Reforma 789, Monterrey, NL",
        "emergency_contact": "Pedro Martínez +52 555 300 4001",
        "family_diabetes_history": False,
        "hypertension_history": False,
        "notes": "Healthy young woman, no significant risk factors.",
        # Clinical data — LOW risk profile
        "clinical": {
            "systolic_bp": 110,
            "diastolic_bp": 72,
            "weight_kg": 58.0,
            "height_cm": 162.0,
            "age": 39,
            "family_diabetes": False,
            "hypertension_history": False,
        },
        # Glucose profile — LOW risk (normal range)
        "glucose_baseline": 88,
        "glucose_std": 8,
        "glucose_trend": -0.02,
    },
    {
        "first_name": "Roberto",
        "last_name": "Sánchez Díaz",
        "date_of_birth": date(1963, 11, 5),
        "gender": "M",
        "phone": "+52 555 400 5000",
        "address": "Blvd. Campestre 321, León, Guanajuato",
        "emergency_contact": "Laura Sánchez +52 555 400 5001",
        "family_diabetes_history": True,
        "hypertension_history": True,
        "notes": "Patient with multiple risk factors. Hypertension under treatment.",
        # Clinical data — HIGH risk profile
        "clinical": {
            "systolic_bp": 148,
            "diastolic_bp": 92,
            "weight_kg": 95.0,
            "height_cm": 170.0,
            "age": 62,
            "family_diabetes": True,
            "hypertension_history": True,
        },
        # Glucose profile — HIGH risk (very elevated)
        "glucose_baseline": 185,
        "glucose_std": 45,
        "glucose_trend": 0.6,
    },
    {
        "first_name": "Lucía",
        "last_name": "Torres Vega",
        "date_of_birth": date(1990, 6, 30),
        "gender": "F",
        "phone": "+52 555 500 6000",
        "address": "Calle Morelos 567, Puebla, Puebla",
        "emergency_contact": "Miguel Torres +52 555 500 6001",
        "family_diabetes_history": False,
        "hypertension_history": False,
        "notes": "Active lifestyle, normal BMI. Occasional stress-related glucose spikes.",
        # Clinical data — LOW risk profile (borderline)
        "clinical": {
            "systolic_bp": 118,
            "diastolic_bp": 76,
            "weight_kg": 63.0,
            "height_cm": 165.0,
            "age": 34,
            "family_diabetes": False,
            "hypertension_history": False,
        },
        # Glucose profile — LOW risk (occasional spikes)
        "glucose_baseline": 92,
        "glucose_std": 12,
        "glucose_trend": 0.03,
    },
]


# ─── Helper Functions ────────────────────────────────────────────────────────

def generate_glucose_readings(
    baseline: float,
    std: float,
    trend: float,
    days: int = 30,
) -> list[dict]:
    """
    Generate realistic glucose readings for a patient over a given number of days.

    Simulates 2-4 readings per day (fasting, postprandial, bedtime) from an
    AccuChek Instant glucometer.

    Returns
    -------
    list[dict]
        Each dict has keys: glucose_mg_dl, measurement_timestamp, context
    """
    readings = []
    now = datetime.utcnow()
    day_start = now - timedelta(days=days)

    for day_offset in range(days):
        current_date = day_start + timedelta(days=day_offset)
        n_readings = rng.choice([2, 3, 3, 4])  # Weighted: mostly 3

        # Reading times (hours)
        if n_readings == 2:
            hours = sorted([rng.uniform(7, 8.5), rng.uniform(20, 22)])
            contexts = ["fasting", "bedtime"]
        elif n_readings == 3:
            hours = sorted([rng.uniform(7, 8.5), rng.uniform(12.5, 14), rng.uniform(20, 22)])
            contexts = ["fasting", "postprandial", "bedtime"]
        else:
            hours = sorted([
                rng.uniform(6.5, 8),
                rng.uniform(10, 11.5),
                rng.uniform(12.5, 14),
                rng.uniform(20, 22),
            ])
            contexts = ["fasting", "other", "postprandial", "bedtime"]

        for i, (hour, context) in enumerate(zip(hours, contexts)):
            # Time trend: slight increase over the observation window
            time_trend = trend * (day_offset / days) * 20

            # Context-specific adjustments
            if context == "fasting":
                context_adj = rng.uniform(-10, 5)
            elif context == "postprandial":
                context_adj = rng.uniform(15, 45)
            elif context == "bedtime":
                context_adj = rng.uniform(-5, 15)
            else:
                context_adj = rng.uniform(-5, 20)

            # Daily variation
            daily_noise = rng.gauss(0, std)

            # Compute reading
            reading_value = baseline + time_trend + context_adj + daily_noise
            reading_value = max(40.0, min(400.0, reading_value))

            # Build timestamp
            minute = int((hour % 1) * 60)
            timestamp = current_date.replace(
                hour=int(hour), minute=minute, second=0, microsecond=0
            )

            readings.append({
                "glucose_mg_dl": round(reading_value, 1),
                "measurement_timestamp": timestamp,
                "context": context,
            })

    # Sort by timestamp
    readings.sort(key=lambda r: r["measurement_timestamp"])
    return readings


# ─── Main Initialization Logic ──────────────────────────────────────────────

async def init_database():
    """Create tables and populate with sample data."""
    logger.info("=" * 60)
    logger.info("Step 1: Creating database tables")
    logger.info("=" * 60)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ All tables created successfully.")

    async with AsyncSessionLocal() as session:
        # ── 2. Insert default users ─────────────────────────────────────
        logger.info("")
        logger.info("=" * 60)
        logger.info("Step 2: Creating default users")
        logger.info("=" * 60)

        admin_user = User(
            username="admin",
            hashed_password=get_password_hash("admin123"),
            full_name="System Administrator",
            role="admin",
            is_active=True,
        )
        session.add(admin_user)

        nurse_user = User(
            username="enfermera",
            hashed_password=get_password_hash("enfermera123"),
            full_name="Enfermera María Elena",
            role="nurse",
            is_active=True,
        )
        session.add(nurse_user)

        await session.flush()
        admin_id = admin_user.id
        nurse_id = nurse_user.id
        logger.info("✅ Admin user created (id=%d, username=admin)", admin_id)
        logger.info("✅ Nurse user created (id=%d, username=enfermera)", nurse_id)

        # ── 3-5. Insert patients, clinical data, glucose readings ───────
        logger.info("")
        logger.info("=" * 60)
        logger.info("Step 3-5: Creating sample patients with clinical data and glucose readings")
        logger.info("=" * 60)

        total_readings = 0

        for idx, patient_data in enumerate(SAMPLE_PATIENTS):
            # Create patient
            patient = Patient(
                first_name=patient_data["first_name"],
                last_name=patient_data["last_name"],
                date_of_birth=patient_data["date_of_birth"],
                gender=patient_data["gender"],
                phone=patient_data["phone"],
                address=patient_data["address"],
                emergency_contact=patient_data["emergency_contact"],
                family_diabetes_history=patient_data["family_diabetes_history"],
                hypertension_history=patient_data["hypertension_history"],
                notes=patient_data["notes"],
            )
            session.add(patient)
            await session.flush()
            patient_id = patient.id

            # Create clinical data
            clinical = patient_data["clinical"]
            bmi = round(clinical["weight_kg"] / (clinical["height_cm"] / 100) ** 2, 2)
            clinical_record = ClinicalData(
                patient_id=patient_id,
                systolic_bp=clinical["systolic_bp"],
                diastolic_bp=clinical["diastolic_bp"],
                weight_kg=clinical["weight_kg"],
                height_cm=clinical["height_cm"],
                bmi=bmi,
                age=clinical["age"],
                family_diabetes=clinical["family_diabetes"],
                hypertension_history=clinical["hypertension_history"],
                recorded_by=nurse_id,
                notes=f"Initial assessment for {patient_data['first_name']} {patient_data['last_name']}",
            )
            session.add(clinical_record)

            # Create glucose readings
            glucose_readings = generate_glucose_readings(
                baseline=patient_data["glucose_baseline"],
                std=patient_data["glucose_std"],
                trend=patient_data["glucose_trend"],
                days=30,
            )

            for seq_num, reading in enumerate(glucose_readings):
                glucose_record = GlucoseReading(
                    patient_id=patient_id,
                    glucose_mg_dl=reading["glucose_mg_dl"],
                    measurement_timestamp=reading["measurement_timestamp"],
                    sequence_number=seq_num + 1,
                    source_device="AccuChek Instant",
                    context=reading["context"],
                    is_synced=True,
                )
                session.add(glucose_record)

            total_readings += len(glucose_readings)
            avg_glucose = sum(r["glucose_mg_dl"] for r in glucose_readings) / len(glucose_readings)
            logger.info(
                "  ✅ Patient %d: %s %s (id=%d) — %d readings, avg glucose=%.1f mg/dL",
                idx + 1,
                patient_data["first_name"],
                patient_data["last_name"],
                patient_id,
                len(glucose_readings),
                avg_glucose,
            )

        await session.flush()

        # ── Summary ─────────────────────────────────────────────────────
        logger.info("")
        logger.info("=" * 60)
        logger.info("Database Initialization Summary")
        logger.info("=" * 60)

        # Count records
        users_count = (await session.execute(select(User))).scalars().all()
        patients_count = (await session.execute(select(Patient))).scalars().all()
        clinical_count = (await session.execute(select(ClinicalData))).scalars().all()
        glucose_count = (await session.execute(select(GlucoseReading))).scalars().all()

        logger.info("  Users:           %d", len(users_count))
        logger.info("  Patients:        %d", len(patients_count))
        logger.info("  Clinical data:   %d", len(clinical_count))
        logger.info("  Glucose readings: %d", len(glucose_count))
        logger.info("")
        logger.info("  Default admin:   username=admin,       password=admin123")
        logger.info("  Default nurse:   username=enfermera,   password=enfermera123")
        logger.info("")

        # Print patient risk profiles
        logger.info("  Patient Risk Profiles:")
        for patient in patients_count:
            clinical_result = await session.execute(
                select(ClinicalData)
                .where(ClinicalData.patient_id == patient.id)
                .order_by(ClinicalData.created_at.desc())
                .limit(1)
            )
            cd = clinical_result.scalar_one_or_none()
            glucose_result = await session.execute(
                select(GlucoseReading)
                .where(GlucoseReading.patient_id == patient.id)
            )
            readings = glucose_result.scalars().all()
            if readings:
                avg_g = sum(r.glucose_mg_dl for r in readings) / len(readings)
            else:
                avg_g = 0

            logger.info(
                "    %s %s: age=%s, bmi=%s, avg_glucose=%.1f, family_hx=%s, htn=%s",
                patient.first_name,
                patient.last_name,
                cd.age if cd else "?",
                cd.bmi if cd else "?",
                avg_g,
                cd.family_diabetes if cd else "?",
                cd.hypertension_history if cd else "?",
            )

        await session.commit()

    logger.info("")
    logger.info("✅ Database initialization complete!")


async def main():
    await init_database()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())