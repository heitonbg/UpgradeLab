export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

let pendingRequests = 0
const requestListeners = new Set()
export const getPendingRequests = () => pendingRequests
export const subscribeRequests = listener => {
  requestListeners.add(listener)
  return () => requestListeners.delete(listener)
}
function publishRequests() { requestListeners.forEach(listener => listener()) }

export async function request(path, options = {}) {
  pendingRequests += 1
  publishRequests()
  try { return await performRequest(path, options) }
  finally { pendingRequests -= 1; publishRequests() }
}

async function performRequest(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!res.ok) {
    if (res.status === 401 && !['/api/auth/me', '/api/auth/login', '/api/auth/register'].includes(path)) {
      window.dispatchEvent(new Event('upgradelab:session-expired'))
    }
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
