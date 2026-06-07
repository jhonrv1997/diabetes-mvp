from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import User, Patient, GlucoseReading
from app.schemas import GlucoseReadingCreate, GlucoseReadingResponse

router = APIRouter(prefix="/api/glucose", tags=["Glucose Readings"])


@router.get("/{patient_id}", response_model=list[GlucoseReadingResponse])
async def get_glucose_readings(
    patient_id: int,
    start_date: datetime = Query(None, description="Start date filter"),
    end_date: datetime = Query(None, description="End date filter"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify patient exists
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    stmt = (
        select(GlucoseReading)
        .where(GlucoseReading.patient_id == patient_id)
        .order_by(desc(GlucoseReading.measurement_timestamp))
    )

    filters = []
    if start_date:
        filters.append(GlucoseReading.measurement_timestamp >= start_date)
    if end_date:
        filters.append(GlucoseReading.measurement_timestamp <= end_date)

    if filters:
        stmt = stmt.where(and_(*filters))

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=GlucoseReadingResponse, status_code=status.HTTP_201_CREATED)
async def create_glucose_reading(
    data: GlucoseReadingCreate,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
):
    # Verify patient exists
    result = await db.execute(select(Patient).where(Patient.id == data.patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    reading = GlucoseReading(
        patient_id=data.patient_id,
        glucose_mg_dl=data.glucose_mg_dl,
        measurement_timestamp=data.measurement_timestamp,
        sequence_number=data.sequence_number,
        source_device=data.source_device,
        context=data.context,
        is_synced=False,  # Manual entry
    )
    db.add(reading)
    await db.flush()
    await db.refresh(reading)
    return reading


@router.get("/{patient_id}/latest", response_model=list[GlucoseReadingResponse])
async def get_latest_readings(
    patient_id: int,
    limit: int = Query(10, ge=1, le=100, description="Number of readings to return"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify patient exists
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    result = await db.execute(
        select(GlucoseReading)
        .where(GlucoseReading.patient_id == patient_id)
        .order_by(desc(GlucoseReading.measurement_timestamp))
        .limit(limit)
    )
    return result.scalars().all()