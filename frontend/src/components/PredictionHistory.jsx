import React, { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import api from '../api/axios'
import { getRiskBadgeClass, getRiskLabel } from '../utils/validation'
import {
  ArrowLeft,
  TrendingUp,
  ChevronLeft,
  ChevronRight,
  Calendar,
  RefreshCw,
} from 'lucide-react'

const ITEMS_PER_PAGE = 10

export default function PredictionHistory() {
  const navigate = useNavigate()
  const { patientId } = useParams()
  const [predictions, setPredictions] = useState([])
  const [patient, setPatient] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [sortDir, setSortDir] = useState('desc')

  useEffect(() => {
    fetchData()
  }, [patientId])

  const fetchData = async () => {
    setLoading(true)
    setError('')
    try {
      const [patientRes, predictionsRes] = await Promise.all([
        api.get(`/patients/${patientId}`).catch(() => null),
        api.get(`/predictions/${patientId}`).catch(() => ({ data: [] })),
      ])
      if (patientRes) setPatient(patientRes.data)
      setPredictions(predictionsRes.data || [])
    } catch {
      setError('Error al cargar el historial de predicciones')
    } finally {
      setLoading(false)
    }
  }

  const sorted = [...predictions].sort((a, b) => {
    const dateA = new Date(a.created_at)
    const dateB = new Date(b.created_at)
    return sortDir === 'desc' ? dateB - dateA : dateA - dateB
  })

  const totalPages = Math.ceil(sorted.length / ITEMS_PER_PAGE)
  const paginated = sorted.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  )

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
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="btn-secondary p-2"
          title="Volver"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-gray-800">Historial de Predicciones</h1>
          <p className="text-sm text-gray-500">
            {patient
              ? `${patient.first_name} ${patient.last_name}`
              : 'Paciente'}{' '}
            - {predictions.length} predicción{predictions.length !== 1 ? 'es' : ''}
          </p>
        </div>
        <button onClick={fetchData} className="btn-secondary gap-2" title="Actualizar">
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      {sorted.length === 0 ? (
        <div className="dashboard-card flex flex-col items-center justify-center py-12 text-gray-400">
          <TrendingUp className="w-12 h-12 mb-3" />
          <p className="text-sm font-medium">Sin predicciones registradas</p>
          <button
            onClick={() => navigate(`/predict/${patientId}`)}
            className="btn-primary gap-2 mt-4 text-xs"
          >
            <TrendingUp className="w-3 h-3" />
            Generar Primera Predicción
          </button>
        </div>
      ) : (
        <>
          <div className="dashboard-card p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th
                      className="table-header px-4 py-3 cursor-pointer hover:text-gray-700"
                      onClick={() => {
                        setSortDir((prev) => (prev === 'desc' ? 'asc' : 'desc'))
                        setCurrentPage(1)
                      }}
                    >
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5" />
                        Fecha {sortDir === 'desc' ? '↓' : '↑'}
                      </span>
                    </th>
                    <th className="table-header px-4 py-3">Probabilidad</th>
                    <th className="table-header px-4 py-3">Nivel de Riesgo</th>
                    <th className="table-header px-4 py-3">Lecturas</th>
                    <th className="table-header px-4 py-3">Método XAI</th>
                    <th className="table-header px-4 py-3">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {paginated.map((pred, idx) => (
                    <tr
                      key={pred.id || idx}
                      className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                    >
                      <td className="table-cell text-sm">
                        {pred.created_at
                          ? new Date(pred.created_at).toLocaleString('es-ES')
                          : '-'}
                      </td>
                      <td className="table-cell">
                        <span className="text-sm font-semibold text-gray-800">
                          {((pred.risk_probability || 0) * 100).toFixed(1)}%
                        </span>
                      </td>
                      <td className="table-cell">
                        <span className={getRiskBadgeClass(pred.risk_level)}>
                          {getRiskLabel(pred.risk_level)}
                        </span>
                      </td>
                      <td className="table-cell text-xs text-gray-500">
                        {pred.glucose_readings_used
                          ? `${pred.glucose_readings_used} lect.`
                          : '-'}
                      </td>
                      <td className="table-cell text-xs">
                        {pred.shap_explanation?.method_used ? (
                          <span className="px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 font-mono text-[10px]">
                            {pred.shap_explanation.method_used === 'shap_kernel' ? 'SHAP' :
                             pred.shap_explanation.method_used === 'integrated_gradients' ? 'IG' :
                             pred.shap_explanation.method_used === 'heuristic' ? 'Heur.' :
                             pred.shap_explanation.method_used}
                          </span>
                        ) : (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                      <td className="table-cell">
                        {pred.shap_explanation ? (
                          <button
                            onClick={() => navigate(`/predict/${patientId}`)}
                            className="text-xs text-primary-600 hover:text-primary-800 underline"
                          >
                            Ver detalle
                          </button>
                        ) : (
                          <span className="text-gray-400 text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-gray-500">
                Mostrando {(currentPage - 1) * ITEMS_PER_PAGE + 1} a{' '}
                {Math.min(currentPage * ITEMS_PER_PAGE, sorted.length)} de {sorted.length}
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="btn-secondary p-2 disabled:opacity-50"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                  <button
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    className={`w-8 h-8 rounded-lg text-sm font-medium transition-colors ${
                      page === currentPage
                        ? 'bg-primary-500 text-white'
                        : 'text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    {page}
                  </button>
                ))}
                <button
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="btn-secondary p-2 disabled:opacity-50"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
