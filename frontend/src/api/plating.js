import api from './index'

export const listPlating = (params) => api.get('/plating/', { params })
export const getPlating = (id) => api.get(`/plating/${id}`)
export const deletePlating = (id) => api.delete(`/plating/${id}`)
export const getPlatingItems = (id) => api.get(`/plating/${id}/items`)
export const createPlating = (data) => api.post('/plating/', data)
export const sendPlating = (id) => api.post(`/plating/${id}/send`)
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
export const updatePlatingOrder = (id, data) => api.patch(`/plating/${id}`, data)
export const updatePlatingStatus = (id, status) => api.patch(`/plating/${id}/status`, { status })
export const updatePlatingDeliveryImages = (id, deliveryImages) =>
  api.patch(`/plating/${id}/delivery-images`, { delivery_images: deliveryImages })
export const getPlatingSuppliers = () => api.get('/plating/suppliers')
export const listPendingReceiveItems = (params) =>
  api.get('/plating/items/pending-receive', { params })

// --- Order links ---
export const getPlatingItemOrders = (orderId, itemId) =>
  api.get(`/plating/${orderId}/items/${itemId}/orders`)
export const deletePlatingItemOrderLink = (orderId, itemId, linkId) =>
  api.delete(`/plating/${orderId}/items/${itemId}/orders/${linkId}`)
