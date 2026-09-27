import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/axios'
import {
  Bell,
  BellOff,
  RefreshCw,
  AlertCircle,
  UtensilsCrossed,
  Calendar,
  CalendarClock,
  Check,
  CheckCheck,
  Smartphone,
  Volume2,
} from 'lucide-react'

const NOTIF_TYPE_META = {
  emergency_alert: {
    label: 'Alerta de Emergencia',
    icon: AlertCircle,
    bg: 'bg-red-50',
    border: 'border-l-4 border-l-risk-high',
    iconColor: 'text-risk-high',
    pulse: true,
  },
  meal_reminder: {
    label: 'Recordatorio de Comida',
    icon: UtensilsCrossed,
    bg: 'bg-amber-50',
    border: 'border-l-4 border-l-amber-400',
    iconColor: 'text-amber-500',
    pulse: false,
  },
  appointment_reminder: {
    label: 'Recordatorio de Cita',
    icon: Calendar,
    bg: 'bg-blue-50',
    border: 'border-l-4 border-l-blue-400',
    iconColor: 'text-blue-500',
    pulse: false,
  },
  appointment_reschedule: {
    label: 'Cita Reagendada',
    icon: CalendarClock,
    bg: 'bg-purple-50',
    border: 'border-l-4 border-l-purple-400',
    iconColor: 'text-purple-500',
    pulse: false,
  },
}

export default function NotificationsPanel() {
  const navigate = useNavigate()
  const [notifs, setNotifs] = useState([])
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')
  const [unreadOnly, setUnreadOnly] = useState(false)

  const fetchData = async () => {
    setLoading(true)
    setError('')
    try {
      const [notifsRes, patientsRes] = await Promise.all([
        api.get('/notifications', { params: { limit: 200 } }),
        api.get('/patients').catch(() => ({ data: [] })),
      ])
      setNotifs(notifsRes.data || [])
      setPatients(patientsRes.data || [])
    } catch (e) {
      setError('Error al cargar las notificaciones')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    // Poll every 30s for new emergency alerts
    const i = setInterval(fetchData, 30000)
    return () => clearInterval(i)
  }, [])

  const getPatientName = (patientId) => {
    const p = patients.find((x) => x.id === patientId)
    return p ? `${p.first_name} ${p.last_name}` : `Paciente #${patientId}`
  }

  const filtered = notifs.filter((n) => {
    if (unreadOnly && n.is_read) return false
    if (filter === 'all') return true
    return n.notification_type === filter
  })

  const markRead = async (id) => {
    try {
      await api.put(`/notifications/${id}/read`)
      setNotifs((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      )
    } catch {
      // ignore
    }
  }

  const markAllRead = async () => {
    const unread = notifs.filter((n) => !n.is_read)
    for (const n of unread) {
      try {
        await api.put(`/notifications/${n.id}/read`)
      } catch {
        // ignore
      }
    }
    setNotifs((prev) => prev.map((n) => ({ ...n, is_read: true })))
  }

  const counts = {
    total: notifs.length,
    emergency: notifs.filter((n) => n.notification_type === 'emergency_alert').length,
    meal: notifs.filter((n) => n.notification_type === 'meal_reminder').length,
    appt: notifs.filter(
      (n) =>
        n.notification_type === 'appointment_reminder' ||
        n.notification_type === 'appointment_reschedule'
    ).length,
    unread: notifs.filter((n) => !n.is_read).length,
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
            Notificaciones Push
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            {counts.total} notificación(es) · {counts.unread} no leída(s)
            {counts.emergency > 0 && (
              <span className="text-risk-high font-medium">
                {' '}· {counts.emergency} de emergencia
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={markAllRead}
            className="btn-secondary gap-2 text-xs"
            disabled={counts.unread === 0}
            title="Marcar todas como leídas"
          >
            <CheckCheck className="w-4 h-4" />
            Marcar todas
          </button>
          <button onClick={fetchData} className="btn-secondary gap-2" title="Actualizar">
            <RefreshCw className="w-4 h-4" />
            Actualizar
          </button>
        </div>
      </div>

      {/* Info banner — HU06 */}
      <div className="dashboard-card bg-blue-50 border-blue-200">
        <div className="flex items-start gap-3">
          <Smartphone className="w-5 h-5 text-blue-500 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-blue-800">
            <p className="font-semibold mb-1">Sistema de notificaciones push a la app móvil del paciente</p>
            <p className="text-xs text-blue-700">
              Esta vista centraliza todas las notificaciones push enviadas a los pacientes:
              alertas de emergencia por glucosa peligrosamente alta (HU06), recordatorios de
              comidas del plan nutricional (HU10) y recordatorios/reagendamientos de citas (HU13).
              Las notificaciones de emergencia se envían con prioridad <code className="bg-blue-100 px-1 rounded">high</code>{' '}
              y sonido <code className="bg-blue-100 px-1 rounded">critical</code>.
            </p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 flex-wrap">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="form-input w-auto"
        >
          <option value="all">Todas las notificaciones</option>
          <option value="emergency_alert">🚨 Alertas de Emergencia</option>
          <option value="meal_reminder">🍽️ Recordatorios de Comida</option>
          <option value="appointment_reminder">📅 Recordatorios de Cita</option>
          <option value="appointment_reschedule">🔄 Citas Reagendadas</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(e) => setUnreadOnly(e.target.checked)}
            className="rounded border-gray-300 text-primary-500 focus:ring-primary-500"
          />
          Solo no leídas
        </label>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Notification list */}
      {filtered.length === 0 ? (
        <div className="dashboard-card flex flex-col items-center justify-center py-12 text-gray-400">
          <BellOff className="w-12 h-12 mb-3" />
          <p className="text-sm font-medium">No hay notificaciones para mostrar</p>
        </div>
      ) : (
        <div className="space-y-3 max-h-[calc(100vh-380px)] overflow-y-auto">
          {filtered.map((n) => {
            const meta = NOTIF_TYPE_META[n.notification_type] || NOTIF_TYPE_META.emergency_alert
            const Icon = meta.icon
            return (
              <div
                key={n.id}
                className={`dashboard-card p-4 ${meta.bg} ${meta.border} ${
                  meta.pulse && !n.is_read ? 'alert-pulse-high' : ''
                } ${n.is_read ? 'opacity-70' : ''}`}
              >
                <div className="flex items-start gap-3">
                  <Icon className={`w-5 h-5 mt-0.5 flex-shrink-0 ${meta.iconColor}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-semibold uppercase tracking-wide text-gray-600">
                        {meta.label}
                      </span>
                      <span className="text-xs text-gray-500">
                        · {getPatientName(n.patient_id)}
                      </span>
                      {n.priority === 'high' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-700">
                          <Volume2 className="w-3 h-3" />
                          PRIORITARIA
                        </span>
                      )}
                      {!n.is_read && (
                        <span className="w-2 h-2 rounded-full bg-primary-500" title="No leída" />
                      )}
                    </div>
                    <p className="text-sm font-semibold text-gray-800 mt-1">
                      {n.title}
                    </p>
                    <p className="text-sm text-gray-700 mt-0.5">{n.body}</p>
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                      <span>
                        📅 {new Date(n.created_at).toLocaleString('es-ES')}
                      </span>
                      <span>
                        Sonido: <strong>{n.sound}</strong>
                      </span>
                      <span>
                        Estado: {n.is_sent ? '✅ Enviada' : '⏸️ Pendiente'}
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-col gap-1 items-end">
                    {!n.is_read && (
                      <button
                        onClick={() => markRead(n.id)}
                        className="btn-secondary text-xs gap-1 px-2 py-1"
                        title="Marcar como leída"
                      >
                        <Check className="w-3 h-3" />
                      </button>
                    )}
                    <button
                      onClick={() => navigate(`/patients/${n.patient_id}`)}
                      className="btn-secondary text-xs gap-1 px-2 py-1"
                      title="Ver paciente"
                    >
                      Ver
                    </button>
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
