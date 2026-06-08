import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/axios'
import { getRiskBadgeClass, getRiskLabel } from '../utils/validation'
import {
  Bell,
  AlertTriangle,
  RefreshCw,
  Filter,
  SortAsc,
  SortDesc,
  Clock,
  User,
} from 'lucide-react'

export default function AlertPanel() {
  const navigate = useNavigate()
  const [alerts, setAlerts] = useState([])
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [riskFilter, setRiskFilter] = useState('all')
  const [sortField, setSortField] = useState('date')
  const [sortDir, setSortDir] = useState('desc')

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    setLoading(true)
    setError('')
    try {
      const [alertsRes, patientsRes] = await Promise.all([
        api.get('/alerts').catch(() => ({ data: [] })),
        api.get('/patients').catch(() => ({ data: [] })),
      ])
      setAlerts(alertsRes.data || [])
      setPatients(patientsRes.data || [])
    } catch {
      setError('Error al cargar las alertas')
    } finally {
      setLoading(false)
    }
  }

  const getPatientName = (patientId) => {
    const patient = patients.find((p) => p.id === patientId)
    return patient ? `${patient.first_name} ${patient.last_name}` : 'Paciente Desconocido'
  }

  // Filter alerts
  const filtered = alerts.filter((alert) => {
    if (riskFilter === 'all') return true
    if (riskFilter === 'high') return alert.severity?.toLowerCase() === 'high'
    if (riskFilter === 'medium') return alert.severity?.toLowerCase() === 'medium'
    return true
  })

  // Sort alerts
  const sorted = [...filtered].sort((a, b) => {
    if (sortField === 'date') {
      const dateA = new Date(a.created_at)
      const dateB = new Date(b.created_at)
      return sortDir === 'desc' ? dateB - dateA : dateA - dateB
    }
    if (sortField === 'risk') {
      const riskOrder = { high: 3, medium: 2, low: 1 }
      const aRisk = riskOrder[a.severity?.toLowerCase()] || 0
      const bRisk = riskOrder[b.severity?.toLowerCase()] || 0
      return sortDir === 'desc' ? bRisk - aRisk : aRisk - bRisk
    }
    return 0
  })

  const activeCount = alerts.filter((a) => a.is_active).length
  const highCount = alerts.filter(
    (a) => a.is_active && a.severity?.toLowerCase() === 'high'
  ).length

  const getBorderColor = (level) => {
    switch (level?.toLowerCase()) {
      case 'high':
        return 'border-l-4 border-l-risk-high'
      case 'medium':
        return 'border-l-4 border-l-risk-medium'
      default:
        return 'border-l-4 border-l-risk-low'
    }
  }

  const getBgColor = (level) => {
    switch (level?.toLowerCase()) {
      case 'high':
        return 'bg-risk-high-light'
      case 'medium':
        return 'bg-risk-medium-light'
      default:
        return 'bg-risk-low-light'
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
            <Bell className="w-6 h-6 text-primary-500" />
            Alertas
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            {activeCount} alerta{activeCount !== 1 ? 's' : ''} activa{activeCount !== 1 ? 's' : ''}
            {highCount > 0 && (
              <span className="text-risk-high font-medium"> ({highCount} de riesgo alto)</span>
            )}
          </p>
        </div>
        <button onClick={fetchData} className="btn-secondary gap-2" title="Actualizar">
          <RefreshCw className="w-4 h-4" />
          Actualizar
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-gray-400" />
          <select
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value)}
            className="form-input w-auto"
          >
            <option value="all">Todos los niveles</option>
            <option value="high">Riesgo Alto</option>
            <option value="medium">Riesgo Medio</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              if (sortField === 'date') {
                setSortDir((prev) => (prev === 'desc' ? 'asc' : 'desc'))
              } else {
                setSortField('date')
                setSortDir('desc')
              }
            }}
            className={`btn-secondary gap-2 text-xs ${sortField === 'date' ? 'ring-2 ring-primary-200' : ''}`}
          >
            {sortField === 'date' && sortDir === 'desc' ? (
              <SortDesc className="w-3 h-3" />
            ) : (
              <SortAsc className="w-3 h-3" />
            )}
            Fecha
          </button>
          <button
            onClick={() => {
              if (sortField === 'risk') {
                setSortDir((prev) => (prev === 'desc' ? 'asc' : 'desc'))
              } else {
                setSortField('risk')
                setSortDir('desc')
              }
            }}
            className={`btn-secondary gap-2 text-xs ${sortField === 'risk' ? 'ring-2 ring-primary-200' : ''}`}
          >
            {sortField === 'risk' && sortDir === 'desc' ? (
              <SortDesc className="w-3 h-3" />
            ) : (
              <SortAsc className="w-3 h-3" />
            )}
            Riesgo
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Alert list */}
      {sorted.length === 0 ? (
        <div className="dashboard-card flex flex-col items-center justify-center py-12 text-gray-400">
          <Bell className="w-12 h-12 mb-3" />
          <p className="text-sm font-medium">
            {riskFilter !== 'all' ? 'No hay alertas para este filtro' : 'No hay alertas activas'}
          </p>
          <p className="text-xs mt-1">Las alertas aparecerán cuando se detecten riesgos</p>
        </div>
      ) : (
        <div className="space-y-3 max-h-[calc(100vh-300px)] overflow-y-auto">
          {sorted.map((alert, idx) => (
            <div
              key={alert.id || idx}
              className={`dashboard-card ${getBorderColor(alert.severity)} ${getBgColor(
                alert.severity
              )} ${
                alert.severity?.toLowerCase() === 'high' &&
                alert.is_active
                  ? 'alert-pulse-high'
                  : ''
              }`}
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-start gap-3 flex-1">
                  <AlertTriangle
                    className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                      alert.severity?.toLowerCase() === 'high'
                        ? 'text-risk-high'
                        : 'text-risk-medium'
                    }`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="text-sm font-semibold text-gray-800">
                        {getPatientName(alert.patient_id)}
                      </h4>
                      <span className={getRiskBadgeClass(alert.severity)}>
                        {getRiskLabel(alert.severity)}
                      </span>
                      {!alert.is_active && (
                        <span className="text-[10px] bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full">
                          Resuelta
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-600 mt-1">
                      {alert.message || 'Riesgo de Diabetes detectado'}
                    </p>

                  </div>
                </div>

                <div className="flex items-center gap-4 flex-shrink-0">
                  <div className="text-right">
                    <p className="text-lg font-bold text-gray-800">
                      {((alert.risk_probability || 0) * 100).toFixed(1)}%
                    </p>
                    <p className="text-[10px] text-gray-400 flex items-center gap-1 justify-end">
                      <Clock className="w-3 h-3" />
                      {alert.created_at
                        ? new Date(alert.created_at).toLocaleString('es-ES')
                        : '-'}
                    </p>
                  </div>
                  <button
                    onClick={() => navigate(`/patients/${alert.patient_id}`)}
                    className="btn-secondary text-xs gap-1 p-2"
                    title="Ver paciente"
                  >
                    <User className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
