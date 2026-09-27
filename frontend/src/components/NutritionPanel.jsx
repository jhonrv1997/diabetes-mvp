import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/axios'
import {
  Apple,
  RefreshCw,
  Plus,
  UtensilsCrossed,
  Activity,
  AlertTriangle,
  CheckCircle,
  XCircle,
  TrendingUp,
  TrendingDown,
} from 'lucide-react'

const RESTRICTION_OPTIONS = [
  'diabetes',
  'hipertension',
  'bajo_sodio',
  'vegetariana',
  'vegana',
  'sin_gluten',
  'sin_lactosa',
  'bajo_azucar',
]

const MEAL_SLOTS = [
  { key: 'desayuno', label: 'Desayuno' },
  { key: 'colacion_manana', label: 'Colación Mañana' },
  { key: 'almuerzo', label: 'Almuerzo' },
  { key: 'colacion_tarde', label: 'Colación Tarde' },
  { key: 'cena', label: 'Cena' },
]

export default function NutritionPanel() {
  const navigate = useNavigate()
  const [plans, setPlans] = useState([])
  const [patients, setPatients] = useState([])
  const [predictions, setPredictions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [selectedPatientId, setSelectedPatientId] = useState(null)
  const [adherence, setAdherence] = useState({})  // plan_id -> adherence data
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState({
    patient_id: '',
    daily_calories: 1800,
    protein_g: 90,
    carbs_g: 200,
    fat_g: 60,
    notes: '',
    restrictions: [],
    meal_schedule: { desayuno: '08:00', almuerzo: '13:00', cena: '19:00' },
  })

  const fetchData = async () => {
    setLoading(true)
    setError('')
    try {
      const [plansRes, patientsRes, predictionsRes] = await Promise.all([
        api.get('/nutrition/plans'),
        api.get('/patients').catch(() => ({ data: [] })),
        api.get('/predictions').catch(() => ({ data: [] })),
      ])
      setPlans(plansRes.data || [])
      setPatients(patientsRes.data || [])
      setPredictions(predictionsRes.data || [])
    } catch (e) {
      setError('Error al cargar los planes nutricionales')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  // Fetch adherence for each plan
  const fetchAdherence = async (planId) => {
    try {
      const r = await api.get(`/nutrition/plans/${planId}/adherence`)
      setAdherence((prev) => ({ ...prev, [planId]: r.data }))
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    plans.forEach((p) => fetchAdherence(p.id))
  }, [plans])

  const getPatient = (id) => patients.find((p) => p.id === id)
  const getPatientName = (id) => {
    const p = getPatient(id)
    return p ? `${p.first_name} ${p.last_name}` : `Paciente #${id}`
  }
  const getLatestRisk = (patientId) => {
    const pred = predictions
      .filter((p) => p.patient_id === patientId)
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0]
    return pred?.risk_level
  }

  const atRiskPatients = patients.filter((p) => {
    const risk = getLatestRisk(p.id)
    return risk === 'medium' || risk === 'high' || risk === 'medio' || risk === 'alto'
  })

  const openCreateForm = (patientId = null) => {
    setSelectedPatientId(patientId)
    setForm({
      patient_id: patientId || '',
      daily_calories: 1800,
      protein_g: 90,
      carbs_g: 200,
      fat_g: 60,
      notes: '',
      restrictions: [],
      meal_schedule: { desayuno: '08:00', almuerzo: '13:00', cena: '19:00' },
    })
    setShowForm(true)
  }

  const handleRestrictionToggle = (r) => {
    setForm((prev) => ({
      ...prev,
      restrictions: prev.restrictions.includes(r)
        ? prev.restrictions.filter((x) => x !== r)
        : [...prev.restrictions, r],
    }))
  }

  const handleMealTimeChange = (key, time) => {
    setForm((prev) => ({
      ...prev,
      meal_schedule: { ...prev.meal_schedule, [key]: time },
    }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.patient_id) {
      setError('Selecciona un paciente')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const payload = {
        ...form,
        daily_calories: parseFloat(form.daily_calories) || 0,
        protein_g: parseFloat(form.protein_g) || null,
        carbs_g: parseFloat(form.carbs_g) || null,
        fat_g: parseFloat(form.fat_g) || null,
      }
      await api.post('/nutrition/plans', payload)
      setShowForm(false)
      await fetchData()
    } catch (e) {
      setError(e.response?.data?.detail || 'Error al crear el plan nutricional')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
            <Apple className="w-6 h-6 text-primary-500" />
            Seguimiento Nutricional
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Planes nutricionales para pacientes con riesgo Medio o Alto ·{' '}
            {plans.length} plan(es) registrado(s)
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchData} className="btn-secondary gap-2" title="Actualizar">
            <RefreshCw className="w-4 h-4" />
            Actualizar
          </button>
          <button onClick={() => openCreateForm()} className="btn-primary gap-2">
            <Plus className="w-4 h-4" />
            Nuevo Plan
          </button>
        </div>
      </div>

      {/* HU10 explanation banner */}
      <div className="dashboard-card bg-amber-50 border-amber-200">
        <div className="flex items-start gap-3">
          <UtensilsCrossed className="w-5 h-5 text-amber-500 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-amber-800">
            <p className="font-semibold mb-1">HU10 · Seguimiento Nutricional Personalizado</p>
            <p className="text-xs text-amber-700">
              Registra planes alimentarios para pacientes con riesgo Medio o Alto, integrados con
              los datos de glucosa y actividad física del sistema IoT. Tras 14 días, el sistema
              cruza los datos de glucosa del sensor con el plan asignado y calcula el porcentaje
              de adherencia. Si la adherencia es menor al 60%, se muestra una recomendación de ajuste.
            </p>
          </div>
        </div>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="dashboard-card border-2 border-primary-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-800">Crear Plan Nutricional</h3>
            <button
              onClick={() => setShowForm(false)}
              className="text-gray-400 hover:text-gray-600"
            >
              <XCircle className="w-5 h-5" />
            </button>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Patient selector */}
            <div>
              <label className="form-label">Paciente (solo riesgo Medio/Alto)</label>
              <select
                value={form.patient_id}
                onChange={(e) => setForm({ ...form, patient_id: parseInt(e.target.value) })}
                className="form-input"
                required
              >
                <option value="">— Selecciona un paciente —</option>
                {atRiskPatients.map((p) => (
                  <option key={p.id} value={p.id}>
                    #{p.id} · {p.first_name} {p.last_name} · Riesgo:{' '}
                    {getLatestRisk(p.id)?.toUpperCase() || 'N/A'}
                  </option>
                ))}
              </select>
              {atRiskPatients.length === 0 && (
                <p className="form-warning text-xs mt-1">
                  ⚠ No hay pacientes con riesgo Medio/Alto. Genera una predicción primero.
                </p>
              )}
            </div>

            {/* Calories + macros */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div>
                <label className="form-label">Calorías/día</label>
                <input
                  type="number"
                  value={form.daily_calories}
                  onChange={(e) => setForm({ ...form, daily_calories: e.target.value })}
                  className="form-input"
                  min="500"
                  max="5000"
                  required
                />
              </div>
              <div>
                <label className="form-label">Proteína (g)</label>
                <input
                  type="number"
                  value={form.protein_g}
                  onChange={(e) => setForm({ ...form, protein_g: e.target.value })}
                  className="form-input"
                  min="0"
                />
              </div>
              <div>
                <label className="form-label">Carbohidratos (g)</label>
                <input
                  type="number"
                  value={form.carbs_g}
                  onChange={(e) => setForm({ ...form, carbs_g: e.target.value })}
                  className="form-input"
                  min="0"
                />
              </div>
              <div>
                <label className="form-label">Grasas (g)</label>
                <input
                  type="number"
                  value={form.fat_g}
                  onChange={(e) => setForm({ ...form, fat_g: e.target.value })}
                  className="form-input"
                  min="0"
                />
              </div>
            </div>

            {/* Restrictions */}
            <div>
              <label className="form-label">Restricciones alimentarias</label>
              <div className="flex flex-wrap gap-2">
                {RESTRICTION_OPTIONS.map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => handleRestrictionToggle(r)}
                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                      form.restrictions.includes(r)
                        ? 'bg-primary-500 text-white border-primary-500'
                        : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>

            {/* Meal schedule */}
            <div>
              <label className="form-label">Horario de comidas (recordatorios automáticos)</label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {MEAL_SLOTS.map((slot) => (
                  <div key={slot.key} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={slot.key in form.meal_schedule}
                      onChange={(e) => {
                        setForm((prev) => {
                          const sched = { ...prev.meal_schedule }
                          if (e.target.checked) {
                            sched[slot.key] = '12:00'
                          } else {
                            delete sched[slot.key]
                          }
                          return { ...prev, meal_schedule: sched }
                        })
                      }}
                      className="rounded border-gray-300 text-primary-500 focus:ring-primary-500"
                    />
                    <span className="text-xs text-gray-700 flex-1">{slot.label}</span>
                    {slot.key in form.meal_schedule && (
                      <input
                        type="time"
                        value={form.meal_schedule[slot.key]}
                        onChange={(e) => handleMealTimeChange(slot.key, e.target.value)}
                        className="form-input text-xs py-1 w-24"
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Notes */}
            <div>
              <label className="form-label">Notas</label>
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                className="form-input"
                rows="2"
                placeholder="Indicaciones adicionales..."
              />
            </div>

            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="btn-secondary"
              >
                Cancelar
              </button>
              <button type="submit" className="btn-primary gap-2" disabled={submitting}>
                <CheckCircle className="w-4 h-4" />
                {submitting ? 'Guardando...' : 'Guardar plan y programar recordatorios'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Error */}
      {error && !showForm && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Plans list */}
      {plans.length === 0 ? (
        <div className="dashboard-card flex flex-col items-center justify-center py-12 text-gray-400">
          <Apple className="w-12 h-12 mb-3" />
          <p className="text-sm font-medium">No hay planes nutricionales registrados</p>
          <p className="text-xs mt-1">
            Crea un plan para un paciente con riesgo Medio o Alto
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {plans.map((plan) => {
            const adh = adherence[plan.id]
            const isEligible = adh?.eligible_for_evaluation
            const adhPct = adh?.adherence_pct || 0
            const needsAdjustment = isEligible && adhPct < 60
            return (
              <div key={plan.id} className="dashboard-card">
                {/* Patient + status header */}
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div>
                    <h3 className="text-base font-semibold text-gray-800">
                      {plan.patient_name || getPatientName(plan.patient_id)}
                    </h3>
                    <p className="text-xs text-gray-500">
                      Plan #{plan.id} · Desde{' '}
                      {new Date(plan.start_date).toLocaleDateString('es-ES')} ·{' '}
                      {plan.is_active ? '🟢 Activo' : '⚪ Inactivo'}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold text-primary-600">
                      {plan.daily_calories}
                    </p>
                    <p className="text-[10px] text-gray-500">kcal/día</p>
                  </div>
                </div>

                {/* Macros */}
                <div className="grid grid-cols-3 gap-2 text-center mb-3">
                  <div className="bg-blue-50 rounded p-2">
                    <p className="text-[10px] text-gray-500">Proteína</p>
                    <p className="text-sm font-semibold text-blue-700">{plan.protein_g || 0}g</p>
                  </div>
                  <div className="bg-amber-50 rounded p-2">
                    <p className="text-[10px] text-gray-500">Carbs</p>
                    <p className="text-sm font-semibold text-amber-700">{plan.carbs_g || 0}g</p>
                  </div>
                  <div className="bg-yellow-50 rounded p-2">
                    <p className="text-[10px] text-gray-500">Grasas</p>
                    <p className="text-sm font-semibold text-yellow-700">{plan.fat_g || 0}g</p>
                  </div>
                </div>

                {/* Restrictions */}
                {plan.restrictions?.length > 0 && (
                  <div className="mb-2">
                    <p className="text-[10px] text-gray-500 uppercase mb-1">Restricciones</p>
                    <div className="flex flex-wrap gap-1">
                      {plan.restrictions.map((r) => (
                        <span
                          key={r}
                          className="px-2 py-0.5 bg-red-50 text-red-700 text-[10px] rounded-full"
                        >
                          {r}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Meal schedule */}
                {plan.meal_schedule && Object.keys(plan.meal_schedule).length > 0 && (
                  <div className="mb-2">
                    <p className="text-[10px] text-gray-500 uppercase mb-1">
                      Recordatorios de comidas
                    </p>
                    <div className="flex flex-wrap gap-2 text-xs">
                      {Object.entries(plan.meal_schedule).map(([k, v]) => (
                        <span
                          key={k}
                          className="px-2 py-0.5 bg-primary-50 text-primary-700 rounded text-[10px]"
                        >
                          🍽️ {k}: {v}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Adherence (HU10 Scenario 2) */}
                {adh && (
                  <div
                    className={`mt-3 p-3 rounded-lg border ${
                      needsAdjustment
                        ? 'bg-red-50 border-red-200'
                        : isEligible
                        ? 'bg-green-50 border-green-200'
                        : 'bg-gray-50 border-gray-200'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-gray-700 flex items-center gap-1">
                        <Activity className="w-3 h-3" />
                        Adherencia (HU10 Esc.2)
                      </span>
                      <span
                        className={`text-lg font-bold ${
                          needsAdjustment
                            ? 'text-risk-high'
                            : isEligible
                            ? 'text-risk-low'
                            : 'text-gray-500'
                        }`}
                      >
                        {adhPct.toFixed(1)}%
                      </span>
                    </div>
                    <div className="text-[11px] text-gray-600 space-y-0.5">
                      <p>
                        Días desde inicio: <strong>{adh.days_since_start}</strong> de 14 requeridos
                      </p>
                      <p>
                        Lecturas de glucosa analizadas: <strong>{adh.glucose_readings_count}</strong>
                      </p>
                      {adh.avg_glucose !== null && (
                        <p>
                          Glucosa promedio: <strong>{adh.avg_glucose} mg/dL</strong> · En rango:{' '}
                          <strong>{adh.glucose_in_target_pct}%</strong>
                        </p>
                      )}
                      {adh.recommendation && (
                        <p
                          className={`mt-1 p-2 rounded text-[11px] ${
                            needsAdjustment
                              ? 'bg-red-100 text-red-800'
                              : isEligible
                              ? 'bg-green-100 text-green-800'
                              : 'bg-gray-100 text-gray-700'
                          }`}
                        >
                          {needsAdjustment && <AlertTriangle className="w-3 h-3 inline mr-1" />}
                          {isEligible && !needsAdjustment && (
                            <CheckCircle className="w-3 h-3 inline mr-1" />
                          )}
                          {adh.recommendation}
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* Footer */}
                <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
                  <span>Nutricionista: {plan.nutritionist_name || 'N/A'}</span>
                  <button
                    onClick={() => navigate(`/patients/${plan.patient_id}`)}
                    className="btn-secondary text-xs px-2 py-1"
                  >
                    Ver paciente
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
