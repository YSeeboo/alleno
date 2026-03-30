import api from './index'

export const listOrders = (params) => api.get('/orders/', { params })
export const getOrder = (id) => api.get(`/orders/${id}`)
export const createOrder = (data) => api.post('/orders/', data)
export const getOrderItems = (id) => api.get(`/orders/${id}/items`)
export const addOrderItem = (id, data) => api.post(`/orders/${id}/items`, data)
export const deleteOrderItem = (id, itemId) => api.delete(`/orders/${id}/items/${itemId}`)
export const getPartsSummary = (id) => api.get(`/orders/${id}/parts-summary`)
export const updateOrderStatus = (id, status) =>
  api.patch(`/orders/${id}/status`, { status })

// --- TodoList & Links ---
export const generateTodo = (id) => api.post(`/orders/${id}/todo`)
export const getTodo = (id) => api.get(`/orders/${id}/todo`)
export const createLink = (orderId, data) => api.post(`/orders/${orderId}/links`, data)
export const batchLink = (orderId, data) => api.post(`/orders/${orderId}/links/batch`, data)
export const deleteLink = (linkId) => api.delete(`/orders/links/${linkId}`)
export const getProgress = (id) => api.get(`/orders/${id}/progress`)

// --- Cost Snapshot & Packaging Cost ---
export const getCostSnapshot = (orderId) => api.get(`/orders/${orderId}/cost-snapshot`)
export const updatePackagingCost = (orderId, data) => api.patch(`/orders/${orderId}/packaging-cost`, data)
