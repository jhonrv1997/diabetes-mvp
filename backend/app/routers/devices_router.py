from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import User, Patient, Device
from app.schemas import DevicePair, DeviceResponse, DeviceSyncRequest

router = APIRouter(prefix="/api/devices", tags=["Devices"])


@router.post("/pair", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def pair_device(
    data: DevicePair,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
):
    # Verify patient exists
    result = await db.execute(select(Patient).where(Patient.id == data.patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    # Check if device already paired
    result = await db.execute(select(Device).where(Device.ble_address == data.ble_address))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device with this BLE address is already registered",
        )

    device = Device(
        patient_id=data.patient_id,
        ble_address=data.ble_address,
        is_paired=True,
        status="disconnected",
    )
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return device


@router.post("/sync", response_model=DeviceResponse)
async def sync_device(
    data: DeviceSyncRequest,
    current_user: User = Depends(require_role(["admin", "nurse"])),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Device).where(Device.id == data.device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    if not device.is_paired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device is not paired with any patient",
        )

    # Simulate sync: update status and last_sync_at
    device.status = "syncing"
    await db.flush()

    # In a real implementation, this would trigger BLE communication
    # For the MVP, we simulate a successful sync
    device.last_sync_at = datetime.utcnow()
    device.status = "connected"
    device.battery_level = max((device.battery_level or 100) - 1, 0)
    await db.flush()
    await db.refresh(device)
    return device


@router.get("/status", response_model=list[DeviceResponse])
async def get_all_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Device).order_by(Device.id))
    return result.scalars().all()


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device(
    device_id: int,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    await db.delete(device)
    await db.flush()
