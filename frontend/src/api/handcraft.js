import api from './index'

export const listHandcraft = (params) => api.get('/handcraft/', { params })
export const getHandcraft = (id) => api.get(`/handcraft/${id}`)
export const getHandcraftParts = (id) => api.get(`/handcraft/${id}/parts`)
export const getHandcraftJewelries = (id) => api.get(`/handcraft/${id}/jewelries`)
export const createHandcraft = (data) => api.post('/handcraft/', data)
export const sendHandcraft = (id) => api.post(`/handcraft/${id}/send`)
export const receiveHandcraft = (id, receipts) =>
  api.post(`/handcraft/${id}/receive`, { receipts })
