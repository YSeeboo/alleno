import api from './index'

export const listRestockSummary = () =>
  api.get('/restock-requests/summary')

export const listRestockHistory = (params) =>
  api.get('/restock-requests/history', { params })

export const listHandcraftRestock = (handcraftOrderId) =>
  api.get(`/handcraft/${encodeURIComponent(handcraftOrderId)}/restock-requests`)

export const createRestock = (payload) =>
  api.post('/restock-requests', payload)

export const markRestockDone = (id) =>
  api.patch(`/restock-requests/${id}`, { status: 'done' })

export const deleteRestock = (id) =>
  api.delete(`/restock-requests/${id}`)

export const markPartRestockDone = (partId) =>
  api.post('/restock-requests/mark-part-done', { part_id: partId })

export const updateRestockShortfall = (id, qty) =>
  api.put(`/restock-requests/${id}/shortfall`, { shortfall_qty: qty })
