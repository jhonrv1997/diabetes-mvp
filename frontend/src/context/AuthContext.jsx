import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../api/axios'

const AuthContext = createContext(null)

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth debe usarse dentro de un AuthProvider')
  }
  return context
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)

  const login = useCallback(async (username, password) => {
    try {
      const formData = new URLSearchParams()
      formData.append('username', username)
      formData.append('password', password)

      const response = await api.post('/auth/login', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })

      const { access_token } = response.data
      localStorage.setItem('access_token', access_token)
      setToken(access_token)
      setIsAuthenticated(true)

      // Fetch user data after login
      const userResponse = await api.get('/auth/me')
      const userData = userResponse.data
      localStorage.setItem('user', JSON.stringify(userData))
      setUser(userData)

      return { success: true }
    } catch (error) {
      let message = 'Error al iniciar sesión'
      if (error.response?.status === 401) {
        message = 'Credenciales inválidas'
      } else if (error.response?.status === 422) {
        message = 'Datos de entrada inválidos'
      } else if (error.message) {
        message = error.message
      }
      return { success: false, message }
    }
  }, [])

  const register = useCallback(async (userData) => {
    try {
      const response = await api.post('/auth/register', userData)
      return { success: true, data: response.data }
    } catch (error) {
      let message = 'Error al registrar usuario'
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail
        if (Array.isArray(detail)) {
          message = detail.map((e) => e.msg).join(', ')
        } else {
          message = detail
        }
      }
      return { success: false, message }
    }
  }, [])

  const getCurrentUser = useCallback(async () => {
    try {
      const response = await api.get('/auth/me')
      const userData = response.data
      localStorage.setItem('user', JSON.stringify(userData))
      setUser(userData)
      return userData
    } catch {
      logout()
      return null
    }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    setToken(null)
    setUser(null)
    setIsAuthenticated(false)
    window.location.href = '/login'
  }, [])

  // Check token on mount
  useEffect(() => {
    const savedToken = localStorage.getItem('access_token')
    const savedUser = localStorage.getItem('user')

    if (savedToken) {
      setToken(savedToken)
      setIsAuthenticated(true)

      if (savedUser) {
        try {
          setUser(JSON.parse(savedUser))
        } catch {
          // Invalid stored user data
        }
      }

      // Verify token is still valid
      api
        .get('/auth/me')
        .then((response) => {
          const userData = response.data
          localStorage.setItem('user', JSON.stringify(userData))
          setUser(userData)
        })
        .catch(() => {
          logout()
        })
        .finally(() => {
          setLoading(false)
        })
    } else {
      setLoading(false)
    }
  }, [logout])

  const value = {
    user,
    token,
    isAuthenticated,
    loading,
    login,
    logout,
    register,
    getCurrentUser,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
