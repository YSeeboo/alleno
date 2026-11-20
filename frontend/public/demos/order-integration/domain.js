// Reuse only the fictional, in-memory demo engine, never the real application API.
import * as demo from '../order-fulfillment/domain.js'
export { balance, lineNumbers, materialNeeds, materials, materialAvailability, materialPlatingUsed, taskStage } from '../order-fulfillment/domain.js'

export const products = Object.fromEntries(Object.entries(demo.products).map(([key, product]) => [key, {
  ...product,
  image: key === 'necklace' ? '../assets/pearl-necklace.svg' : `../order-fulfillment/${key === 'earrings' ? 'earrings' : 'chain'}.svg`,
}]))

export function createState() {
  const state = demo.createState()
  state.orders.push({ id: 'OR-1006', customer: '青木选物', date: '2026-11-01', due: '2026-11-26', legacy: true, requiresReview: true, note: '存量订单：曾口头安排发货，尚无可核对凭据。', lines: [{ id: 'd1', product: 'necklace', qty: 50, shipped: 0, reserved: 0, code: 'AM-N018' }] })
  for (const order of state.orders) {
    order.packaging = 30
    order.requirements = { barcode: true, barcodeText: '客户货号 + 品名，每件一贴', shippingMark: `${order.customer}\n饰品轻放 / 防潮`, note: order.note }
    for (const line of order.lines) line.price = { necklace: 28, earrings: 18, chain: 3.5 }[line.product]
  }
  state.references = [{ orderId: 'OR-1042', id: 'HC-0062', lineId: 'a1', label: '早期生产关联', detail: '记录保留，但未记明本单份额；不并入当前计划数量。' }]
  return state
}

export function currentOrder(state, orderId) {
  const order = state.orders.find(item => item.id === orderId)
  if (!order) throw new Error('订单不存在')
  return order
}

export function editableOrder(state, orderId) {
  const order = currentOrder(state, orderId)
  if (order.legacy) throw new Error(order.requiresReview ? '请先核对历史实发，不能直接从 0 记账' : '已完成订单只读')
  if (order.lines.length && order.lines.every(line => line.shipped >= line.qty)) throw new Error('已完成订单只读')
  return order
}

export function stage(order) {
  if (order.requiresReview) return '历史实发待核对'
  if (order.legacy) return '已完成'
  if (order.lines.length && order.lines.every(line => line.shipped >= line.qty)) return '已完成'
  return order.lines.some(line => line.shipped > 0) ? '部分出货' : '待出货'
}

export function editable(order) { return !order.legacy && stage(order) !== '已完成' }
export function total(order) { return order.lines.reduce((sum, line) => sum + line.qty * line.price, 0) + order.packaging }
export function taskLabel(task) { return task.documentId || task.id }

function record(state, title, detail) { state.events.unshift({ title, detail, time: '刚刚 · Demo' }) }
function amount(value, label) {
  if (!['number', 'string'].includes(typeof value) || String(value).trim() === '' || !Number.isFinite(Number(value)) || Number(value) < 0 || Number(value) > 1000000) throw new Error(`${label}须为 0 至 1,000,000 的有效金额`)
  return Math.round(Number(value) * 100) / 100
}

export function editInfo(state, orderId, values) {
  const order = editableOrder(state, orderId)
  if (!values.customer?.trim()) throw new Error('请填写客户名')
  const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value
  if (!validDate(values.date) || !validDate(values.due) || values.due < values.date) throw new Error('请填写有效日期，交期不能早于创建日期')
  Object.assign(order, { customer: values.customer.trim(), date: values.date, due: values.due })
  record(state, '订单资料已更新', orderId)
}

export function editRequirements(state, orderId, values) {
  const order = editableOrder(state, orderId)
  order.requirements = { barcode: !!values.barcode, barcodeText: values.barcodeText.trim(), shippingMark: values.shippingMark.trim(), note: values.note.trim() }
  record(state, '订单要求已更新', orderId)
}

export function lineProtected(state, line) {
  return line.shipped > 0 || line.reserved > 0 || demo.lineNumbers(state, line).planned > 0 || state.shipments.some(s => s.status !== 'void' && s.lines.some(entry => entry.lineId === line.id)) || state.references.some(ref => ref.lineId === line.id)
}

export function editLine(state, orderId, lineId, values) {
  const order = editableOrder(state, orderId)
  const line = order.lines.find(item => item.id === lineId)
  if (!line) throw new Error('明细不存在')
  const qty = demo.integer(values.qty, '订购数量')
  const price = amount(values.price, '单价')
  const product = values.product || line.product
  if (!products[product]) throw new Error('请选择商品')
  if (product !== line.product && lineProtected(state, line)) throw new Error('已有生产、预留、历史关联或出货记录，不能替换商品')
  const floor = Math.max(line.shipped + line.reserved, demo.lineNumbers(state, line).planned)
  const draftFloor = state.shipments.filter(s => s.status === 'draft').reduce((max, s) => Math.max(max, line.shipped + (s.lines.find(e => e.lineId === line.id)?.qty || 0)), 0)
  if (qty < Math.max(floor, draftFloor)) throw new Error(`已有业务记录，订购数量不能低于 ${Math.max(floor, draftFloor)}`)
  Object.assign(line, { product, qty, price, code: values.code.trim() })
  record(state, '订单明细已修改', `${orderId} · 明细 ${line.id}；原身份不变`)
}

export function addLine(state, orderId, values) {
  const order = editableOrder(state, orderId)
  if (!products[values.product]) throw new Error('请选择商品')
  const qty = demo.integer(values.qty, '订购数量'), price = amount(values.price, '单价')
  const line = { id: `new-${state.nextLine || 1}`, product: values.product, qty, price, code: values.code.trim(), shipped: 0, reserved: 0 }
  state.nextLine = (state.nextLine || 1) + 1
  order.lines.push(line)
  record(state, '新增订单明细', `${orderId} · 独立明细 ${line.id}，不合并同款行`)
}

export function removeLine(state, orderId, lineId) {
  const order = editableOrder(state, orderId), line = order.lines.find(item => item.id === lineId)
  if (!line) throw new Error('明细不存在')
  if (lineProtected(state, line)) throw new Error('已有业务记录，不能直接删除；请先处理关联凭据')
  if (order.lines.length === 1) throw new Error('订单至少保留一条明细')
  order.lines = order.lines.filter(item => item.id !== lineId)
  record(state, '未执行明细已移除', `${orderId} · ${lineId}`)
}

export function editPackaging(state, orderId, value) {
  const order = editableOrder(state, orderId)
  order.packaging = amount(value, '包装费')
}

export function verifyNoShipment(state, orderId, checked) {
  const order = currentOrder(state, orderId)
  if (!order.requiresReview || checked !== true) throw new Error('只有明确确认无历史实发，才可从 0 开始记录')
  order.legacy = false
  order.requiresReview = false
  record(state, '已确认无历史实发', `${orderId} · 未补出货，未调整库存`)
}

export function reserve(state, lineId, qty, release = false) {
  editableOrder(state, demo.locateLine(state, lineId).order.id)
  return release ? demo.releaseLine(state, lineId, qty) : demo.reserveLine(state, lineId, qty)
}
export function arrange(state, values) {
  const { order, line } = demo.locateLine(state, values.lineId)
  editableOrder(state, order.id)
  if (line.product === 'chain') throw new Error('此示例配件请从已有电镀来源分配')
  const qty = demo.integer(values.qty, '安排给本行数量')
  const planned = demo.integer(values.planned ?? values.qty, '整条产出计划')
  if (planned < qty) throw new Error('整条产出计划不能少于安排给本行的数量')
  const open = Math.max(0, line.qty - line.shipped - demo.lineNumbers(state, line).planned)
  if (qty > open) throw new Error(`本行尚未安排需求只有 ${open}`)
  if (!values.supplier?.trim()) throw new Error('请填写商家')
  const targetId = values.targetId || 'new'
  let target
  if (targetId !== 'new') {
    target = state.tasks.find(t => t.id === targetId)
    if (!target || target.type !== 'handcraft' || target.status !== 'pending' || target.supplier !== values.supplier.trim()) throw new Error('只能明确追加到同商家未发出的手工单')
  }
  const number = String(state.nextTask++).padStart(4, '0')
  const task = { id: target ? `OUT-${number}` : `HC-${number}`, documentId: target ? taskLabel(target) : `HC-${number}`, type: 'handcraft', supplier: values.supplier.trim(), product: line.product, qty: planned, received: 0, loss: 0, status: 'pending', date: '2026-11-18', allocations: { [line.id]: qty } }
  state.tasks.push(task)
  record(state, target ? '明确追加独立产出行' : '新建独立制作单', `${order.id} → ${taskLabel(task)} · 本行 ${qty}，公共计划 ${planned - qty}；不改写原产出，不移动库存`)
  return task
}
export function allocate(state, taskId, orderId, values) {
  editableOrder(state, orderId)
  return demo.saveOrderAllocation(state, taskId, orderId, values)
}
export function sourceMaterial(state, orderId, id, values) {
  editableOrder(state, orderId)
  return demo.saveMaterialSourcing(state, orderId, id, values)
}
export function draftShipment(state, values) {
  editableOrder(state, values.orderId)
  return demo.saveDraft(state, values)
}
export function confirm(state, id) {
  const shipment = state.shipments.find(item => item.id === id)
  if (!shipment) throw new Error('出货单不存在')
  if (shipment.status !== 'confirmed') editableOrder(state, shipment.orderId)
  return demo.confirmShipment(state, id)
}
export { checkShipment, voidDraft, receiveStock } from '../order-fulfillment/domain.js'
