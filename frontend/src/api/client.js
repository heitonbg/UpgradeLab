export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const data = await res.json()
      if (typeof data?.detail === 'string') detail = data.detail
      else if (Array.isArray(data?.detail)) {
        detail = data.detail.map((e) => e.msg ?? JSON.stringify(e)).join('; ')
      }
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail)
  }

  if (res.status === 204) return null
  return res.json()
}