import React, { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api/axios'
import { getRiskLabel } from '../utils/validation'
import {
  TrendingUp,
  ArrowLeft,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  AlertCircle,
  Shield,
  Activity,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

export default function PredictionView() {
  const navigate = useNavigate()
  const { patientId } = useParams()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [prediction, setPrediction] = useState(null)
  const [patient, setPatient] = useState(null)

  useEffect(() => {
    fetchPatientAndPredict()
  }, [patientId])

  const fetchPatientAndPredict = async () => {
    setLoading(true)
    setError('')
    try {
      // Fetch patient info
      const patientRes = await api.get(`/patients/${patientId}`)
      setPatient(patientRes.data)

      // Generate prediction
      const predRes = await api.post(`/predict/${patientId}`)
      setPrediction(predRes.data)
    } catch (err) {
      if (err.response?.status === 404) {
        setError('No se encontraron datos clínicos para este paciente. Registre datos clínicos primero.')
      } else if (err.response?.status === 422) {
        setError('Datos insuficientes para generar una predicción. Complete el perfil clínico del paciente.')
      } else {
        setError(err.response?.data?.detail || 'Error al generar la predicción')
      }
    } finally {
      setLoading(false)
    }
  }

  const generateNewPrediction = async () => {
    setLoading(true)
    setError('')
    try {
      const predRes = await api.post(`/predict/${patientId}`)
      setPrediction(predRes.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al generar la predicción')
    } finally {
      setLoading(false)
    }
  }

  const getRiskColor = (level) => {
    switch (level?.toLowerCase()) {
      case 'high':
      case 'alto':
        return { bg: 'bg-risk-high', text: 'text-risk-high', light: 'bg-risk-high-light', border: 'border-risk-high' }
      case 'medium':
      case 'medio':
        return { bg: 'bg-risk-medium', text: 'text-risk-medium', light: 'bg-risk-medium-light', border: 'border-risk-medium' }
      case 'low':
      case 'bajo':
      default:
        return { bg: 'bg-risk-low', text: 'text-risk-low', light: 'bg-risk-low-light', border: 'border-risk-low' }
    }
  }

  const getRecommendedAction = (level) => {
    switch (level?.toLowerCase()) {
      case 'high':
      case 'alto':
        return {
          icon: AlertTriangle,
          text: 'Referir a especialista de inmediato. Iniciar protocolo de seguimiento intensivo. Monitoreo continuo de glucosa y signos vitales.',
          urgency: 'URGENTE',
        }
      case 'medium':
      case 'medio':
        return {
          icon: AlertCircle,
          text: 'Programar consulta de seguimiento en 2-4 semanas. Reforzar medidas de estilo de vida. Monitoreo periódico de glucosa.',
          urgency: 'MODERADA',
        }
      case 'low':
      case 'bajo':
      default:
        return {
          icon: CheckCircle,
          text: 'Continuar con seguimiento rutinario. Promover hábitos saludables. Próxima evaluación en 6 meses.',
          urgency: 'RUTINARIA',
        }
    }
  }

  // Parse SHAP features if available
  const getShapData = () => {
    if (!prediction?.feature_importance && !prediction?.shap_values) return []

    // Handle different API response formats
    if (Array.isArray(prediction.feature_importance)) {
      return prediction.feature_importance
        .map((f) => ({
          name: f.feature || f.name,
          value: Math.abs(f.importance || f.value || f.shap_value || 0),
          direction: (f.importance || f.value || f.shap_value || 0) >= 0 ? 'positive' : 'negative',
        }))
        .sort((a, b) => b.value - a.value)
    }

    if (typeof prediction.feature_importance === 'object') {
      return Object.entries(prediction.feature_importance)
        .map(([name, value]) => ({
          name,
          value: Math.abs(value),
          direction: value >= 0 ? 'positive' : 'negative',
        }))
        .sort((a, b) => b.value - a.value)
    }

    if (prediction.shap_values) {
      const shap = prediction.shap_values
      if (typeof shap === 'object') {
        return Object.entries(shap)
          .map(([name, value]) => ({
            name,
            value: Math.abs(value),
            direction: value >= 0 ? 'positive' : 'negative',
          }))
          .sort((a, b) => b.value - a.value)
      }
    }

    return []
  }

  const shapData = getShapData()
  const riskColors = getRiskColor(prediction?.risk_level)
  const riskAction = prediction ? getRecommendedAction(prediction.risk_level) : null

  // Translate feature names
  const translateFeature = (name) => {
    const translations = {
      glucose_level: 'Glucosa',
      systolic_bp: 'Presión Sistólica',
      diastolic_bp: 'Presión Diastólica',
      weight: 'Peso',
      bmi: 'IMC',
      age: 'Edad',
      family_diabetes_history: 'Antecedentes DM2',
      hypertension_history: 'Hipertensión',
      height: 'Altura',
    }
    return translations[name] || name
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner"></div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="btn-secondary p-2"
          title="Volver"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-gray-800">Resultado de Predicción</h1>
          <p className="text-sm text-gray-500">
            {patient
              ? `${patient.first_name} ${patient.last_name}`
              : 'Paciente'}
          </p>
        </div>
        <button
          onClick={generateNewPrediction}
          disabled={loading}
          className="btn-primary gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Nueva Predicción
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="dashboard-card border-red-200 bg-red-50">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-800">{error}</p>
              <button
                onClick={() => navigate(`/clinical-data/${patientId}`)}
                className="mt-2 text-xs text-red-700 underline hover:no-underline"
              >
                Registrar datos clínicos
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Prediction result */}
      {prediction && (
        <>
          {/* Main risk indicator */}
          <div className={`dashboard-card border-2 ${riskColors.border}`}>
            <div className="flex flex-col sm:flex-row items-center gap-6">
              {/* Risk circle */}
              <div className="flex-shrink-0">
                <div
                  className={`w-32 h-32 rounded-full ${riskColors.bg} flex flex-col items-center justify-center text-white`}
                >
                  <span className="text-3xl font-bold">
                    {((prediction.risk_probability || 0) * 100).toFixed(1)}%
                  </span>
                  <span className="text-xs mt-1 opacity-80">probabilidad</span>
                </div>
              </div>

              {/* Risk details */}
              <div className="flex-1 text-center sm:text-left">
                <div className="flex items-center gap-2 justify-center sm:justify-start">
                  <Shield className={`w-6 h-6 ${riskColors.text}`} />
                  <h2 className={`text-2xl font-bold ${riskColors.text}`}>
                    Riesgo {getRiskLabel(prediction.risk_level)}
                  </h2>
                </div>
                <p className="text-sm text-gray-600 mt-2">
                  El modelo predice un{' '}
                  <strong>{((prediction.risk_probability || 0) * 100).toFixed(1)}%</strong> de
                  probabilidad de desarrollar Diabetes Tipo 2.
                </p>
                <p className="text-xs text-gray-400 mt-2">
                  Fecha de predicción:{' '}
                  {prediction.created_at
                    ? new Date(prediction.created_at).toLocaleString('es-ES')
                    : new Date().toLocaleString('es-ES')}
                </p>
              </div>
            </div>
          </div>

          {/* Recommended action */}
          {riskAction && (
            <div className={`dashboard-card border ${riskColors.border}`}>
              <div className="flex items-start gap-3">
                <riskAction.icon className={`w-5 h-5 ${riskColors.text} flex-shrink-0 mt-0.5`} />
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-bold px-2 py-0.5 rounded ${riskColors.bg} text-white`}>
                      {riskAction.urgency}
                    </span>
                    <h3 className="text-sm font-semibold text-gray-800">
                      Acción Clínica Recomendada
                    </h3>
                  </div>
                  <p className="text-sm text-gray-700">{riskAction.text}</p>
                </div>
              </div>
            </div>
          )}

          {/* SHAP feature importance chart */}
          {shapData.length > 0 && (
            <div className="dashboard-card">
              <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <Activity className="w-4 h-4 text-primary-500" />
                Factores de Influencia (SHAP)
              </h3>
              <p className="text-xs text-gray-500 mb-4">
                Los siguientes factores contribuyen más a la predicción del riesgo:
              </p>
              <ResponsiveContainer width="100%" height={shapData.length * 40 + 40}>
                <BarChart
                  data={shapData.slice(0, 8)}
                  layout="vertical"
                  margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis
                    dataKey="name"
                    type="category"
                    tick={{ fontSize: 11 }}
                    width={120}
                    tickFormatter={translateFeature}
                  />
                  <Tooltip
                    formatter={(value, name) => [value.toFixed(4), 'Importancia']}
                    labelFormatter={translateFeature}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={20}>
                    {shapData.slice(0, 8).map((entry, index) => (
                      <Cell
                        key={index}
                        fill={
                          entry.direction === 'positive'
                            ? '#8e4f49'
                            : '#47805a'
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
                <div className="flex items-center gap-1">
                  <div className="w-3 h-3 rounded bg-risk-high" />
                  <span>Incrementa riesgo</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-3 h-3 rounded bg-risk-low" />
                  <span>Reduce riesgo</span>
                </div>
              </div>
            </div>
          )}

          {/* Quick actions */}
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => navigate(`/patients/${patientId}`)}
              className="btn-secondary gap-2"
            >
              Ver Paciente
            </button>
            <button
              onClick={() => navigate(`/history/${patientId}`)}
              className="btn-secondary gap-2"
            >
              Historial de Predicciones
            </button>
            <button
              onClick={() => navigate(`/clinical-data/${patientId}`)}
              className="btn-secondary gap-2"
            >
              Registrar Nuevos Datos
            </button>
          </div>
        </>
      )}
    </div>
  )
}
