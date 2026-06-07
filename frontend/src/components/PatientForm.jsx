import React, { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api/axios'
import { Save, X, AlertCircle, UserPlus } from 'lucide-react'

export default function PatientForm() {
  const navigate = useNavigate()
  const { id } = useParams()
  const isEditing = Boolean(id)

  const [loading, setLoading] = useState(false)
  const [fetchingPatient, setFetchingPatient] = useState(isEditing)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    date_of_birth: '',
    gender: '',
    phone: '',
    address: '',
    emergency_contact: '',
    family_diabetes_history: false,
    hypertension_history: false,
    notes: '',
  })

  const [errors, setErrors] = useState({})

  useEffect(() => {
    if (isEditing) {
      fetchPatient()
    }
  }, [id])

  const fetchPatient = async () => {
    setFetchingPatient(true)
    try {
      const response = await api.get(`/patients/${id}`)
      const patient = response.data
      setForm({
        first_name: patient.first_name || '',
        last_name: patient.last_name || '',
        date_of_birth: patient.date_of_birth ? patient.date_of_birth.split('T')[0] : '',
        gender: patient.gender || '',
        phone: patient.phone || '',
        address: patient.address || '',
        emergency_contact: patient.emergency_contact || '',
        family_diabetes_history: patient.family_diabetes_history || false,
        hypertension_history: patient.hypertension_history || false,
        notes: patient.notes || '',
      })
    } catch {
      setError('Error al cargar los datos del paciente')
    } finally {
      setFetchingPatient(false)
    }
  }

  const validate = () => {
    const newErrors = {}

    if (!form.first_name.trim()) {
      newErrors.first_name = 'El nombre es obligatorio'
    }
    if (!form.last_name.trim()) {
      newErrors.last_name = 'El apellido es obligatorio'
    }
    if (!form.date_of_birth) {
      newErrors.date_of_birth = 'La fecha de nacimiento es obligatoria'
    }
    if (!form.gender) {
      newErrors.gender = 'El género es obligatorio'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setForm((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }))
    // Clear error for field on change
    if (errors[name]) {
      setErrors((prev) => {
        const updated = { ...prev }
        delete updated[name]
        return updated
      })
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')

    if (!validate()) return

    setLoading(true)
    try {
      if (isEditing) {
        await api.put(`/patients/${id}`, form)
        setSuccess('Paciente actualizado exitosamente')
      } else {
        await api.post('/patients', form)
        setSuccess('Paciente registrado exitosamente')
      }
      setTimeout(() => navigate('/patients'), 1200)
    } catch (err) {
      setError(
        err.response?.data?.detail || 'Error al guardar el paciente'
      )
    } finally {
      setLoading(false)
    }
  }

  if (fetchingPatient) {
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
          <UserPlus className="w-5 h-5 text-primary-500" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-800">
            {isEditing ? 'Editar Paciente' : 'Registrar Nuevo Paciente'}
          </h1>
          <p className="text-sm text-gray-500">
            {isEditing
              ? 'Actualice los datos del paciente'
              : 'Complete los datos del nuevo paciente'}
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

      {/* Form */}
      <form onSubmit={handleSubmit} className="dashboard-card space-y-5">
        {/* Personal info */}
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
            Información Personal
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="first_name" className="form-label">
                Nombre <span className="text-red-500">*</span>
              </label>
              <input
                id="first_name"
                name="first_name"
                type="text"
                value={form.first_name}
                onChange={handleChange}
                className={`form-input ${errors.first_name ? 'form-input-error' : ''}`}
                placeholder="Nombre del paciente"
                disabled={loading}
              />
              {errors.first_name && (
                <p className="form-error">{errors.first_name}</p>
              )}
            </div>

            <div>
              <label htmlFor="last_name" className="form-label">
                Apellido <span className="text-red-500">*</span>
              </label>
              <input
                id="last_name"
                name="last_name"
                type="text"
                value={form.last_name}
                onChange={handleChange}
                className={`form-input ${errors.last_name ? 'form-input-error' : ''}`}
                placeholder="Apellido del paciente"
                disabled={loading}
              />
              {errors.last_name && (
                <p className="form-error">{errors.last_name}</p>
              )}
            </div>

            <div>
              <label htmlFor="date_of_birth" className="form-label">
                Fecha de Nacimiento <span className="text-red-500">*</span>
              </label>
              <input
                id="date_of_birth"
                name="date_of_birth"
                type="date"
                value={form.date_of_birth}
                onChange={handleChange}
                className={`form-input ${errors.date_of_birth ? 'form-input-error' : ''}`}
                disabled={loading}
              />
              {errors.date_of_birth && (
                <p className="form-error">{errors.date_of_birth}</p>
              )}
            </div>

            <div>
              <label htmlFor="gender" className="form-label">
                Género <span className="text-red-500">*</span>
              </label>
              <select
                id="gender"
                name="gender"
                value={form.gender}
                onChange={handleChange}
                className={`form-input ${errors.gender ? 'form-input-error' : ''}`}
                disabled={loading}
              >
                <option value="">Seleccionar...</option>
                <option value="M">Masculino</option>
                <option value="F">Femenino</option>
                <option value="O">Otro</option>
              </select>
              {errors.gender && (
                <p className="form-error">{errors.gender}</p>
              )}
            </div>

            <div>
              <label htmlFor="phone" className="form-label">
                Teléfono
              </label>
              <input
                id="phone"
                name="phone"
                type="tel"
                value={form.phone}
                onChange={handleChange}
                className="form-input"
                placeholder="Ej: +52 555 123 4567"
                disabled={loading}
              />
            </div>

            <div>
              <label htmlFor="emergency_contact" className="form-label">
                Contacto de Emergencia
              </label>
              <input
                id="emergency_contact"
                name="emergency_contact"
                type="text"
                value={form.emergency_contact}
                onChange={handleChange}
                className="form-input"
                placeholder="Nombre y teléfono"
                disabled={loading}
              />
            </div>
          </div>
        </div>

        {/* Address */}
        <div>
          <label htmlFor="address" className="form-label">
            Dirección
          </label>
          <input
            id="address"
            name="address"
            type="text"
            value={form.address}
            onChange={handleChange}
            className="form-input"
            placeholder="Dirección del paciente"
            disabled={loading}
          />
        </div>

        {/* Medical history */}
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
            Antecedentes Médicos
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
              <div>
                <span className="text-sm font-medium text-gray-700">
                  Antecedentes Familiares de DM2
                </span>
                <p className="text-xs text-gray-500">
                  Diabetes Mellitus Tipo 2 en familiares directos
                </p>
              </div>
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
              <div>
                <span className="text-sm font-medium text-gray-700">
                  Historial de Hipertensión
                </span>
                <p className="text-xs text-gray-500">
                  Diagnóstico previo de hipertensión arterial
                </p>
              </div>
            </label>
          </div>
        </div>

        {/* Notes */}
        <div>
          <label htmlFor="notes" className="form-label">
            Notas Adicionales
          </label>
          <textarea
            id="notes"
            name="notes"
            value={form.notes}
            onChange={handleChange}
            className="form-input min-h-[80px]"
            placeholder="Observaciones adicionales sobre el paciente..."
            disabled={loading}
            rows={3}
          />
        </div>

        {/* Buttons */}
        <div className="flex items-center gap-3 pt-4 border-t border-gray-100">
          <button
            type="submit"
            disabled={loading}
            className="btn-primary gap-2"
          >
            {loading ? (
              <div className="spinner w-4 h-4 border-2" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {isEditing ? 'Actualizar Paciente' : 'Registrar Paciente'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/patients')}
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
