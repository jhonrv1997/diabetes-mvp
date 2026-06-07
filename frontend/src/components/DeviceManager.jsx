import React, { useState, useEffect } from 'react'
import api from '../api/axios'
import {
  Bluetooth,
  BluetoothSearching,
  RefreshCw,
  Plus,
  Link2,
  Unlink,
  RefreshCcw,
  Battery,
  AlertCircle,
  X,
  CheckCircle,
  Wifi,
  WifiOff,
  Loader2,
} from 'lucide-react'

export default function DeviceManager() {
  const [devices, setDevices] = useState([])
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showPairForm, setShowPairForm] = useState(false)
  const [pairing, setPairing] = useState(false)
  const [syncing, setSyncing] = useState(null)
  const [success, setSuccess] = useState('')

  const [pairForm, setPairForm] = useState({
    ble_address: '',
    patient_id: '',
    device_name: '',
  })

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    setLoading(true)
    setError('')
    try {
      const [devicesRes, patientsRes] = await Promise.all([
        api.get('/devices/status').catch(() => ({ data: [] })),
        api.get('/patients').catch(() => ({ data: [] })),
      ])
      setDevices(devicesRes.data || [])
      setPatients(patientsRes.data || [])
    } catch {
      setError('Error al cargar los dispositivos')
    } finally {
      setLoading(false)
    }
  }

  const handlePair = async (e) => {
    e.preventDefault()
    setPairing(true)
    setError('')
    setSuccess('')

    if (!pairForm.ble_address.trim() || !pairForm.patient_id) {
      setError('Complete la dirección BLE y seleccione un paciente')
      setPairing(false)
      return
    }

    try {
      await api.post('/devices/pair', {
        ble_address: pairForm.ble_address,
        patient_id: pairForm.patient_id,
        device_name: pairForm.device_name || `Glucómetro-${pairForm.ble_address.slice(-4)}`,
      })
      setSuccess('Dispositivo vinculado exitosamente')
      setShowPairForm(false)
      setPairForm({ ble_address: '', patient_id: '', device_name: '' })
      fetchData()
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al vincular el dispositivo')
    } finally {
      setPairing(false)
    }
  }

  const handleSync = async (deviceId) => {
    setSyncing(deviceId)
    setError('')
    try {
      await api.post('/devices/sync', { device_id: deviceId })
      setSuccess('Sincronización completada')
      fetchData()
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al sincronizar el dispositivo')
    } finally {
      setSyncing(null)
    }
  }

  const getStatusConfig = (status) => {
    switch (status?.toLowerCase()) {
      case 'connected':
        return { icon: Wifi, color: 'text-risk-low', bg: 'bg-risk-low-light', label: 'Conectado' }
      case 'disconnected':
        return { icon: WifiOff, color: 'text-gray-400', bg: 'bg-gray-100', label: 'Desconectado' }
      case 'syncing':
        return { icon: Loader2, color: 'text-primary-500', bg: 'bg-primary-50', label: 'Sincronizando' }
      case 'error':
        return { icon: AlertCircle, color: 'text-risk-high', bg: 'bg-risk-high-light', label: 'Error' }
      default:
        return { icon: WifiOff, color: 'text-gray-400', bg: 'bg-gray-100', label: status || 'Desconocido' }
    }
  }

  const getPatientName = (patientId) => {
    const patient = patients.find((p) => p.id === patientId)
    return patient ? `${patient.first_name} ${patient.last_name}` : 'Sin asignar'
  }

  const getBatteryColor = (level) => {
    if (!level) return 'text-gray-400'
    if (level > 60) return 'text-risk-low'
    if (level > 20) return 'text-risk-medium'
    return 'text-risk-high'
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
            <Bluetooth className="w-6 h-6 text-primary-500" />
            Dispositivos
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            {devices.length} dispositivo{devices.length !== 1 ? 's' : ''} registrado{devices.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchData} className="btn-secondary gap-2" title="Actualizar">
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setShowPairForm(!showPairForm)}
            className="btn-primary gap-2"
          >
            <Plus className="w-4 h-4" />
            Vincular Dispositivo
          </button>
        </div>
      </div>

      {/* Success message */}
      {success && (
        <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm flex items-center gap-2">
          <CheckCircle className="w-4 h-4" />
          {success}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Pair device form */}
      {showPairForm && (
        <div className="dashboard-card border-2 border-primary-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <BluetoothSearching className="w-4 h-4 text-primary-500" />
              Vincular Nuevo Dispositivo
            </h3>
            <button
              onClick={() => setShowPairForm(false)}
              className="text-gray-400 hover:text-gray-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <form onSubmit={handlePair} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="device_name" className="form-label">
                  Nombre del Dispositivo
                </label>
                <input
                  id="device_name"
                  type="text"
                  value={pairForm.device_name}
                  onChange={(e) => setPairForm({ ...pairForm, device_name: e.target.value })}
                  className="form-input"
                  placeholder="Ej: Glucómetro Sala 3"
                  disabled={pairing}
                />
              </div>

              <div>
                <label htmlFor="ble_address" className="form-label">
                  Dirección BLE <span className="text-red-500">*</span>
                </label>
                <input
                  id="ble_address"
                  type="text"
                  value={pairForm.ble_address}
                  onChange={(e) => setPairForm({ ...pairForm, ble_address: e.target.value })}
                  className="form-input"
                  placeholder="Ej: AA:BB:CC:DD:EE:FF"
                  disabled={pairing}
                  required
                />
              </div>

              <div className="sm:col-span-2">
                <label htmlFor="patient_id" className="form-label">
                  Asignar a Paciente <span className="text-red-500">*</span>
                </label>
                <select
                  id="patient_id"
                  value={pairForm.patient_id}
                  onChange={(e) => setPairForm({ ...pairForm, patient_id: e.target.value })}
                  className="form-input"
                  disabled={pairing}
                  required
                >
                  <option value="">Seleccionar paciente...</option>
                  {patients.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.first_name} {p.last_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button type="submit" disabled={pairing} className="btn-primary gap-2">
                {pairing ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Link2 className="w-4 h-4" />
                )}
                Vincular
              </button>
              <button
                type="button"
                onClick={() => setShowPairForm(false)}
                className="btn-secondary gap-2"
              >
                <X className="w-4 h-4" />
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Device list */}
      {devices.length === 0 ? (
        <div className="dashboard-card flex flex-col items-center justify-center py-12 text-gray-400">
          <Bluetooth className="w-12 h-12 mb-3" />
          <p className="text-sm font-medium">No hay dispositivos vinculados</p>
          <p className="text-xs mt-1">Vincule un glucómetro BLE para sincronizar lecturas</p>
          <button
            onClick={() => setShowPairForm(true)}
            className="btn-primary gap-2 mt-4 text-xs"
          >
            <Plus className="w-3 h-3" />
            Vincular Primer Dispositivo
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {devices.map((device, idx) => {
            const statusConfig = getStatusConfig(device.status)
            const StatusIcon = statusConfig.icon

            return (
              <div key={device.id || idx} className="dashboard-card">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Bluetooth className="w-5 h-5 text-primary-500" />
                    <h4 className="text-sm font-semibold text-gray-800">
                      {device.device_name || `Dispositivo ${device.id}`}
                    </h4>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${statusConfig.bg} ${statusConfig.color}`}
                  >
                    <StatusIcon className={`w-3 h-3 ${device.status?.toLowerCase() === 'syncing' ? 'animate-spin' : ''}`} />
                    {statusConfig.label}
                  </span>
                </div>

                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Dirección BLE</span>
                    <span className="text-gray-700 font-mono text-xs">
                      {device.ble_address || '-'}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Paciente</span>
                    <span className="text-gray-700 text-xs">
                      {getPatientName(device.patient_id)}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Última Sincronización</span>
                    <span className="text-gray-700 text-xs">
                      {device.last_sync
                        ? new Date(device.last_sync).toLocaleString('es-ES')
                        : 'Nunca'}
                    </span>
                  </div>

                  {device.battery_level != null && (
                    <div className="flex items-center justify-between">
                      <span className="text-gray-500">Batería</span>
                      <span className={`flex items-center gap-1 text-xs font-medium ${getBatteryColor(device.battery_level)}`}>
                        <Battery className="w-3.5 h-3.5" />
                        {device.battery_level}%
                      </span>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2 mt-4 pt-3 border-t border-gray-100">
                  <button
                    onClick={() => handleSync(device.id)}
                    disabled={syncing === device.id || device.status?.toLowerCase() === 'syncing'}
                    className="btn-primary gap-2 text-xs flex-1"
                  >
                    {syncing === device.id ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <RefreshCcw className="w-3 h-3" />
                    )}
                    Sincronizar
                  </button>
                  <button
                    className="btn-secondary text-xs gap-1 p-2 text-risk-high hover:bg-risk-high-light"
                    title="Desvincular"
                  >
                    <Unlink className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
