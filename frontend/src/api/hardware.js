import { request } from './client'

export const getHardware = () => request('/api/hardware')