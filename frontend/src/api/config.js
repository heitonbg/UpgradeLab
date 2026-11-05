const configuredApiBase = import.meta.env?.VITE_API_BASE_URL || ''

export const API_BASE_URL = configuredApiBase.replace(/\/+$/, '')

export function apiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${normalizedPath}`
}
