export const shipmentLabel = data => data?.managed ? `已全部发货 ${data.completed_items} / ${data.total_items} 项` : '历史待核对，不补记出货'

export function legacyNextStatus(status, managed) {
  if (status === '待生产') return '生产中'
  // Fail closed while activation status is unknown/loading.
  return status === '生产中' && managed === false ? '已完成' : null
}

export function shipmentEntries(lines, selected, quantities) {
  const entries = lines.filter(line => selected[line.id]).map(line => {
    const quantity = quantities[line.id]
    if (!Number.isSafeInteger(quantity) || quantity <= 0) throw new Error('请逐项填写实际出货的正整数数量')
    if (quantity > Number(line.remaining)) throw new Error(`${line.product_name} 超过剩余待发数量`)
    return { order_item_id: line.id, quantity }
  })
  if (!entries.length) throw new Error('请手动勾选至少一项实际出货商品')
  return entries
}

export function stockWarnings(lines, entries) {
  const needs = new Map()
  for (const entry of entries) {
    const line = lines.find(line => line.id === entry.order_item_id)
    if (!line) return ['订单明细已变化，请返回重新选择']
    if (Number(entry.quantity) > Number(line.remaining)) return [`${line.product_name} 剩余待发数量已变化`]
    const key = `${line.product_type}:${line.product_id}`
    const previous = needs.get(key) || { quantity: 0, line }
    previous.quantity += Math.max(0, Number(entry.quantity) - Number(line.reserved))
    needs.set(key, previous)
  }
  return [...needs.values()].filter(value => value.quantity > Number(value.line.public_available))
    .map(value => `${value.line.product_name} 需要公共现货 ${value.quantity}，当前公共可用 ${value.line.public_available} ${value.line.unit || ''}；不能挪用其他明细预留`)
}
