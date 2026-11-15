"""
Router de gestión de usuarios y roles — Epic 05, HU12 Escenario 1.

El Administrador del Sistema registra las cuentas del personal del Centro
de Salud y selecciona el rol correspondiente (Médico, Nutricionista,
Enfermera, Jefe del Centro de Salud, Administrador). El sistema asigna
automáticamente los permisos asociados a cada rol (ver matriz en
GET /api/users/permissions) para cumplir con la Ley de Protección de
Datos Personales: cada profesional accede solo a la información
estrictamente necesaria para su función.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_password_hash, require_role
from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserUpdate, UserResponse, RolePermissions

router = APIRouter(prefix="/api/users", tags=["Users & Roles (HU12)"])

# Matriz de permisos por rol (fuente única de verdad documental).
# Se refleja tanto en el backend (dependencias require_role) como en la
# navegación del frontend. HU12 Escenario 1.
ROLE_PERMISSIONS: dict[str, RolePermissions] = {
    "admin": RolePermissions(
        role="admin",
        label="Administrador",
        modules=[
            "Usuarios y roles",
            "Auditoría de accesos",
            "Pacientes",
            "Datos clínicos (triaje)",
            "Predicciones e historial",
            "Dispositivos IoT",
            "Alertas y notificaciones",
            "Nutrición",
            "Citas",
            "Reportes poblacionales y DIRESA",
        ],
    ),
    "health_manager": RolePermissions(
        role="health_manager",
        label="Jefe del Centro de Salud",
        modules=[
            "Dashboard",
            "Pacientes (solo lectura)",
            "Reportes poblacionales (HU07)",
            "Reportes DIRESA (HU11)",
        ],
    ),
    "doctor": RolePermissions(
        role="doctor",
        label="Médico",
        modules=[
            "Dashboard",
            "Pacientes (solo lectura)",
            "Predicciones e historial",
            "Alertas clínicas",
            "Notificaciones",
        ],
    ),
    "nurse": RolePermissions(
        role="nurse",
        label="Enfermera",
        modules=[
            "Dashboard",
            "Pacientes",
            "Datos de triaje (datos clínicos, glucosa)",
            "Dispositivos IoT",
            "Alertas y notificaciones",
            "Citas",
        ],
    ),
    "nutritionist": RolePermissions(
        role="nutritionist",
        label="Nutricionista",
        modules=[
            "Planes alimentarios (nutrición)",
        ],
    ),
}


@router.get("/permissions", response_model=list[RolePermissions])
async def get_role_permissions(
    current_user: User = Depends(require_role(["admin"])),
):
    """Matriz de permisos por rol: se asignan automáticamente al crear la cuenta."""
    return list(ROLE_PERMISSIONS.values())


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Lista todo el personal registrado con su rol y estado."""
    result = await db.execute(select(User).order_by(User.id))
    return result.scalars().all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Registra la cuenta de un nuevo profesional y le asigna el rol seleccionado.

    HU12 Escenario 1: al crear la cuenta con el rol (Médico, Nutricionista,
    Enfermera, ...), el sistema asocia automáticamente los permisos de esa
    matriz (ver /api/users/permissions).
    """
    if user_data.role not in ROLE_PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rol desconocido: {user_data.role}",
        )

    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    user = User(
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza rol, nombre, contraseña o estado de una cuenta existente."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user_data.role is not None and user_data.role not in ROLE_PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rol desconocido: {user_data.role}",
        )

    # Protección: no permitir desactivarse ni degradarse a sí mismo
    if user.id == current_user.id:
        if user_data.role is not None and user_data.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes quitarte tu propio rol de administrador",
            )
        if user_data.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes desactivar tu propia cuenta",
            )

    update_data = user_data.model_dump(exclude_unset=True)
    if "password" in update_data:
        if update_data["password"]:
            user.hashed_password = get_password_hash(update_data.pop("password"))
        else:
            update_data.pop("password")
    for field, value in update_data.items():
        setattr(user, field, value)

    await db.flush()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_role(["admin"])),
    db: AsyncSession = Depends(get_db),
):
    """Desactiva una cuenta (baja lógica: se conserva por requisitos de auditoría)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta",
        )
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.is_active = False
    await db.flush()
