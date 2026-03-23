import api from './index'

export const listPurchaseOrders = (params) => api.get('/purchase-orders/', { params })
export const getPurchaseOrderVendors = () => api.get('/purchase-orders/vendors')
export const createPurchaseOrder = (data) => api.post('/purchase-orders/', data)
export const getPurchaseOrder = (id) => api.get(`/purchase-orders/${id}`)
export const deletePurchaseOrder = (id) => api.delete(`/purchase-orders/${id}`)
export const updatePurchaseOrderStatus = (id, status) => api.patch(`/purchase-orders/${id}/status`, { status })
export const updatePurchaseOrderDeliveryImages = (id, deliveryImages) => api.patch(`/purchase-orders/${id}/delivery-images`, { delivery_images: deliveryImages })
export const updatePurchaseOrderItem = (id, itemId, data) => api.put(`/purchase-orders/${id}/items/${itemId}`, data)
export const deletePurchaseOrderItem = (id, itemId) => api.delete(`/purchase-orders/${id}/items/${itemId}`)
export const createPurchaseOrderItemAddon = (id, itemId, data) => api.post(`/purchase-orders/${id}/items/${itemId}/addons`, data)
export const updatePurchaseOrderItemAddon = (id, itemId, addonId, data) => api.put(`/purchase-orders/${id}/items/${itemId}/addons/${addonId}`, data)
export const deletePurchaseOrderItemAddon = (id, itemId, addonId) => api.delete(`/purchase-orders/${id}/items/${itemId}/addons/${addonId}`)
