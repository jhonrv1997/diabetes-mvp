import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/axios'
import { getRiskBadgeClass, getRiskLabel } from '../utils/validation'
import {
  Users,
  AlertTriangle,
  Activity,
  Bell,
  Plus,
  TrendingUp,
  ChevronRight,
  RefreshCw,
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

export default function Dashboard() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [patients, setPatients] = useState([])
  const [predictions, setPredictions] = useState([])
  const [alerts, setAlerts] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    fetchDashboardData()
  }, [])

  const fetchDashboardData = async () => {
    setLoading(true)
    setError('')
    try {
      const [patientsRes, predictionsRes, alertsRes] = await Promise.all([
        api.get('/patients').catch(() => ({ data: [] })),
        api.get('/predictions').catch(() => ({ data: [] })),
        api.get('/alerts').catch(() => ({ data: [] })),
      ])
      setPatients(patientsRes.data || [])
      setPredictions(predictionsRes.data || [])
      setAlerts(alertsRes.data || [])
    } catch {
      setError('Error al cargar los datos del dashboard')
    } finally {
      setLoading(false)
    }
  }

  // Calculate summary stats
  const highRiskCount = predictions.filter(
    (p) => p.risk_level?.toLowerCase() === 'high' || p.risk_level?.toLowerCase() === 'alto'
  ).length
  const mediumRiskCount = predictions.filter(
    (p) => p.risk_level?.toLowerCase() === 'medium' || p.risk_level?.toLowerCase() === 'medio'
  ).length
  const activeAlertsCount = alerts.filter((a) => a.is_active).length

  // Risk distribution chart data
  const riskDistribution = [
    { name: 'Bajo', count: predictions.filter((p) => p.risk_level?.toLowerCase() === 'low' || p.risk_level?.toLowerCase() === 'bajo').length, color: '#47805a' },
    { name: 'Medio', count: mediumRiskCount, color: '#9b8048' },
    { name: 'Alto', count: highRiskCount, color: '#8e4f49' },
  ]

  // Get latest prediction per patient
  const getLatestPrediction = (patientId) => {
    const patientPreds = predictions
      .filter((p) => p.patient_id === patientId)
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    return patientPreds[0] || null
  }

  // Recent high-risk alerts (last 5)
  const recentHighAlerts = alerts
    .filter((a) => a.is_active && a.severity?.toLowerCase() === 'high')
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 5)

  const getPatientName = (patientId) => {
    const patient = patients.find((p) => p.id === patientId)
    return patient ? `${patient.first_name} ${patient.last_name}` : 'Desconocido'
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
        <button onClick={fetchDashboardData} className="btn-primary gap-2">
          <RefreshCw className="w-4 h-4" />
          Reintentar
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">Resumen general del sistema</p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchDashboardData} className="btn-secondary gap-2" title="Actualizar">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigate('/patients/new')}
            className="btn-primary gap-2"
          >
            <Plus className="w-4 h-4" />
            Nuevo Paciente
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="dashboard-card flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-primary-50 flex items-center justify-center">
            <Users className="w-6 h-6 text-primary-500" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Total Pacientes</p>
            <p className="text-2xl font-bold text-gray-800">{patients.length}</p>
          </div>
        </div>

        <div className="dashboard-card flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-risk-high-light flex items-center justify-center">
            <AlertTriangle className="w-6 h-6 text-risk-high" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Riesgo Alto</p>
            <p className="text-2xl font-bold text-risk-high">{highRiskCount}</p>
          </div>
        </div>

        <div className="dashboard-card flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-risk-medium-light flex items-center justify-center">
            <TrendingUp className="w-6 h-6 text-risk-medium" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Riesgo Medio</p>
            <p className="text-2xl font-bold text-risk-medium">{mediumRiskCount}</p>
          </div>
        </div>

        <div className="dashboard-card flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-red-50 flex items-center justify-center">
            <Bell className="w-6 h-6 text-red-500" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Alertas Activas</p>
            <p className="text-2xl font-bold text-red-600">{activeAlertsCount}</p>
          </div>
        </div>
      </div>

      {/* Charts and tables row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Risk distribution chart */}
        <div className="dashboard-card lg:col-span-1">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            Distribución de Riesgo
          </h3>
          {predictions.length === 0 ? (
            <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
              Sin predicciones aún
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={riskDistribution} barSize={50}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                <Tooltip />
                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                  {riskDistribution.map((entry, index) => (
                    <Cell key={index} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Patient list */}
        <div className="dashboard-card lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-700">Pacientes Recientes</h3>
            <button
              onClick={() => navigate('/patients')}
              className="text-xs text-primary-500 hover:text-primary-700 font-medium flex items-center gap-1"
            >
              Ver todos <ChevronRight className="w-3 h-3" />
            </button>
          </div>
          {patients.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-gray-400">
              <Users className="w-10 h-10 mb-2" />
              <p className="text-sm">No hay pacientes registrados</p>
              <button
                onClick={() => navigate('/patients/new')}
                className="btn-primary gap-2 mt-3 text-xs"
              >
                <Plus className="w-3 h-3" />
                Registrar Paciente
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto max-h-80 overflow-y-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="table-header px-4 py-2">Nombre</th>
                    <th className="table-header px-4 py-2">Edad</th>
                    <th className="table-header px-4 py-2">Nivel de Riesgo</th>
                    <th className="table-header px-4 py-2">Última Predicción</th>
                    <th className="table-header px-4 py-2">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {patients.slice(0, 10).map((patient) => {
                    const latestPred = getLatestPrediction(patient.id)
                    return (
                      <tr
                        key={patient.id}
                        className="border-b border-gray-50 hover:bg-gray-50 cursor-pointer transition-colors"
                        onClick={() => navigate(`/patients/${patient.id}`)}
                      >
                        <td className="table-cell font-medium">
                          {patient.first_name} {patient.last_name}
                        </td>
                        <td className="table-cell">
                          {calculateAge(patient.date_of_birth)} años
                        </td>
                        <td className="table-cell">
                          {latestPred ? (
                            <span className={getRiskBadgeClass(latestPred.risk_level)}>
                              {getRiskLabel(latestPred.risk_level)}
                            </span>
                          ) : (
                            <span className="text-gray-400 text-xs">Sin predicción</span>
                          )}
                        </td>
                        <td className="table-cell text-gray-500 text-xs">
                          {latestPred
                            ? new Date(latestPred.created_at).toLocaleDateString('es-ES')
                            : '-'}
                        </td>
                        <td className="table-cell">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              navigate(`/predict/${patient.id}`)
                            }}
                            className="text-xs text-primary-500 hover:text-primary-700 font-medium"
                          >
                            Nueva Predicción
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Recent alerts */}
      {recentHighAlerts.length > 0 && (
        <div className="dashboard-card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-risk-high" />
              Alertas Recientes de Riesgo Alto
            </h3>
            <button
              onClick={() => navigate('/alerts')}
              className="text-xs text-primary-500 hover:text-primary-700 font-medium flex items-center gap-1"
            >
              Ver todas <ChevronRight className="w-3 h-3" />
            </button>
          </div>
          <div className="space-y-2">
            {recentHighAlerts.map((alert, idx) => (
              <div
                key={alert.id || idx}
                className="flex items-center justify-between p-3 bg-risk-high-light rounded-lg border border-risk-high/20 alert-pulse-high"
              >
                <div className="flex items-center gap-3">
                  <AlertTriangle className="w-4 h-4 text-risk-high" />
                  <div>
                    <p className="text-sm font-medium text-gray-800">
                      {getPatientName(alert.patient_id)}
                    </p>
                    <p className="text-xs text-gray-500">
                      {alert.message || 'Riesgo alto detectado'}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <span className="badge-risk-high">
                    {(alert.risk_probability * 100).toFixed(1)}%
                  </span>
                  <p className="text-[10px] text-gray-400 mt-1">
                    {new Date(alert.created_at).toLocaleString('es-ES')}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
