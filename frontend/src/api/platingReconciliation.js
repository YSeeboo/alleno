import api from './index'

export const listReconciliation = (params) => api.get('/plating-reconciliation/', { params, _silentError: true })
export const updateReconciliationPrice = (id, overridePrice) =>
  api.patch(`/plating-reconciliation/items/${id}`, { override_price: overridePrice }, { _silentError: true })
export const downloadReconciliationExcel = (params) =>
  api.get('/plating-reconciliation/excel', { params, responseType: 'blob', _silentError: true })
