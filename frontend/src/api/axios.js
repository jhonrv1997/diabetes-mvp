import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor: add Authorization Bearer token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor: handle 401 and errors
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    if (error.response) {
      const status = error.response.status

      if (status === 401) {
        localStorage.removeItem('access_token')
        localStorage.removeItem('user')
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
      }

      if (status === 422) {
        const detail = error.response.data?.detail
        if (Array.isArray(detail)) {
          error.message = detail.map((e) => e.msg).join(', ')
        } else if (typeof detail === 'string') {
          error.message = detail
        }
      }
    } else if (error.request) {
      error.message = 'No se pudo conectar con el servidor. Verifique su conexión.'
    }

    return Promise.reject(error)
  }
)

export default api