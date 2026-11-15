import api from '../api/axios'

/**
 * Descarga un archivo protegido por autenticación (PDF/CSV) vía axios
 * (window.open no puede enviar el header Authorization Bearer).
 */
export async function downloadFile(url, fallbackName = 'descarga') {
  const response = await api.get(url, { responseType: 'blob' })
  const contentType = response.headers['content-type'] || 'application/octet-stream'

  let ext = '.bin'
  if (contentType.includes('pdf')) ext = '.pdf'
  else if (contentType.includes('csv')) ext = '.csv'

  const disposition = response.headers['content-disposition'] || ''
  const match = disposition.match(/filename="?([^";]+)"?/)
  const name = match ? match[1] : fallbackName + ext

  const blob = new Blob([response.data], { type: contentType })
  const link = document.createElement('a')
  link.href = window.URL.createObjectURL(blob)
  link.download = name
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(link.href)
  return name
}
