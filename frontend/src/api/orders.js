import api from './index'

export const listOrders = (params) => api.get('/orders/', { params })
export const getOrder = (id) => api.get(`/orders/${id}`)
export const createOrder = (data) => api.post('/orders/', data)
export const getOrderItems = (id) => api.get(`/orders/${id}/items`)
export const getPartsSummary = (id) => api.get(`/orders/${id}/parts-summary`)
export const updateOrderStatus = (id, status) =>
  api.patch(`/orders/${id}/status`, { status })
