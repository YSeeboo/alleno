import api from './index'

export const getBom = (jewelryId) => api.get(`/bom/${jewelryId}`)
export const setBom = (jewelryId, partId, qtyPerUnit) =>
  api.put(`/bom/${jewelryId}/${partId}`, { qty_per_unit: qtyPerUnit })
export const deleteBom = (jewelryId, partId) =>
  api.delete(`/bom/${jewelryId}/${partId}`)
