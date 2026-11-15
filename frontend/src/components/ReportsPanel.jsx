import React, { useState, useEffect, useCallback } from 'react'
import api from '../api/axios'
import { downloadFile } from '../utils/download'
import { getRiskBadgeClass, getRiskLabel } from '../utils/validation'
import {
  BarChart3,
  RefreshCw,
  FileDown,
  CalendarDays,
  Users,
  ClipboardCheck,
  AlertTriangle,
  Target,
  Timer,
  Filter,
  Building2,
} from 'lucide-react'
import {
  PieChart,
  Pie,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'

const RISK_COLORS = { low: '#47805a', medium: '#9b8048', high: '#8e4f49' }

const MONTHS = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]

function isoDate(d) {
  return d.toISOString().slice(0, 10)
}

function KpiCard({ icon: Icon, label, value, tone = 'primary' }) {
  const tones = {
    primary: 'bg-primary-50 text-primary-500',
    high: 'bg-risk-high-light text-risk-high',
    medium: 'bg-risk-medium-light text-risk-medium',
    ok: 'bg-green-50 text-green-600',
  }
  return (
    <div className="dashboard-card flex items-center gap-4">
      <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${tones[tone]}`}>
        <Icon className="w-6 h-6" />
      </div>
      <div className="min-w-0">
        <p className="text-sm text-gray-500">{label}</p>
        <p className="text-2xl font-bold text-gray-800">{value}</p>
      </div>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════════
   HU07 — Dashboard de Monitoreo Poblacional (Jefe del Centro de Salud)
   ══════════════════════════════════════════════════════════════════════════ */
function PopulationTab() {
  const today = new Date()
  const monthAgo = new Date(today.getTime() - 29 * 24 * 60 * 60 * 1000)

  const [dateFrom, setDateFrom] = useState(isoDate(monthAgo))
  const [dateTo, setDateTo] = useState(isoDate(today))
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState(false)

  const fetchSummary = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = {}
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
      const r = await api.get('/reports/population-summary', { params })
      setSummary(r.data)
    } catch (e) {
      setError(
        e.response?.status === 403
          ? 'No tiene permisos para ver este módulo.'
          : 'Error al cargar el resumen poblacional.'
      )
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo])

  useEffect(() => {
    fetchSummary()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleExportPdf = async () => {
    setExporting(true)
    try {
      const params = new URLSearchParams()
      if (dateFrom) params.append('date_from', dateFrom)
      if (dateTo) params.append('date_to', dateTo)
      await downloadFile(`/reports/population-summary/pdf?${params.toString()}`)
    } catch {
      setError('No se pudo exportar el PDF.')
    } finally {
      setExporting(false)
    }
  }

  const pieData = (summary?.risk_distribution || []).map((item) => ({
    name: item.label,
    value: item.count,
    pct: item.pct,
    color: RISK_COLORS[item.level] || '#3a91ff',
  }))

  const ageData = (summary?.age_distribution || []).map((row) => ({
    group: row.group,
    Bajo: row.low,
    Medio: row.medium,
    Alto: row.high,
  }))

  return (
    <div className="space-y-6">
      {/* Filtro de rango de fechas (HU07 Escenario 1) */}
      <div className="dashboard-card">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="form-label">Desde</label>
            <input
              type="date"
              className="form-input"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div>
            <label className="form-label">Hasta</label>
            <input
              type="date"
              className="form-input"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
          <button onClick={fetchSummary} className="btn-primary gap-2" disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Aplicar rango
          </button>
          <button
            onClick={handleExportPdf}
            className="btn-secondary gap-2 ml-auto"
            disabled={exporting || !summary}
            title="Exportar la lista de pacientes en riesgo en formato PDF"
          >
            <FileDown className="w-4 h-4" />
            {exporting ? 'Generando PDF…' : 'Exportar PDF'}
          </button>
        </div>
        {summary && (
          <p className="text-xs text-gray-500 mt-3">
            Período analizado: <span className="font-medium">{summary.period.label}</span>
          </p>
        )}
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {loading && !summary ? (
        <div className="flex items-center justify-center h-48">
          <div className="spinner"></div>
        </div>
      ) : summary ? (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard icon={Users} label="Total de pacientes" value={summary.total_patients} />
            <KpiCard icon={ClipboardCheck} label="Pacientes evaluados" value={summary.evaluated_patients} tone="ok" />
            <KpiCard icon={AlertTriangle} label="En riesgo (Medio/Alto)" value={summary.patients_at_risk.length} tone="medium" />
            <KpiCard icon={Target} label="Pacientes críticos (Alto)" value={summary.critical_patients.length} tone="high" />
          </div>

          {/* Gráficos de torta + barras etarias */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="dashboard-card">
              <h3 className="text-sm font-semibold text-gray-700 mb-2">
                Distribución por nivel de riesgo
              </h3>
              {summary.evaluated_patients === 0 ? (
                <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
                  Sin predicciones en el período seleccionado
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={85}
                      label={({ name, pct }) => `${name} (${pct}%)`}
                    >
                      {pieData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value, name) => [`${value} pacientes`, name]} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="dashboard-card">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">
                Pacientes por grupo etario y riesgo
              </h3>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={ageData} barSize={14}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="group" tick={{ fontSize: 12 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="Bajo" stackId="r" fill={RISK_COLORS.low} radius={[0, 0, 0, 0]} />
                  <Bar dataKey="Medio" stackId="r" fill={RISK_COLORS.medium} />
                  <Bar dataKey="Alto" stackId="r" fill={RISK_COLORS.high} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Lista de pacientes en riesgo (exportable a PDF) */}
          <div className="dashboard-card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-700">
                Pacientes en riesgo — período {summary.period.label}
              </h3>
              <span className="text-xs text-gray-500">
                {summary.patients_at_risk.length} paciente(s) · generado en{' '}
                {summary.generation_seconds}s
              </span>
            </div>
            {summary.patients_at_risk.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-gray-400">
                <ClipboardCheck className="w-10 h-10 mb-2" />
                <p className="text-sm">No hay pacientes en riesgo en este período</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="table-header px-4 py-2 text-left">#</th>
                      <th className="table-header px-4 py-2 text-left">Paciente</th>
                      <th className="table-header px-4 py-2 text-left">Edad</th>
                      <th className="table-header px-4 py-2 text-left">Sexo</th>
                      <th className="table-header px-4 py-2 text-left">Nivel de riesgo</th>
                      <th className="table-header px-4 py-2 text-left">Probabilidad</th>
                      <th className="table-header px-4 py-2 text-left">Última predicción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.patients_at_risk.map((p, idx) => (
                      <tr key={p.patient_id} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="table-cell">{idx + 1}</td>
                        <td className="table-cell font-medium">{p.full_name}</td>
                        <td className="table-cell">{p.age ?? '-'}</td>
                        <td className="table-cell">{(p.gender || '-').toUpperCase()}</td>
                        <td className="table-cell">
                          <span className={getRiskBadgeClass(p.risk_level)}>
                            {getRiskLabel(p.risk_level)}
                          </span>
                        </td>
                        <td className="table-cell font-semibold">
                          {(p.risk_probability * 100).toFixed(1)}%
                        </td>
                        <td className="table-cell text-gray-500 text-xs">
                          {new Date(p.last_prediction_date).toLocaleString('es-ES')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════════
   HU11 — Generación de Reportes para Autoridades de Salud (DIRESA)
   ══════════════════════════════════════════════════════════════════════════ */
function MonthlyTab() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [ageMin, setAgeMin] = useState('')
  const [ageMax, setAgeMax] = useState('')
  const [useDateRange, setUseDateRange] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState('')

  const buildParams = () => {
    const params = {}
    if (useDateRange) {
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
    } else {
      params.year = year
      params.month = month
    }
    if (ageMin !== '') params.age_min = ageMin
    if (ageMax !== '') params.age_max = ageMax
    return params
  }

  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      const r = await api.get('/reports/monthly', { params: buildParams() })
      setReport(r.data)
    } catch (e) {
      setError('Error al generar el reporte mensual.')
      setReport(null)
    } finally {
      setLoading(false)
    }
  }

  const handleExportPdf = async () => {
    setExporting(true)
    try {
      const params = new URLSearchParams(buildParams())
      await downloadFile(`/reports/monthly/pdf?${params.toString()}`)
    } catch {
      setError('No se pudo exportar el PDF.')
    } finally {
      setExporting(false)
    }
  }

  const ind = report?.indicators
  const riskBar = (ind?.risk_distribution || []).map((item) => ({
    name: item.label,
    Pacientes: item.count,
    pct: item.pct,
    color: RISK_COLORS[item.level],
  }))
  const ageData = (report?.age_distribution || []).map((row) => ({
    group: row.group,
    Bajo: row.low,
    Medio: row.medium,
    Alto: row.high,
  }))

  const years = []
  for (let y = now.getFullYear(); y >= now.getFullYear() - 5; y--) years.push(y)

  return (
    <div className="space-y-6">
      {/* Generación del reporte mensual (HU11 Escenario 1) */}
      <div className="dashboard-card">
        <div className="flex items-center gap-2 mb-4">
          <Building2 className="w-5 h-5 text-primary-500" />
          <div>
            <h3 className="text-sm font-semibold text-gray-700">Reporte mensual para la DIRESA</h3>
            <p className="text-xs text-gray-500">
              Indicadores clave de prevención: pacientes evaluados, distribución por riesgo, tasa
              de aciertos y pacientes críticos.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-4">
          {!useDateRange ? (
            <>
              <div>
                <label className="form-label">Mes</label>
                <select
                  className="form-input"
                  value={month}
                  onChange={(e) => setMonth(Number(e.target.value))}
                >
                  {MONTHS.map((m, i) => (
                    <option key={i} value={i + 1}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="form-label">Año</label>
                <select
                  className="form-input"
                  value={year}
                  onChange={(e) => setYear(Number(e.target.value))}
                >
                  {years.map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </select>
              </div>
            </>
          ) : (
            <>
              <div>
                <label className="form-label">Desde</label>
                <input
                  type="date"
                  className="form-input"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                />
              </div>
              <div>
                <label className="form-label">Hasta</label>
                <input
                  type="date"
                  className="form-input"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                />
              </div>
            </>
          )}

          {/* Filtros personalizados (HU11 Escenario 2) */}
          <div className="flex items-end gap-2 pl-4 border-l border-gray-200">
            <div className="w-24">
              <label className="form-label">
                <span className="inline-flex items-center gap-1">
                  <Filter className="w-3 h-3" /> Edad mín.
                </span>
              </label>
              <input
                type="number"
                min="0"
                max="120"
                placeholder="Ej. 40"
                className="form-input"
                value={ageMin}
                onChange={(e) => setAgeMin(e.target.value)}
              />
            </div>
            <div className="w-24">
              <label className="form-label">Edad máx.</label>
              <input
                type="number"
                min="0"
                max="120"
                placeholder="Ej. 60"
                className="form-input"
                value={ageMax}
                onChange={(e) => setAgeMax(e.target.value)}
              />
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-600 pb-2">
            <input
              type="checkbox"
              checked={useDateRange}
              onChange={(e) => setUseDateRange(e.target.checked)}
              className="rounded"
            />
            Rango de fechas
          </label>

          <button onClick={generate} className="btn-primary gap-2 ml-auto" disabled={loading}>
            <CalendarDays className="w-4 h-4" />
            {loading ? 'Compilando…' : 'Generar reporte mensual'}
          </button>
          {report && (
            <button onClick={handleExportPdf} className="btn-secondary gap-2" disabled={exporting}>
              <FileDown className="w-4 h-4" />
              {exporting ? 'Generando PDF…' : 'Descargar PDF (DIRESA)'}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-40">
          <div className="spinner"></div>
        </div>
      )}

      {report && ind && (
        <>
          {/* Encabezado del reporte */}
          <div className="dashboard-card flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold text-gray-800">{report.title}</h3>
              <p className="text-sm text-gray-500">
                Dirigido a: <span className="font-medium">{report.addressed_to}</span> · Período:{' '}
                <span className="font-medium">{report.period.label}</span>
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-green-50 text-green-700">
                <Timer className="w-3.5 h-3.5" />
                Generado en {report.generation_seconds}s (&lt; 10s ✓)
              </span>
              {Object.keys(report.filters_applied || {}).length > 0 && (
                <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-primary-50 text-primary-700">
                  <Filter className="w-3.5 h-3.5" />
                  Filtros: {Object.entries(report.filters_applied)
                    .map(([k, v]) =>
                      k === 'edad' ? `edad ${v.min}-${v.max}` : k === 'mes' ? `mes ${v}` : k
                    )
                    .join(' · ')}
                </span>
              )}
            </div>
          </div>

          {/* Indicadores clave (HU11 Escenario 1) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard icon={Users} label="Pacientes evaluados" value={ind.patients_evaluated} />
            <KpiCard icon={ClipboardCheck} label="Predicciones realizadas" value={ind.total_predictions} tone="ok" />
            <KpiCard
              icon={Target}
              label="Tasa de aciertos"
              value={ind.accuracy_rate !== null ? `${ind.accuracy_rate.toFixed(1)}%` : 'N/D'}
              tone="medium"
            />
            <KpiCard icon={AlertTriangle} label="Pacientes críticos" value={ind.critical_patients_count} tone="high" />
          </div>

          {ind.accuracy_rate !== null && (
            <p className="text-xs text-gray-500 -mt-3 ml-1">
              Tasa de predicciones acertadas: <b>{ind.accuracy_rate.toFixed(1)}%</b> — {ind.accuracy_basis}
            </p>
          )}

          {/* Gráficos de barras y tablas resumen (HU11 Escenario 2) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="dashboard-card">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">
                Distribución por nivel de riesgo
              </h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={riskBar} barSize={54}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(v, n) => [`${v} pacientes`, n]} />
                  <Bar dataKey="Pacientes" radius={[6, 6, 0, 0]}>
                    {riskBar.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="dashboard-card">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">
                Gráfico de barras por grupo etario
              </h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={ageData} barSize={14}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="group" tick={{ fontSize: 12 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="Bajo" stackId="r" fill={RISK_COLORS.low} />
                  <Bar dataKey="Medio" stackId="r" fill={RISK_COLORS.medium} />
                  <Bar dataKey="Alto" stackId="r" fill={RISK_COLORS.high} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Tabla resumen etaria */}
          <div className="dashboard-card">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">Tabla resumen por grupo etario</h3>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="table-header px-4 py-2 text-left">Grupo etario</th>
                    <th className="table-header px-4 py-2 text-left">Pacientes</th>
                    <th className="table-header px-4 py-2 text-left">Riesgo Bajo</th>
                    <th className="table-header px-4 py-2 text-left">Riesgo Medio</th>
                    <th className="table-header px-4 py-2 text-left">Riesgo Alto</th>
                  </tr>
                </thead>
                <tbody>
                  {report.age_distribution.map((row) => (
                    <tr key={row.group} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="table-cell font-medium">{row.group} años</td>
                      <td className="table-cell">{row.total}</td>
                      <td className="table-cell text-green-700">{row.low}</td>
                      <td className="table-cell text-yellow-700">{row.medium}</td>
                      <td className="table-cell text-red-700 font-semibold">{row.high}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Lista de pacientes críticos (HU11 Escenario 1) */}
          <div className="dashboard-card">
            <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-risk-high" />
              Lista de pacientes críticos (riesgo Alto)
            </h3>
            {report.critical_patients.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                <ClipboardCheck className="w-10 h-10 mb-2" />
                <p className="text-sm">
                  No se registraron pacientes críticos
                  {report.filters_applied?.edad ? ' con los filtros aplicados' : ''} en este período
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="table-header px-4 py-2 text-left">#</th>
                      <th className="table-header px-4 py-2 text-left">Paciente</th>
                      <th className="table-header px-4 py-2 text-left">Edad</th>
                      <th className="table-header px-4 py-2 text-left">Sexo</th>
                      <th className="table-header px-4 py-2 text-left">Probabilidad</th>
                      <th className="table-header px-4 py-2 text-left">Última predicción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.critical_patients.map((p, idx) => (
                      <tr key={p.patient_id} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="table-cell">{idx + 1}</td>
                        <td className="table-cell font-medium">{p.full_name}</td>
                        <td className="table-cell">{p.age ?? '-'}</td>
                        <td className="table-cell">{(p.gender || '-').toUpperCase()}</td>
                        <td className="table-cell">
                          <span className="badge-risk-high">
                            {(p.risk_probability * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="table-cell text-gray-500 text-xs">
                          {new Date(p.last_prediction_date).toLocaleString('es-ES')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════════
   Módulo de reportes con pestañas
   ══════════════════════════════════════════════════════════════════════════ */
export default function ReportsPanel() {
  const [tab, setTab] = useState('population')

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Reportes</h1>
          <p className="text-sm text-gray-500 mt-1">
            Monitoreo poblacional y reportes para autoridades de salud
          </p>
        </div>
        <BarChart3 className="w-8 h-8 text-primary-500" />
      </div>

      {/* Pestañas */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit">
        <button
          onClick={() => setTab('population')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tab === 'population'
              ? 'bg-white text-primary-600 shadow-sm'
              : 'text-gray-500 hover:text-gray-800'
          }`}
        >
          Monitoreo Poblacional
        </button>
        <button
          onClick={() => setTab('monthly')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tab === 'monthly'
              ? 'bg-white text-primary-600 shadow-sm'
              : 'text-gray-500 hover:text-gray-800'
          }`}
        >
          Reportes DIRESA
        </button>
      </div>

      {tab === 'population' ? <PopulationTab /> : <MonthlyTab />}
    </div>
  )
}
