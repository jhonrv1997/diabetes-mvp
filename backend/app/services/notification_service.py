"""
Push Notification Service — Epic 04, HU06.

Genera y "envía" notificaciones push a los pacientes. En un entorno de
producción, este servicio delegaría a FCM (Android) / APNs (iOS) utilizando
los tokens registrados en la tabla `notification_tokens`. Para el MVP, las
notificaciones se persisten en `push_notifications` con `is_sent=True` y
`sent_at=now()`, simulando el envío al dispositivo. El frontend puede
entonces leerlas y mostrarlas como si llegaran vía push.

Cubre el Escenario 1 de HU06:
    "Cuando se confirma la anomalía en el backend,
     entonces se envía una notificación Push al celular del paciente
     con el mensaje 'Alerta de Salud: Acuda a emergencia' y sonido prioritario."
"""

import json
import logging
from datetime import datetime
from typing import Optional, Iterable

from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    NotificationToken,
    PushNotification,
    Patient,
    User,
)

logger = logging.getLogger(__name__)


class NotificationService:
    """Crea y registra notificaciones push para los pacientes."""

    # Mensaje canónico definido en el criterio de aceptación de HU06.
    EMERGENCY_TITLE = "Alerta de Salud"
    EMERGENCY_BODY = "Alerta de Salud: Acuda a emergencia"

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Envío de notificaciones ────────────────────────────────────────────

    async def send_push_notification(
        self,
        patient_id: int,
        notification_type: str,
        title: str,
        body: str,
        priority: str = "normal",
        sound: str = "default",
        payload: Optional[dict] = None,
    ) -> Optional[PushNotification]:
        """
        Crea un registro de notificación push y lo marca como enviado.

        En el MVP no existe un proveedor externo (FCM/APNs) configurado; por
        ello se simula el envío marcando `is_sent=True` y registrando `sent_at`.
        En producción, aquí se invocaría al cliente del proveedor usando los
        tokens activos del paciente.
        """
        # Verificar que exista al menos un token registrado (simula que el
        # paciente tiene la app instalada). Si no hay token, aún así creamos
        # el registro (is_sent=False) para que el equipo sepa que el paciente
        # no recibió la notificación.
        tokens = await self._get_active_tokens(patient_id)
        is_sent = len(tokens) > 0

        notif = PushNotification(
            patient_id=patient_id,
            notification_type=notification_type,
            title=title,
            body=body,
            priority=priority,
            sound=sound,
            is_sent=is_sent,
            sent_at=datetime.utcnow() if is_sent else None,
            is_read=False,
            payload_json=json.dumps(payload) if payload else None,
        )
        self.db.add(notif)
        await self.db.flush()
        await self.db.refresh(notif)

        logger.info(
            "PushNotification created: type=%s patient=%d priority=%s sent=%s",
            notification_type, patient_id, priority, is_sent,
        )
        return notif

    async def send_emergency_alert(
        self,
        patient_id: int,
        glucose_mg_dl: float,
        custom_message: Optional[str] = None,
    ) -> Optional[PushNotification]:
        """
        Dispara la alerta de emergencia definida en HU06:
            Título:  'Alerta de Salud'
            Cuerpo:  'Alerta de Salud: Acuda a emergencia'
            Prioridad: 'high'  → sonido prioritario en el dispositivo.
        """
        body = custom_message or self.EMERGENCY_BODY
        payload = {
            "alert_type": "emergency",
            "glucose_mg_dl": glucose_mg_dl,
            "action": "SEEK_EMERGENCY_CARE",
            "sound": "critical",
        }
        return await self.send_push_notification(
            patient_id=patient_id,
            notification_type="emergency_alert",
            title=self.EMERGENCY_TITLE,
            body=body,
            priority="high",
            sound="critical",
            payload=payload,
        )

    async def send_meal_reminder(
        self,
        patient_id: int,
        meal_name: str,
        scheduled_time: str,
    ) -> Optional[PushNotification]:
        """Recordatorio de comida programado por el plan nutricional (HU10 Escenario 1)."""
        return await self.send_push_notification(
            patient_id=patient_id,
            notification_type="meal_reminder",
            title="Recordatorio de comida",
            body=f"Es hora de tu {meal_name} ({scheduled_time}). Recuerda seguir tu plan nutricional.",
            priority="normal",
            sound="default",
            payload={"meal": meal_name, "scheduled_time": scheduled_time},
        )

    async def send_appointment_reminder(
        self,
        patient_id: int,
        scheduled_date: datetime,
    ) -> Optional[PushNotification]:
        """Recordatorio de cita de seguimiento (HU13 Escenario 1)."""
        return await self.send_push_notification(
            patient_id=patient_id,
            notification_type="appointment_reminder",
            title="Recordatorio de cita",
            body=f"Tienes una cita de seguimiento programada para el "
                 f"{scheduled_date.strftime('%d/%m/%Y a las %H:%M')}.",
            priority="high",
            sound="default",
            payload={"scheduled_date": scheduled_date.isoformat()},
        )

    async def send_appointment_reschedule(
        self,
        patient_id: int,
        new_date: datetime,
        reason: str = "Reagendamiento por inasistencia",
    ) -> Optional[PushNotification]:
        """Notificación de reagendamiento por inasistencia (HU13 Escenario 2)."""
        return await self.send_push_notification(
            patient_id=patient_id,
            notification_type="appointment_reschedule",
            title="Cita reagendada",
            body=f"Se reagendó tu cita de seguimiento para el "
                 f"{new_date.strftime('%d/%m/%Y a las %H:%M')}. "
                 f"Motivo: {reason}.",
            priority="high",
            sound="default",
            payload={"new_date": new_date.isoformat(), "reason": reason},
        )

    # ── Consulta de notificaciones ──────────────────────────────────────────

    async def list_notifications(
        self,
        patient_id: Optional[int] = None,
        unread_only: bool = False,
        limit: int = 100,
    ) -> list[PushNotification]:
        stmt = select(PushNotification).order_by(desc(PushNotification.created_at)).limit(limit)
        filters = []
        if patient_id is not None:
            filters.append(PushNotification.patient_id == patient_id)
        if unread_only:
            filters.append(PushNotification.is_read == False)  # noqa: E712
        if filters:
            stmt = stmt.where(and_(*filters)).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def mark_as_read(self, notification_id: int) -> Optional[PushNotification]:
        result = await self.db.execute(
            select(PushNotification).where(PushNotification.id == notification_id)
        )
        notif = result.scalar_one_or_none()
        if notif is None:
            return None
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = datetime.utcnow()
            await self.db.flush()
            await self.db.refresh(notif)
        return notif

    # ── Tokens ─────────────────────────────────────────────────────────────

    async def register_token(
        self,
        patient_id: int,
        token: str,
        platform: str = "android",
    ) -> NotificationToken:
        # Invalidar tokens anteriores del mismo valor (reusar token en otro
        # dispositivo es un caso edge; aquí simplemente reactivamos el existente).
        existing = await self.db.execute(
            select(NotificationToken).where(NotificationToken.token == token)
        )
        existing_tok = existing.scalar_one_or_none()
        if existing_tok is not None:
            existing_tok.is_active = True
            existing_tok.patient_id = patient_id
            existing_tok.platform = platform
            await self.db.flush()
            await self.db.refresh(existing_tok)
            return existing_tok

        new_tok = NotificationToken(
            patient_id=patient_id,
            token=token,
            platform=platform,
            is_active=True,
        )
        self.db.add(new_tok)
        await self.db.flush()
        await self.db.refresh(new_tok)
        return new_tok

    async def _get_active_tokens(self, patient_id: int) -> list[NotificationToken]:
        result = await self.db.execute(
            select(NotificationToken).where(
                and_(
                    NotificationToken.patient_id == patient_id,
                    NotificationToken.is_active == True,  # noqa: E712
                )
            )
        )
        return list(result.scalars().all())
