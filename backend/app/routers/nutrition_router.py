"""
Nutrition Router — Epic 04, HU10.

Endpoints para:
  • Crear un plan nutricional (solo nutricionista) — HU10 Escenario 1.
  • Listar planes (nutricionista, admin, nurse).
  • Obtener plan activo de un paciente.
  • Actualizar / desactivar un plan.
  • Evaluar adherencia tras 14 días — HU10 Escenario 2.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import User, Patient, NutritionPlan
from app.schemas import (
    NutritionPlanCreate,
    NutritionPlanUpdate,
    NutritionPlanResponse,
    NutritionAdherenceResponse,
)
from app.services.nutrition_service import NutritionService

router = APIRouter(prefix="/api/nutrition", tags=["Nutrition"])


def _to_response(plan: NutritionPlan) -> NutritionPlanResponse:
    """Construye el response incluyendo nombres de paciente y nutricionista."""
    return NutritionPlanResponse(
        id=plan.id,
        patient_id=plan.patient_id,
        nutritionist_id=plan.nutritionist_id,
        nutritionist_name=None,  # se rellena en el endpoint si hace falta
        patient_name=None,
        daily_calories=plan.daily_calories,
        protein_g=plan.protein_g,
        carbs_g=plan.carbs_g,
        fat_g=plan.fat_g,
        restrictions=plan.restrictions,
        meal_schedule=plan.meal_schedule,
        notes=plan.notes,
        is_active=plan.is_active,
        start_date=plan.start_date,
        end_date=plan.end_date,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


async def _enrich_with_names(db: AsyncSession, plan: NutritionPlan) -> NutritionPlanResponse:
    """Agrega patient_name y nutritionist_name al response."""
    resp = _to_response(plan)
    # patient
    patient = (await db.execute(select(Patient).where(Patient.id == plan.patient_id))).scalar_one_or_none()
    if patient:
        resp.patient_name = f"{patient.first_name} {patient.last_name}"
    # nutritionist
    if plan.nutritionist_id:
        n = (await db.execute(select(User).where(User.id == plan.nutritionist_id))).scalar_one_or_none()
        if n:
            resp.nutritionist_name = n.full_name
    return resp


# ── HU10 Escenario 1 — Creación de plan nutricional ────────────────────────

@router.post("/plans", response_model=NutritionPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_nutrition_plan(
    data: NutritionPlanCreate,
    current_user: User = Depends(require_role(["admin", "nutritionist"])),
    db: AsyncSession = Depends(get_db),
):
    """
    Crea un plan nutricional para un paciente con riesgo Medio o Alto.
    Solo el nutricionista (o admin) puede crear planes. El sistema programa
    notificaciones de recordatorio de comidas en la app móvil del paciente.
    """
    service = NutritionService(db)
    try:
        plan = await service.create_plan(
            patient_id=data.patient_id,
            daily_calories=data.daily_calories,
            protein_g=data.protein_g,
            carbs_g=data.carbs_g,
            fat_g=data.fat_g,
            restrictions=data.restrictions,
            meal_schedule=data.meal_schedule,
            notes=data.notes,
            nutritionist_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return await _enrich_with_names(db, plan)


@router.get("/plans", response_model=list[NutritionPlanResponse])
async def list_nutrition_plans(
    patient_id: int | None = None,
    active_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista planes nutricionales (opcionalmente por paciente o solo activos)."""
    service = NutritionService(db)
    plans = await service.list_plans(patient_id=patient_id, active_only=active_only)
    return [await _enrich_with_names(db, p) for p in plans]


@router.get("/plans/{plan_id}", response_model=NutritionPlanResponse)
async def get_nutrition_plan(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await service_get_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return await _enrich_with_names(db, plan)


async def service_get_plan(db: AsyncSession, plan_id: int):
    service = NutritionService(db)
    return await service.get_plan(plan_id)


@router.get("/patients/{patient_id}/active-plan", response_model=NutritionPlanResponse | None)
async def get_patient_active_plan(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve el plan nutricional activo del paciente, si existe."""
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    service = NutritionService(db)
    plan = await service.get_patient_active_plan(patient_id)
    if plan is None:
        return None
    return await _enrich_with_names(db, plan)


@router.put("/plans/{plan_id}", response_model=NutritionPlanResponse)
async def update_nutrition_plan(
    plan_id: int,
    data: NutritionPlanUpdate,
    current_user: User = Depends(require_role(["admin", "nutritionist"])),
    db: AsyncSession = Depends(get_db),
):
    service = NutritionService(db)
    plan = await service.update_plan(plan_id, **data.model_dump(exclude_unset=True))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return await _enrich_with_names(db, plan)


# ── HU10 Escenario 2 — Evaluación de adherencia ────────────────────────────

@router.get("/plans/{plan_id}/adherence", response_model=NutritionAdherenceResponse)
async def evaluate_plan_adherence(
    plan_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Evalúa la adherencia del paciente a su plan nutricional cruzando los
    datos de glucosa del sensor IoT con el plan asignado. Genera una
    recomendación de ajuste si el porcentaje de adherencia es menor al 60%.
    """
    service = NutritionService(db)
    try:
        result = await service.evaluate_adherence(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return NutritionAdherenceResponse(**result)
