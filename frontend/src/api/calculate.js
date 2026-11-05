import { request } from './client'
import { runSearch } from './searchJobs'

export const calculateUpgrade = (payload, options) => payload.refresh_avito_prices
  ? runSearch('calculate', payload, options)
  : request('/api/calculate', { method: 'POST', body: payload })
