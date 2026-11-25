import api from './index'

export const getBom = (jewelryId) => api.get(`/bom/${jewelryId}`)
export const setBom = (jewelryId, partId, qtyPerUnit) =>
  api.put(`/bom/${jewelryId}/${partId}`, { qty_per_unit: qtyPerUnit })
export const deleteBom = (jewelryId, partId) =>
  api.delete(`/bom/${jewelryId}/${partId}`)

export const listBomCopySources = (targetId, params) =>
  api.get(`/bom/${targetId}/copy-sources`, { params, _silentError: true })
export const previewBomCopy = (targetId, sourceId) =>
  api.get(`/bom/${targetId}/copy-preview/${sourceId}`, { _silentError: true })
export const copyBomItems = (targetId, data) =>
  api.post(`/bom/${targetId}/copy`, data, { _silentError: true })
