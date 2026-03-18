import api from './index'

export const listHandcraft = (params) => api.get('/handcraft/', { params })
export const getHandcraft = (id) => api.get(`/handcraft/${id}`)
export const getHandcraftParts = (id) => api.get(`/handcraft/${id}/parts`)
export const getHandcraftJewelries = (id) => api.get(`/handcraft/${id}/jewelries`)
export const createHandcraft = (data) => api.post('/handcraft/', data)
export const sendHandcraft = (id) => api.post(`/handcraft/${id}/send`)
export const receiveHandcraft = (id, receipts) =>
  api.post(`/handcraft/${id}/receive`, { receipts })
export const addHandcraftPart = (id, data) => api.post(`/handcraft/${id}/parts`, data)
export const updateHandcraftPart = (id, itemId, data) => api.put(`/handcraft/${id}/parts/${itemId}`, data)
export const deleteHandcraftPart = (id, itemId) => api.delete(`/handcraft/${id}/parts/${itemId}`)
export const addHandcraftJewelry = (id, data) => api.post(`/handcraft/${id}/jewelries`, data)
export const updateHandcraftJewelry = (id, itemId, data) => api.put(`/handcraft/${id}/jewelries/${itemId}`, data)
export const deleteHandcraftJewelry = (id, itemId) => api.delete(`/handcraft/${id}/jewelries/${itemId}`)
export const updateHandcraftStatus = (id, status) => api.patch(`/handcraft/${id}/status`, { status })
