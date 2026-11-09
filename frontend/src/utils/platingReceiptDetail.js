// Receipt quantities are actual receipts, not the source order's cumulative receipts/losses.
export function summarizePlatingReceipt(items) {
  const quantities = new Map()
  let weightKg = 0
  let hasWeight = false
  for (const item of items) {
    const unit = item.unit || '未标单位'
    quantities.set(unit, (quantities.get(unit) || 0) + Number(item.qty || 0))
    if (item.weight != null && ['g', 'kg'].includes(item.weight_unit || 'g')) {
      hasWeight = true
      // Legacy receipt weights without a unit are displayed as grams in the detail table.
      weightKg += Number(item.weight) / (item.weight_unit === 'kg' ? 1 : 1000)
    }
  }
  return {
    partCount: new Set(items.map((item) => item.part_id).filter(Boolean)).size,
    quantities: [...quantities].map(([unit, qty]) => ({ unit, qty: Number(qty.toFixed(4)) })),
    weightKg: hasWeight ? Number(weightKg.toFixed(10)) : null,
    unpricedCount: items.filter((item) => item.amount == null).length,
  }
}
