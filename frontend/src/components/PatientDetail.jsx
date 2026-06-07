import React, { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api/axios'
import { getRiskBadgeClass, getRiskLabel, calculateBMI } from '../utils/validation'
import GlucoseChart from './GlucoseChart'
import {
  ArrowLeft,
  Edit,
  ClipboardList,
  TrendingUp,
  Bluetooth,
  User,
  Heart,
  Activity,
  AlertTriangle,
  RefreshCw,
  Calendar,
  Phone,
  MapPin,
  FileText,
} from 'lucide-react'

export default function PatientDetail() {
  const navigate = useNavigate()
  const { id } = useParams()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [patient, setPatient] = useState(null)
  const [clinicalData, setClinicalData] = useState(null)
  const [predictions, setPredictions] = useState([])
  const [glucoseReadings, setGlucoseReadings] = useState([])

  useEffect(() => {
    fetchPatientData()
  }, [id])

  const fetchPatientData = async () => {
    setLoading(true)
    setError('')
    try {
      const [patientRes, clinicalRes, predictionsRes, glucoseRes] =
        await Promise.all([
          api.get(`/patients/${id}`).catch(() => null),
          api.get(`/clinical-data/${id}`).catch(() => null),
          api.get(`/predictions/${id}`).catch(() => ({ data: [] })),
          api.get(`/glucose/${id}`).catch(() => ({ data: [] })),
        ])

      if (!patientRes) {
        setError('Paciente no encontrado')
        return
      }

      setPatient(patientRes.data)
      setClinicalData(clinicalRes?.data || null)
      setPredictions(predictionsRes.data || [])
      setGlucoseReadings(glucoseRes.data || [])
    } catch {
      setError('Error al cargar los datos del paciente')
    } finally {
      setLoading(false)
    }
  }

  const calculateAge = (dob) => {
    if (!dob) return '-'
    const birthDate = new Date(dob)
    const today = new Date()
    let age = today.getFullYear() - birthDate.getFullYear()
    const m = today.getMonth() - birthDate.getMonth()
    if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) age--
    return age
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 mb-4">{error}</p>
        <button onClick={() => navigate('/patients')} className="btn-primary gap-2">
          <ArrowLeft className="w-4 h-4" />
          Volver a Pacientes
        </button>
      </div>
    )
  }

  if (!patient) return null

  const bmi = clinicalData
    ? calculateBMI(clinicalData.weight, clinicalData.height)
    : null

  const latestPrediction = predictions.sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  )[0]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/patients')}
            className="btn-secondary p-2"
            title="Volver"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-800">
              {patient.first_name} {patient.last_name}
            </h1>
            <p className="text-sm text-gray-500">
              {calculateAge(patient.date_of_birth)} años •{' '}
              {patient.gender === 'M' ? 'Masculino' : patient.gender === 'F' ? 'Femenino' : 'Otro'}
            </p>
          </div>
          {latestPrediction && (
            <span className={getRiskBadgeClass(latestPrediction.risk_level)}>
              Riesgo {getRiskLabel(latestPrediction.risk_level)}
            </span>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => navigate(`/patients/${id}/edit`)}
            className="btn-secondary gap-2"
          >
            <Edit className="w-4 h-4" />
            Editar
          </button>
          <button
            onClick={() => navigate(`/clinical-data/${id}`)}
            className="btn-secondary gap-2"
          >
            <ClipboardList className="w-4 h-4" />
            Registrar Datos
          </button>
          <button
            onClick={() => navigate(`/predict/${id}`)}
            className="btn-primary gap-2"
          >
            <TrendingUp className="w-4 h-4" />
            Nueva Predicción
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Patient info card */}
        <div className="dashboard-card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <User className="w-4 h-4 text-primary-500" />
            Información del Paciente
          </h3>
          <div className="space-y-3">
            <InfoRow icon={Calendar} label="Fecha de Nacimiento" value={patient.date_of_birth ? new Date(patient.date_of_birth).toLocaleDateString('es-ES') : '-'} />
            <InfoRow icon={Phone} label="Teléfono" value={patient.phone || '-'} />
            <InfoRow icon={MapPin} label="Dirección" value={patient.address || '-'} />
            <InfoRow icon={Phone} label="Contacto de Emergencia" value={patient.emergency_contact || '-'} />
            <div className="pt-2 border-t border-gray-100">
              <h4 className="text-xs font-semibold text-gray-600 mb-2">Antecedentes</h4>
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${patient.family_diabetes_history ? 'bg-risk-high' : 'bg-gray-300'}`} />
                  <span className="text-xs text-gray-600">
                    Antecedentes Familiares DM2: {patient.family_diabetes_history ? 'Sí' : 'No'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${patient.hypertension_history ? 'bg-risk-medium' : 'bg-gray-300'}`} />
                  <span className="text-xs text-gray-600">
                    Historial de Hipertensión: {patient.hypertension_history ? 'Sí' : 'No'}
                  </span>
                </div>
              </div>
            </div>
            {patient.notes && (
              <div className="pt-2 border-t border-gray-100">
                <InfoRow icon={FileText} label="Notas" value={patient.notes} />
              </div>
            )}
          </div>
        </div>

        {/* Clinical data card */}
        <div className="dashboard-card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <Heart className="w-4 h-4 text-risk-high" />
            Últimos Datos Clínicos
          </h3>
          {clinicalData ? (
            <div className="space-y-3">
              <VitalCard
                label="Presión Arterial"
                value={`${clinicalData.systolic_bp || '-'}/${clinicalData.diastolic_bp || '-'} mmHg`}
                color="text-risk-medium"
              />
              <VitalCard
                label="Peso"
                value={clinicalData.weight ? `${clinicalData.weight} kg` : '-'}
                color="text-primary-500"
              />
              {clinicalData.height && (
                <VitalCard
                  label="Altura"
                  value={`${clinicalData.height} cm`}
                  color="text-primary-500"
                />
              )}
              {bmi.bmi && (
                <VitalCard
                  label="IMC"
                  value={`${bmi.bmi} (${bmi.category})`}
                  color={
                    bmi.category === 'Normal'
                      ? 'text-risk-low'
                      : bmi.category === 'Sobrepeso' || bmi.category === 'Obesidad'
                      ? 'text-risk-high'
                      : 'text-risk-medium'
                  }
                />
              )}
              {clinicalData.age && (
                <VitalCard
                  label="Edad al Registro"
                  value={`${clinicalData.age} años`}
                  color="text-primary-500"
                />
              )}
              <p className="text-[10px] text-gray-400 pt-2 border-t border-gray-100">
                Registrado: {new Date(clinicalData.created_at).toLocaleString('es-ES')}
              </p>
            </div>
          ) : (
            <div className="text-center py-6 text-gray-400">
              <Activity className="w-8 h-8 mx-auto mb-2" />
              <p className="text-sm">Sin datos clínicos registrados</p>
              <button
                onClick={() => navigate(`/clinical-data/${id}`)}
                className="btn-primary gap-2 mt-3 text-xs"
              >
                <ClipboardList className="w-3 h-3" />
                Registrar Datos
              </button>
            </div>
          )}
        </div>

        {/* Latest prediction */}
        <div className="dashboard-card">
          <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-risk-medium" />
            Última Predicción
          </h3>
          {latestPrediction ? (
            <div className="space-y-4">
              <div className="text-center">
                <div
                  className={`inline-flex items-center justify-center w-20 h-20 rounded-full text-white text-lg font-bold ${
                    latestPrediction.risk_level?.toLowerCase() === 'high' ||
                    latestPrediction.risk_level?.toLowerCase() === 'alto'
                      ? 'bg-risk-high'
                      : latestPrediction.risk_level?.toLowerCase() === 'medium' ||
                        latestPrediction.risk_level?.toLowerCase() === 'medio'
                      ? 'bg-risk-medium'
                      : 'bg-risk-low'
                  }`}
                >
                  {((latestPrediction.risk_probability || 0) * 100).toFixed(0)}%
                </div>
                <p className="mt-2 text-sm font-medium text-gray-700">
                  Riesgo {getRiskLabel(latestPrediction.risk_level)}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  Probabilidad: {((latestPrediction.risk_probability || 0) * 100).toFixed(1)}%
                </p>
              </div>
              {latestPrediction.recommended_action && (
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-xs font-medium text-gray-600 mb-1">Acción Recomendada</p>
                  <p className="text-xs text-gray-700">{latestPrediction.recommended_action}</p>
                </div>
              )}
              <p className="text-[10px] text-gray-400">
                Fecha: {new Date(latestPrediction.created_at).toLocaleString('es-ES')}
              </p>
              <button
                onClick={() => navigate(`/predict/${id}`)}
                className="btn-primary gap-2 w-full text-xs"
              >
                <TrendingUp className="w-3 h-3" />
                Nueva Predicción
              </button>
            </div>
          ) : (
            <div className="text-center py-6 text-gray-400">
              <AlertTriangle className="w-8 h-8 mx-auto mb-2" />
              <p className="text-sm">Sin predicciones</p>
              <button
                onClick={() => navigate(`/predict/${id}`)}
                className="btn-primary gap-2 mt-3 text-xs"
              >
                <TrendingUp className="w-3 h-3" />
                Generar Predicción
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Glucose chart */}
      <div className="dashboard-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary-500" />
            Lecturas de Glucosa
          </h3>
          <button onClick={fetchPatientData} className="text-gray-400 hover:text-gray-600">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
        <GlucoseChart readings={glucoseReadings} />
      </div>

      {/* Prediction history */}
      {predictions.length > 1 && (
        <div className="dashboard-card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-primary-500" />
              Historial de Predicciones
            </h3>
            <button
              onClick={() => navigate(`/history/${id}`)}
              className="text-xs text-primary-500 hover:text-primary-700 font-medium"
            >
              Ver todo
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="table-header px-4 py-2">Fecha</th>
                  <th className="table-header px-4 py-2">Probabilidad</th>
                  <th className="table-header px-4 py-2">Nivel</th>
                </tr>
              </thead>
              <tbody>
                {predictions
                  .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                  .slice(0, 5)
                  .map((pred, idx) => (
                    <tr key={pred.id || idx} className="border-b border-gray-50">
                      <td className="table-cell text-xs">
                        {new Date(pred.created_at).toLocaleString('es-ES')}
                      </td>
                      <td className="table-cell text-xs font-medium">
                        {((pred.risk_probability || 0) * 100).toFixed(1)}%
                      </td>
                      <td className="table-cell">
                        <span className={getRiskBadgeClass(pred.risk_level)}>
                          {getRiskLabel(pred.risk_level)}
                        </span>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function InfoRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-start gap-2">
      <Icon className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
      <div>
        <p className="text-[10px] text-gray-500">{label}</p>
        <p className="text-sm text-gray-800">{value}</p>
      </div>
    </div>
  )
}

function VitalCard({ label, value, color }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`text-sm font-semibold ${color}`}>{value}</span>
    </div>
  )
}
