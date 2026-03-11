import api from './index'

export const getStock = (itemType, itemId) =>
  api.get(`/inventory/${itemType}/${itemId}`)
export const getStockLog = (itemType, itemId) =>
  api.get(`/inventory/${itemType}/${itemId}/log`)
export const addStock = (itemType, itemId, data) =>
  api.post(`/inventory/${itemType}/${itemId}/add`, data)
export const deductStock = (itemType, itemId, data) =>
  api.post(`/inventory/${itemType}/${itemId}/deduct`, data)
