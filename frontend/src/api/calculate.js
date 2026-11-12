import { publicSourceIds } from '../lib/publicSources'
import { request } from './client'
import { runSearch } from './searchJobs'

export const calculateUpgrade = (payload, options) => payload.refresh_avito_prices
  ? runSearch('calculate', {...payload,price_sources:publicSourceIds(payload.price_sources)}, options)
  : request('/api/calculate', { method: 'POST', body: {...payload,price_sources:publicSourceIds(payload.price_sources)} })
