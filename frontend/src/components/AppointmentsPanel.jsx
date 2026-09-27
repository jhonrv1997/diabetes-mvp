import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/axios'
import {
  Calendar,
  CalendarPlus,
  CalendarClock,
  CalendarX,
  RefreshCw,
  Plus,
  User,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  RotateCcw,
} from 'lucide-react'

const STATUS_META = {
  scheduled: {
    label: 'Programada',
    icon: Clock,
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-l-4 border-l-blue-400',
  },
  completed: {
    label: 'Completada',
    icon: CheckCircle,
    bg: 'bg-green-50',
    text: 'text-green-700',
    border: 'border-l-4 border-l-green-500',
  },
  no_show: {
    label: 'Inasistencia',
    icon: XCircle,
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-l-4 border-l-risk-high',
  },
  rescheduled: {
    label: 'Reagendada',
    icon: RotateCcw,
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    border: 'border-l-4 border-l-purple-400',
  },
  cancelled: {
    label: 'Cancelada',
    icon: CalendarX,
    bg: 'bg-gray-100',
    text: 'text-gray-700',
    border: 'border-l-4 border-l-gray-300',
  },
}

const REASON_LABEL = {
  risk_high_auto: 'Cita automática · Riesgo Alto',
  risk_medium_auto: 'Cita automática · Riesgo Medio',
  manual: 'Cita manual',
  rescheduled_no_show: 'Reagendada por inasistencia',
}

export default function AppointmentsPanel() {
  const navigate = useNavigate()
  const [appointments, setAppointments] = useState([])
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')
  const [showForm, setShowForm] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState({
    patient_id: '',
    scheduled_date: '',
    time: '10:00',
    notes: '',
  })
  const [markingNoShow, setMarkingNoShow] = useState(null)

  const fetchData = async () => {
    setLoading(true)
    setError('')
    try {
      const [apptsRes, patientsRes] = await Promise.all([
        api.get('/appointments'),
        api.get('/patients').catch(() => ({ data: [] })),
      ])
      setAppointments(apptsRes.data || [])
      setPatients(patientsRes.data || [])
    } catch (e) {
      setError('Error al cargar las citas')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  const getPatientName = (id) => {
    const p = patients.find((x) => x.id === id)
    return p ? `${p.first_name} ${p.last_name}` : `Paciente #${id}`
  }

  const filtered = appointments.filter((a) => {
    if (filter === 'all') return true
    if (filter === 'upcoming') return a.status === 'scheduled' && new Date(a.scheduled_date) > new Date()
    return a.status === filter
  })

  const sorted = [...filtered].sort(
    (a, b) => new Date(b.scheduled_date) - new Date(a.scheduled_date)
  )

  const stats = {
    total: appointments.length,
    scheduled: appointments.filter((a) => a.status === 'scheduled').length,
    completed: appointments.filter((a) => a.status === 'completed').length,
    no_show: appointments.filter((a) => a.status === 'no_show').length,
    auto: appointments.filter((a) => a.auto_generated).length,
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!form.patient_id || !form.scheduled_date) {
      setError('Selecciona paciente y fecha')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const isoDate = new Date(`${form.scheduled_date}T${form.time || '10:00'}`).toISOString()
      await api.post('/appointments', {
        patient_id: parseInt(form.patient_id),
        scheduled_date: isoDate,
        reason: 'manual',
        notes: form.notes,
      })
      setShowForm(false)
      setForm({ patient_id: '', scheduled_date: '', time: '10:00', notes: '' })
      await fetchData()
    } catch (e) {
      setError(e.response?.data?.detail || 'Error al crear la cita')
    } finally {
      setSubmitting(false)
    }
  }

  const handleMarkNoShow = async (id) => {
    if (!window.confirm(
      '¿Confirmar inasistencia? El sistema reagendará automáticamente la cita en los próximos 3 días y enviará una notificación push al paciente.'
    )) {
      return
    }
    setMarkingNoShow(id)
    try {
      const r = await api.post(`/appointments/${id}/mark-no-show`)
      alert(
        `${r.data.message}\n\n` +
        `Cita reagendada #${r.data.rescheduled_appointment.id} para ` +
        new Date(r.data.rescheduled_appointment.scheduled_date).toLocaleString('es-ES') +
        `\nInasistencias acumuladas: ${r.data.rescheduled_appointment.no_show_count}`
      )
      await fetchData()
    } catch (e) {
      alert(e.response?.data?.detail || 'Error al marcar inasistencia')
    } finally {
      setMarkingNoShow(null)
    }
  }

  const handleMarkCompleted = async (id) => {
    if (!window.confirm('¿Marcar esta cita como completada?')) return
    try {
      await api.put(`/appointments/${id}`, { status: 'completed' })
      await fetchData()
    } catch (e) {
      alert(e.response?.data?.detail || 'Error')
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
            <Calendar className="w-6 h-6 text-primary-500" />
            Citas de Seguimiento
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Calendario del Centro de Salud · {stats.total} citas registradas
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchData} className="btn-secondary gap-2" title="Actualizar">
            <RefreshCw className="w-4 h-4" />
            Actualizar
          </button>
          <button onClick={() => setShowForm(true)} className="btn-primary gap-2">
            <Plus className="w-4 h-4" />
            Nueva Cita
          </button>
        </div>
      </div>

      {/* HU13 explanation banner */}
      <div className="dashboard-card bg-blue-50 border-blue-200">
        <div className="flex items-start gap-3">
          <CalendarClock className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-blue-800">
            <p className="font-semibold mb-1">HU13 · Programación de citas de seguimiento</p>
            <p className="text-xs text-blue-700">
              El sistema crea automáticamente una cita dentro de los 7 días siguientes cuando
              clasifica a un paciente con riesgo Alto. Si el paciente no asiste, se marca la
              inasistencia, se notifica al paciente y se genera automáticamente una nueva cita
              en los próximos 3 días. El indicador de inasistencia se acumula para seguimiento prioritario.
            </p>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div className="dashboard-card p-3 text-center">
          <p className="text-2xl font-bold text-gray-800">{stats.total}</p>
          <p className="text-xs text-gray-500">Total</p>
        </div>
        <div className="dashboard-card p-3 text-center">
          <p className="text-2xl font-bold text-blue-600">{stats.scheduled}</p>
          <p className="text-xs text-gray-500">Programadas</p>
        </div>
        <div className="dashboard-card p-3 text-center">
          <p className="text-2xl font-bold text-green-600">{stats.completed}</p>
          <p className="text-xs text-gray-500">Completadas</p>
        </div>
        <div className="dashboard-card p-3 text-center">
          <p className="text-2xl font-bold text-red-600">{stats.no_show}</p>
          <p className="text-xs text-gray-500">Inasistencias</p>
        </div>
        <div className="dashboard-card p-3 text-center">
          <p className="text-2xl font-bold text-purple-600">{stats.auto}</p>
          <p className="text-xs text-gray-500">Automáticas</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        {[
          { v: 'all', label: 'Todas' },
          { v: 'upcoming', label: 'Próximas' },
          { v: 'scheduled', label: 'Programadas' },
          { v: 'completed', label: 'Completadas' },
          { v: 'no_show', label: 'Inasistencias' },
        ].map((f) => (
          <button
            key={f.v}
            onClick={() => setFilter(f.v)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              filter === f.v
                ? 'bg-primary-500 text-white border-primary-500'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Create form */}
      {showForm && (
        <div className="dashboard-card border-2 border-primary-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
              <CalendarPlus className="w-5 h-5 text-primary-500" />
              Programar Cita Manual
            </h3>
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
          <form onSubmit={handleCreate} className="space-y-3">
            <div>
              <label className="form-label">Paciente</label>
              <select
                value={form.patient_id}
                onChange={(e) => setForm({ ...form, patient_id: e.target.value })}
                className="form-input"
                required
              >
                <option value="">— Selecciona —</option>
                {patients.map((p) => (
                  <option key={p.id} value={p.id}>
                    #{p.id} · {p.first_name} {p.last_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="form-label">Fecha</label>
                <input
                  type="date"
                  value={form.scheduled_date}
                  onChange={(e) => setForm({ ...form, scheduled_date: e.target.value })}
                  className="form-input"
                  required
                />
              </div>
              <div>
                <label className="form-label">Hora</label>
                <input
                  type="time"
                  value={form.time}
                  onChange={(e) => setForm({ ...form, time: e.target.value })}
                  className="form-input"
                />
              </div>
            </div>
            <div>
              <label className="form-label">Notas</label>
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                className="form-input"
                rows="2"
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
                {submitting ? 'Guardando...' : 'Programar cita'}
              </button>
            </div>
          </form>
        </div>
      )}

      {error && !showForm && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Appointments list */}
      {sorted.length === 0 ? (
        <div className="dashboard-card flex flex-col items-center justify-center py-12 text-gray-400">
          <CalendarX className="w-12 h-12 mb-3" />
          <p className="text-sm font-medium">No hay citas para mostrar</p>
          <p className="text-xs mt-1">
            Las citas automáticas se generan tras una predicción de riesgo Alto
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {sorted.map((a) => {
            const meta = STATUS_META[a.status] || STATUS_META.scheduled
            const Icon = meta.icon
            const dateObj = new Date(a.scheduled_date)
            const isPast = dateObj < new Date()
            return (
              <div key={a.id} className={`dashboard-card p-4 ${meta.border} ${meta.bg}`}>
                <div className="flex items-start gap-3">
                  {/* Date column */}
                  <div className="flex flex-col items-center justify-center bg-white rounded-lg border border-gray-200 p-2 min-w-[64px]">
                    <p className="text-[10px] uppercase font-semibold text-gray-500">
                      {dateObj.toLocaleDateString('es-ES', { month: 'short' })}
                    </p>
                    <p className="text-2xl font-bold text-gray-800 leading-none">
                      {dateObj.getDate()}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {dateObj.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="text-sm font-semibold text-gray-800 flex items-center gap-1">
                        <User className="w-4 h-4 text-gray-400" />
                        {a.patient_name || getPatientName(a.patient_id)}
                      </h4>
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${meta.bg} ${meta.text}`}
                      >
                        <Icon className="w-3 h-3" />
                        {meta.label}
                      </span>
                      {a.auto_generated && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-purple-100 text-purple-700">
                          ⚡ Automática
                        </span>
                      )}
                      {a.no_show_count > 0 && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-700">
                          <AlertTriangle className="w-3 h-3" />
                          {a.no_show_count} inasistencia(s)
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-600 mt-1">
                      {REASON_LABEL[a.reason] || a.reason}
                      {a.nurse_name && ` · Enfermera: ${a.nurse_name}`}
                    </p>
                    {a.notes && (
                      <p className="text-xs text-gray-500 mt-1 italic">📝 {a.notes}</p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col gap-1 items-end">
                    <button
                      onClick={() => navigate(`/patients/${a.patient_id}`)}
                      className="btn-secondary text-xs px-2 py-1"
                    >
                      Ver paciente
                    </button>
                    {a.status === 'scheduled' && !isPast && (
                      <>
                        <button
                          onClick={() => handleMarkCompleted(a.id)}
                          className="btn-secondary text-xs px-2 py-1 gap-1 text-green-700 hover:bg-green-50"
                        >
                          <CheckCircle className="w-3 h-3" />
                          Completar
                        </button>
                        {markingNoShow === a.id ? (
                          <span className="text-xs text-gray-500">Marcando...</span>
                        ) : (
                          <button
                            onClick={() => handleMarkNoShow(a.id)}
                            className="btn-danger text-xs px-2 py-1 gap-1"
                          >
                            <XCircle className="w-3 h-3" />
                            Inasistencia
                          </button>
                        )}
                      </>
                    )}
                    {a.status === 'scheduled' && isPast && (
                      <button
                        onClick={() => handleMarkNoShow(a.id)}
                        className="btn-danger text-xs px-2 py-1 gap-1"
                        disabled={markingNoShow === a.id}
                      >
                        <XCircle className="w-3 h-3" />
                        {markingNoShow === a.id ? 'Marcando...' : 'No asistió'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
