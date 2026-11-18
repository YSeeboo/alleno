// received_qty is the existing settlement counter: receipts + confirmed losses.
// Do not add loss_qty again, or compare aggregate quantities across source rows.
export function handcraftCompletion(order, outputs = [], materials = []) {
  const hasOutputs = outputs.length > 0
  const rows = hasOutputs ? outputs : materials
  const remaining = rows.filter((row) => {
    const expected = Number(hasOutputs ? row.qty : (row.actual_qty ?? row.qty))
    const settled = Number(row.received_qty ?? 0)
    return !Number.isFinite(expected) || !Number.isFinite(settled) || expected < 0 || settled < expected
  }).length
  const settled = rows.length > 0 && remaining === 0
  return {
    hasOutputs,
    remaining,
    settled,
    canComplete: !!order && !order.archived_at && order.status === 'processing' && settled,
    hint: hasOutputs
      ? (settled ? '产出已结清，可确认完成；材料余额不影响完成，也不会自动退回入库。' : `还有 ${remaining} 条产出未结清，请先回收或确认损耗。`)
      : (settled ? '本单无产出，材料已结清，可确认完成。' : '本单无产出，沿用材料结清规则；请先完成材料回收。'),
  }
}
