"""
Router de reportes — Epic 05 (HU07, HU11).

Módulo de reportes del Centro de Salud, orientado al Jefe del Centro
(rol `health_manager`) y al administrador:

  HU07 — Dashboard de Monitoreo Poblacional
    GET /api/reports/population-summary        Resumen estadístico con rango de fechas
    GET /api/reports/population-summary/pdf    Exporta la lista de pacientes en riesgo a PDF

  HU11 — Generación de Reportes para Autoridades de Salud (DIRESA)
    GET /api/reports/monthly                   Reporte mensual con indicadores clave
    GET /api/reports/monthly/pdf               PDF con logotipo, gráfico de barras y tablas
"""

import io
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_role
from app.database import get_db
from app.models import User
from app.schemas import PopulationSummary, MonthlyReport
from app.services import report_service
from app.services.pdf_report_builder import build_monthly_pdf, build_population_pdf

router = APIRouter(prefix="/api/reports", tags=["Reports (HU07/HU11)"])

# El módulo de reportes es del Jefe del Centro de Salud y del administrador.
_REPORT_ROLES = ["admin", "health_manager"]


def _pdf_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── HU07: Dashboard de Monitoreo Poblacional ─────────────────────────────────

@router.get("/population-summary", response_model=PopulationSummary)
async def population_summary(
    date_from: date = Query(None, description="Inicio del rango de fechas (YYYY-MM-DD)"),
    date_to: date = Query(None, description="Fin del rango de fechas (YYYY-MM-DD)"),
    current_user: User = Depends(require_role(_REPORT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Resumen estadístico de los pacientes en riesgo de diabetes de la
    población (HU07 Escenario 1): distribución por nivel de riesgo para los
    gráficos de torta, análisis etario y lista exportable de pacientes."""
    return await report_service.compute_population_summary(
        db,
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
    )


@router.get("/population-summary/pdf")
async def population_summary_pdf(
    date_from: date = Query(None, description="Inicio del rango de fechas (YYYY-MM-DD)"),
    date_to: date = Query(None, description="Fin del rango de fechas (YYYY-MM-DD)"),
    current_user: User = Depends(require_role(_REPORT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Exporta el resumen poblacional con la lista de pacientes en riesgo en
    formato PDF (HU07: 'permite exportar la lista en formato PDF')."""
    summary = await report_service.compute_population_summary(
        db,
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
    )
    pdf_bytes = build_population_pdf(
        summary, generated_by=f"{current_user.full_name} ({current_user.username})"
    )
    filename = (
        f"monitoreo_poblacional_{summary['period']['date_from'].isoformat()[:10]}_"
        f"{summary['period']['date_to'].isoformat()[:10]}.pdf"
    )
    return _pdf_response(pdf_bytes, filename)


# ── HU11: Reportes para Autoridades de Salud ────────────────────────────────

@router.get("/monthly", response_model=MonthlyReport)
async def monthly_report(
    year: int = Query(None, description="Año del reporte mensual (por defecto, el actual)"),
    month: int = Query(None, ge=1, le=12, description="Mes del reporte (1-12)"),
    date_from: date = Query(None, description="Filtro: inicio del rango de fechas personalizado"),
    date_to: date = Query(None, description="Filtro: fin del rango de fechas personalizado"),
    age_min: int = Query(None, ge=0, le=120, description="Filtro: edad mínima (p. ej. 40)"),
    age_max: int = Query(None, ge=0, le=120, description="Filtro: edad máxima (p. ej. 60)"),
    current_user: User = Depends(require_role(_REPORT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Genera el reporte mensual con indicadores clave de prevención (HU11
    Escenario 1): pacientes evaluados, distribución por nivel de riesgo,
    tasa de predicciones acertadas y lista de pacientes críticos.

    Admite filtros personalizados de grupo etario y rango de fechas
    (HU11 Escenario 2). El tiempo de generación se devuelve en
    `generation_seconds` (requisito: < 10 segundos)."""
    return await report_service.compute_monthly_report(
        db,
        year=year,
        month=month,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        age_min=age_min,
        age_max=age_max,
    )


@router.get("/monthly/pdf")
async def monthly_report_pdf(
    year: int = Query(None, description="Año del reporte mensual"),
    month: int = Query(None, ge=1, le=12, description="Mes del reporte (1-12)"),
    date_from: date = Query(None, description="Filtro: inicio del rango de fechas"),
    date_to: date = Query(None, description="Filtro: fin del rango de fechas"),
    age_min: int = Query(None, ge=0, le=120, description="Filtro: edad mínima"),
    age_max: int = Query(None, ge=0, le=120, description="Filtro: edad máxima"),
    current_user: User = Depends(require_role(_REPORT_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    """Exporta el reporte mensual en formato PDF con el logotipo del Centro
    de Salud, gráfico de barras por grupo etario y tablas resumen, listo
    para su envío a la DIRESA (HU11 Escenario 1)."""
    report = await report_service.compute_monthly_report(
        db,
        year=year,
        month=month,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        age_min=age_min,
        age_max=age_max,
    )
    pdf_bytes = build_monthly_pdf(
        report, generated_by=f"{current_user.full_name} ({current_user.username})"
    )
    period_tag = report["period"]["date_from"].strftime("%Y%m%d")
    suffix = ""
    if age_min is not None or age_max is not None:
        suffix = f"_edad_{age_min or 0}-{age_max or 120}"
    filename = f"reporte_mensual_DIRESA_{period_tag}{suffix}.pdf"
    return _pdf_response(pdf_bytes, filename)
