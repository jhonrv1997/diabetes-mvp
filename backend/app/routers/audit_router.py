"""
Router de auditoría de accesos — Epic 05, HU12 Escenario 2.

El administrador puede verificar quién accedió a los datos de un paciente:
un listado cronológico con fecha, hora, usuario y acción realizada
(consulta, edición, exportación), con posibilidad de exportar el log en
formato CSV (compatible con Excel, con BOM UTF-8).
"""

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_role
from app.database import get_db
from app.audit_database import get_audit_db
from app.models import User, Patient
from app.audit_models import AuditLog
from app.schemas import AuditLogResponse, AuditLogListResponse

router = APIRouter(prefix="/api/audit", tags=["Audit (HU12)"])

# La auditoría es exclusiva del Administrador del Sistema (HU12 Escenario 2).
_AUDIT_ROLES = ["admin"]

ACTION_LABELS = {
    "consulta": "Consulta",
    "creacion": "Creación",
    "edicion": "Edición",
    "eliminacion": "Eliminación",
    "exportacion": "Exportación",
}


def _to_response(log: AuditLog, patient_name: Optional[str] = None) -> AuditLogResponse:
    data = {
        "id": log.id,
        "created_at": log.created_at,
        "user_id": log.user_id,
        "username": log.username,
        "user_role": log.user_role,
        "patient_id": log.patient_id,
        "patient_name": patient_name,
        "action": log.action,
        "resource": log.resource,
        "method": log.method,
        "endpoint": log.endpoint,
        "status_code": log.status_code,
        "details": log.details,
    }
    return AuditLogResponse(**data)


async def _attach_patient_names(db: AsyncSession, logs: list[AuditLog]) -> list[AuditLogResponse]:
    """Enriquece las entradas con el nombre del paciente (BD principal)."""
    if not logs:
        return []
    patient_ids = {log.patient_id for log in logs if log.patient_id is not None}
    names: dict[int, str] = {}
    if patient_ids:
        result = await db.execute(select(Patient).where(Patient.id.in_(patient_ids)))
        for patient in result.scalars().all():
            names[patient.id] = f"{patient.first_name} {patient.last_name}"
    return [_to_response(log, names.get(log.patient_id)) for log in logs]


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.strptime(str(value)[:10], "%Y-%m-%d")


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    patient_id: int = Query(None, description="Filtrar por paciente"),
    user_id: int = Query(None, description="Filtrar por usuario"),
    action: str = Query(None, description="consulta|creacion|edicion|eliminacion|exportacion"),
    date_from: str = Query(None, description="Fecha inicial (YYYY-MM-DD)"),
    date_to: str = Query(None, description="Fecha final (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_role(_AUDIT_ROLES)),
    db: AsyncSession = Depends(get_db),
    audit_db: AsyncSession = Depends(get_audit_db),
):
    """Registro global de auditoría con filtros (más reciente primero)."""
    conditions = []
    if patient_id is not None:
        conditions.append(AuditLog.patient_id == patient_id)
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if action:
        conditions.append(AuditLog.action == action)
    dt_from = _parse_dt(date_from)
    dt_to = _parse_dt(date_to)
    if dt_from:
        conditions.append(AuditLog.created_at >= dt_from)
    if dt_to:
        conditions.append(AuditLog.created_at <= datetime.combine(dt_to.date(), datetime.max.time()))

    where = and_(*conditions) if conditions else True

    total = (
        await audit_db.execute(select(func.count(AuditLog.id)).where(where))
    ).scalar_one()

    result = await audit_db.execute(
        select(AuditLog)
        .where(where)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    logs = list(result.scalars().all())
    items = await _attach_patient_names(db, logs)
    return AuditLogListResponse(total=total, items=items)


@router.get("/patient/{patient_id}", response_model=AuditLogListResponse)
async def patient_audit_log(
    patient_id: int,
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(require_role(_AUDIT_ROLES)),
    db: AsyncSession = Depends(get_db),
    audit_db: AsyncSession = Depends(get_audit_db),
):
    """HU12 Escenario 2: listado cronológico de accesos a los datos de un
    paciente, con fecha, hora, usuario y acción realizada."""
    patient = (
        await db.execute(select(Patient).where(Patient.id == patient_id))
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    result = await audit_db.execute(
        select(AuditLog)
        .where(AuditLog.patient_id == patient_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    logs = list(result.scalars().all())
    items = await _attach_patient_names(db, logs)
    return AuditLogListResponse(total=len(items), items=items)


def _csv_response(rows: list[list], filename: str) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    # BOM UTF-8 para que Excel muestre correctamente los acentos
    buffer.write("\ufeff")
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_AUDIT_CSV_HEADER = ["Fecha", "Hora", "Usuario", "Rol", "Acción", "Paciente", "Recurso", "Detalles"]


def _log_to_csv_row(log: AuditLog, patient_name: Optional[str]) -> list:
    created = log.created_at
    return [
        created.strftime("%d/%m/%Y") if created else "",
        created.strftime("%H:%M:%S") if created else "",
        log.username or "-",
        log.user_role or "-",
        ACTION_LABELS.get(log.action, log.action),
        patient_name if patient_name else ("-"),
        log.resource or "-",
        log.details or (f"{log.method} {log.endpoint}" if log.endpoint else ""),
    ]


@router.get("/patient/{patient_id}/export/csv")
async def export_patient_audit_csv(
    patient_id: int,
    current_user: User = Depends(require_role(_AUDIT_ROLES)),
    db: AsyncSession = Depends(get_db),
    audit_db: AsyncSession = Depends(get_audit_db),
):
    """Exporta el registro de auditoría del paciente en formato CSV (HU12
    Escenario 2: 'permite exportar el log en formato CSV')."""
    patient = (
        await db.execute(select(Patient).where(Patient.id == patient_id))
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    result = await audit_db.execute(
        select(AuditLog)
        .where(AuditLog.patient_id == patient_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )
    logs = list(result.scalars().all())
    patient_name = f"{patient.first_name} {patient.last_name}"

    rows = [_AUDIT_CSV_HEADER]
    rows.extend(_log_to_csv_row(log, patient_name) for log in logs)
    filename = f"auditoria_paciente_{patient_id}.csv"
    return _csv_response(rows, filename)


@router.get("/export/csv")
async def export_audit_csv(
    patient_id: int = Query(None, description="Filtrar por paciente"),
    limit: int = Query(5000, ge=1, le=50000),
    current_user: User = Depends(require_role(_AUDIT_ROLES)),
    db: AsyncSession = Depends(get_db),
    audit_db: AsyncSession = Depends(get_audit_db),
):
    """Exporta el registro global de auditoría en formato CSV."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
    if patient_id is not None:
        stmt = stmt.where(AuditLog.patient_id == patient_id)
    result = await audit_db.execute(stmt)
    logs = list(result.scalars().all())

    patient_ids = {log.patient_id for log in logs if log.patient_id is not None}
    names: dict[int, str] = {}
    if patient_ids:
        pr = await db.execute(select(Patient).where(Patient.id.in_(patient_ids)))
        for patient in pr.scalars().all():
            names[patient.id] = f"{patient.first_name} {patient.last_name}"

    rows = [_AUDIT_CSV_HEADER]
    rows.extend(_log_to_csv_row(log, names.get(log.patient_id)) for log in logs)
    filename = f"auditoria_global{'_paciente_' + str(patient_id) if patient_id else ''}.csv"
    return _csv_response(rows, filename)
