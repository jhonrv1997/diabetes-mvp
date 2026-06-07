import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/axios'
import { getRiskBadgeClass, getRiskLabel } from '../utils/validation'
import {
  Search,
  Plus,
  Users,
  Eye,
  TrendingUp,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'

const ITEMS_PER_PAGE = 10

export default function PatientList() {
  const navigate = useNavigate()
  const [patients, setPatients] = useState([])
  const [predictions, setPredictions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [sortBy, setSortBy] = useState('name')
  const [sortDir, setSortDir] = useState('asc')
  const [currentPage, setCurrentPage] = useState(1)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    setLoading(true)
    setError('')
    try {
      const [patientsRes, predictionsRes] = await Promise.all([
        api.get('/patients').catch(() => ({ data: [] })),
        api.get('/predictions').catch(() => ({ data: [] })),
      ])
      setPatients(patientsRes.data || [])
      setPredictions(predictionsRes.data || [])
    } catch {
      setError('Error al cargar los pacientes')
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

  // Get latest prediction per patient
  const getLatestPrediction = (patientId) => {
    const patientPreds = predictions
      .filter((p) => p.patient_id === patientId)
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    return patientPreds[0] || null
  }

  // Filter patients by search term
  const filtered = patients.filter((p) => {
    if (!searchTerm) return true
    const term = searchTerm.toLowerCase()
    return (
      p.first_name?.toLowerCase().includes(term) ||
      p.last_name?.toLowerCase().includes(term) ||
      `${p.first_name} ${p.last_name}`.toLowerCase().includes(term)
    )
  })

  // Sort patients
  const sorted = [...filtered].sort((a, b) => {
    let comparison = 0
    if (sortBy === 'name') {
      comparison = `${a.first_name} ${a.last_name}`.localeCompare(
        `${b.first_name} ${b.last_name}`
      )
    } else if (sortBy === 'risk') {
      const riskOrder = { high: 3, alto: 3, medium: 2, medio: 2, low: 1, bajo: 1 }
      const aRisk = riskOrder[getLatestPrediction(a.id)?.risk_level?.toLowerCase()] || 0
      const bRisk = riskOrder[getLatestPrediction(b.id)?.risk_level?.toLowerCase()] || 0
      comparison = bRisk - aRisk
    } else if (sortBy === 'age') {
      comparison = calculateAge(a.date_of_birth) - calculateAge(b.date_of_birth)
    }
    return sortDir === 'asc' ? comparison : -comparison
  })

  // Pagination
  const totalPages = Math.ceil(sorted.length / ITEMS_PER_PAGE)
  const paginated = sorted.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  )

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(field)
      setSortDir('asc')
    }
    setCurrentPage(1)
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
          <h1 className="text-2xl font-bold text-gray-800">Pacientes</h1>
          <p className="text-sm text-gray-500 mt-1">
            {patients.length} paciente{patients.length !== 1 ? 's' : ''} registrado{patients.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchData} className="btn-secondary gap-2" title="Actualizar">
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

      {/* Search and sort */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value)
              setCurrentPage(1)
            }}
            placeholder="Buscar por nombre..."
            className="form-input pl-9"
          />
        </div>
        <select
          value={sortBy}
          onChange={(e) => handleSort(e.target.value)}
          className="form-input w-auto"
        >
          <option value="name">Ordenar por Nombre</option>
          <option value="age">Ordenar por Edad</option>
          <option value="risk">Ordenar por Riesgo</option>
        </select>
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
          <Users className="w-12 h-12 mb-3" />
          <p className="text-sm font-medium">
            {searchTerm ? 'No se encontraron pacientes' : 'No hay pacientes registrados'}
          </p>
          {!searchTerm && (
            <button
              onClick={() => navigate('/patients/new')}
              className="btn-primary gap-2 mt-4 text-xs"
            >
              <Plus className="w-3 h-3" />
              Registrar Primer Paciente
            </button>
          )}
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
                      onClick={() => handleSort('name')}
                    >
                      Nombre {sortBy === 'name' && (sortDir === 'asc' ? '↑' : '↓')}
                    </th>
                    <th
                      className="table-header px-4 py-3 cursor-pointer hover:text-gray-700"
                      onClick={() => handleSort('age')}
                    >
                      Edad {sortBy === 'age' && (sortDir === 'asc' ? '↑' : '↓')}
                    </th>
                    <th className="table-header px-4 py-3">Última Glucosa</th>
                    <th
                      className="table-header px-4 py-3 cursor-pointer hover:text-gray-700"
                      onClick={() => handleSort('risk')}
                    >
                      Nivel de Riesgo {sortBy === 'risk' && (sortDir === 'asc' ? '↑' : '↓')}
                    </th>
                    <th className="table-header px-4 py-3 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {paginated.map((patient) => {
                    const latestPred = getLatestPrediction(patient.id)
                    return (
                      <tr
                        key={patient.id}
                        className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                      >
                        <td className="table-cell font-medium">
                          {patient.first_name} {patient.last_name}
                        </td>
                        <td className="table-cell">
                          {calculateAge(patient.date_of_birth)} años
                        </td>
                        <td className="table-cell text-gray-500">
                          {latestPred?.glucose_level
                            ? `${latestPred.glucose_level} mg/dL`
                            : '-'}
                        </td>
                        <td className="table-cell">
                          {latestPred ? (
                            <span className={getRiskBadgeClass(latestPred.risk_level)}>
                              {getRiskLabel(latestPred.risk_level)}
                            </span>
                          ) : (
                            <span className="text-gray-400 text-xs">Sin evaluar</span>
                          )}
                        </td>
                        <td className="table-cell text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => navigate(`/patients/${patient.id}`)}
                              className="text-xs text-primary-500 hover:text-primary-700 font-medium flex items-center gap-1"
                            >
                              <Eye className="w-3.5 h-3.5" />
                              Ver
                            </button>
                            <button
                              onClick={() => navigate(`/predict/${patient.id}`)}
                              className="text-xs text-risk-medium hover:text-risk-medium-dark font-medium flex items-center gap-1"
                            >
                              <TrendingUp className="w-3.5 h-3.5" />
                              Predecir
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
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
