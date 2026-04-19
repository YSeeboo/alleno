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
export const getTodo = (id) => api.get(`/orders/${id}/todo`)
export const createLink = (orderId, data) => api.post(`/orders/${orderId}/links`, data)
export const batchLink = (orderId, data) => api.post(`/orders/${orderId}/links/batch`, data)
export const deleteLink = (linkId) => api.delete(`/orders/links/${linkId}`)
export const getProgress = (id) => api.get(`/orders/${id}/progress`)
export const batchGetProgress = (orderIds) =>
  api.get('/orders/batch-progress', { params: { order_ids: orderIds.join(',') } })

// --- Batch & Jewelry Status ---
export const getJewelryStatus = (orderId) => api.get(`/orders/${orderId}/jewelry-status`)
export const getJewelryForBatch = (orderId) => api.get(`/orders/${orderId}/jewelry-for-batch`)
export const createTodoBatch = (orderId, items) =>
  api.post(`/orders/${orderId}/todo-batch`, { items })
export const getTodoBatches = (orderId) => api.get(`/orders/${orderId}/todo-batches`)
export const deleteTodoBatch = (orderId, batchId) => api.delete(`/orders/${orderId}/todo-batch/${batchId}`)
export const linkBatchSupplier = (orderId, batchId, supplierName) =>
  api.post(`/orders/${orderId}/todo-batch/${batchId}/link-supplier`, { supplier_name: supplierName }, { _silentError: true })
export const downloadBatchPdf = (orderId, batchId) =>
  api.get(`/orders/${orderId}/todo-pdf`, { params: { batch_id: batchId }, responseType: 'blob' })
// --- Customer Code ---
export const updateOrderItem = (orderId, itemId, data) =>
  api.patch(`/orders/${orderId}/items/${itemId}`, data)
export const batchFillCustomerCode = (orderId, data) =>
  api.post(`/orders/${orderId}/items/batch-customer-code`, data)

// --- Extra Info ---
export const updateExtraInfo = (orderId, data) =>
  api.patch(`/orders/${orderId}/extra-info`, data)

// --- Cost Snapshot & Packaging Cost ---
export const getCostSnapshot = (orderId) => api.get(`/orders/${orderId}/cost-snapshot`)
export const updatePackagingCost = (orderId, data) => api.patch(`/orders/${orderId}/packaging-cost`, data)

// --- Cutting Stats ---
export const getCuttingStats = (orderId) => api.get(`/orders/${orderId}/cutting-stats`)
export const downloadCuttingStatsPdf = (orderId) =>
  api.post(`/orders/${orderId}/cutting-stats/pdf`, {}, { responseType: 'blob' })

// --- Picking Simulation (配货模拟) ---
export const getPicking = (orderId) => api.get(`/orders/${orderId}/picking`)
export const markPicked = (orderId, partId, qtyPerUnit) =>
  api.post(`/orders/${orderId}/picking/mark`, {
    part_id: partId,
    qty_per_unit: qtyPerUnit,
  })
export const unmarkPicked = (orderId, partId, qtyPerUnit) =>
  api.post(`/orders/${orderId}/picking/unmark`, {
    part_id: partId,
    qty_per_unit: qtyPerUnit,
  })
export const resetPicking = (orderId) =>
  api.delete(`/orders/${orderId}/picking/reset`)
export const downloadPickingListPdf = (orderId, includePicked = false) =>
  api.post(
    `/orders/${orderId}/picking/pdf`,
    { include_picked: includePicked },
    { responseType: 'blob' },
  )
