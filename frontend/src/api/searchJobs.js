import { request, ApiError } from './client.js'

const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
const retryable = error => !(error instanceof ApiError) || [429, 502, 503, 504].includes(error.status)
const browserStorage = () => { try { return globalThis.sessionStorage } catch { return null } }

export async function runSearch(kind, payload, { onProgress, send = request, sleep = pause,
  storage = browserStorage(), timeoutMs = 240000 } = {}) {
  const key = `upgradelab:search:${kind}`
  const signature = JSON.stringify(payload)
  let saved
  try { saved = JSON.parse(storage?.getItem(key) || 'null') } catch { /* storage can be disabled */ }
  if (saved?.signature !== signature) saved = null
  const state = saved || { signature, requestId: globalThis.crypto.randomUUID().replaceAll('-', '_') }
  const persist = () => { try { storage?.setItem(key, JSON.stringify(state)) } catch { /* optional */ } }
  const clear = () => { try { storage?.removeItem(key) } catch { /* optional */ } }
  persist()
  const deadline = Date.now() + timeoutMs
  let failures = 0
  while (Date.now() < deadline) {
    let job
    try {
      job = state.id
        ? await send(`/api/search-jobs/${state.id}`, { timeoutMs: 12000 })
        : await send('/api/search-jobs', { method: 'POST', timeoutMs: 12000,
          body: { kind, payload, client_request_id: state.requestId } })
      failures = 0
    } catch (error) {
      if (state.id && error instanceof ApiError && error.status === 404) {
        clear()
        throw new Error('Сервер больше не хранит этот поиск. Запустите подбор снова.')
      }
      if (!retryable(error)) {
        clear()
        if (error.status === 404) throw new Error('На backend ещё нет нового поиска. Загрузите обновлённый backend и пересоберите приложение Amvera.')
        throw error
      }
      failures += 1
      onProgress?.('Восстанавливаем связь с backend. Повторный поиск не создаётся.')
      if (failures >= 8) throw new Error('Backend Amvera недоступен. Поиск сохранён в этой вкладке; после запуска сервера нажмите повторить.')
      await sleep(2000)
      continue
    }
    state.id = job.id
    persist()
    onProgress?.(job.progress || 'Поиск выполняется на сервере')
    if (job.status === 'completed') {
      clear()
      return job.result
    }
    if (job.status === 'failed') {
      clear()
      throw new Error(job.error || 'Поиск не завершился. Повторите подбор.')
    }
    await sleep(job.status === 'queued' ? 5000 : 4000)
  }
  throw new Error('Поиск ещё выполняется на сервере. Нажмите повторить, чтобы получить его результат без создания нового поиска.')
}
