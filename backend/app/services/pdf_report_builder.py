"""
Generador de PDFs institucionales — Epic 05 (HU07, HU11).

Construye los documentos PDF del Centro de Salud con ReportLab:
  * build_population_pdf: lista de pacientes en riesgo + gráfico de torta
    de la distribución por nivel de riesgo (HU07 — exportación a PDF).
  * build_monthly_pdf: reporte mensual para la DIRESA con logotipo,
    indicadores clave, gráfico de barras por grupo etario y tablas resumen
    (HU11 — Escenarios 1 y 2).

Ambos documentos incluyen el logotipo oficial del Centro de Salud
(app/assets/logo_centro_salud.png) y pie de página con fecha/hora de
generación y usuario responsable.
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import os

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "logo_centro_salud.png")

# Paleta institucional
DARK_BLUE = HexColor("#2c5282")
MID_BLUE = HexColor("#3a91ff")
LIGHT_BLUE = HexColor("#d1e6ff")
GREY_TEXT = HexColor("#4a5568")

RISK_COLORS = {
    "low": HexColor("#47805a"),
    "medium": HexColor("#9b8048"),
    "high": HexColor("#8e4f49"),
}

RISK_LABELS = {"low": "Bajo", "medium": "Medio", "high": "Alto"}

PAGE_W, PAGE_H = A4


# ── Estilos ───────────────────────────────────────────────────────────────────

def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "RptTitle", parent=base["Title"], fontSize=16, textColor=DARK_BLUE,
            spaceAfter=2, alignment=1,
        ),
        "subtitle": ParagraphStyle(
            "RptSubtitle", parent=base["Normal"], fontSize=10, textColor=GREY_TEXT,
            alignment=1,
        ),
        "h2": ParagraphStyle(
            "RptH2", parent=base["Heading2"], fontSize=12, textColor=DARK_BLUE,
            spaceBefore=10, spaceAfter=6,
        ),
        "normal": ParagraphStyle(
            "RptNormal", parent=base["Normal"], fontSize=9.5, textColor=GREY_TEXT, leading=13,
        ),
        "small": ParagraphStyle(
            "RptSmall", parent=base["Normal"], fontSize=8, textColor=GREY_TEXT,
        ),
        "kpi_value": ParagraphStyle(
            "KpiValue", parent=base["Normal"], fontSize=17, textColor=DARK_BLUE,
            alignment=1, leading=20,
        ),
        "kpi_label": ParagraphStyle(
            "KpiLabel", parent=base["Normal"], fontSize=7.5, textColor=colors.white,
            alignment=1, leading=9,
        ),
    }


# ── Encabezado / pie de página ────────────────────────────────────────────────

def _header_footer(canv, doc, generated_by: str = ""):
    canv.saveState()

    # Encabezado con logotipo del Centro de Salud
    if os.path.exists(LOGO_PATH):
        canv.drawImage(LOGO_PATH, 15 * mm, PAGE_H - 24 * mm, width=14 * mm, height=14 * mm,
                       mask="auto", preserveAspectRatio=True)
    canv.setFillColor(DARK_BLUE)
    canv.setFont("Helvetica-Bold", 12)
    canv.drawString(33 * mm, PAGE_H - 15 * mm, "CENTRO DE SALUD")
    canv.setFont("Helvetica", 8)
    canv.setFillColor(GREY_TEXT)
    canv.drawString(33 * mm, PAGE_H - 19.5 * mm, "Sistema de Detección Temprana de Diabetes Tipo 2")
    canv.drawString(33 * mm, PAGE_H - 23.5 * mm, "Monitoreo IoT y Predicción de Riesgo")

    canv.setStrokeColor(DARK_BLUE)
    canv.setLineWidth(1.2)
    canv.line(15 * mm, PAGE_H - 27 * mm, PAGE_W - 15 * mm, PAGE_H - 27 * mm)

    # Pie de página
    canv.setStrokeColor(colors.HexColor("#cbd5e0"))
    canv.setLineWidth(0.6)
    canv.line(15 * mm, 14 * mm, PAGE_W - 15 * mm, 14 * mm)
    canv.setFont("Helvetica", 7.5)
    canv.setFillColor(GREY_TEXT)
    now = datetime.utcnow().strftime("%d/%m/%Y %H:%M")
    canv.drawString(15 * mm, 10 * mm, f"Generado: {now} UTC{(' — ' + generated_by) if generated_by else ''}")
    canv.drawRightString(PAGE_W - 15 * mm, 10 * mm, f"Página {canv.getPageNumber()}")
    canv.restoreState()


# ── Componentes reutilizables ────────────────────────────────────────────────

def _kpi_cards(kpis: list[tuple[str, str]], styles) -> Table:
    """Fila de tarjetas de indicadores (valor + etiqueta)."""
    cells = []
    for label, value in kpis:
        inner = Table(
            [[Paragraph(value, styles["kpi_value"])], [Paragraph(label.upper(), styles["kpi_label"])]],
            colWidths=[42 * mm],
        )
        inner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), LIGHT_BLUE),
            ("BACKGROUND", (0, 1), (0, 1), DARK_BLUE),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        cells.append(inner)
    table = Table([cells], colWidths=[44 * mm] * len(kpis))
    table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _pie_chart(risk_distribution: list[dict], width=150, height=130) -> Drawing:
    """Gráfico de torta: distribución de pacientes por nivel de riesgo (HU07)."""
    drawing = Drawing(width, height)
    pie = Pie()
    pie.x = width / 2
    pie.y = height / 2 - 5
    pie.xradius = 46
    pie.yradius = 46
    pie.data = [item["count"] for item in risk_distribution]
    pie.labels = [
        f"{item['label']} ({item['count']} — {item['pct']:.1f}%)" for item in risk_distribution
    ]
    for i, item in enumerate(risk_distribution):
        pie.slices[i].fillColor = RISK_COLORS.get(item["level"], MID_BLUE)
        pie.slices[i].strokeColor = colors.white
        pie.slices[i].strokeWidth = 1.5
    pie.sideLabels = True
    pie.sideLabelsOffset = 0.2
    pie.checkLabelOverlap = True
    drawing.add(pie)

    # Título del gráfico
    title = String(width / 2, height - 8, "Distribución por nivel de riesgo",
                   fontName="Helvetica-Bold", fontSize=8.5, fillColor=DARK_BLUE, textAnchor="middle")
    drawing.add(title)
    return drawing


def _bar_chart(age_distribution: list[dict], width=440, height=170) -> Drawing:
    """Gráfico de barras: pacientes por grupo etario y nivel de riesgo (HU11)."""
    drawing = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x = 45
    chart.y = 22
    chart.width = width - 60
    chart.height = height - 55
    chart.data = [
        [row["low"] for row in age_distribution],
        [row["medium"] for row in age_distribution],
        [row["high"] for row in age_distribution],
    ]
    chart.categoryAxis.categoryNames = [row["group"] for row in age_distribution]
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(1, max(max(s) for s in chart.data if s) if any(any(x > 0 for x in s) for s in chart.data) else 1)
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.valueStep = max(1, int(chart.valueAxis.valueMax / 5) or 1)
    for i, level in enumerate(("low", "medium", "high")):
        chart.bars[i].fillColor = RISK_COLORS[level]
        chart.bars[i].strokeColor = colors.white
    chart.barWidth = 9
    chart.groupSpacing = 8
    drawing.add(chart)

    # Título y leyenda manual
    drawing.add(String(width / 2, height - 12, "Pacientes evaluados por grupo etario y nivel de riesgo",
                        fontName="Helvetica-Bold", fontSize=8.5, fillColor=DARK_BLUE, textAnchor="middle"))
    legend_x = width / 2 - 66
    for i, level in enumerate(("low", "medium", "high")):
        lx = legend_x + i * 48
        drawing.add(Rect(lx, height - 26, 8, 8, fillColor=RISK_COLORS[level], strokeColor=None))
        drawing.add(String(lx + 11, height - 24.5, RISK_LABELS[level],
                            fontName="Helvetica", fontSize=7.5, fillColor=GREY_TEXT))
    return drawing


def _data_table(header: list[str], rows: list[list], col_widths=None, styles=None) -> Table:
    """Tabla institucional con encabezado azul."""
    table = Table([header] + rows, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), GREY_TEXT),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HexColor("#f1f5f9")]),
    ]
    table.setStyle(TableStyle(style))
    return table


def _build_pdf(story, generated_by: str = "") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=32 * mm, bottomMargin=20 * mm,
        title="Centro de Salud — Reporte",
    )

    def _hf(canv, d):
        _header_footer(canv, d, generated_by)

    doc.build(story, onFirstPage=_hf, onLaterPages=_hf)
    return buffer.getvalue()


# ── HU07: PDF del resumen poblacional ────────────────────────────────────────

def build_population_pdf(summary: dict, generated_by: str = "") -> bytes:
    """PDF del Dashboard de Monitoreo Poblacional (HU07): gráfico de torta
    y lista de pacientes en riesgo exportable."""
    st = _styles()
    story = []

    story.append(Paragraph("Dashboard de Monitoreo Poblacional", st["title"]))
    story.append(Paragraph(f"Período: {summary['period']['label']}", st["subtitle"]))
    story.append(Spacer(1, 8))

    story.append(_kpi_cards([
        ("Total de pacientes", str(summary["total_patients"])),
        ("Pacientes evaluados", str(summary["evaluated_patients"])),
        ("En riesgo (Medio/Alto)", str(len(summary["patients_at_risk"]))),
        ("Pacientes críticos (Alto)", str(len(summary["critical_patients"]))),
    ], st))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Distribución de pacientes por nivel de riesgo", st["h2"]))
    story.append(_pie_chart(summary["risk_distribution"]))
    story.append(Spacer(1, 6))

    if summary["patients_at_risk"]:
        story.append(Paragraph("Lista de pacientes en riesgo", st["h2"]))
        rows = []
        for i, p in enumerate(summary["patients_at_risk"], start=1):
            rows.append([
                str(i),
                p["full_name"],
                str(p["age"] if p["age"] is not None else "-"),
                (p["gender"] or "-").upper(),
                RISK_LABELS.get(p["risk_level"], p["risk_level"]),
                f"{p['risk_probability'] * 100:.1f}%",
                p["last_prediction_date"].strftime("%d/%m/%Y") if hasattr(p["last_prediction_date"], "strftime") else str(p["last_prediction_date"]),
            ])
        story.append(_data_table(
            ["#", "Paciente", "Edad", "Sexo", "Nivel de riesgo", "Probabilidad", "Última predicción"],
            rows,
            col_widths=[8 * mm, 52 * mm, 12 * mm, 12 * mm, 25 * mm, 24 * mm, 27 * mm],
        ))
    else:
        story.append(Paragraph(
            "No se registraron pacientes en riesgo durante el período seleccionado.",
            st["normal"],
        ))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Documento generado automáticamente por el sistema para la toma de decisiones "
        "de salud pública y campañas preventivas focalizadas.",
        st["small"],
    ))
    return _build_pdf(story, generated_by)


# ── HU11: PDF del reporte mensual para la DIRESA ─────────────────────────────

def build_monthly_pdf(report: dict, generated_by: str = "") -> bytes:
    """PDF del reporte mensual con logotipo del Centro de Salud (HU11):
    indicadores clave, gráfico de barras por grupo etario y pacientes críticos."""
    st = _styles()
    ind = report["indicators"]
    story = []

    story.append(Paragraph(report["title"], st["title"]))
    story.append(Paragraph(f"Período: {report['period']['label']}", st["subtitle"]))
    story.append(Paragraph(f"Dirigido a: {report['addressed_to']}", st["subtitle"]))
    story.append(Spacer(1, 8))

    # Indicadores clave (HU11 Escenario 1)
    story.append(Paragraph("Indicadores clave de prevención", st["h2"]))
    story.append(_kpi_cards([
        ("Pacientes evaluados", str(ind["patients_evaluated"])),
        ("Predicciones realizadas", str(ind["total_predictions"])),
        ("Tasa de aciertos", f"{ind['accuracy_rate']:.1f}%" if ind["accuracy_rate"] is not None else "N/D"),
        ("Pacientes críticos", str(ind["critical_patients_count"])),
    ], st))
    story.append(Spacer(1, 8))

    acc = ind["accuracy_rate"]
    basis = ind["accuracy_basis"]
    if acc is not None:
        story.append(Paragraph(f"Tasa de predicciones acertadas: <b>{acc:.1f}%</b> — {basis}", st["small"]))
    story.append(Spacer(1, 6))

    # Distribución por nivel de riesgo
    story.append(Paragraph("Distribución por nivel de riesgo", st["h2"]))
    rows = [
        [
            RISK_LABELS.get(item["level"], item["level"]),
            str(item["count"]),
            f"{item['pct']:.1f}%",
        ]
        for item in ind["risk_distribution"]
    ]
    story.append(_data_table(
        ["Nivel de riesgo", "Pacientes", "Porcentaje"],
        rows,
        col_widths=[60 * mm, 45 * mm, 45 * mm],
    ))
    story.append(Spacer(1, 10))

    # Gráfico de barras por grupo etario (HU11 Escenario 2)
    story.append(Paragraph("Análisis por grupo etario", st["h2"]))
    story.append(_bar_chart(report["age_distribution"]))
    story.append(Spacer(1, 4))

    age_rows = [
        [row["group"], str(row["total"]), str(row["low"]), str(row["medium"]), str(row["high"])]
        for row in report["age_distribution"]
    ]
    story.append(_data_table(
        ["Grupo etario", "Pacientes", "Riesgo Bajo", "Riesgo Medio", "Riesgo Alto"],
        age_rows,
        col_widths=[34 * mm, 28 * mm, 30 * mm, 30 * mm, 30 * mm],
    ))

    # Filtros aplicados (HU11 Escenario 2)
    if report.get("filters_applied"):
        filters = report["filters_applied"]
        parts = []
        if "rango_fechas" in filters:
            parts.append(
                f"rango de fechas {filters['rango_fechas']['desde']} a {filters['rango_fechas']['hasta']}"
            )
        if "mes" in filters:
            parts.append(f"mes {filters['mes']}")
        if "edad" in filters:
            parts.append(f"edad {filters['edad']['min']}-{filters['edad']['max']} años")
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Filtros aplicados: {', '.join(parts)}.", st["small"]))

    story.append(PageBreak())

    # Lista de pacientes críticos (HU11 Escenario 1)
    story.append(Paragraph("Lista de pacientes críticos (riesgo Alto)", st["h2"]))
    if report["critical_patients"]:
        rows = []
        for i, p in enumerate(report["critical_patients"], start=1):
            rows.append([
                str(i),
                p["full_name"],
                str(p["age"] if p["age"] is not None else "-"),
                (p["gender"] or "-").upper(),
                f"{p['risk_probability'] * 100:.1f}%",
                p["last_prediction_date"].strftime("%d/%m/%Y") if hasattr(p["last_prediction_date"], "strftime") else str(p["last_prediction_date"]),
            ])
        story.append(_data_table(
            ["#", "Paciente", "Edad", "Sexo", "Probabilidad", "Última predicción"],
            rows,
            col_widths=[10 * mm, 62 * mm, 16 * mm, 16 * mm, 30 * mm, 30 * mm],
        ))
    else:
        story.append(Paragraph(
            "No se registraron pacientes críticos durante el período del reporte.",
            st["normal"],
        ))

    # Área de firma para la rendición de cuentas
    story.append(Spacer(1, 42))
    sign = Table(
        [["_________________________", "_________________________"],
         ["Jefe del Centro de Salud", "Sello institucional"]],
        colWidths=[80 * mm, 80 * mm],
    )
    sign.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, 1), 8.5),
        ("TEXTCOLOR", (0, 1), (-1, 1), GREY_TEXT),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
    ]))
    sign_row = Table([[sign]], colWidths=[170 * mm])
    sign_row.setStyle(TableStyle([("ALIGN", (0, 0), (0, 0), "CENTER")]))
    story.append(sign_row)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Reporte generado automáticamente para la rendición de cuentas ante la DIRESA "
        "y la asignación de recursos sanitarios a la región.",
        st["small"],
    ))
    return _build_pdf(story, generated_by)
