import api from './index'

export const listHandcraft = (params) => api.get('/handcraft/', { params })
export const getHandcraftSuppliers = () => api.get('/handcraft/suppliers')
export const getHandcraft = (id) => api.get(`/handcraft/${id}`)
export const deleteHandcraft = (id) => api.delete(`/handcraft/${id}`)
export const getHandcraftParts = (id) => api.get(`/handcraft/${id}/parts`)
export const getHandcraftJewelries = (id) => api.get(`/handcraft/${id}/jewelries`)
export const createHandcraft = (data) => api.post('/handcraft/', data)
export const sendHandcraft = (id) => api.post(`/handcraft/${id}/send`)
export const receiveHandcraft = (id, receipts) =>
  api.post(`/handcraft/${id}/receive`, { receipts })
export const downloadHandcraftExcel = (id) =>
  api.get(`/handcraft/${id}/excel`, {
    responseType: 'blob',
  })
export const downloadHandcraftPdf = (id) =>
  api.get(`/handcraft/${id}/pdf`, {
    responseType: 'blob',
  })
export const addHandcraftPart = (id, data) => api.post(`/handcraft/${id}/parts`, data)
export const updateHandcraftPart = (id, itemId, data) => api.put(`/handcraft/${id}/parts/${itemId}`, data)
export const deleteHandcraftPart = (id, itemId) => api.delete(`/handcraft/${id}/parts/${itemId}`)
export const addHandcraftJewelry = (id, data) => api.post(`/handcraft/${id}/jewelries`, data)
export const updateHandcraftJewelry = (id, itemId, data) => api.put(`/handcraft/${id}/jewelries/${itemId}`, data)
export const deleteHandcraftJewelry = (id, itemId) => api.delete(`/handcraft/${id}/jewelries/${itemId}`)
export const updateHandcraft = (id, data) => api.patch(`/handcraft/${id}`, data)
export const updateHandcraftStatus = (id, status) => api.patch(`/handcraft/${id}/status`, { status })
export const updateHandcraftDeliveryImages = (id, deliveryImages) =>
  api.patch(`/handcraft/${id}/delivery-images`, { delivery_images: deliveryImages })

// --- Order links ---
export const getHandcraftPartOrders = (orderId, itemId) =>
  api.get(`/handcraft/${orderId}/parts/${itemId}/orders`)
export const deleteHandcraftPartOrderLink = (orderId, itemId, linkId) =>
  api.delete(`/handcraft/${orderId}/parts/${itemId}/orders/${linkId}`)
export const getHandcraftJewelryOrders = (orderId, itemId) =>
  api.get(`/handcraft/${orderId}/jewelries/${itemId}/orders`)
export const deleteHandcraftJewelryOrderLink = (orderId, itemId, linkId) =>
  api.delete(`/handcraft/${orderId}/jewelries/${itemId}/orders/${linkId}`)
