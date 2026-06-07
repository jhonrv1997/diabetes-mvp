import React, { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api/axios'
import {
  validateBloodPressure,
  validateWeight,
  calculateBMI,
  RANGES,
} from '../utils/validation'
import {
  Save,
  X,
  AlertCircle,
  AlertTriangle,
  ClipboardList,
  Info,
  Calculator,
} from 'lucide-react'

export default function ClinicalDataForm() {
  const navigate = useNavigate()
  const { patientId } = useParams()
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(false)
  const [fetchingPatients, setFetchingPatients] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [form, setForm] = useState({
    patient_id: patientId || '',
    systolic_bp: '',
    diastolic_bp: '',
    weight: '',
    height: '',
    age: '',
    family_diabetes_history: false,
    hypertension_history: false,
    glucose_level: '',
    notes: '',
  })

  const [validation, setValidation] = useState({
    bp: { valid: true, warnings: [], errors: [] },
    weight: { valid: true, warnings: [] },
    bmi: { bmi: null, category: '' },
  })

  const [lastWeight, setLastWeight] = useState(null)

  useEffect(() => {
    fetchPatients()
  }, [])

  useEffect(() => {
    if (form.patient_id) {
      fetchLastWeight(form.patient_id)
    }
  }, [form.patient_id])

  const fetchPatients = async () => {
    setFetchingPatients(true)
    try {
      const response = await api.get('/patients')
      setPatients(response.data || [])
    } catch {
      setError('Error al cargar la lista de pacientes')
    } finally {
      setFetchingPatients(false)
    }
  }

  const fetchLastWeight = async (pid) => {
    try {
      const response = await api.get(`/clinical-data/${pid}`)
      if (response.data?.weight) {
        setLastWeight(response.data.weight)
      }
    } catch {
      setLastWeight(null)
    }
  }

  const runValidation = (updatedForm) => {
    const bpResult = validateBloodPressure(
      Number(updatedForm.systolic_bp),
      Number(updatedForm.diastolic_bp)
    )
    const weightResult = validateWeight(
      Number(updatedForm.weight),
      lastWeight
    )
    const bmiResult = calculateBMI(
      Number(updatedForm.weight),
      Number(updatedForm.height)
    )

    setValidation({
      bp: bpResult,
      weight: weightResult,
      bmi: bmiResult,
    })
  }

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    const updatedForm = {
      ...form,
      [name]: type === 'checkbox' ? checked : value,
    }
    setForm(updatedForm)

    // Run validation on relevant fields
    if (['systolic_bp', 'diastolic_bp', 'weight', 'height'].includes(name)) {
      runValidation(updatedForm)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    // Validate before submit
    const bpResult = validateBloodPressure(
      Number(form.systolic_bp),
      Number(form.diastolic_bp)
    )
    if (!bpResult.valid) {
      setError(bpResult.errors.join('. '))
      return
    }

    if (!form.patient_id) {
      setError('Debe seleccionar un paciente')
      return
    }

    setLoading(true)
    try {
      const payload = {
        patient_id: form.patient_id,
        systolic_bp: Number(form.systolic_bp) || null,
        diastolic_bp: Number(form.diastolic_bp) || null,
        weight: Number(form.weight) || null,
        height: form.height ? Number(form.height) : null,
        age: Number(form.age) || null,
        family_diabetes_history: form.family_diabetes_history,
        hypertension_history: form.hypertension_history,
        glucose_level: form.glucose_level ? Number(form.glucose_level) : null,
        notes: form.notes || null,
      }

      await api.post('/clinical-data', payload)
      setSuccess('Datos clínicos registrados exitosamente')
      setTimeout(() => navigate(`/patients/${form.patient_id}`), 1500)
    } catch (err) {
      setError(
        err.response?.data?.detail || 'Error al guardar los datos clínicos'
      )
    } finally {
      setLoading(false)
    }
  }

  if (fetchingPatients) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner"></div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center">
          <ClipboardList className="w-5 h-5 text-primary-500" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-800">Registrar Datos Clínicos</h1>
          <p className="text-sm text-gray-500">
            Ingrese las mediciones y antecedentes del paciente
          </p>
        </div>
      </div>

      {/* Success message */}
      {success && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
          {success}
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Patient selection */}
        <div className="dashboard-card">
          <label htmlFor="patient_id" className="form-label">
            Paciente <span className="text-red-500">*</span>
          </label>
          <select
            id="patient_id"
            name="patient_id"
            value={form.patient_id}
            onChange={handleChange}
            className="form-input"
            disabled={!!patientId || loading}
          >
            <option value="">Seleccionar paciente...</option>
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.first_name} {p.last_name}
              </option>
            ))}
          </select>
        </div>

        {/* Blood pressure */}
        <div className="dashboard-card">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
            Presión Arterial
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="systolic_bp" className="form-label">
                Sistólica (mmHg)
              </label>
              <input
                id="systolic_bp"
                name="systolic_bp"
                type="number"
                value={form.systolic_bp}
                onChange={handleChange}
                className="form-input"
                placeholder={`${RANGES.bloodPressure.systolic.min}-${RANGES.bloodPressure.systolic.max}`}
                min={RANGES.bloodPressure.systolic.min}
                max={RANGES.bloodPressure.systolic.max}
                disabled={loading}
              />
            </div>
            <div>
              <label htmlFor="diastolic_bp" className="form-label">
                Diastólica (mmHg)
              </label>
              <input
                id="diastolic_bp"
                name="diastolic_bp"
                type="number"
                value={form.diastolic_bp}
                onChange={handleChange}
                className="form-input"
                placeholder={`${RANGES.bloodPressure.diastolic.min}-${RANGES.bloodPressure.diastolic.max}`}
                min={RANGES.bloodPressure.diastolic.min}
                max={RANGES.bloodPressure.diastolic.max}
                disabled={loading}
              />
            </div>
          </div>

          {/* BP Validation messages */}
          {validation.bp.errors.length > 0 && (
            <div className="mt-2 space-y-1">
              {validation.bp.errors.map((err, idx) => (
                <p key={idx} className="form-error">
                  <AlertCircle className="w-3 h-3" />
                  {err}
                </p>
              ))}
            </div>
          )}
          {validation.bp.warnings.length > 0 && (
            <div className="mt-2 space-y-1">
              {validation.bp.warnings.map((warn, idx) => (
                <p key={idx} className="form-warning">
                  <AlertTriangle className="w-3 h-3" />
                  {warn}
                </p>
              ))}
            </div>
          )}
        </div>

        {/* Body measurements */}
        <div className="dashboard-card">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
            Mediciones Corporales
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label htmlFor="weight" className="form-label">
                Peso (kg)
              </label>
              <input
                id="weight"
                name="weight"
                type="number"
                step="0.1"
                value={form.weight}
                onChange={handleChange}
                className="form-input"
                placeholder={`${RANGES.weight.min}-${RANGES.weight.max}`}
                min={RANGES.weight.min}
                max={RANGES.weight.max}
                disabled={loading}
              />
              {validation.weight.warnings.length > 0 && (
                <div className="mt-1 space-y-1">
                  {validation.weight.warnings.map((warn, idx) => (
                    <p key={idx} className="form-warning">
                      <AlertTriangle className="w-3 h-3" />
                      {warn}
                    </p>
                  ))}
                </div>
              )}
            </div>

            <div>
              <label htmlFor="height" className="form-label">
                Altura (cm) <span className="text-gray-400 font-normal">- opcional</span>
              </label>
              <input
                id="height"
                name="height"
                type="number"
                step="0.1"
                value={form.height}
                onChange={handleChange}
                className="form-input"
                placeholder={`${RANGES.height.min}-${RANGES.height.max}`}
                min={RANGES.height.min}
                max={RANGES.height.max}
                disabled={loading}
              />
            </div>

            <div>
              <label htmlFor="age" className="form-label">
                Edad (años)
              </label>
              <input
                id="age"
                name="age"
                type="number"
                value={form.age}
                onChange={handleChange}
                className="form-input"
                placeholder={`${RANGES.age.min}-${RANGES.age.max}`}
                min={RANGES.age.min}
                max={RANGES.age.max}
                disabled={loading}
              />
            </div>
          </div>

          {/* BMI display */}
          {validation.bmi.bmi && (
            <div className="mt-4 p-3 bg-gray-50 rounded-lg flex items-center gap-3">
              <Calculator className="w-5 h-5 text-primary-500" />
              <div>
                <p className="text-xs text-gray-500">Índice de Masa Corporal (IMC)</p>
                <p className="text-sm font-semibold text-gray-800">
                  {validation.bmi.bmi} - {validation.bmi.category}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Glucose */}
        <div className="dashboard-card">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
            Glucosa
          </h3>
          <div>
            <label htmlFor="glucose_level" className="form-label">
              Nivel de Glucosa (mg/dL)
            </label>
            <input
              id="glucose_level"
              name="glucose_level"
              type="number"
              step="0.1"
              value={form.glucose_level}
              onChange={handleChange}
              className="form-input"
              placeholder="Ej: 95"
              disabled={loading}
            />
            {form.glucose_level > RANGES.glucose.hyperHigh && (
              <p className="form-warning mt-1">
                <AlertTriangle className="w-3 h-3" />
                Glucosa muy alta (&gt;300 mg/dL) - Riesgo de cetoacidosis
              </p>
            )}
            {form.glucose_level && form.glucose_level < RANGES.glucose.hypo && (
              <p className="form-warning mt-1">
                <AlertTriangle className="w-3 h-3" />
                Glucosa baja (&lt;70 mg/dL) - Riesgo de hipoglucemia
              </p>
            )}
          </div>
        </div>

        {/* Medical history */}
        <div className="dashboard-card">
          <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
            Antecedentes
          </h3>
          <div className="space-y-3">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                name="family_diabetes_history"
                checked={form.family_diabetes_history}
                onChange={handleChange}
                className="w-4 h-4 rounded border-gray-300 text-primary-500 focus:ring-primary-500"
                disabled={loading}
              />
              <span className="text-sm text-gray-700">
                Antecedentes Familiares de DM2
              </span>
            </label>

            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                name="hypertension_history"
                checked={form.hypertension_history}
                onChange={handleChange}
                className="w-4 h-4 rounded border-gray-300 text-primary-500 focus:ring-primary-500"
                disabled={loading}
              />
              <span className="text-sm text-gray-700">
                Historial de Hipertensión
              </span>
            </label>
          </div>
        </div>

        {/* Notes */}
        <div className="dashboard-card">
          <label htmlFor="notes" className="form-label">
            Notas Adicionales
          </label>
          <textarea
            id="notes"
            name="notes"
            value={form.notes}
            onChange={handleChange}
            className="form-input min-h-[80px]"
            placeholder="Observaciones adicionales..."
            disabled={loading}
            rows={3}
          />
        </div>

        {/* Buttons */}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={loading || !validation.bp.valid}
            className="btn-primary gap-2"
          >
            {loading ? (
              <div className="spinner w-4 h-4 border-2" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            Guardar Datos Clínicos
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="btn-secondary gap-2"
          >
            <X className="w-4 h-4" />
            Cancelar
          </button>
        </div>
      </form>
    </div>
  )
}
