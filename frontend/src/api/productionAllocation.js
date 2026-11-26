import api from './index'

export const getOrderProduction = (orderId) => api.get(`/orders/${orderId}/production`)
export const replaceOrderProduction = (orderId, data) => api.put(`/orders/${orderId}/production`, data)
export const replaceOrderProductionBatch = (orderId, sources) => api.post(`/orders/${orderId}/production/batch`, { sources })
export const createOrderHandcraft = (orderId, data) => api.post(`/orders/${orderId}/production/handcraft`, data, { _silentError: true })
export const createOrderHandcraftBatch = (orderId, data) => api.post(`/orders/${encodeURIComponent(orderId)}/production/handcraft/batch`, data, { _silentError: true })
export const getProductionUses = (type, id) => api.get(`/${type}/${id}/production-uses`)
