import api from './index'

export const listParts = (params) => api.get('/parts/', { params })
export const getPart = (id) => api.get(`/parts/${id}`)
export const createPart = (data) => api.post('/parts/', data)
export const updatePart = (id, data) => api.patch(`/parts/${id}`, data)
export const deletePart = (id) => api.delete(`/parts/${id}`)
