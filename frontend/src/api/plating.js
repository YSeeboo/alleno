import api from './index'

export const listPlating = (params) => api.get('/plating/', { params })
export const getPlating = (id) => api.get(`/plating/${id}`)
export const getPlatingItems = (id) => api.get(`/plating/${id}/items`)
export const createPlating = (data) => api.post('/plating/', data)
export const sendPlating = (id) => api.post(`/plating/${id}/send`)
export const receivePlating = (id, receipts) =>
  api.post(`/plating/${id}/receive`, { receipts })
export const downloadPlatingExcel = (id) =>
  api.get(`/plating/${id}/excel`, {
    responseType: 'blob',
  })
export const downloadPlatingPdf = (id) =>
  api.get(`/plating/${id}/pdf`, {
    responseType: 'blob',
  })
export const addPlatingItem = (id, data) => api.post(`/plating/${id}/items`, data)
export const updatePlatingItem = (id, itemId, data) => api.put(`/plating/${id}/items/${itemId}`, data)
export const deletePlatingItem = (id, itemId) => api.delete(`/plating/${id}/items/${itemId}`)
export const updatePlatingStatus = (id, status) => api.patch(`/plating/${id}/status`, { status })
export const updatePlatingDeliveryImages = (id, deliveryImages) =>
  api.patch(`/plating/${id}/delivery-images`, { delivery_images: deliveryImages })
