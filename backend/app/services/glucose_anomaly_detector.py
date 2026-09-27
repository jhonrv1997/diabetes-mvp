"""
Glucose Anomaly Detector — Epic 04, HU06.

Detecta patrones de glucosa peligrosamente altos en tiempo real. Cuando se
confirma la anomalía en el backend (con `confirm_emergency_anomaly`), se
invoca a `NotificationService.send_emergency_alert` para enviar la
notificación push con el mensaje 'Alerta de Salud: Acuda a emergencia' y
sonido prioritario (priority=high, sound=critical).

Reglas de anomalía (configurables):
  • Lectura individual >= GLUCOSE_EMERGENCY_THRESHOLD (default 250 mg/dL)
  • Patrón: >= 2 lecturas consecutivas en las últimas 2 horas por encima
    del umbral, o promedio de las últimas 3 >= 240 mg/dL.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GlucoseReading, Patient
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class GlucoseAnomalyDetector:
    """Detecta anomalías graves en lecturas de glucosa y dispara alertas push."""

    # Umbral de emergencia: una sola lectura >= 250 mg/dL se considera
    # peligroso alto y dispara la alerta de emergencia.
    GLUCOSE_EMERGENCY_THRESHOLD = 250.0
    PATTERN_WINDOW_HOURS = 2
    PATTERN_MIN_READINGS = 2
    PATTERN_AVG_THRESHOLD = 240.0

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notifications = NotificationService(db)

    async def check_reading(
        self,
        reading: GlucoseReading,
    ) -> Optional[dict]:
        """
        Evalúa una nueva lectura de glucosa y, si corresponde, dispara la
        alerta de emergencia (HU06 Escenario 1).

        Retorna un dict con el detalle de la anomalía si se detectó, o None.
        """
        # 1. ¿Lectura individual peligrosa?
        if reading.glucose_mg_dl >= self.GLUCOSE_EMERGENCY_THRESHOLD:
            return await self.confirm_emergency_anomaly(
                patient_id=reading.patient_id,
                glucose_mg_dl=reading.glucose_mg_dl,
                reason=f"Lectura individual >= {self.GLUCOSE_EMERGENCY_THRESHOLD} mg/dL",
            )

        # 2. ¿Patrón peligroso en las últimas 2 horas?
        window_start = datetime.utcnow() - timedelta(hours=self.PATTERN_WINDOW_HOURS)
        result = await self.db.execute(
            select(GlucoseReading)
            .where(
                and_(
                    GlucoseReading.patient_id == reading.patient_id,
                    GlucoseReading.measurement_timestamp >= window_start,
                )
            )
            .order_by(desc(GlucoseReading.measurement_timestamp))
            .limit(10)
        )
        recent = list(result.scalars().all())
        if len(recent) >= self.PATTERN_MIN_READINGS:
            avg = sum(r.glucose_mg_dl for r in recent) / len(recent)
            high_count = sum(
                1 for r in recent if r.glucose_mg_dl >= self.PATTERN_AVG_THRESHOLD
            )
            if avg >= self.PATTERN_AVG_THRESHOLD or high_count >= self.PATTERN_MIN_READINGS:
                return await self.confirm_emergency_anomaly(
                    patient_id=reading.patient_id,
                    glucose_mg_dl=reading.glucose_mg_dl,
                    reason=(
                        f"Patrón peligroso: {len(recent)} lecturas en "
                        f"{self.PATTERN_WINDOW_HOURS}h, promedio={avg:.1f} mg/dL"
                    ),
                )

        return None

    async def confirm_emergency_anomaly(
        self,
        patient_id: int,
        glucose_mg_dl: float,
        reason: str = "",
    ) -> Optional[dict]:
        """
        Confirma la anomalía en el backend y envía la notificación push
        prioritaria al paciente con el mensaje 'Alerta de Salud: Acuda a
        emergencia' (HU06 Escenario 1, paso "Cuando se confirma la anomalía
        en el backend").
        """
        patient = await self._get_patient(patient_id)
        if patient is None:
            logger.warning("Anomaly for unknown patient %d — skipping.", patient_id)
            return None

        # Enviar notificación push prioritaria
        notification = await self.notifications.send_emergency_alert(
            patient_id=patient_id,
            glucose_mg_dl=glucose_mg_dl,
        )

        logger.warning(
            "EMERGENCY GLUCOSE ANOMALY detected: patient=%s (%s) glucose=%.1f mg/dL reason=%s "
            "→ push sent=%s",
            patient_id,
            f"{patient.first_name} {patient.last_name}",
            glucose_mg_dl,
            reason,
            notification.is_sent if notification else False,
        )

        return {
            "patient_id": patient_id,
            "patient_name": f"{patient.first_name} {patient.last_name}",
            "glucose_mg_dl": glucose_mg_dl,
            "reason": reason,
            "notification_id": notification.id if notification else None,
            "notification_sent": notification.is_sent if notification else False,
            "message": "Alerta de Salud: Acuda a emergencia",
        }

    async def _get_patient(self, patient_id: int) -> Optional[Patient]:
        result = await self.db.execute(
            select(Patient).where(Patient.id == patient_id)
        )
        return result.scalar_one_or_none()
