from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.config import settings
from app.database import get_db
from app.models import User, Patient, ClinicalData
from app.schemas import ClinicalDataCreate, ClinicalDataResponse

router = APIRouter(prefix="/api/clinical-data", tags=["Clinical Data"])


@router.post("", response_model=ClinicalDataResponse, status_code=status.HTTP_201_CREATED)
async def create_clinical_data(
    data: ClinicalDataCreate,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Patient).where(Patient.id == data.patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    clinical_record = ClinicalData(
        patient_id=data.patient_id,
        systolic_bp=data.systolic_bp,
        diastolic_bp=data.diastolic_bp,
        weight_kg=data.weight_kg,
        height_cm=data.height_cm,
        bmi=data.bmi,
        age=data.age,
        family_diabetes=data.family_diabetes,
        hypertension_history=data.hypertension_history,
        recorded_by=data.recorded_by or current_user.id,
        notes=data.notes,
    )
    db.add(clinical_record)
    await db.flush()
    await db.refresh(clinical_record)
    return clinical_record


@router.get("/{patient_id}", response_model=ClinicalDataResponse)
async def get_latest_clinical_data(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ClinicalData)
        .where(ClinicalData.patient_id == patient_id)
        .order_by(desc(ClinicalData.created_at))
        .limit(1)
    )
    clinical = result.scalar_one_or_none()
    if clinical is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No clinical data found for this patient",
        )
    return clinical


@router.get("/{patient_id}/history", response_model=list[ClinicalDataResponse])
async def get_clinical_data_history(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ClinicalData)
        .where(ClinicalData.patient_id == patient_id)
        .order_by(desc(ClinicalData.created_at))
    )
    return result.scalars().all()
