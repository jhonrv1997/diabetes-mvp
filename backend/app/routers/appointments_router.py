"""
Appointments Router — Epic 04, HU13.

Endpoints para:
  • Listar / crear / actualizar citas (enfermera o admin).
  • Marcar inasistencia (HU13 Escenario 2: dispara reagendamiento
    automático en los próximos 3 días + notificación push al paciente).
  • Calendario del Centro de Salud (lista de próximas citas).

Las citas automáticas por riesgo Alto se generan en `predictions_router`
tras cada predicción (HU13 Escenario 1).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import User, Patient, Appointment
from app.schemas import (
    AppointmentCreate,
    AppointmentUpdate,
    AppointmentResponse,
    MarkNoShowResponse,
)
from app.services.appointment_service import AppointmentService

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


async def _enrich(db: AsyncSession, appt: Appointment) -> AppointmentResponse:
    """Construye el response con nombres de paciente y enfermera."""
    resp = AppointmentResponse(
        id=appt.id,
        patient_id=appt.patient_id,
        patient_name=None,
        nurse_id=appt.nurse_id,
        nurse_name=None,
        scheduled_date=appt.scheduled_date,
        status=appt.status,
        reason=appt.reason,
        auto_generated=appt.auto_generated,
        no_show_count=appt.no_show_count,
        notes=appt.notes,
        created_at=appt.created_at,
        updated_at=appt.updated_at,
    )
    patient = (await db.execute(select(Patient).where(Patient.id == appt.patient_id))).scalar_one_or_none()
    if patient:
        resp.patient_name = f"{patient.first_name} {patient.last_name}"
    if appt.nurse_id:
        n = (await db.execute(select(User).where(User.id == appt.nurse_id))).scalar_one_or_none()
        if n:
            resp.nurse_name = n.full_name
    return resp


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    data: AppointmentCreate,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
):
    """Crea manualmente una cita de seguimiento (enfermera o admin)."""
    service = AppointmentService(db)
    try:
        appt = await service.create_appointment(
            patient_id=data.patient_id,
            scheduled_date=data.scheduled_date,
            nurse_id=current_user.id,
            reason=data.reason or "manual",
            notes=data.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return await _enrich(db, appt)


@router.get("", response_model=list[AppointmentResponse])
async def list_appointments(
    patient_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    upcoming_only: bool = Query(False, description="Solo citas futuras"),
    limit: int = Query(200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista citas. Permite filtrar por paciente, estado y solo futuras."""
    service = AppointmentService(db)
    appts = await service.list_appointments(
        patient_id=patient_id,
        status=status_filter,
        upcoming_only=upcoming_only,
        limit=limit,
    )
    return [await _enrich(db, a) for a in appts]


@router.get("/calendar", response_model=list[AppointmentResponse])
async def get_calendar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve las próximas citas programadas (calendario del Centro de Salud)."""
    service = AppointmentService(db)
    appts = await service.list_appointments(upcoming_only=True, limit=100)
    return [await _enrich(db, a) for a in appts]


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AppointmentService(db)
    appt = await service.get_appointment(appointment_id)
    if appt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return await _enrich(db, appt)


@router.put("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: int,
    data: AppointmentUpdate,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
):
    service = AppointmentService(db)
    appt = await service.update_appointment(
        appointment_id,
        scheduled_date=data.scheduled_date,
        status=data.status,
        reason=data.reason,
        notes=data.notes,
    )
    if appt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return await _enrich(db, appt)


# ── HU13 Escenario 2 — Reagendamiento por inasistencia ────────────────────

@router.post("/{appointment_id}/mark-no-show", response_model=MarkNoShowResponse)
async def mark_no_show(
    appointment_id: int,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Registra la inasistencia de un paciente a su cita. El sistema:
      1. Marca la cita original como `no_show`.
      2. Genera automáticamente una nueva cita en los próximos 3 días.
      3. Envía una notificación push de recordatorio al paciente.
      4. Actualiza el contador de inasistencias para seguimiento prioritario.
    """
    service = AppointmentService(db)
    try:
        result = await service.mark_no_show(appointment_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return MarkNoShowResponse(
        original_appointment=await _enrich(db, result["original_appointment"]),
        rescheduled_appointment=await _enrich(db, result["rescheduled_appointment"]),
        notifications_sent=result["notifications_sent"],
        message=result["message"],
    )
