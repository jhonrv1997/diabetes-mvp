import React, { useState, useEffect, useCallback } from 'react'
import api from '../api/axios'
import { downloadFile } from '../utils/download'
import {
  FileSearch,
  FileDown,
  RefreshCw,
  Eye,
  Pencil,
  Download,
  PlusCircle,
  Trash2,
  UserRound,
  Clock,
} from 'lucide-react'

const ACTION_META = {
  consulta: { label: 'Consulta', badge: 'bg-blue-100 text-blue-700', icon: Eye },
  creacion: { label: 'Creación', badge: 'bg-green-100 text-green-700', icon: PlusCircle },
  edicion: { label: 'Edición', badge: 'bg-amber-100 text-amber-700', icon: Pencil },
  eliminacion: { label: 'Eliminación', badge: 'bg-gray-200 text-gray-700', icon: Trash2 },
  exportacion: { label: 'Exportación', badge: 'bg-purple-100 text-purple-700', icon: Download },
}

const ROLE_LABELS = {
  admin: 'Administrador',
  doctor: 'Médico',
  nurse: 'Enfermera',
  nutritionist: 'Nutricionista',
  health_manager: 'Jefe C. Salud',
}

export default function AuditPanel() {
  const [patients, setPatients] = useState([])
  const [patientId, setPatientId] = useState('')
  const [action, setAction] = useState('')
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .get('/patients')
      .then((r) => setPatients(r.data || []))
      .catch(() => {})
  }, [])

  const fetchAudit = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { limit: 200 }
      if (action) params.action = action
      const url = patientId
        ? `/audit/patient/${patientId}`
        : '/audit'
      const r = await api.get(url, { params })
      setItems(r.data.items || [])
      setTotal(r.data.total || 0)
    } catch {
      setError('Error al consultar el registro de auditoría.')
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [patientId, action])

  useEffect(() => {
    fetchAudit()
  }, [fetchAudit])

  const handleExportCsv = async () => {
    setExporting(true)
    try {
      const url = patientId
        ? `/audit/patient/${patientId}/export/csv`
        : '/audit/export/csv'
      await downloadFile(url)
    } catch {
      setError('No se pudo exportar el CSV.')
    } finally {
      setExporting(false)
    }
  }

  const counts = items.reduce((acc, i) => {
    acc[i.action] = (acc[i.action] || 0) + 1
    return acc
  }, {})

  const selectedPatient = patients.find((p) => p.id === Number(patientId))

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Auditoría de Accesos</h1>
          <p className="text-sm text-gray-500 mt-1">
            Registro cronológico de quién accedió a los datos de los pacientes y qué acción realizó
          </p>
        </div>
        <FileSearch className="w-8 h-8 text-primary-500" />
      </div>

      {/* Filtros (HU12 Escenario 2) */}
      <div className="dashboard-card">
        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-64">
            <label className="form-label">Paciente</label>
            <select
              className="form-input"
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
            >
              <option value="">Todos los pacientes (registro global)</option>
              {patients.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.first_name} {p.last_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="form-label">Acción</label>
            <select className="form-input" value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">Todas las acciones</option>
              {Object.entries(ACTION_META).map(([value, meta]) => (
                <option key={value} value={value}>
                  {meta.label}
                </option>
              ))}
            </select>
          </div>
          <button onClick={fetchAudit} className="btn-primary gap-2" disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Consultar
          </button>
          <button
            onClick={handleExportCsv}
            className="btn-secondary gap-2 ml-auto"
            disabled={exporting}
            title="Exportar el log en formato CSV"
          >
            <FileDown className="w-4 h-4" />
            {exporting ? 'Exportando…' : 'Exportar CSV'}
          </button>
        </div>

        {/* Resumen rápido */}
        <div className="flex flex-wrap items-center gap-2 mt-4">
          <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
            <Clock className="w-3.5 h-3.5" />
            {total} registro(s){selectedPatient ? ` — ${selectedPatient.first_name} ${selectedPatient.last_name}` : ''}
          </span>
          {Object.entries(ACTION_META).map(([key, meta]) =>
            counts[key] ? (
              <span
                key={key}
                className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium ${meta.badge}`}
              >
                <meta.icon className="w-3.5 h-3.5" />
                {meta.label}: {counts[key]}
              </span>
            ) : null
          )}
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Listado cronológico */}
      <div className="dashboard-card">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <div className="spinner"></div>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <FileSearch className="w-12 h-12 mb-3" />
            <p className="text-sm font-medium text-gray-500">Sin registros de auditoría</p>
            <p className="text-xs mt-1">
              El sistema registrará automáticamente cada consulta, edición y exportación de datos.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto max-h-[560px] overflow-y-auto">
            <table className="w-full">
              <thead className="sticky top-0 bg-white z-10">
                <tr className="border-b border-gray-100">
                  <th className="table-header px-4 py-2 text-left">Fecha</th>
                  <th className="table-header px-4 py-2 text-left">Hora</th>
                  <th className="table-header px-4 py-2 text-left">Usuario</th>
                  <th className="table-header px-4 py-2 text-left">Acción</th>
                  <th className="table-header px-4 py-2 text-left">Recurso</th>
                  <th className="table-header px-4 py-2 text-left">Detalles</th>
                  <th className="table-header px-4 py-2 text-left">Estado</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const meta = ACTION_META[item.action] || {
                    label: item.action,
                    badge: 'bg-gray-100 text-gray-700',
                    icon: Eye,
                  }
                  const dt = new Date(item.created_at)
                  return (
                    <tr key={item.id} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="table-cell text-xs">{dt.toLocaleDateString('es-ES')}</td>
                      <td className="table-cell text-xs font-mono">
                        {dt.toLocaleTimeString('es-ES')}
                      </td>
                      <td className="table-cell">
                        <div className="flex items-center gap-2">
                          <span className="w-7 h-7 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                            <UserRound className="w-3.5 h-3.5 text-primary-600" />
                          </span>
                          <div>
                            <p className="text-sm font-medium text-gray-800 leading-tight">
                              {item.username || '—'}
                            </p>
                            <p className="text-[10px] text-gray-500">
                              {ROLE_LABELS[item.user_role] || item.user_role || ''}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="table-cell">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold ${meta.badge}`}
                        >
                          <meta.icon className="w-3 h-3" />
                          {meta.label}
                        </span>
                      </td>
                      <td className="table-cell text-xs capitalize">
                        {(item.resource || '-').replace('_', ' ')}
                      </td>
                      <td className="table-cell text-xs text-gray-500 max-w-xs truncate" title={item.details}>
                        {item.details || `${item.method} ${item.endpoint}`}
                      </td>
                      <td className="table-cell">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            item.status_code === 403 || item.status_code === 401
                              ? 'bg-red-100 text-red-700'
                              : 'bg-green-100 text-green-700'
                          }`}
                        >
                          {item.status_code === 403 || item.status_code === 401
                            ? 'Denegado'
                            : 'OK'}
                        </span>
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
  )
}
