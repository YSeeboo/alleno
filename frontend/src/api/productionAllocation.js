import api from './index'

export const getOrderProduction = (orderId) => api.get(`/orders/${orderId}/production`)
export const replaceOrderProduction = (orderId, data) => api.put(`/orders/${orderId}/production`, data)
export const createOrderHandcraft = (orderId, data) => api.post(`/orders/${orderId}/production/handcraft`, data, { _silentError: true })
export const getProductionUses = (type, id) => api.get(`/${type}/${id}/production-uses`)
