import api from './index'

export const listHandcraftReceipts = (params) => api.get('/handcraft-receipts/', { params })
export const getHandcraftReceiptSuppliers = () => api.get('/handcraft-receipts/suppliers')
export const createHandcraftReceipt = (data) => api.post('/handcraft-receipts/', data)
export const getHandcraftReceipt = (id) => api.get(`/handcraft-receipts/${id}`)
export const deleteHandcraftReceipt = (id) => api.delete(`/handcraft-receipts/${id}`)
export const updateHandcraftReceiptStatus = (id, status) => api.patch(`/handcraft-receipts/${id}/status`, { status })
export const updateHandcraftReceiptDeliveryImages = (id, deliveryImages) => api.patch(`/handcraft-receipts/${id}/delivery-images`, { delivery_images: deliveryImages })
export const updateHandcraftReceiptItem = (id, itemId, data) => api.put(`/handcraft-receipts/${id}/items/${itemId}`, data)
export const deleteHandcraftReceiptItem = (id, itemId) => api.delete(`/handcraft-receipts/${id}/items/${itemId}`)
export const addHandcraftReceiptItems = (id, data) => api.post(`/handcraft-receipts/${id}/items`, data)
export const listHandcraftPendingReceiveItems = (params) => api.get('/handcraft/items/pending-receive', { params })
