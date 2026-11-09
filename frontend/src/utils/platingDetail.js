const number = (value) => Number(value) || 0
const rounded = (value) => Number(value.toFixed(4))

// The API's received_qty includes both actual receipts and confirmed losses.
export function platingReceiptQuantities(item) {
  const qty = number(item.qty)
  const settled = number(item.received_qty)
  const loss = number(item.loss_qty)
  return {
    qty,
    actual: rounded(Math.max(0, settled - loss)),
    loss,
    remaining: rounded(Math.max(0, qty - settled)),
    receivedPercent: qty > 0 ? Math.min(100, Math.max(0, (settled - loss) / qty * 100)) : 0,
    lossPercent: qty > 0 ? Math.min(100, Math.max(0, loss / qty * 100)) : 0,
  }
}

export function summarizePlatingDetail(items) {
  const losses = new Map()
  let settledCount = 0
  let weightKg = 0
  let hasWeight = false
  for (const item of items) {
    const quantities = platingReceiptQuantities(item)
    if (quantities.remaining === 0) settledCount++
    if (quantities.loss) {
      const unit = item.unit || '未标单位'
      losses.set(unit, rounded((losses.get(unit) || 0) + quantities.loss))
    }
    if (item.weight != null && ['g', 'kg'].includes(item.weight_unit || 'g')) {
      hasWeight = true
      weightKg += number(item.weight) / ((item.weight_unit || 'g') === 'g' ? 1000 : 1)
    }
  }
  return {
    partCount: new Set(items.map((item) => item.part_id)).size,
    settledCount,
    remainingCount: items.length - settledCount,
    losses: [...losses].map(([unit, qty]) => ({ unit, qty })),
    weightKg: hasWeight ? rounded(weightKg) : null,
  }
}

export function canLinkPlatingReceipt(order, item) {
  return !!order && !order.archived_at && order.status === 'processing'
    && item.status === '电镀中' && platingReceiptQuantities(item).remaining > 0
}
