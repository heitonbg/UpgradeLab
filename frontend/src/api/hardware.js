import { request } from './client'

// Hidden calculator panels share the same request while it is in progress.
// Responses are never cached: a later call still observes the current prices.
let pending
export function getHardware() {
  if (!pending) pending = request('/api/hardware').finally(() => { pending = null })
  return pending
}
