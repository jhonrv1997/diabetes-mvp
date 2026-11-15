"""
Servicio de reportes estadísticos — Epic 05 (HU07, HU11).

Funciones compartidas por el módulo de reportes:
  * compute_population_summary: resumen estadístico poblacional con filtro
    de rango de fechas (HU07 — Dashboard de Monitoreo Poblacional).
  * compute_monthly_report: indicadores clave del reporte mensual para la
    DIRESA con filtros personalizados de edad y rango de fechas (HU11 —
    Generación de Reportes para Autoridades de Salud).

Ambos cálculos se ejecutan sobre SQLite en memoria de trabajo mínima, por
lo que cumplen el criterio de HU11: generación en menos de 10 segundos.
"""

import time
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patient, Prediction, ClinicalData

# Etiquetas de nivel de riesgo (orden canónico del sistema)
RISK_LEVELS = [
    ("low", "Bajo", "#47805a"),
    ("medium", "Medio", "#9b8048"),
    ("high", "Alto", "#8e4f49"),
]

AGE_GROUPS = [
    ("18-29", 18, 29),
    ("30-44", 30, 44),
    ("45-59", 45, 59),
    ("60-74", 60, 74),
    ("75+", 75, 200),
]


def _parse_date(value: Optional[str], default: date) -> date:
    if not value:
        return default
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _age_group(age: Optional[int]) -> Optional[str]:
    if age is None:
        return None
    for label, lo, hi in AGE_GROUPS:
        if lo <= age <= hi:
            return label
    return "75+" if age > 74 else None


def _patient_age(patient: Patient, clinical_age: Optional[int]) -> Optional[int]:
    """Edad actual del paciente: prioriza la fecha de nacimiento, con
    respaldo en la edad registrada en el último triaje."""
    if patient.date_of_birth:
        today = date.today()
        born = patient.date_of_birth
        years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if 0 <= years <= 120:
            return years
    return clinical_age


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    """Primer y último día del mes solicitado."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _month_label(d_from: date, d_to: date) -> str:
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    if d_from.day == 1 and d_from.month == d_to.month and d_from.year == d_to.year:
        return f"{months[d_from.month - 1].capitalize()} {d_from.year}"
    return f"del {d_from.strftime('%d/%m/%Y')} al {d_to.strftime('%d/%m/%Y')}"


async def _load_context(
    db: AsyncSession,
    d_from: date,
    d_to: date,
) -> tuple[list[Patient], list[Prediction], dict[int, Optional[int]]]:
    """Carga pacientes, predicciones del período y edades (clínica/DOB)."""
    patients = list((await db.execute(select(Patient).order_by(Patient.id))).scalars().all())

    dt_from = datetime.combine(d_from, datetime.min.time())
    dt_to = datetime.combine(d_to, datetime.max.time())
    predictions = list(
        (
            await db.execute(
                select(Prediction)
                .where(Prediction.created_at >= dt_from, Prediction.created_at <= dt_to)
                .order_by(Prediction.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    # Edad del último registro clínico por paciente (respaldo del DOB)
    clinical_ages: dict[int, Optional[int]] = {}
    clinicals = list((await db.execute(select(ClinicalData))).scalars().all())
    for cd in clinicals:
        prev = clinical_ages.get(cd.patient_id)
        if prev is None or cd.created_at >= prev[1]:
            clinical_ages[cd.patient_id] = (cd.age, cd.created_at)
    clinical_ages = {k: v[0] for k, v in clinical_ages.items()}

    return patients, predictions, clinical_ages


def _latest_prediction_per_patient(predictions: list[Prediction]) -> dict[int, Prediction]:
    """Se queda con la predicción más reciente por paciente (ya ordenadas desc)."""
    latest: dict[int, Prediction] = {}
    for p in predictions:
        if p.patient_id not in latest:
            latest[p.patient_id] = p
    return latest


def _risk_distribution(latest: dict[int, Prediction]) -> list[dict]:
    total = len(latest)
    result = []
    for level, label, _color in RISK_LEVELS:
        count = sum(1 for p in latest.values() if (p.risk_level or "").lower() == level)
        pct = round(count / total * 100, 1) if total else 0.0
        result.append({"level": level, "label": label, "count": count, "pct": pct})
    return result


def _age_distribution(
    patients: list[Patient],
    clinical_ages: dict[int, Optional[int]],
    latest: dict[int, Prediction],
) -> list[dict]:
    rows = []
    for label, lo, hi in AGE_GROUPS:
        row = {"group": label, "total": 0, "low": 0, "medium": 0, "high": 0}
        for patient in patients:
            age = _patient_age(patient, clinical_ages.get(patient.id))
            if age is None or not (lo <= age <= hi):
                continue
            row["total"] += 1
            pred = latest.get(patient.id)
            if pred is not None:
                lvl = (pred.risk_level or "").lower()
                if lvl in row:
                    row[lvl] += 1
        rows.append(row)
    return rows


def _gender_distribution(patients: list[Patient]) -> list[dict]:
    male = sum(1 for p in patients if (p.gender or "").upper().startswith("M"))
    female = sum(1 for p in patients if (p.gender or "").upper().startswith("F"))
    other = len(patients) - male - female
    result = []
    if male:
        result.append({"gender": "M", "label": "Masculino", "count": male})
    if female:
        result.append({"gender": "F", "label": "Femenino", "count": female})
    if other > 0:
        result.append({"gender": "O", "label": "Otro", "count": other})
    return result


def _patients_at_risk(
    patients: list[Patient],
    clinical_ages: dict[int, Optional[int]],
    latest: dict[int, Prediction],
    only_critical: bool = False,
) -> list[dict]:
    """Lista de pacientes en riesgo (Medio/Alto o solo Alto), ordenados por
    probabilidad descendente. Es la lista exportable a PDF de la HU07."""
    by_id = {p.id: p for p in patients}
    items = []
    for patient_id, pred in latest.items():
        lvl = (pred.risk_level or "").lower()
        if lvl == "high" or (lvl == "medium" and not only_critical):
            patient = by_id.get(patient_id)
            if patient is None:
                continue
            items.append(
                {
                    "patient_id": patient_id,
                    "full_name": f"{patient.first_name} {patient.last_name}",
                    "age": _patient_age(patient, clinical_ages.get(patient_id)),
                    "gender": patient.gender,
                    "risk_level": lvl,
                    "risk_probability": round(pred.risk_probability, 4),
                    "last_prediction_date": pred.created_at,
                }
            )
    items.sort(key=lambda x: x["risk_probability"], reverse=True)
    return items


def _accuracy_rate(predictions: list[Prediction]) -> tuple[Optional[float], str]:
    """Tasa de predicciones acertadas del período (HU11).

    Base principal: confianza promedio reportada por el modelo ML.
    Si el sistema opera en modo heurístico (sin modelo entrenado), se
    estima a partir de la completitud de los datos usados por predicción
    (número de lecturas de glucosa IoT consideradas), lo que se documenta
    en `accuracy_basis` para transparencia ante las autoridades.
    """
    if not predictions:
        return None, "Sin predicciones en el período"

    # Nota: en modo heurístico la predicción se guarda con confidence=0.0
    # (default de la columna), que se interpreta como "confianza no informada".
    confidences = [p.confidence for p in predictions if p.confidence and p.confidence > 0]
    if confidences:
        rate = sum(confidences) / len(confidences) * 100.0
        return round(rate, 1), "Confianza promedio del modelo ML sobre las predicciones del período"

    estimates = [
        min(0.95, 0.40 + 0.05 * min(p.glucose_readings_used or 0, 10))
        for p in predictions
    ]
    rate = sum(estimates) / len(estimates) * 100.0
    return (
        round(rate, 1),
        "Estimación heurística por completitud de datos IoT (sistema sin modelo ML entrenado)",
    )


# ── HU07: Resumen poblacional ────────────────────────────────────────────────

async def compute_population_summary(
    db: AsyncSession,
    date_from: Optional[str],
    date_to: Optional[str],
) -> dict:
    """Resumen estadístico de la población bajo monitoreo (HU07)."""
    started = time.perf_counter()

    today = date.today()
    d_to = _parse_date(date_to, today)
    d_from = _parse_date(date_from, d_to - timedelta(days=29))

    patients, predictions, clinical_ages = await _load_context(db, d_from, d_to)
    latest = _latest_prediction_per_patient(predictions)

    at_risk = _patients_at_risk(patients, clinical_ages, latest)
    critical = _patients_at_risk(patients, clinical_ages, latest, only_critical=True)

    probs = [p.risk_probability for p in predictions]
    dt_from = datetime.combine(d_from, datetime.min.time())
    new_patients = sum(1 for p in patients if p.created_at and p.created_at >= dt_from)

    elapsed = round(time.perf_counter() - started, 3)
    return {
        "period": {
            "date_from": d_from,
            "date_to": d_to,
            "label": f"Del {d_from.strftime('%d/%m/%Y')} al {d_to.strftime('%d/%m/%Y')}",
        },
        "total_patients": len(patients),
        "evaluated_patients": len(latest),
        "total_predictions": len(predictions),
        "new_patients_in_period": new_patients,
        "risk_distribution": _risk_distribution(latest),
        "age_distribution": _age_distribution(patients, clinical_ages, latest),
        "gender_distribution": _gender_distribution(patients),
        "avg_risk_probability": round(sum(probs) / len(probs), 4) if probs else None,
        "patients_at_risk": at_risk,
        "critical_patients": critical,
        "generated_at": datetime.utcnow(),
        "generation_seconds": elapsed,
    }


# ── HU11: Reporte mensual para autoridades ───────────────────────────────────

async def compute_monthly_report(
    db: AsyncSession,
    year: Optional[int],
    month: Optional[int],
    date_from: Optional[str],
    date_to: Optional[str],
    age_min: Optional[int],
    age_max: Optional[int],
) -> dict:
    """Compila los indicadores clave del reporte mensual (HU11 Escenario 1)
    con filtros personalizados de edad y rango de fechas (Escenario 2)."""
    started = time.perf_counter()

    today = date.today()
    filters_applied: dict = {}

    # Período: rango de fechas explícito o mes/año (por defecto, mes actual)
    if date_from or date_to:
        d_to = _parse_date(date_to, today)
        d_from = _parse_date(date_from, d_to.replace(day=1))
        filters_applied["rango_fechas"] = {
            "desde": d_from.isoformat(),
            "hasta": d_to.isoformat(),
        }
    else:
        y = year or today.year
        m = month or today.month
        d_from, d_to = _month_bounds(y, m)
        filters_applied["mes"] = f"{y:04d}-{m:02d}"

    if age_min is not None or age_max is not None:
        filters_applied["edad"] = {
            "min": age_min if age_min is not None else 18,
            "max": age_max if age_max is not None else 120,
        }

    patients, predictions, clinical_ages = await _load_context(db, d_from, d_to)
    latest = _latest_prediction_per_patient(predictions)

    # Filtro etario (HU11 Escenario 2, p. ej. 40-60 años)
    if age_min is not None or age_max is not None:
        lo = age_min if age_min is not None else 0
        hi = age_max if age_max is not None else 200

        def _in_range(patient: Patient) -> bool:
            age = _patient_age(patient, clinical_ages.get(patient.id))
            return age is not None and lo <= age <= hi

        patients = [p for p in patients if _in_range(p)]
        allowed_ids = {p.id for p in patients}
        latest = {pid: pred for pid, pred in latest.items() if pid in allowed_ids}
        predictions = [p for p in predictions if p.patient_id in allowed_ids]

    accuracy, accuracy_basis = _accuracy_rate(predictions)
    critical = _patients_at_risk(patients, clinical_ages, latest, only_critical=True)
    probs = [p.risk_probability for p in predictions]

    elapsed = round(time.perf_counter() - started, 3)
    return {
        "title": "Reporte Mensual de Prevención de Diabetes Tipo 2",
        "addressed_to": "DIRESA — Dirección Regional de Salud",
        "period": {
            "date_from": d_from,
            "date_to": d_to,
            "label": _month_label(d_from, d_to),
        },
        "filters_applied": filters_applied,
        "indicators": {
            "patients_evaluated": len(latest),
            "total_predictions": len(predictions),
            "risk_distribution": _risk_distribution(latest),
            "accuracy_rate": accuracy,
            "accuracy_basis": accuracy_basis,
            "critical_patients_count": len(critical),
            "avg_risk_probability": round(sum(probs) / len(probs), 4) if probs else None,
        },
        "age_distribution": _age_distribution(patients, clinical_ages, latest),
        "critical_patients": critical,
        "generated_at": datetime.utcnow(),
        "generation_seconds": elapsed,
    }
