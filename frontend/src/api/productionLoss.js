import request from './index'

export function confirmPlatingLoss(orderId, itemId, data) {
  return request.post(`/plating/${orderId}/items/${itemId}/confirm-loss`, data)
}

export function confirmHandcraftLoss(orderId, itemId, data) {
  return request.post(`/handcraft/${orderId}/items/${itemId}/confirm-loss`, data)
}

export function batchConfirmPlatingLoss(receiptId, data) {
  return request.post(`/plating-receipts/${receiptId}/confirm-loss`, data)
}

export function batchConfirmHandcraftLoss(receiptId, data) {
  return request.post(`/handcraft-receipts/${receiptId}/confirm-loss`, data)
}
