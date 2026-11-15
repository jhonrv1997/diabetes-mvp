import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import Login from './components/Login'
import Dashboard from './components/Dashboard'
import PatientForm from './components/PatientForm'
import PatientList from './components/PatientList'
import PatientDetail from './components/PatientDetail'
import ClinicalDataForm from './components/ClinicalDataForm'
import PredictionView from './components/PredictionView'
import PredictionHistory from './components/PredictionHistory'
import AlertPanel from './components/AlertPanel'
import DeviceManager from './components/DeviceManager'
// Epic 04 — Sprint 03: Nuevos módulos
import NotificationsPanel from './components/NotificationsPanel'
import NutritionPanel from './components/NutritionPanel'
import AppointmentsPanel from './components/AppointmentsPanel'
// Epic 05 — Sprint 04: Reportes, usuarios y auditoría
import ReportsPanel from './components/ReportsPanel'
import UsersPanel from './components/UsersPanel'
import AuditPanel from './components/AuditPanel'

/**
 * Error boundary global: evita la pantalla en blanco ante un error de
 * renderizado y muestra el detalle para diagnóstico.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary capturó:', error, info?.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-background p-6">
          <div className="max-w-xl w-full bg-white rounded-xl shadow-lg border border-red-100 p-6">
            <h1 className="text-lg font-bold text-red-600 mb-2">Ocurrió un error inesperado</h1>
            <pre className="text-xs text-gray-700 bg-gray-50 rounded-lg p-3 overflow-auto whitespace-pre-wrap">
              {String(this.state.error?.message || this.state.error)}
            </pre>
            <button
              onClick={() => window.location.reload()}
              className="btn-primary mt-4"
            >
              Recargar
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="spinner"></div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return children
}

/**
 * Epic 05 — HU12: ruta restringida por rol.
 * Cada profesional solo accede a los módulos de su función; si intenta
 * entrar a una ruta restringida se le redirige a su pantalla principal.
 */
function RoleRoute({ children, roles }) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="spinner"></div>
      </div>
    )
  }

  if (!user || !roles.includes(user.role)) {
    // La nutricionista no tiene Dashboard: su módulo principal es Nutrición
    return <Navigate to={user?.role === 'nutritionist' ? '/nutrition' : '/dashboard'} replace />
  }

  return children
}

/** Página de inicio según el rol (HU12). */
function HomeRedirect() {
  const { user } = useAuth()
  return (
    <Navigate
      to={user?.role === 'nutritionist' ? '/nutrition' : '/dashboard'}
      replace
    />
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<HomeRedirect />} />
        <Route
          path="dashboard"
          element={
            <RoleRoute roles={['admin', 'nurse', 'doctor', 'health_manager']}>
              <Dashboard />
            </RoleRoute>
          }
        />
        <Route path="patients" element={<PatientList />} />
        <Route
          path="patients/new"
          element={
            <RoleRoute roles={['admin', 'nurse']}>
              <PatientForm />
            </RoleRoute>
          }
        />
        <Route path="patients/:id" element={<PatientDetail />} />
        <Route
          path="patients/:id/edit"
          element={
            <RoleRoute roles={['admin', 'nurse']}>
              <PatientForm />
            </RoleRoute>
          }
        />
        <Route
          path="clinical-data"
          element={
            <RoleRoute roles={['admin', 'nurse']}>
              <ClinicalDataForm />
            </RoleRoute>
          }
        />
        <Route
          path="clinical-data/:patientId"
          element={
            <RoleRoute roles={['admin', 'nurse']}>
              <ClinicalDataForm />
            </RoleRoute>
          }
        />
        <Route
          path="predict/:patientId"
          element={
            <RoleRoute roles={['admin', 'nurse', 'doctor']}>
              <PredictionView />
            </RoleRoute>
          }
        />
        <Route path="history/:patientId" element={<PredictionHistory />} />
        <Route
          path="devices"
          element={
            <RoleRoute roles={['admin', 'nurse']}>
              <DeviceManager />
            </RoleRoute>
          }
        />
        <Route
          path="alerts"
          element={
            <RoleRoute roles={['admin', 'nurse', 'doctor']}>
              <AlertPanel />
            </RoleRoute>
          }
        />
        {/* Epic 04 — Sprint 03 */}
        <Route
          path="notifications"
          element={
            <RoleRoute roles={['admin', 'nurse', 'doctor']}>
              <NotificationsPanel />
            </RoleRoute>
          }
        />
        <Route
          path="nutrition"
          element={
            <RoleRoute roles={['admin', 'nutritionist']}>
              <NutritionPanel />
            </RoleRoute>
          }
        />
        <Route
          path="appointments"
          element={
            <RoleRoute roles={['admin', 'nurse']}>
              <AppointmentsPanel />
            </RoleRoute>
          }
        />
        {/* Epic 05 — Sprint 04 (HU07 / HU11 / HU12) */}
        <Route
          path="reports"
          element={
            <RoleRoute roles={['admin', 'health_manager']}>
              <ReportsPanel />
            </RoleRoute>
          }
        />
        <Route
          path="users"
          element={
            <RoleRoute roles={['admin']}>
              <UsersPanel />
            </RoleRoute>
          }
        />
        <Route
          path="audit"
          element={
            <RoleRoute roles={['admin']}>
              <AuditPanel />
            </RoleRoute>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
