from pydantic import BaseModel, Field, model_validator, computed_field
from typing import Optional, Literal, Dict, Any
from datetime import datetime, date


# ── Auth schemas ──────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    full_name: str
    role: Literal["admin", "nurse", "nutritionist"]


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# ── Patient schemas ───────────────────────────────────────────────────────────

class PatientCreate(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    family_diabetes_history: bool = False
    hypertension_history: bool = False
    notes: Optional[str] = None


class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    family_diabetes_history: Optional[bool] = None
    hypertension_history: Optional[bool] = None
    notes: Optional[str] = None


class PatientResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[str] = None
    family_diabetes_history: bool
    hypertension_history: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# ── Clinical Data schemas ─────────────────────────────────────────────────────

class ClinicalDataCreate(BaseModel):
    patient_id: int
    systolic_bp: int = Field(..., ge=60, le=250)
    diastolic_bp: int = Field(..., ge=40, le=150)
    weight_kg: float = Field(..., ge=20, le=300)
    height_cm: Optional[float] = Field(None, ge=50, le=250)
    age: int = Field(..., ge=18, le=120)
    family_diabetes: bool
    hypertension_history: bool
    recorded_by: Optional[int] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_bp(self) -> "ClinicalDataCreate":
        if self.systolic_bp <= self.diastolic_bp:
            raise ValueError("systolic_bp must be greater than diastolic_bp")
        return self

    @computed_field
    @property
    def bmi(self) -> Optional[float]:
        if self.height_cm is not None and self.height_cm > 0:
            height_m = self.height_cm / 100
            return round(self.weight_kg / (height_m ** 2), 2)
        return None


class ClinicalDataResponse(BaseModel):
    id: int
    patient_id: int
    systolic_bp: int
    diastolic_bp: int
    weight_kg: float
    height_cm: Optional[float] = None
    bmi: Optional[float] = None
    age: int
    family_diabetes: bool
    hypertension_history: bool
    recorded_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# ── Glucose schemas ───────────────────────────────────────────────────────────

class GlucoseReadingCreate(BaseModel):
    patient_id: int
    glucose_mg_dl: float = Field(..., ge=20, le=600)
    measurement_timestamp: datetime
    sequence_number: Optional[int] = None
    source_device: str = "AccuChek Instant"
    context: Optional[str] = None


class GlucoseReadingResponse(BaseModel):
    id: int
    patient_id: int
    glucose_mg_dl: float
    measurement_timestamp: datetime
    sequence_number: Optional[int] = None
    source_device: str
    context: Optional[str] = None
    is_synced: bool
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class GlucoseReadingSync(BaseModel):
    glucose_mg_dl: float = Field(..., ge=20, le=600)
    measurement_timestamp: datetime
    sequence_number: Optional[int] = None
    context: Optional[str] = None


# ── Prediction schemas ────────────────────────────────────────────────────────

class PredictionRequest(BaseModel):
    patient_id: int


class SHAPFeatureNote(BaseModel):
    feature: str
    note: str
    is_abnormal: bool = False
    contribution_pct: float = 0.0
    direction: str = "neutral"


class SHAPClinicalInterpretation(BaseModel):
    summary: str = ""
    feature_notes: list[SHAPFeatureNote] = []
    recommendation: str = ""
    risk_label: str = ""
    base_risk_pct: float = 0.0
    predicted_risk_pct: float = 0.0
    risk_delta_pct: float = 0.0


class SHAPFeatureMeta(BaseModel):
    label: str = ""
    unit: str = ""
    normal_low: float = 0.0
    normal_high: float = 100.0


class SHAPTopRiskFactor(BaseModel):
    feature: str
    shap_value: float = 0.0
    value: Optional[Any] = None
    direction: str = "neutral"
    importance_pct: float = 0.0


class SHAPExplanation(BaseModel):
    """Structured SHAP explanation returned alongside predictions."""
    shap_values: Dict[str, float] = {}
    base_value: float = 0.0
    prediction: float = 0.0
    normalized_importance: Dict[str, float] = {}
    feature_values: Dict[str, Any] = {}
    direction: Dict[str, str] = {}
    clinical_interpretation: Optional[SHAPClinicalInterpretation] = None
    top_risk_factors: list[SHAPTopRiskFactor] = []
    method_used: str = "heuristic"
    feature_names: list[str] = []
    feature_meta: Dict[str, SHAPFeatureMeta] = {}


class PredictionResponse(BaseModel):
    id: int
    patient_id: int
    risk_probability: float
    risk_level: str
    confidence: Optional[float] = None
    glucose_readings_used: int
    model_version: str
    shap_values: Optional[Dict[str, Any]] = None
    shap_explanation: Optional[SHAPExplanation] = None
    predicted_by: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# ── Device schemas ────────────────────────────────────────────────────────────

class DevicePair(BaseModel):
    patient_id: int
    ble_address: str


class DeviceResponse(BaseModel):
    id: int
    patient_id: Optional[int] = None
    device_name: str
    ble_address: str
    is_paired: bool
    last_sync_at: Optional[datetime] = None
    status: str
    battery_level: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class DeviceSyncRequest(BaseModel):
    device_id: int


# ── Alert schemas ─────────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    prediction_id: Optional[int] = None
    patient_id: int
    alert_type: Literal["immediate", "monitoring", "info"]
    severity: Literal["high", "medium", "low"]
    risk_probability: float
    message: str


class AlertResponse(BaseModel):
    id: int
    prediction_id: Optional[int] = None
    patient_id: int
    patient_name: Optional[str] = None
    alert_type: str
    severity: str
    risk_probability: float
    message: str
    is_active: bool
    dismissed_by: Optional[int] = None
    dismissed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# ── Epic 04 — Sprint 03 schemas ─────────────────────────────────────────────
# HU06: Notificaciones push
# HU10: Plan nutricional + adherencia
# HU13: Citas de seguimiento


# ── HU06: Push notifications ─────────────────────────────────────────────────
class NotificationTokenRegister(BaseModel):
    patient_id: int
    token: str = Field(..., min_length=10, max_length=512)
    platform: Literal["android", "ios", "web"] = "android"


class NotificationTokenResponse(BaseModel):
    id: int
    patient_id: int
    token: str
    platform: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class PushNotificationResponse(BaseModel):
    id: int
    patient_id: int
    notification_type: str
    title: str
    body: str
    priority: str
    sound: str
    is_sent: bool
    sent_at: Optional[datetime] = None
    is_read: bool
    read_at: Optional[datetime] = None
    payload: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class EmergencyAlertRequest(BaseModel):
    """Endpoint para que el backend confirme una anomalía grave y dispare la
    notificación push prioritaria al paciente (HU06 Escenario 1)."""
    patient_id: int
    glucose_mg_dl: float = Field(..., ge=20, le=600)
    message: Optional[str] = None


# ── HU10: Nutritional plans ─────────────────────────────────────────────────
class NutritionPlanCreate(BaseModel):
    patient_id: int
    daily_calories: float = Field(..., gt=0, le=10000)
    protein_g: Optional[float] = Field(None, ge=0, le=500)
    carbs_g: Optional[float] = Field(None, ge=0, le=1000)
    fat_g: Optional[float] = Field(None, ge=0, le=500)
    restrictions: list[str] = []
    meal_schedule: Dict[str, str] = {}
    notes: Optional[str] = None


class NutritionPlanUpdate(BaseModel):
    daily_calories: Optional[float] = Field(None, gt=0, le=10000)
    protein_g: Optional[float] = Field(None, ge=0, le=500)
    carbs_g: Optional[float] = Field(None, ge=0, le=1000)
    fat_g: Optional[float] = Field(None, ge=0, le=500)
    restrictions: Optional[list[str]] = None
    meal_schedule: Optional[Dict[str, str]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class NutritionPlanResponse(BaseModel):
    id: int
    patient_id: int
    nutritionist_id: Optional[int] = None
    nutritionist_name: Optional[str] = None
    patient_name: Optional[str] = None
    daily_calories: float
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    restrictions: list[str] = []
    meal_schedule: Dict[str, str] = {}
    notes: Optional[str] = None
    is_active: bool
    start_date: datetime
    end_date: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class NutritionAdherenceResponse(BaseModel):
    """Resultado de la evaluación de adherencia a un plan nutricional (HU10 Escenario 2)."""
    plan_id: int
    patient_id: int
    patient_name: Optional[str] = None
    days_since_start: int
    eligible_for_evaluation: bool  # True si han pasado >= 14 días
    adherence_pct: float  # 0-100
    glucose_readings_count: int
    avg_glucose: Optional[float] = None
    glucose_in_target_pct: Optional[float] = None  # % de mediciones en rango objetivo
    recommendation: Optional[str] = None
    plan_active: bool


# ── HU13: Appointments ──────────────────────────────────────────────────────
class AppointmentCreate(BaseModel):
    patient_id: int
    scheduled_date: datetime
    reason: Optional[str] = "manual"
    notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    scheduled_date: Optional[datetime] = None
    status: Optional[Literal["scheduled", "completed", "no_show", "rescheduled", "cancelled"]] = None
    reason: Optional[str] = None
    notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: int
    patient_id: int
    patient_name: Optional[str] = None
    nurse_id: Optional[int] = None
    nurse_name: Optional[str] = None
    scheduled_date: datetime
    status: str
    reason: Optional[str] = None
    auto_generated: bool
    no_show_count: int
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class MarkNoShowResponse(BaseModel):
    """Resultado del proceso de no-asistencia (HU13 Escenario 2)."""
    original_appointment: AppointmentResponse
    rescheduled_appointment: Optional[AppointmentResponse] = None
    notifications_sent: int = 0
    message: str