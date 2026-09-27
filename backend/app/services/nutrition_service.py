"""
Nutrition Service — Epic 04, HU10.

Implementa los dos escenarios del Seguimiento Nutricional Personalizado:

    Escenario 1 — Creación de plan nutricional
      • Verifica que el paciente tenga riesgo Medio o Alto.
      • Persiste el plan (calorías, macros, restricciones, horario de comidas).
      • Programa notificaciones push de recordatorio de comidas (HU06/HU10).

    Escenario 2 — Evaluación de adherencia (>= 14 días)
      • Cruza los datos de glucosa del sensor IoT con el plan asignado.
      • Calcula el porcentaje de adherencia (% de mediciones en rango objetivo).
      • Genera recomendación de ajuste si el % es < 60%.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    NutritionPlan,
    Patient,
    Prediction,
    GlucoseReading,
    User,
)
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class NutritionService:
    """Gestión de planes nutricionales y adherencia."""

    # Rango objetivo de glucosa post-prandial considerado "adherente".
    # Definido por criterios clínicos estándar (ADA). Si la mayoría de las
    # mediciones caen en este rango, consideramos que el plan está cumplido.
    GLUCOSE_TARGET_LOW = 70   # mg/dL
    GLUCOSE_TARGET_HIGH = 180  # mg/dL
    ADHERENCE_THRESHOLD_PCT = 60.0  # por debajo → recomendación de ajuste
    EVALUATION_MIN_DAYS = 14

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notifications = NotificationService(db)

    # ── Creación de plan (Escenario 1) ─────────────────────────────────────

    async def create_plan(
        self,
        patient_id: int,
        daily_calories: float,
        protein_g: Optional[float] = None,
        carbs_g: Optional[float] = None,
        fat_g: Optional[float] = None,
        restrictions: Optional[list[str]] = None,
        meal_schedule: Optional[dict] = None,
        notes: Optional[str] = None,
        nutritionist_id: Optional[int] = None,
    ) -> NutritionPlan:
        """
        Crea un plan nutricional para un paciente con riesgo Medio o Alto.

        Lanza ValueError si el paciente no existe o no está clasificado
        con riesgo Medio/Alto según la última predicción.
        """
        # Verificar paciente
        patient = await self._get_patient(patient_id)
        if patient is None:
            raise ValueError(f"Paciente #{patient_id} no encontrado")

        # Verificar que el paciente tenga riesgo Medio o Alto
        risk_level = await self._get_latest_risk_level(patient_id)
        if risk_level is None:
            raise ValueError(
                f"El paciente #{patient_id} no tiene una predicción de riesgo registrada. "
                f"No se puede asignar un plan nutricional sin clasificación de riesgo."
            )
        if risk_level not in ("medium", "high"):
            raise ValueError(
                f"El paciente #{patient_id} tiene riesgo '{risk_level}'. "
                f"Solo se asignan planes a pacientes con riesgo Medio o Alto."
            )

        # Desactivar planes anteriores del paciente (solo un plan activo)
        await self._deactivate_previous_plans(patient_id)

        plan = NutritionPlan(
            patient_id=patient_id,
            nutritionist_id=nutritionist_id,
            daily_calories=daily_calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
            restrictions_json=json.dumps(restrictions or []),
            meal_schedule_json=json.dumps(meal_schedule or {}),
            notes=notes,
            is_active=True,
            start_date=datetime.utcnow(),
        )
        self.db.add(plan)
        await self.db.flush()
        await self.db.refresh(plan)

        # Programa notificaciones de recordatorio de comidas
        await self._schedule_meal_reminders(plan)

        logger.info(
            "Plan nutricional #%d creado para paciente #%d (riesgo=%s, kcal=%.0f)",
            plan.id, patient_id, risk_level, daily_calories,
        )
        return plan

    async def update_plan(
        self,
        plan_id: int,
        **kwargs,
    ) -> Optional[NutritionPlan]:
        result = await self.db.execute(
            select(NutritionPlan).where(NutritionPlan.id == plan_id)
        )
        plan = result.scalar_one_or_none()
        if plan is None:
            return None

        for key in ("daily_calories", "protein_g", "carbs_g", "fat_g", "notes", "is_active"):
            if key in kwargs and kwargs[key] is not None:
                setattr(plan, key, kwargs[key])
        if "restrictions" in kwargs and kwargs["restrictions"] is not None:
            plan.restrictions_json = json.dumps(kwargs["restrictions"])
        if "meal_schedule" in kwargs and kwargs["meal_schedule"] is not None:
            plan.meal_schedule_json = json.dumps(kwargs["meal_schedule"])

        await self.db.flush()
        await self.db.refresh(plan)
        return plan

    async def get_plan(self, plan_id: int) -> Optional[NutritionPlan]:
        result = await self.db.execute(
            select(NutritionPlan).where(NutritionPlan.id == plan_id)
        )
        return result.scalar_one_or_none()

    async def get_patient_active_plan(self, patient_id: int) -> Optional[NutritionPlan]:
        result = await self.db.execute(
            select(NutritionPlan)
            .where(
                and_(
                    NutritionPlan.patient_id == patient_id,
                    NutritionPlan.is_active == True,  # noqa: E712
                )
            )
            .order_by(desc(NutritionPlan.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_plans(
        self,
        patient_id: Optional[int] = None,
        active_only: bool = False,
    ) -> list[NutritionPlan]:
        stmt = select(NutritionPlan).order_by(desc(NutritionPlan.created_at))
        filters = []
        if patient_id is not None:
            filters.append(NutritionPlan.patient_id == patient_id)
        if active_only:
            filters.append(NutritionPlan.is_active == True)  # noqa: E712
        if filters:
            stmt = stmt.where(and_(*filters))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ── Evaluación de adherencia (Escenario 2) ──────────────────────────────

    async def evaluate_adherence(self, plan_id: int) -> dict:
        """
        Cruza los datos de glucosa del paciente con el plan asignado y
        devuelve el porcentaje de adherencia junto con recomendaciones.

        Solo se considera válida si han pasado >= 14 días desde `start_date`.
        """
        plan = await self.get_plan(plan_id)
        if plan is None:
            raise ValueError(f"Plan #{plan_id} no encontrado")

        days_since_start = (datetime.utcnow() - plan.start_date).days
        eligible = days_since_start >= self.EVALUATION_MIN_DAYS

        # Recoger lecturas de glucosa desde el inicio del plan
        result = await self.db.execute(
            select(GlucoseReading)
            .where(
                and_(
                    GlucoseReading.patient_id == plan.patient_id,
                    GlucoseReading.measurement_timestamp >= plan.start_date,
                )
            )
            .order_by(desc(GlucoseReading.measurement_timestamp))
        )
        readings = list(result.scalars().all())
        readings_count = len(readings)

        adherence_pct = 0.0
        avg_glucose = None
        in_target_pct = None
        recommendation = None

        if readings_count > 0:
            in_target = sum(
                1 for r in readings
                if self.GLUCOSE_TARGET_LOW <= r.glucose_mg_dl <= self.GLUCOSE_TARGET_HIGH
            )
            in_target_pct = round(100.0 * in_target / readings_count, 1)
            avg_glucose = round(sum(r.glucose_mg_dl for r in readings) / readings_count, 1)
            # Adherencia = % de lecturas en rango objetivo
            adherence_pct = in_target_pct

        # Generar recomendación si ha pasado suficiente tiempo
        if eligible and readings_count > 0:
            if adherence_pct < self.ADHERENCE_THRESHOLD_PCT:
                recommendation = self._build_adjustment_recommendation(
                    plan=plan,
                    adherence_pct=adherence_pct,
                    avg_glucose=avg_glucose,
                    readings_count=readings_count,
                )
            else:
                recommendation = (
                    f"El plan está funcionando adecuadamente. Adherencia {adherence_pct:.1f}% "
                    f"(≥ {self.ADHERENCE_THRESHOLD_PCT:.0f}%). Continúe con el plan actual "
                    f"y mantenga el monitoreo regular."
                )
        elif not eligible:
            recommendation = (
                f"Aún no se puede evaluar la adherencia: han pasado {days_since_start} días "
                f"de {self.EVALUATION_MIN_DAYS} requeridos. La evaluación estará disponible "
                f"tras {self.EVALUATION_MIN_DAYS} días de uso del plan."
            )

        patient = await self._get_patient(plan.patient_id)
        patient_name = (
            f"{patient.first_name} {patient.last_name}" if patient else None
        )

        return {
            "plan_id": plan.id,
            "patient_id": plan.patient_id,
            "patient_name": patient_name,
            "days_since_start": days_since_start,
            "eligible_for_evaluation": eligible,
            "adherence_pct": round(adherence_pct, 1),
            "glucose_readings_count": readings_count,
            "avg_glucose": avg_glucose,
            "glucose_in_target_pct": in_target_pct,
            "recommendation": recommendation,
            "plan_active": plan.is_active,
        }

    # ── Helpers ────────────────────────────────────────────────────────────

    def _build_adjustment_recommendation(
        self,
        plan: NutritionPlan,
        adherence_pct: float,
        avg_glucose: Optional[float],
        readings_count: int,
    ) -> str:
        msg = (
            f"Adherencia insuficiente ({adherence_pct:.1f}% < {self.ADHERENCE_THRESHOLD_PCT:.0f}%). "
            f"Se recomienda ajustar el plan nutricional del paciente."
        )
        if avg_glucose is not None:
            if avg_glucose > 180:
                msg += (
                    f" Glucosa promedio elevada ({avg_glucose} mg/dL): considere "
                    f"reducir carbohidratos (actual: {plan.carbs_g or 'N/A'} g) "
                    f"y reforzar restricciones."
                )
            elif avg_glucose < 70:
                msg += (
                    f" Glucosa promedio baja ({avg_glucose} mg/dL): revise "
                    f"distribución de macronutrientes y horarios de comida."
                )
        msg += (
            f" Datos analizados: {readings_count} mediciones desde "
            f"{plan.start_date.strftime('%d/%m/%Y')}."
        )
        return msg

    async def _schedule_meal_reminders(self, plan: NutritionPlan) -> int:
        """
        Programa recordatorios de comidas para los próximos 7 días según el
        meal_schedule del plan. En el MVP solo se simula registrando una
        notificación por comida del día 1 (suficiente para validar el flujo).
        """
        schedule = plan.meal_schedule or {}
        if not schedule:
            return 0
        count = 0
        for meal_name, time_str in schedule.items():
            try:
                await self.notifications.send_meal_reminder(
                    patient_id=plan.patient_id,
                    meal_name=meal_name,
                    scheduled_time=time_str,
                )
                count += 1
            except Exception as exc:
                logger.warning("No se pudo programar recordatorio de %s: %s", meal_name, exc)
        return count

    async def _get_latest_risk_level(self, patient_id: int) -> Optional[str]:
        result = await self.db.execute(
            select(Prediction.risk_level)
            .where(Prediction.patient_id == patient_id)
            .order_by(desc(Prediction.created_at))
            .limit(1)
        )
        row = result.first()
        return row[0] if row else None

    async def _get_patient(self, patient_id: int) -> Optional[Patient]:
        result = await self.db.execute(
            select(Patient).where(Patient.id == patient_id)
        )
        return result.scalar_one_or_none()

    async def _deactivate_previous_plans(self, patient_id: int) -> int:
        result = await self.db.execute(
            select(NutritionPlan).where(
                and_(
                    NutritionPlan.patient_id == patient_id,
                    NutritionPlan.is_active == True,  # noqa: E712
                )
            )
        )
        plans = result.scalars().all()
        for p in plans:
            p.is_active = False
            p.end_date = datetime.utcnow()
        await self.db.flush()
        return len(plans)
