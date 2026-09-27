import json as _json

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
    role = Column(String, nullable=False, default="nurse")  # "admin" / "nurse" / "nutritionist"
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
    shap_explanation_json = Column(Text, nullable=True)  # Full SHAP explanation
    shap_base_value = Column(Float, nullable=True)  # SHAP base value (E[f(x)])
    shap_method = Column(String, nullable=True)  # "shap_kernel" / "integrated_gradients" / "heuristic"
    predicted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="predictions")
    predictor = relationship("User", back_populates="predictions", foreign_keys=[predicted_by])

    @property
    def shap_values(self):
        """Parse shap_values_json into a dict for API responses."""
        if self.shap_values_json:
            try:
                return _json.loads(self.shap_values_json)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def shap_explanation(self):
        """Parse shap_explanation_json into a dict for API responses."""
        if self.shap_explanation_json:
            try:
                return _json.loads(self.shap_explanation_json)
            except (ValueError, TypeError):
                return None
        return None


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


# ── Epic 04 — Monitoreo y seguimiento (Sprint 03) ────────────────────────────
# HU06: Recepción de alertas tempranas (notificaciones push)
# HU10: Seguimiento nutricional personalizado
# HU13: Programación de citas de seguimiento


class NotificationToken(Base):
    """Token de dispositivo móvil del paciente para enviar notificaciones push."""
    __tablename__ = "notification_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, nullable=False, index=True)  # FCM / APNs token
    platform = Column(String, default="android")  # "android" / "ios" / "web"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", foreign_keys=[patient_id])


class PushNotification(Base):
    """Registro de notificaciones push enviadas al paciente."""
    __tablename__ = "push_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    notification_type = Column(String, nullable=False)
    # "emergency_alert" / "meal_reminder" / "appointment_reminder" / "appointment_reschedule"
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    priority = Column(String, default="normal")  # "normal" / "high"
    sound = Column(String, default="default")  # "default" / "critical" / "silent"
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime, nullable=True)
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    payload_json = Column(Text, nullable=True)  # extra data
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", foreign_keys=[patient_id])

    @property
    def payload(self):
        if self.payload_json:
            try:
                return _json.loads(self.payload_json)
            except (ValueError, TypeError):
                return None
        return None


class NutritionPlan(Base):
    """Plan nutricional personalizado asignado a un paciente en riesgo."""
    __tablename__ = "nutrition_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    nutritionist_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    daily_calories = Column(Float, nullable=False)
    protein_g = Column(Float, nullable=True)        # gramos de proteína / día
    carbs_g = Column(Float, nullable=True)          # gramos de carbohidratos / día
    fat_g = Column(Float, nullable=True)             # gramos de grasa / día
    restrictions_json = Column(Text, nullable=True)  # JSON array: ["diabetes","hipertension","vegetariana", ...]
    meal_schedule_json = Column(Text, nullable=True) # JSON: { "desayuno":"08:00", "almuerzo":"13:00", ... }
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", foreign_keys=[patient_id])
    nutritionist = relationship("User", foreign_keys=[nutritionist_id])

    @property
    def restrictions(self):
        if self.restrictions_json:
            try:
                return _json.loads(self.restrictions_json)
            except (ValueError, TypeError):
                return []
        return []

    @property
    def meal_schedule(self):
        if self.meal_schedule_json:
            try:
                return _json.loads(self.meal_schedule_json)
            except (ValueError, TypeError):
                return {}
        return {}


class Appointment(Base):
    """Cita de seguimiento programada para un paciente en riesgo."""
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    nurse_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scheduled_date = Column(DateTime, nullable=False, index=True)
    status = Column(String, default="scheduled")
    # "scheduled" / "completed" / "no_show" / "rescheduled" / "cancelled"
    reason = Column(String, nullable=True)  # "risk_high_auto" / "risk_medium_auto" / "manual" / "rescheduled_no_show"
    auto_generated = Column(Boolean, default=False)
    no_show_count = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", foreign_keys=[patient_id])
    nurse = relationship("User", foreign_keys=[nurse_id])