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

export default function App() {
  return (
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
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="patients" element={<PatientList />} />
        <Route path="patients/new" element={<PatientForm />} />
        <Route path="patients/:id" element={<PatientDetail />} />
        <Route path="patients/:id/edit" element={<PatientForm />} />
        <Route path="clinical-data" element={<ClinicalDataForm />} />
        <Route path="clinical-data/:patientId" element={<ClinicalDataForm />} />
        <Route path="predict/:patientId" element={<PredictionView />} />
        <Route path="history/:patientId" element={<PredictionHistory />} />
        <Route path="devices" element={<DeviceManager />} />
        <Route path="alerts" element={<AlertPanel />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
