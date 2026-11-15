import React, { useState, useEffect, useCallback } from 'react'
import api from '../api/axios'
import { useAuth } from '../context/AuthContext'
import {
  UserCog,
  Plus,
  X,
  ShieldCheck,
  KeyRound,
  Power,
  Search,
} from 'lucide-react'

const ROLE_LABELS = {
  admin: 'Administrador',
  doctor: 'Médico',
  nurse: 'Enfermera',
  nutritionist: 'Nutricionista',
  health_manager: 'Jefe del Centro de Salud',
}

const ROLE_BADGES = {
  admin: 'bg-purple-100 text-purple-700',
  doctor: 'bg-blue-100 text-blue-700',
  nurse: 'bg-pink-100 text-pink-700',
  nutritionist: 'bg-green-100 text-green-700',
  health_manager: 'bg-amber-100 text-amber-700',
}

export default function UsersPanel() {
  const { user: current } = useAuth()
  const [users, setUsers] = useState([])
  const [permissions, setPermissions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [search, setSearch] = useState('')
  const [saving, setSaving] = useState(false)

  const [form, setForm] = useState({
    username: '',
    full_name: '',
    password: '',
    role: 'nurse',
  })

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [usersRes, permsRes] = await Promise.all([
        api.get('/users').catch(() => ({ data: [] })),
        api.get('/users/permissions').catch(() => ({ data: [] })),
      ])
      setUsers(usersRes.data || [])
      setPermissions(permsRes.data || [])
    } catch {
      setError('Error al cargar los usuarios.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const notify = (msg) => {
    setSuccess(msg)
    setError('')
    setTimeout(() => setSuccess(''), 3500)
  }

  const createUser = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.post('/users', form)
      notify(`Cuenta creada: ${form.full_name} (${ROLE_LABELS[form.role]}). Permisos asignados automáticamente.`)
      setShowForm(false)
      setForm({ username: '', full_name: '', password: '', role: 'nurse' })
      fetchData()
    } catch (e) {
      setError(e.response?.data?.detail || 'No se pudo crear el usuario.')
    } finally {
      setSaving(false)
    }
  }

  const changeRole = async (userId, role) => {
    try {
      await api.put(`/users/${userId}`, { role })
      notify(`Rol actualizado a ${ROLE_LABELS[role]}.`)
      fetchData()
    } catch (e) {
      setError(e.response?.data?.detail || 'No se pudo actualizar el rol.')
    }
  }

  const toggleActive = async (u) => {
    try {
      await api.put(`/users/${u.id}`, { is_active: !u.is_active })
      notify(`Cuenta ${u.is_active ? 'desactivada' : 'activada'}: ${u.full_name}.`)
      fetchData()
    } catch (e) {
      setError(e.response?.data?.detail || 'No se pudo cambiar el estado.')
    }
  }

  const resetPassword = async (u) => {
    const newPassword = prompt(
      `Nueva contraseña para ${u.full_name} (mínimo 6 caracteres):`
    )
    if (!newPassword) return
    if (newPassword.length < 6) {
      setError('La contraseña debe tener al menos 6 caracteres.')
      return
    }
    try {
      await api.put(`/users/${u.id}`, { password: newPassword })
      notify(`Contraseña restablecida para ${u.full_name}.`)
    } catch (e) {
      setError(e.response?.data?.detail || 'No se pudo restablecer la contraseña.')
    }
  }

  const filteredUsers = users.filter(
    (u) =>
      !search ||
      u.username?.toLowerCase().includes(search.toLowerCase()) ||
      u.full_name?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-6">
      {/* Encabezado */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Usuarios y Roles</h1>
          <p className="text-sm text-gray-500 mt-1">
            Control de acceso y privacidad de datos (Ley de Protección de Datos Personales)
          </p>
        </div>
        <UserCog className="w-8 h-8 text-primary-500" />
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}
      {success && (
        <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
          {success}
        </div>
      )}

      {/* Formulario de nuevo usuario (HU12 Escenario 1) */}
      {showForm && (
        <div className="dashboard-card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-700">
              Registrar cuenta de un nuevo profesional
            </h3>
            <button onClick={() => setShowForm(false)} className="text-gray-400 hover:text-gray-600">
              <X className="w-5 h-5" />
            </button>
          </div>
          <form onSubmit={createUser} className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="form-label">Usuario</label>
              <input
                className="form-input"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                minLength="3"
                required
                placeholder="jperez"
              />
            </div>
            <div>
              <label className="form-label">Nombre completo</label>
              <input
                className="form-input"
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                required
                placeholder="Dra. Juanita Pérez"
              />
            </div>
            <div>
              <label className="form-label">Contraseña</label>
              <input
                type="password"
                className="form-input"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                minLength="6"
                required
                placeholder="Mínimo 6 caracteres"
              />
            </div>
            <div>
              <label className="form-label">Rol</label>
              <select
                className="form-input"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                {Object.entries(ROLE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-4">
              <button type="submit" className="btn-primary gap-2" disabled={saving}>
                <Plus className="w-4 h-4" />
                {saving ? 'Creando cuenta…' : 'Crear cuenta y asignar permisos'}
              </button>
              <p className="text-xs text-gray-500 mt-2">
                Al seleccionar el rol, el sistema asigna automáticamente los permisos asociados
                (ver matriz inferior).
              </p>
            </div>
          </form>
        </div>
      )}

      {/* Lista de usuarios */}
      <div className="dashboard-card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h3 className="text-sm font-semibold text-gray-700">
            Personal del Centro de Salud ({users.length})
          </h3>
          <div className="flex gap-2">
            <div className="relative">
              <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                className="form-input pl-9 w-56"
                placeholder="Buscar usuario…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button onClick={() => setShowForm(!showForm)} className="btn-primary gap-2">
              <Plus className="w-4 h-4" />
              Nuevo Usuario
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="spinner"></div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="table-header px-4 py-2 text-left">Usuario</th>
                  <th className="table-header px-4 py-2 text-left">Nombre completo</th>
                  <th className="table-header px-4 py-2 text-left">Rol (permisos)</th>
                  <th className="table-header px-4 py-2 text-left">Estado</th>
                  <th className="table-header px-4 py-2 text-left">Creado</th>
                  <th className="table-header px-4 py-2 text-left">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((u) => (
                  <tr key={u.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="table-cell font-medium">@{u.username}</td>
                    <td className="table-cell">
                      {u.full_name}
                      {u.id === current?.id && (
                        <span className="ml-2 text-[10px] text-primary-500 font-semibold">
                          (usted)
                        </span>
                      )}
                    </td>
                    <td className="table-cell">
                      <select
                        className="form-input !py-1 !px-2 text-xs w-52"
                        value={u.role}
                        disabled={u.id === current?.id}
                        onChange={(e) => changeRole(u.id, e.target.value)}
                        title={
                          u.id === current?.id
                            ? 'No puede cambiar su propio rol'
                            : 'Cambiar rol del usuario'
                        }
                      >
                        {Object.entries(ROLE_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="table-cell">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${
                          u.is_active
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-200 text-gray-600'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            u.is_active ? 'bg-green-500' : 'bg-gray-400'
                          }`}
                        ></span>
                        {u.is_active ? 'Activo' : 'Inactivo'}
                      </span>
                    </td>
                    <td className="table-cell text-gray-500 text-xs">
                      {new Date(u.created_at).toLocaleDateString('es-ES')}
                    </td>
                    <td className="table-cell">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => resetPassword(u)}
                          className="p-1.5 rounded-lg hover:bg-primary-50 text-gray-400 hover:text-primary-600"
                          title="Restablecer contraseña"
                        >
                          <KeyRound className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => toggleActive(u)}
                          disabled={u.id === current?.id}
                          className={`p-1.5 rounded-lg hover:bg-red-50 disabled:opacity-30 disabled:cursor-not-allowed ${
                            u.is_active ? 'text-gray-400 hover:text-red-500' : 'text-green-500 hover:text-green-600'
                          }`}
                          title={u.is_active ? 'Desactivar cuenta' : 'Activar cuenta'}
                        >
                          <Power className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Matriz de permisos por rol (HU12 Escenario 1) */}
      <div className="dashboard-card">
        <div className="flex items-center gap-2 mb-4">
          <ShieldCheck className="w-5 h-5 text-primary-500" />
          <div>
            <h3 className="text-sm font-semibold text-gray-700">
              Matriz de permisos por rol (asignación automática)
            </h3>
            <p className="text-xs text-gray-500">
              Cada profesional accede solo a la información estrictamente necesaria para su función.
            </p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {permissions.map((p) => (
            <div key={p.role} className="border border-gray-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${ROLE_BADGES[p.role] || 'bg-gray-100 text-gray-700'}`}>
                  {p.label}
                </span>
                <span className="text-[10px] text-gray-400 font-mono">{p.role}</span>
              </div>
              <ul className="space-y-1.5">
                {p.modules.map((m, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-gray-600">
                    <ShieldCheck className="w-3.5 h-3.5 text-green-500 mt-0.5 flex-shrink-0" />
                    {m}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
