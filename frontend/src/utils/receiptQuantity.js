// Source received_qty is the settlement counter (receipts + confirmed loss).
export const remainingQuantity = (item) => Math.max(0, Number((Number(item.qty) - Number(item.received_qty || 0)).toFixed(4)))
export const excessQuantity = (item) => Math.max(0, Number((Number(item.received_qty || 0) - Number(item.qty)).toFixed(4)))
export const sourceBalance = (item) => excessQuantity(item) ? `0 · 结清超出 ${excessQuantity(item)}` : remainingQuantity(item)
export const receiptSourceExcess = (item) => excessQuantity({ qty: item.source_qty, received_qty: item.source_received_qty })
