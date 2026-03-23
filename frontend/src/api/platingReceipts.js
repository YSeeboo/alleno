import api from './index'

export const listPlatingReceipts = (params) => api.get('/plating-receipts/', { params })
export const getPlatingReceiptVendors = () => api.get('/plating-receipts/vendors')
export const createPlatingReceipt = (data) => api.post('/plating-receipts/', data)
export const getPlatingReceipt = (id) => api.get(`/plating-receipts/${id}`)
export const deletePlatingReceipt = (id) => api.delete(`/plating-receipts/${id}`)
export const updatePlatingReceiptStatus = (id, status) => api.patch(`/plating-receipts/${id}/status`, { status })
export const updatePlatingReceiptDeliveryImages = (id, deliveryImages) => api.patch(`/plating-receipts/${id}/delivery-images`, { delivery_images: deliveryImages })
export const updatePlatingReceiptItem = (id, itemId, data) => api.put(`/plating-receipts/${id}/items/${itemId}`, data)
export const deletePlatingReceiptItem = (id, itemId) => api.delete(`/plating-receipts/${id}/items/${itemId}`)
