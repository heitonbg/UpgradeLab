import { request } from './client'

export const getListings = () => request('/api/listings')
export const createListing = (payload) =>
  request('/api/listings', { method: 'POST', body: payload })