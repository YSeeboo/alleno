import api from './index'

export const listJewelries = (params) => api.get('/jewelries/', { params })
export const getJewelry = (id) => api.get(`/jewelries/${id}`)
export const createJewelry = (data) => api.post('/jewelries/', data)
export const updateJewelry = (id, data) => api.patch(`/jewelries/${id}`, data)
export const updateJewelryStatus = (id, status) =>
  api.patch(`/jewelries/${id}/status`, { status })
export const deleteJewelry = (id) => api.delete(`/jewelries/${id}`)
