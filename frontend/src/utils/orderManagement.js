// Real order-page presentation helpers. No demo data or business writes.
export const orderStatuses = ['待生产', '生产中', '已完成', '已取消']

export function filterOrderRows(orders, summaries, { status, search = '', history = false, sort = 'date' }) {
  const query = search.trim().toLowerCase()
  return orders.filter(order => (!status || order.status === status)
    && (!history || summaries[order.id]?.managed === false)
    && `${order.id} ${order.customer_name}`.toLowerCase().includes(query))
    .sort((a, b) => sort === 'amount'
      ? Number(b.total_amount ?? 0) - Number(a.total_amount ?? 0) || String(b.id).localeCompare(String(a.id))
      : String(b.created_at || '').localeCompare(String(a.created_at || '')) || String(b.id).localeCompare(String(a.id)))
}

export function reservedOrderText(summary) {
  if (!summary) return '加载失败，待重试'
  if (!summary.managed) return '—'
  const units = new Map()
  for (const line of summary.lines || []) {
    const unit = line.unit || '未填单位'
    if (Number(line.reserved) > 0) units.set(unit, (units.get(unit) || 0) + Number(line.reserved))
  }
  return [...units].map(([unit, qty]) => `${qty} ${unit}`).join(' / ') || '无待发预留'
}

export function canDeleteOrder(order, summary) {
  return summary?.managed === false && ['待生产', '已取消'].includes(order.status)
}

const SCALE = 10000000n
export function orderPriceUnits(value) {
  if (value == null || value === '' || !Number.isFinite(Number(value)) || Number(value) < 0) throw Error('单价需为非负数，最多 7 位小数')
  let text = String(value)
  if (/e/i.test(text)) {
    text = Number(value).toFixed(7)
    if (Number(text) !== Number(value)) throw Error('单价最多支持 7 位小数')
  }
  if (!/^\d+(?:\.\d{1,7})?$/.test(text)) throw Error('单价需为非负数，最多 7 位小数')
  const [integer, fraction = ''] = text.split('.')
  return BigInt(integer) * SCALE + BigInt(fraction.padEnd(7, '0'))
}

export function orderLineAmount(line) {
  if (!Number.isSafeInteger(line.quantity) || line.quantity <= 0) throw Error('数量需为正整数')
  return BigInt(line.quantity) * orderPriceUnits(line.unit_price)
}

export function formatOrderAmount(units) {
  const fraction = (units % SCALE).toString().padStart(7, '0').replace(/0+$/, '').padEnd(2, '0')
  return `${(units / SCALE).toLocaleString('en-US')}.${fraction}`
}

export function orderDraftTotals(jewelryItems, partItems, jewelryMap, partMap) {
  const groups = { jewelry: 0n, part: 0n }, quantities = new Map()
  let invalid = false
  for (const [kind, lines, catalog, field] of [['jewelry', jewelryItems, jewelryMap, 'jewelry_id'], ['part', partItems, partMap, 'part_id']]) {
    for (const line of lines) {
      try {
        const product = catalog[line[field]]
        if (!product) throw Error('请选择商品')
        groups[kind] += orderLineAmount(line)
        const unit = product.unit || '未填单位'
        quantities.set(unit, (quantities.get(unit) || 0) + line.quantity)
      } catch { invalid = true }
    }
  }
  return { groups, total: groups.jewelry + groups.part, invalid, units: [...quantities].map(([unit, qty]) => `${qty} ${unit}`).join(' / ') }
}
