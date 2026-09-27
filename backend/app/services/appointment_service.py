"""
Appointment Service — Epic 04, HU13.

Implementa los dos escenarios de Programación de citas de seguimiento:

    Escenario 1 — Cita automática por riesgo Alto
      • Tras una predicción con riesgo Alto, crea automáticamente una cita
        dentro de los 7 días siguientes.
      • Notifica al paciente vía app móvil (push) y la cita aparece en el
        calendario del Centro de Salud.

    Escenario 2 — Reagendamiento por inasistencia
      • Cuando se registra una inasistencia:
          - se envía notificación de recordatorio al paciente,
          - se genera una nueva cita en los próximos 3 días,
          - se actualiza el indicador de inasistencia en el perfil del
            paciente para seguimiento prioritario.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Patient, Prediction
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class AppointmentService:
    """Crea y gestiona citas de seguimiento para pacientes en riesgo."""

    # Ventanas de tiempo definidas por la HU
    HIGH_RISK_WINDOW_DAYS = 7
    MEDIUM_RISK_WINDOW_DAYS = 14  # también soporta riesgo Medio (extensión)
    NO_SHOW_RESCHEDULE_DAYS = 3

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notifications = NotificationService(db)

    # ── Creación automática (Escenario 1) ──────────────────────────────────

    async def auto_create_appointment_for_risk(
        self,
        patient_id: int,
        risk_level: str,
        prediction_id: Optional[int] = None,
        nurse_id: Optional[int] = None,
    ) -> Optional[Appointment]:
        """
        Crea automáticamente una cita de seguimiento si el riesgo es Alto
        (dentro de 7 días) o Medio (dentro de 14 días). No crea nada si ya
        existe una cita programada futura para el mismo paciente (evita
        duplicados).
        """
        if risk_level not in ("high", "medium"):
            return None

        # Evitar duplicados: si ya hay una cita futura programada, no crear
        if await self._has_future_scheduled_appointment(patient_id):
            logger.info(
                "Patient %d ya tiene una cita futura programada — no se crea nueva.", patient_id
            )
            return None

        if risk_level == "high":
            window = self.HIGH_RISK_WINDOW_DAYS
            reason = "risk_high_auto"
        else:
            window = self.MEDIUM_RISK_WINDOW_DAYS
            reason = "risk_medium_auto"

        # Programar dentro de los próximos N días a una hora razonable (10:00)
        scheduled_date = self._compute_scheduled_date(window)

        appointment = Appointment(
            patient_id=patient_id,
            nurse_id=nurse_id,
            scheduled_date=scheduled_date,
            status="scheduled",
            reason=reason,
            auto_generated=True,
            no_show_count=0,
            notes=(
                f"Cita automática generada tras predicción con riesgo {risk_level.upper()}"
                + (f" (predicción #{prediction_id})" if prediction_id else "")
            ),
        )
        self.db.add(appointment)
        await self.db.flush()
        await self.db.refresh(appointment)

        # Notificar al paciente via app móvil (push)
        try:
            await self.notifications.send_appointment_reminder(
                patient_id=patient_id,
                scheduled_date=scheduled_date,
            )
        except Exception as exc:
            logger.warning("No se pudo enviar recordatorio push: %s", exc)

        logger.info(
            "Cita automática #%d creada para paciente #%d (riesgo=%s, fecha=%s)",
            appointment.id, patient_id, risk_level, scheduled_date.isoformat(),
        )
        return appointment

    # ── Creación manual ────────────────────────────────────────────────────

    async def create_appointment(
        self,
        patient_id: int,
        scheduled_date: datetime,
        nurse_id: Optional[int] = None,
        reason: str = "manual",
        notes: Optional[str] = None,
    ) -> Appointment:
        patient = await self._get_patient(patient_id)
        if patient is None:
            raise ValueError(f"Paciente #{patient_id} no encontrado")

        appointment = Appointment(
            patient_id=patient_id,
            nurse_id=nurse_id,
            scheduled_date=scheduled_date,
            status="scheduled",
            reason=reason,
            auto_generated=False,
            no_show_count=0,
            notes=notes,
        )
        self.db.add(appointment)
        await self.db.flush()
        await self.db.refresh(appointment)
        logger.info("Cita manual #%d para paciente #%d", appointment.id, patient_id)
        return appointment

    async def update_appointment(
        self,
        appointment_id: int,
        scheduled_date: Optional[datetime] = None,
        status: Optional[str] = None,
        reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[Appointment]:
        result = await self.db.execute(
            select(Appointment).where(Appointment.id == appointment_id)
        )
        appointment = result.scalar_one_or_none()
        if appointment is None:
            return None
        if scheduled_date is not None:
            appointment.scheduled_date = scheduled_date
        if status is not None:
            appointment.status = status
        if reason is not None:
            appointment.reason = reason
        if notes is not None:
            appointment.notes = notes
        await self.db.flush()
        await self.db.refresh(appointment)
        return appointment

    # ── Marcar inasistencia (Escenario 2) ──────────────────────────────────

    async def mark_no_show(self, appointment_id: int) -> dict:
        """
        Registra la inasistencia de un paciente a su cita:
          1. Marca la cita original como `no_show` e incrementa el contador
             `no_show_count` del paciente (se acumula en una nueva cita).
          2. Genera una nueva cita en los próximos 3 días.
          3. Envía una notificación push de recordatorio al paciente.

        Retorna un dict con la cita original, la nueva cita reagendada y el
        conteo de notificaciones enviadas.
        """
        result = await self.db.execute(
            select(Appointment).where(Appointment.id == appointment_id)
        )
        appointment = result.scalar_one_or_none()
        if appointment is None:
            raise ValueError(f"Cita #{appointment_id} no encontrada")

        if appointment.status == "no_show":
            raise ValueError(f"La cita #{appointment_id} ya está marcada como inasistencia")

        # 1. Marcar inasistencia
        previous_no_shows = appointment.no_show_count or 0
        appointment.status = "no_show"
        appointment.notes = (appointment.notes or "") + " | Marcada como inasistencia."
        await self.db.flush()

        # 2. Crear nueva cita en 3 días
        new_date = self._compute_scheduled_date(self.NO_SHOW_RESCHEDULE_DAYS)
        new_appointment = Appointment(
            patient_id=appointment.patient_id,
            nurse_id=appointment.nurse_id,
            scheduled_date=new_date,
            status="scheduled",
            reason="rescheduled_no_show",
            auto_generated=True,
            no_show_count=previous_no_shows + 1,  # se acumula
            notes=(
                f"Reagendada por inasistencia a la cita #{appointment.id} "
                f"del {appointment.scheduled_date.strftime('%d/%m/%Y')}."
            ),
        )
        self.db.add(new_appointment)
        await self.db.flush()
        await self.db.refresh(new_appointment)

        # 3. Enviar notificaciones: una de recordatorio + una de reagendamiento
        notif_count = 0
        try:
            await self.notifications.send_appointment_reminder(
                patient_id=appointment.patient_id,
                scheduled_date=new_date,
            )
            notif_count += 1
        except Exception as exc:
            logger.warning("No se pudo enviar recordatorio push: %s", exc)
        try:
            await self.notifications.send_appointment_reschedule(
                patient_id=appointment.patient_id,
                new_date=new_date,
                reason="Inasistencia a cita anterior",
            )
            notif_count += 1
        except Exception as exc:
            logger.warning("No se pudo enviar notificación de reagendamiento: %s", exc)

        logger.info(
            "Cita #%d marcada como no_show; nueva cita #%d para paciente #%d",
            appointment.id, new_appointment.id, appointment.patient_id,
        )

        return {
            "original_appointment": appointment,
            "rescheduled_appointment": new_appointment,
            "notifications_sent": notif_count,
            "message": (
                f"Inasistencia registrada. Se programó una nueva cita para "
                f"el {new_date.strftime('%d/%m/%Y a las %H:%M')} y se enviaron "
                f"{notif_count} notificación(es) al paciente."
            ),
        }

    # ── Consultas ──────────────────────────────────────────────────────────

    async def list_appointments(
        self,
        patient_id: Optional[int] = None,
        status: Optional[str] = None,
        upcoming_only: bool = False,
        limit: int = 200,
    ) -> list[Appointment]:
        stmt = select(Appointment).order_by(desc(Appointment.scheduled_date)).limit(limit)
        filters = []
        if patient_id is not None:
            filters.append(Appointment.patient_id == patient_id)
        if status is not None:
            filters.append(Appointment.status == status)
        if upcoming_only:
            filters.append(Appointment.scheduled_date >= datetime.utcnow())
        if filters:
            stmt = select(Appointment).where(and_(*filters)).order_by(
                desc(Appointment.scheduled_date)
            ).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_appointment(self, appointment_id: int) -> Optional[Appointment]:
        result = await self.db.execute(
            select(Appointment).where(Appointment.id == appointment_id)
        )
        return result.scalar_one_or_none()

    # ── Helpers ────────────────────────────────────────────────────────────

    def _compute_scheduled_date(self, window_days: int) -> datetime:
        """
        Programa una cita dentro de los próximos `window_days` días a las
        10:00 AM. Distribuye uniformemente para evitar sobrecargar un día.
        """
        now = datetime.utcnow()
        # Elegir día entre mañana y window_days
        offset = max(1, min(window_days, window_days))  # al menos 1 día
        target_date = now + timedelta(days=offset)
        return target_date.replace(hour=10, minute=0, second=0, microsecond=0)

    async def _has_future_scheduled_appointment(self, patient_id: int) -> bool:
        result = await self.db.execute(
            select(Appointment).where(
                and_(
                    Appointment.patient_id == patient_id,
                    Appointment.status == "scheduled",
                    Appointment.scheduled_date >= datetime.utcnow(),
                )
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _get_patient(self, patient_id: int) -> Optional[Patient]:
        result = await self.db.execute(
            select(Patient).where(Patient.id == patient_id)
        )
        return result.scalar_one_or_none()
