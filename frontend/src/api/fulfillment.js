import api from './index'

export const getFulfillment = id => api.get(`/fulfillment/orders/${encodeURIComponent(id)}`)
export const getFulfillmentBatch = ids => api.get('/fulfillment/orders', { params: { order_ids: ids.join(',') } })
export const activateFulfillment = id => api.post(`/fulfillment/orders/${encodeURIComponent(id)}/activate`, { confirmed_no_prior_shipments: true })
export const updateReservation = (id, lineId, data) => api.put(`/fulfillment/orders/${encodeURIComponent(id)}/reservations/${lineId}`, data)
export const listShipments = orderId => api.get('/fulfillment/shipments', { params: { order_id: orderId } })
export const getShipment = id => api.get(`/fulfillment/shipments/${encodeURIComponent(id)}`)
export const createShipment = data => api.post('/fulfillment/shipments', data)
export const confirmShipment = id => api.post(`/fulfillment/shipments/${encodeURIComponent(id)}/confirm`, { actual_goods_checked: true })
export const voidShipment = id => api.post(`/fulfillment/shipments/${encodeURIComponent(id)}/void`)
