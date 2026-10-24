import { request } from './client'

export const calculateUpgrade = (payload) =>
  request('/api/calculate', { method: 'POST', body: payload })