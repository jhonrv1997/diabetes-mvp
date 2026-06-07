from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import User, Patient
from app.schemas import PatientCreate, PatientUpdate, PatientResponse

router = APIRouter(prefix="/api/patients", tags=["Patients"])


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    patient_data: PatientCreate,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
):
    patient = Patient(**patient_data.model_dump())
    db.add(patient)
    await db.flush()
    await db.refresh(patient)
    return patient


@router.get("", response_model=list[PatientResponse])
async def list_patients(
    search: str = Query(None, description="Search by first or last name"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Patient).order_by(Patient.last_name, Patient.first_name)
    if search:
        stmt = stmt.where(
            or_(
                Patient.first_name.ilike(f"%{search}%"),
                Patient.last_name.ilike(f"%{search}%"),
            )
        )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: int,
    patient_data: PatientUpdate,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    update_data = patient_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(patient, field, value)

    await db.flush()
    await db.refresh(patient)
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: int,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    await db.delete(patient)
    await db.flush()
