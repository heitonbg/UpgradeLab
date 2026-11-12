import { apiUrl } from './config.js'

export class ApiError extends Error {
  constructor(status, message, challenge = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.challenge = challenge
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

async function performRequest(path, { method = 'GET', body, timeoutMs, headers = {} } = {}) {
  const url = apiUrl(path)
  const controller = timeoutMs ? new AbortController() : null
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null
  let res
  try { res = await fetch(url, {
    method,
    credentials: 'include',
    cache: 'no-store',
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...headers },
    body: body ? JSON.stringify(body) : undefined,
    signal: controller?.signal,
  }) } catch {
    throw new Error('Нет ответа от backend. Проверьте, запущено ли приложение Amvera, и повторите запрос.')
  } finally { if (timer) clearTimeout(timer) }

  if (!res.ok) {
    if (res.status === 401 && !['/api/auth/me', '/api/auth/login', '/api/auth/register'].includes(path)) {
      window.dispatchEvent(new Event('upgradelab:session-expired'))
    }
    let detail = `HTTP ${res.status}`
    let challenge = null
    try {
      const data = await res.json()
      if (typeof data?.detail === 'string') detail = data.detail
      else if (typeof data?.detail?.message === 'string') {
        detail = data.detail.message
        challenge = data.detail.challenge || null
      } else if (Array.isArray(data?.detail)) {
        detail = data.detail.map((e) => e.msg ?? JSON.stringify(e)).join('; ')
      }
    } catch { /* ignore */ }
    throw new ApiError(res.status, detail, challenge)
  }

  if (res.status === 204) return null
  return res.json()
}
