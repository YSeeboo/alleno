import api from './index'

export const listHandcraftDispatchedSummary = (params) => api.get('/handcraft-summary/dispatched', { params })
export const listHandcraftReceivedSummary = (params) => api.get('/handcraft-summary/received', { params })
