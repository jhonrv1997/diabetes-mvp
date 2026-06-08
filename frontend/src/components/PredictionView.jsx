import React, { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api/axios'
import { getRiskLabel } from '../utils/validation'
import SHAPWaterfall from './SHAPWaterfall'
import {
  TrendingUp,
  ArrowLeft,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  AlertCircle,
  Shield,
  Activity,
  Info,
  ChevronDown,
  ChevronUp,
  Heart,
  Brain,
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

// Feature name translations
const FEATURE_TRANSLATIONS = {
  glucose_avg: 'Glucosa promedio',
  glucose_std: 'Variabilidad glucosa',
  glucose_trend: 'Tendencia glucosa',
  age: 'Edad',
  bmi: 'IMC',
  systolic_bp: 'Presión sistólica',
  diastolic_bp: 'Presión diastólica',
  family_diabetes: 'Antecedentes DM2',
  hypertension: 'Hipertensión',
  glucose_level: 'Glucosa',
  weight: 'Peso',
  height: 'Altura',
  family_diabetes_history: 'Antecedentes DM2',
  hypertension_history: 'Hipertensión',
}

export default function PredictionView() {
  const navigate = useNavigate()
  const { patientId } = useParams()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [prediction, setPrediction] = useState(null)
  const [patient, setPatient] = useState(null)
  const [showWaterfall, setShowWaterfall] = useState(true)
  const [showDetailTable, setShowDetailTable] = useState(true)
  const [showClinicalNarrative, setShowClinicalNarrative] = useState(true)

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

  // Translate feature names
  const translateFeature = (name) => {
    return FEATURE_TRANSLATIONS[name] || name
  }

  // Get SHAP explanation data
  const getShapExplanation = () => {
    return prediction?.shap_explanation || null
  }

  // Get legacy SHAP bar chart data (for simple bar chart)
  const getShapBarData = () => {
    const explanation = getShapExplanation()
    if (!explanation?.shap_values) {
      // Fallback to legacy format
      if (prediction?.shap_values && typeof prediction.shap_values === 'object') {
        return Object.entries(prediction.shap_values)
          .map(([name, value]) => ({
            name,
            value: Math.abs(value),
            direction: value >= 0 ? 'positive' : 'negative',
          }))
          .sort((a, b) => b.value - a.value)
      }
      return []
    }

    return Object.entries(explanation.shap_values)
      .map(([name, value]) => ({
        name,
        value: Math.abs(value),
        direction: value >= 0 ? 'positive' : 'negative',
      }))
      .sort((a, b) => b.value - a.value)
  }

  // Check if a feature value is outside normal range
  const isAbnormal = (feature, value) => {
    const explanation = getShapExplanation()
    if (!explanation?.feature_meta?.[feature]) return false
    const meta = explanation.feature_meta[feature]
    if (meta.normal_low === 0 && meta.normal_high === 100) return false // Skip if no range defined
    return value < meta.normal_low || value > meta.normal_high
  }

  const shapBarData = getShapBarData()
  const shapExplanation = getShapExplanation()
  const riskColors = getRiskColor(prediction?.risk_level)
  const riskAction = prediction ? getRecommendedAction(prediction.risk_level) : null

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="spinner"></div>
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
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
          {/* ── Main risk indicator ──────────────────────────────────── */}
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
                {shapExplanation?.base_value != null && (
                  <p className="text-xs text-gray-500 mt-1">
                    Valor base poblacional: <strong>{(shapExplanation.base_value * 100).toFixed(1)}%</strong>
                    {' '}→ Los factores del paciente{' '}
                    {shapExplanation.prediction > shapExplanation.base_value ? 'aumentan' : 'reducen'}{' '}
                    el riesgo en{' '}
                    <strong>{Math.abs((shapExplanation.prediction - shapExplanation.base_value) * 100).toFixed(1)} pp</strong>
                  </p>
                )}
                <p className="text-xs text-gray-400 mt-2">
                  Fecha de predicción:{' '}
                  {prediction.created_at
                    ? new Date(prediction.created_at).toLocaleString('es-ES')
                    : new Date().toLocaleString('es-ES')}
                  {shapExplanation?.method_used && (
                    <> · Método XAI: <span className="font-mono text-xs">{shapExplanation.method_used}</span></>
                  )}
                </p>
              </div>
            </div>
          </div>

          {/* ── Recommended action ───────────────────────────────────── */}
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

          {/* ── Clinical Interpretation Narrative ────────────────────── */}
          {shapExplanation?.clinical_interpretation && (
            <div className="dashboard-card">
              <button
                onClick={() => setShowClinicalNarrative(!showClinicalNarrative)}
                className="w-full flex items-center justify-between"
              >
                <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                  <Brain className="w-4 h-4 text-indigo-500" />
                  Interpretación Clínica
                </h3>
                {showClinicalNarrative ? (
                  <ChevronUp className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                )}
              </button>

              {showClinicalNarrative && (
                <div className="mt-4 space-y-4">
                  {/* Summary */}
                  <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-4">
                    <p className="text-sm text-gray-800 leading-relaxed">
                      {shapExplanation.clinical_interpretation.summary}
                    </p>
                  </div>

                  {/* Per-feature notes */}
                  {shapExplanation.clinical_interpretation.feature_notes?.length > 0 && (
                    <div className="space-y-2">
                      {shapExplanation.clinical_interpretation.feature_notes.map((note, idx) => (
                        <div
                          key={idx}
                          className={`flex items-start gap-2 p-3 rounded-lg border ${
                            note.is_abnormal
                              ? 'bg-red-50 border-red-200'
                              : 'bg-gray-50 border-gray-100'
                          }`}
                        >
                          <div
                            className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                              note.direction === 'aumenta' ? 'bg-red-500' : 'bg-green-500'
                            }`}
                          />
                          <div className="flex-1">
                            <p className="text-sm text-gray-700">{note.note}</p>
                          </div>
                          <span className="text-xs font-medium text-gray-500 whitespace-nowrap">
                            {note.contribution_pct.toFixed(1)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Recommendation */}
                  <div className="bg-blue-50 border border-blue-100 rounded-lg p-4">
                    <div className="flex items-start gap-2">
                      <Heart className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
                      <p className="text-sm text-gray-800 leading-relaxed">
                        {shapExplanation.clinical_interpretation.recommendation}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── SHAP Waterfall Chart ─────────────────────────────────── */}
          {shapExplanation && (
            <div className="dashboard-card">
              <button
                onClick={() => setShowWaterfall(!showWaterfall)}
                className="w-full flex items-center justify-between"
              >
                <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-primary-500" />
                  Explicación de Factores (SHAP Waterfall)
                </h3>
                {showWaterfall ? (
                  <ChevronUp className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                )}
              </button>
              {showWaterfall && (
                <div className="mt-4">
                  <p className="text-xs text-gray-500 mb-3">
                    Este gráfico muestra cómo cada factor empuja la predicción desde el valor base
                    poblacional hasta la predicción final. Las barras rojas aumentan el riesgo,
                    las verdes lo reducen.
                  </p>
                  <SHAPWaterfall explanation={shapExplanation} />
                </div>
              )}
            </div>
          )}

          {/* ── SHAP Feature Importance Bar Chart ────────────────────── */}
          {shapBarData.length > 0 && (
            <div className="dashboard-card">
              <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-primary-500" />
                Importancia de Factores (SHAP)
              </h3>
              <p className="text-xs text-gray-500 mb-4">
                Los siguientes factores contribuyen más a la predicción del riesgo,
                ordenados por magnitud de impacto:
              </p>
              <ResponsiveContainer width="100%" height={shapBarData.length * 40 + 40}>
                <BarChart
                  data={shapBarData.slice(0, 9)}
                  layout="vertical"
                  margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis
                    dataKey="name"
                    type="category"
                    tick={{ fontSize: 11 }}
                    width={140}
                    tickFormatter={translateFeature}
                  />
                  <Tooltip
                    formatter={(value, name) => [value.toFixed(4), 'Importancia SHAP']}
                    labelFormatter={translateFeature}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={20}>
                    {shapBarData.slice(0, 9).map((entry, index) => (
                      <Cell
                        key={index}
                        fill={
                          entry.direction === 'positive'
                            ? '#ef4444'
                            : '#22c55e'
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
                <div className="flex items-center gap-1">
                  <div className="w-3 h-3 rounded bg-red-500" />
                  <span>Incrementa riesgo</span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-3 h-3 rounded bg-green-500" />
                  <span>Reduce riesgo</span>
                </div>
              </div>
            </div>
          )}

          {/* ── Feature Detail Table ─────────────────────────────────── */}
          {shapExplanation?.shap_values && (
            <div className="dashboard-card">
              <button
                onClick={() => setShowDetailTable(!showDetailTable)}
                className="w-full flex items-center justify-between"
              >
                <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                  <Info className="w-4 h-4 text-primary-500" />
                  Detalle de Factores por Paciente
                </h3>
                {showDetailTable ? (
                  <ChevronUp className="w-4 h-4 text-gray-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-gray-400" />
                )}
              </button>

              {showDetailTable && (
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200">
                        <th className="text-left py-2 px-3 text-gray-600 font-medium">Factor</th>
                        <th className="text-right py-2 px-3 text-gray-600 font-medium">Valor</th>
                        <th className="text-right py-2 px-3 text-gray-600 font-medium">Rango Normal</th>
                        <th className="text-right py-2 px-3 text-gray-600 font-medium">SHAP</th>
                        <th className="text-right py-2 px-3 text-gray-600 font-medium">Impacto</th>
                        <th className="text-center py-2 px-3 text-gray-600 font-medium">Dirección</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shapExplanation.top_risk_factors?.map((factor, idx) => {
                        const meta = shapExplanation.feature_meta?.[factor.feature] || {}
                        const isAbn = isAbnormal(factor.feature, factor.value)
                        return (
                          <tr
                            key={idx}
                            className={`border-b border-gray-100 ${isAbn ? 'bg-red-50/50' : ''}`}
                          >
                            <td className="py-2 px-3">
                              <span className="font-medium text-gray-800">
                                {meta.label || translateFeature(factor.feature)}
                              </span>
                              {isAbn && (
                                <span className="ml-1 text-xs text-red-500 font-medium">
                                  ⚠
                                </span>
                              )}
                            </td>
                            <td className="py-2 px-3 text-right text-gray-700">
                              {factor.value !== null && factor.value !== undefined
                                ? `${factor.value}${meta.unit ? ' ' + meta.unit : ''}`
                                : '—'}
                            </td>
                            <td className="py-2 px-3 text-right text-gray-500 text-xs">
                              {meta.normal_low != null && meta.normal_high != null
                                ? `${meta.normal_low} – ${meta.normal_high} ${meta.unit || ''}`
                                : '—'}
                            </td>
                            <td className="py-2 px-3 text-right font-mono text-xs">
                              <span className={factor.shap_value >= 0 ? 'text-red-600' : 'text-green-600'}>
                                {factor.shap_value >= 0 ? '+' : ''}{factor.shap_value.toFixed(4)}
                              </span>
                            </td>
                            <td className="py-2 px-3 text-right text-gray-600">
                              {factor.importance_pct.toFixed(1)}%
                            </td>
                            <td className="py-2 px-3 text-center">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                                  factor.direction === 'increases'
                                    ? 'bg-red-100 text-red-700'
                                    : factor.direction === 'decreases'
                                    ? 'bg-green-100 text-green-700'
                                    : 'bg-gray-100 text-gray-600'
                                }`}
                              >
                                {factor.direction === 'increases'
                                  ? '↑ Riesgo'
                                  : factor.direction === 'decreases'
                                  ? '↓ Riesgo'
                                  : '— Neutral'}
                              </span>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                    {shapExplanation.base_value != null && (
                      <tfoot>
                        <tr className="border-t-2 border-gray-300">
                          <td className="py-2 px-3 font-semibold text-gray-700" colSpan={3}>
                            Valor base (E[f])
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-xs" colSpan={3}>
                            {(shapExplanation.base_value * 100).toFixed(1)}%
                          </td>
                        </tr>
                        <tr>
                          <td className="py-2 px-3 font-semibold text-indigo-700" colSpan={3}>
                            Predicción final
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-xs font-bold text-indigo-700" colSpan={3}>
                            {(shapExplanation.prediction * 100).toFixed(1)}%
                          </td>
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ── Method Info ──────────────────────────────────────────── */}
          {shapExplanation?.method_used && (
            <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
              <div className="flex items-start gap-2">
                <Info className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" />
                <div className="text-xs text-gray-600">
                  <p className="font-medium mb-1">Sobre el método de explicación</p>
                  {shapExplanation.method_used === 'shap_kernel' && (
                    <p>
                      Se utilizó <strong>SHAP KernelExplainer</strong>, un método modelo-agnóstico
                      que calcula la contribución exacta de cada factor según la teoría de valores
                      de Shapley. Esto garantiza que la suma de todas las contribuciones más el
                      valor base iguala la predicción del modelo.
                    </p>
                  )}
                  {shapExplanation.method_used === 'integrated_gradients' && (
                    <p>
                      Se utilizó <strong>Integrated Gradients</strong>, un método basado en gradientes
                      que calcula la contribución de cada factor integrando los gradientes del modelo
                      desde un valor base hasta la entrada actual.
                    </p>
                  )}
                  {shapExplanation.method_used === 'heuristic' && (
                    <p>
                      Se utilizó un <strong>método heurístico</strong> basado en umbrales clínicos,
                      ya que el modelo de ML no está disponible. Las contribuciones son aproximaciones
                      basadas en rangos clínicos conocidos.
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ── Quick actions ────────────────────────────────────────── */}
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
