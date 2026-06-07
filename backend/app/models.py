from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, Text, ForeignKey,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False, default="nurse")  # "admin" or "nurse"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    clinical_records = relationship("ClinicalData", back_populates="recorder", foreign_keys="ClinicalData.recorded_by")
    predictions = relationship("Prediction", back_populates="predictor", foreign_keys="Prediction.predicted_by")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    gender = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    emergency_contact = Column(String, nullable=True)
    family_diabetes_history = Column(Boolean, default=False)
    hypertension_history = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    glucose_readings = relationship("GlucoseReading", back_populates="patient", cascade="all, delete-orphan")
    clinical_data = relationship("ClinicalData", back_populates="patient", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="patient", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="patient", cascade="all, delete-orphan")


class GlucoseReading(Base):
    __tablename__ = "glucose_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    glucose_mg_dl = Column(Float, nullable=False)
    measurement_timestamp = Column(DateTime, nullable=False)
    sequence_number = Column(Integer, nullable=True)
    source_device = Column(String, default="AccuChek Instant")
    context = Column(String, nullable=True)  # "fasting"/"postprandial"/"bedtime"/"other"
    is_synced = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="glucose_readings")


class ClinicalData(Base):
    __tablename__ = "clinical_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    systolic_bp = Column(Integer, nullable=False)
    diastolic_bp = Column(Integer, nullable=False)
    weight_kg = Column(Float, nullable=False)
    height_cm = Column(Float, nullable=True)
    bmi = Column(Float, nullable=True)
    age = Column(Integer, nullable=False)
    family_diabetes = Column(Boolean, default=False)
    hypertension_history = Column(Boolean, default=False)
    recorded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="clinical_data")
    recorder = relationship("User", back_populates="clinical_records", foreign_keys=[recorded_by])


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_probability = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)  # "low"/"medium"/"high"
    confidence = Column(Float, nullable=True, default=0.0)
    glucose_readings_used = Column(Integer, nullable=False)
    model_version = Column(String, default="1.0")
    shap_values_json = Column(Text, nullable=True)
    predicted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="predictions")
    predictor = relationship("User", back_populates="predictions", foreign_keys=[predicted_by])


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="SET NULL"), nullable=True)
    device_name = Column(String, default="AccuChek Instant")
    ble_address = Column(String, unique=True, nullable=False)
    is_paired = Column(Boolean, default=False)
    last_sync_at = Column(DateTime, nullable=True)
    status = Column(String, default="disconnected")  # "disconnected"/"connected"/"syncing"/"error"
    battery_level = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="devices")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prediction_id = Column(Integer, ForeignKey("predictions.id", ondelete="CASCADE"), nullable=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type = Column(String, nullable=False)  # "immediate" / "monitoring" / "info"
    severity = Column(String, nullable=False)  # "high" / "medium" / "low"
    risk_probability = Column(Float, nullable=False)
    message = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    dismissed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    prediction = relationship("Prediction", foreign_keys=[prediction_id])
    patient = relationship("Patient", foreign_keys=[patient_id])
    dismisser = relationship("User", foreign_keys=[dismissed_by])