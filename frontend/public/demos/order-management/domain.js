// Standalone, fictional UI review data. No business modules or persistence.
export const statuses = ['待生产', '生产中', '已完成', '已取消']
export const catalog = [
  { id: 'SP-0218', kind: 'jewelry', name: '月光 · 淡水珍珠项链', unit: '条', price: '28.1234567', image: '../assets/pearl-necklace.svg' },
  { id: 'SP-0246', kind: 'jewelry', name: '微光 · 珍珠手链', unit: '条', price: '18', image: '../assets/pearl-necklace.svg' },
  { id: 'SP-0312', kind: 'jewelry', name: '白露 · 极简珍珠耳饰', unit: '对', price: '22', image: '../assets/pearl-necklace.svg' },
  { id: 'PJ-0816', kind: 'part', name: '细圈链条 · 金色', unit: '条', price: '3.5' },
  { id: 'PJ-0901', kind: 'part', name: '龙虾扣 · 浅金', unit: '个', price: '0.1234567' },
  { id: 'PJ-0924', kind: 'part', name: '延长链 · 银色', unit: '条', price: '1.2' },
]
export const product = id => catalog.find(p => p.id === id)
export const emptyDraft = () => ({ customer: '', date: '', barcode: false, lines: [] })
export const exampleDraft = () => ({ customer: '栖物生活', date: '2026-11-20', barcode: true, lines: [
  { key: 1, kind: 'jewelry', product: 'SP-0218', quantity: '100', price: '28.1234567', remarks: '每条独立装袋' },
  { key: 2, kind: 'jewelry', product: 'SP-0312', quantity: '60', price: '22', remarks: '一对一卡' },
  { key: 3, kind: 'part', product: 'PJ-0901', quantity: '200', price: '0.1234567', remarks: '' },
] })
export function createState() {
  const records = [
    ['OR-1050', '栖物生活', '待生产', '2026-11-20', '4157.03701', 3, 0, true, true, '无待发预留'],
    ['OR-1049', 'MORI STUDIO', '生产中', '2026-11-19', '8640', 5, 2, true, false, '80 条 / 40 对'],
    ['OR-1048', 'LUNA SELECT', '生产中', '2026-11-19', '3280', 4, 0, true, true, '60 条'],
    ['OR-1047', '山野集物', '待生产', '2026-11-18', '1560', 2, 0, true, false, '无待发预留'],
    ['OR-1046', '栖物生活', '已完成', '2026-11-17', '6120', 4, 4, true, true, '无待发预留'],
    ['OR-1045', 'NORTH & CO.', '生产中', '2026-11-16', '12480', 6, 3, true, false, '100 个 / 20 条'],
    ['OR-1044', 'MORI STUDIO', '已取消', '2026-11-15', '980', 2, 0, true, false, '无待发预留'],
    ['OR-0988', '旧时光选物', '已完成', '2026-09-08', '2680', 3, null, false, true, '—'],
    ['OR-0972', '青禾商店', '待生产', '2026-09-02', '1820', 2, null, false, false, '—'],
  ]
  return { orders: records.map(([id, customer, status, date, amount, items, completed, managed, barcode, reserved]) => ({ id, customer, status, date, amount, items, completed, managed, barcode, reserved })), draft: exampleDraft(), nextKey: 4, nextOrder: 1051 }
}
const SCALE = 10000000n
export function priceUnits(value) {
  const text = String(value ?? '').trim()
  if (!/^\d{1,9}(?:\.\d{1,7})?$/.test(text)) throw Error('单价需为非负数，最多 7 位小数、9 位整数')
  return amountUnits(text)
}
export function amountUnits(text) {
  if (!/^\d+(?:\.\d{1,7})?$/.test(String(text))) throw Error('金额格式无效')
  const [integer, decimals = ''] = String(text).split('.')
  return BigInt(integer) * SCALE + BigInt(decimals.padEnd(7, '0'))
}
export function money(units) {
  const integer = (units / SCALE).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const fraction = (units % SCALE).toString().padStart(7, '0').replace(/0+$/, '').padEnd(2, '0')
  return `¥${integer}.${fraction}`
}
export function lineTotal(line) {
  if (!/^\d+$/.test(String(line.quantity)) || !Number.isSafeInteger(Number(line.quantity)) || Number(line.quantity) < 1 || Number(line.quantity) > 999999999) throw Error('数量需为 1 至 999999999 的整数')
  return BigInt(line.quantity) * priceUnits(line.price)
}
export function draftTotals(draft) {
  let total = 0n, invalid = false
  const groups = { jewelry: 0n, part: 0n }, units = new Map()
  for (const line of draft.lines) {
    try {
      if (product(line.product)?.kind !== line.kind) throw Error('请选择商品')
      const amount = lineTotal(line)
      groups[line.kind] += amount; total += amount
      const unit = product(line.product).unit
      units.set(unit, (units.get(unit) || 0) + Number(line.quantity))
    } catch { invalid = true }
  }
  return { total, groups, invalid, units: [...units].map(([unit, qty]) => `${qty} ${unit}`).join(' / ') }
}
export function addLine(state, kind) {
  if (!['jewelry', 'part'].includes(kind)) throw Error('无效商品类型')
  state.draft.lines.push({ key: state.nextKey++, kind, product: '', quantity: '1', price: '0', remarks: '' })
}
export function selectProduct(line, id) {
  const p = product(id)
  if (id && (!p || p.kind !== line.kind)) throw Error('商品类型不匹配')
  line.product = id; line.price = p?.price || '0'
}
export function validateDraft(draft) {
  if (!draft.customer.trim()) throw Error('请填写客户名称')
  if (draft.date) {
    const date = new Date(`${draft.date}T00:00:00Z`)
    if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.date) || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== draft.date) throw Error('请填写有效创建日期')
  }
  if (!draft.lines.length) throw Error('请至少添加一项饰品或配件')
  for (const line of draft.lines) {
    if (!product(line.product) || product(line.product).kind !== line.kind) throw Error('请为每条明细选择商品')
    lineTotal(line)
  }
}
export function createDemoOrder(state, today = new Date().toISOString().slice(0, 10)) {
  validateDraft(state.draft)
  const draft = state.draft
  const total = draftTotals(draft).total
  const record = { id: `OR-DEMO-${state.nextOrder++}`, customer: draft.customer.trim(), date: draft.date || today, barcode: draft.barcode, status: '待生产', amount: (total / SCALE).toString() + '.' + (total % SCALE).toString().padStart(7, '0'), items: draft.lines.length, completed: 0, managed: true, reserved: '无待发预留', lines: structuredClone(draft.lines) }
  state.orders.unshift(record)
  state.draft = emptyDraft()
  return record
}
export function filterOrders(orders, filters) {
  const query = (filters.search || '').trim().toLowerCase()
  return orders.filter(o => (!filters.status || o.status === filters.status) && (!filters.history || !o.managed) && `${o.id} ${o.customer}`.toLowerCase().includes(query))
    .sort((a, b) => filters.sort === 'amount' ? Number(b.amount) - Number(a.amount) : b.date.localeCompare(a.date) || b.id.localeCompare(a.id))
}
