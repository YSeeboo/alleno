import api from './index'

export const listPlating = (params) => api.get('/plating/', { params })
export const getPlating = (id) => api.get(`/plating/${id}`)
export const getPlatingItems = (id) => api.get(`/plating/${id}/items`)
export const createPlating = (data) => api.post('/plating/', data)
export const sendPlating = (id) => api.post(`/plating/${id}/send`)
export const receivePlating = (id, receipts) =>
  api.post(`/plating/${id}/receive`, { receipts })
