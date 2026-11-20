// Share the existing fictional engine only. This variant never imports business code.
import * as demo from '../order-integration/domain.js'
export * from '../order-integration/domain.js'

export function createState() {
  const state = demo.createState()
  // The real order model has no due date. Do not propose one as existing metadata.
  for (const order of state.orders) delete order.due
  state.shipments[0].date = '2026-11-19'
  state.events[0].time = '11-19 16:30'
  return state
}

export function editCustomer(state, orderId, customer) {
  const order = demo.editableOrder(state, orderId)
  if (!customer?.trim()) throw new Error('请填写客户名')
  order.customer = customer.trim()
  state.events.unshift({ title: '客户资料已更新', detail: orderId, time: '刚刚 · Demo' })
}

export function editInfo(state, orderId, values) {
  const date = values.date
  if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0, 10) !== date) throw new Error('请填写有效的创建日期')
  editCustomer(state, orderId, values.customer)
  demo.currentOrder(state, orderId).date = date
  state.events[0].title = '订单资料已更新'
}

function price(value) {
  if (!/^\d+(?:\.\d{1,7})?$/.test(String(value)) || Number(value) > 1000000) throw new Error('单价须为 0 至 1,000,000 的金额，最多 7 位小数')
  return Number(value)
}

export function editLine(state, orderId, lineId, values) {
  const exact = price(values.price)
  demo.editLine(state, orderId, lineId, values)
  demo.currentOrder(state, orderId).lines.find(line => line.id === lineId).price = exact
}

export function addLine(state, orderId, values) {
  const exact = price(values.price)
  demo.addLine(state, orderId, values)
  demo.currentOrder(state, orderId).lines.at(-1).price = exact
}
