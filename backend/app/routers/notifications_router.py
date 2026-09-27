"""
Notifications Router — Epic 04, HU06.

Endpoints para:
  • Registrar tokens de dispositivo móvil del paciente (FCM/APNs simulado).
  • Listar notificaciones push enviadas al paciente (historial).
  • Marcar notificaciones como leídas.
  • Disparar manualmente una alerta de emergencia (HU06 Escenario 1).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import User, Patient
from app.schemas import (
    NotificationTokenRegister,
    NotificationTokenResponse,
    PushNotificationResponse,
    EmergencyAlertRequest,
)
from app.services.notification_service import NotificationService
from app.services.glucose_anomaly_detector import GlucoseAnomalyDetector

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.post("/token", response_model=NotificationTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_notification_token(
    data: NotificationTokenRegister,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Registra un token de dispositivo para que el paciente reciba notificaciones push."""
    # Verificar paciente
    result = await db.execute(select(Patient).where(Patient.id == data.patient_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    service = NotificationService(db)
    token = await service.register_token(
        patient_id=data.patient_id,
        token=data.token,
        platform=data.platform,
    )
    return NotificationTokenResponse.model_validate(token)


@router.get("", response_model=list[PushNotificationResponse])
async def list_notifications(
    patient_id: Optional[int] = Query(None, description="Filtrar por paciente"),
    unread_only: bool = Query(False, description="Solo no leídas"),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista el historial de notificaciones push enviadas."""
    service = NotificationService(db)
    notifs = await service.list_notifications(
        patient_id=patient_id, unread_only=unread_only, limit=limit
    )
    return [PushNotificationResponse.model_validate(n) for n in notifs]


@router.get("/{patient_id}", response_model=list[PushNotificationResponse])
async def list_patient_notifications(
    patient_id: int,
    unread_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista las notificaciones push de un paciente específico."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    service = NotificationService(db)
    notifs = await service.list_notifications(
        patient_id=patient_id, unread_only=unread_only, limit=limit
    )
    return [PushNotificationResponse.model_validate(n) for n in notifs]


@router.put("/{notification_id}/read", response_model=PushNotificationResponse)
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Marca una notificación como leída."""
    service = NotificationService(db)
    notif = await service.mark_as_read(notification_id)
    if notif is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return PushNotificationResponse.model_validate(notif)


@router.post("/emergency-alert", status_code=status.HTTP_201_CREATED)
async def trigger_emergency_alert(
    data: EmergencyAlertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirma una anomalía grave en el backend y dispara la notificación push
    prioritaria al paciente (HU06 Escenario 1, paso "Cuando se confirma la
    anomalía en el backend").

    Respuesta: detalle de la anomalía y la notificación enviada.
    """
    result = await db.execute(select(Patient).where(Patient.id == data.patient_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    detector = GlucoseAnomalyDetector(db)
    detail = await detector.confirm_emergency_anomaly(
        patient_id=data.patient_id,
        glucose_mg_dl=data.glucose_mg_dl,
        reason=data.message or "Confirmed by clinical staff",
    )
    if detail is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not create alert")
    return detail
