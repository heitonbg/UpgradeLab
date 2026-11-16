import { request } from './client'

// Selector records contain hardware attributes, not live prices. Reuse them
// across calculator modes to avoid repeating the same large catalog request.
let pending
let cached
let cachedAt = 0
const CACHE_MS = 5 * 60 * 1000
export function getHardware({refresh=false}={}) {
  if (!refresh && cached && Date.now()-cachedAt < CACHE_MS) return Promise.resolve(cached)
  if (!pending) pending = request('/api/hardware/selectors').finally(() => { pending = null })
  return pending.then(data=>{cached=data;cachedAt=Date.now();return data})
}
