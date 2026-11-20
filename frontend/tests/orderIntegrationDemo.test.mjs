import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import * as D from '../public/demos/order-integration/domain.js'

const source = file => readFileSync(new URL(`../public/demos/order-integration/${file}`, import.meta.url), 'utf8')
const unchanged = (state, fn) => { const before = structuredClone(state); assert.throws(fn); assert.deepEqual(state, before) }
const line = (state, id = 'a1') => state.orders.flatMap(o => o.lines).find(l => l.id === id)
function render(hash, state = D.createState()) {
  const app = { innerHTML: '', querySelectorAll: () => [] }, modal = { addEventListener() {} }
  runInNewContext(source('app.js').replace(/^import \* as D from ['"][^'"]+['"]/, 'const D = demoDomain'), {
    demoDomain: { ...D, createState: () => state },
    document: { querySelector: s => s === '#app' ? app : modal, addEventListener() {}, body: { classList: { remove() {} } } },
    location: { hash }, window: { addEventListener() {} },
  })
  return app.innerHTML
}

test('integration demo is isolated from business APIs, credentials and persistence', () => {
  const html = source('index.html')
  assert.match(html, /connect-src 'none'/)
  assert.match(html, /form-action 'none'/)
  assert.doesNotMatch(source('app.js') + source('domain.js'), /fetch\(|XMLHttpRequest|localStorage|sessionStorage|\/api\/|@\/|\.\.\/\.\.\/src/)
  assert.match(source('styles.css'), /width: 240px/)
  assert.match(source('styles.css'), /background: #10141A/)
})

test('real demo renders exactly two business tabs, with the old functionality integrated', () => {
  const html = render('#order/OR-1042/details')
  assert.equal((html.match(/role="tab"/g) || []).length, 2)
  for (const text of ['订单详情', '生产安排', '基本信息', '订单要求', '商品明细', '费用与成本', '出货记录', '编辑明细', '添加商品', '已全部发货 0 / 3 项']) assert.ok(html.includes(text), text)
  assert.doesNotMatch(html, /订单资料与旧流程|启用逐笔履约|核对历史实发/)
  assert.match(html, /ALLENOP/)
})

test('production page integrates source tracing, BOM and local incomplete references', () => {
  const html = render('#order/OR-1042/production')
  for (const text of ['本单制作需求', '关联生产任务', '配件备料与 BOM', '关联记录待核对', '从已有任务分配', '按制作任务', '订单 BOM 汇总']) assert.ok(html.includes(text), text)
  assert.doesNotMatch(html, /订单资料与旧流程|标记完成/)
  assert.doesNotMatch(render('#order/OR-1043/production'), /关联记录待核对/)
})

test('unverified historical data gets a contextual notice, not a third module', () => {
  const html = render('#order/OR-1006/details')
  assert.match(html, /本单历史实发数量待核对/)
  assert.equal((html.match(/role="tab"/g) || []).length, 2)
  assert.match(html, /data-action="new-shipment"[^>]*disabled/)
  const completed = render('#order/OR-0988/details')
  assert.match(completed, /历史实发未核实/)
  assert.doesNotMatch(completed, /data-action="verify"/)
})

test('cross-order views reuse the same fictional records and line identities', () => {
  assert.match(render('#readiness'), /data-id="a1"/)
  assert.match(render('#shipments'), /SH-0001/)
})

test('editing customer and requirements leaves shipments, inventory and plans intact', () => {
  const state = D.createState(), before = structuredClone(state)
  D.editInfo(state, 'OR-1042', { customer: '测试客户', date: '2026-11-18', due: '2026-11-30' })
  D.editRequirements(state, 'OR-1042', { barcode: false, barcodeText: '', shippingMark: '独立包装', note: '新要求' })
  assert.equal(state.orders[0].customer, '测试客户')
  assert.equal(state.orders[0].requirements.shippingMark, '独立包装')
  for (const key of ['stock', 'tasks', 'shipments', 'materialSources']) assert.deepEqual(state[key], before[key])
})

test('line editing preserves exact identity and blocks replacement or reduction below business records', () => {
  const state = D.createState()
  const original = line(state)
  D.editLine(state, 'OR-1042', 'a1', { qty: 110, price: 29, code: 'NEW-CODE' })
  assert.equal(line(state), original)
  assert.equal(line(state).code, 'NEW-CODE')
  unchanged(state, () => D.editLine(state, 'OR-1042', 'a1', { qty: 30, price: 29, code: 'x' }))
  unchanged(state, () => D.editLine(state, 'OR-1042', 'a1', { qty: 110, price: 29, code: 'x', product: 'earrings' }))
  unchanged(state, () => D.removeLine(state, 'OR-1042', 'a1'))
})

test('a pending shipment draft prevents deleting or replacing its exact line', () => {
  const state = D.createState()
  D.addLine(state, 'OR-1042', { product: 'necklace', qty: 10, price: 28, code: 'EXTRA' })
  const id = state.orders[0].lines.at(-1).id
  D.draftShipment(state, { orderId: 'OR-1042', lines: [{ lineId: id, qty: 8 }] })
  unchanged(state, () => D.removeLine(state, 'OR-1042', id))
  unchanged(state, () => D.editLine(state, 'OR-1042', id, { qty: 7, price: 28, code: 'EXTRA' }))
})

test('adding same-product rows does not merge identities or previous customer codes', () => {
  const state = D.createState()
  D.addLine(state, 'OR-1042', { product: 'necklace', qty: 10, price: 28, code: 'SECOND-CODE' })
  const added = state.orders[0].lines.at(-1)
  assert.notEqual(added.id, 'a1')
  assert.equal(line(state).qty, 100)
  assert.equal(line(state).code, 'QW-N018')
  D.removeLine(state, 'OR-1042', added.id)
  assert.equal(state.orders[0].lines.length, 3)
})

test('invalid money and dates are rejected without partial writes', () => {
  const state = D.createState()
  for (const value of ['', ' ', null, true, [], -1, Infinity]) unchanged(state, () => D.editPackaging(state, 'OR-1042', value))
  unchanged(state, () => D.editInfo(state, 'OR-1042', { customer: 'X', date: '2026-11-18', due: '2026-11-01' }))
  unchanged(state, () => D.editInfo(state, 'OR-1042', { customer: 'X', date: '2026-02-30', due: '2026-11-01' }))
  const before = D.total(state.orders[0])
  D.editPackaging(state, 'OR-1042', 50)
  assert.equal(D.total(state.orders[0]), before + 20)
})

test('reservations and cancellation never change physical stock or count as shipment', () => {
  const state = D.createState(), stock = structuredClone(state.stock)
  D.reserve(state, 'a1', 10)
  assert.equal(line(state).reserved, 50)
  D.reserve(state, 'a1', 10, true)
  assert.equal(line(state).reserved, 40)
  assert.equal(line(state).shipped, 20)
  assert.deepEqual(state.stock, stock)
})

test('new production defaults to independent task and cannot silently absorb an existing task', () => {
  const state = D.createState(), count = state.tasks.length, stock = structuredClone(state.stock)
  D.arrange(state, { lineId: 'a1', supplier: '青禾手作', qty: 10 })
  assert.equal(state.tasks.length, count + 1)
  assert.equal(state.tasks.find(t => t.id === 'HC-0086').qty, 300)
  assert.deepEqual(state.stock, stock)
  assert.equal(line(state).reserved, 40)
})

test('shared production allocation preserves the other customer and total capacity', () => {
  const state = D.createState()
  D.allocate(state, 'HC-0086', 'OR-1042', { a1: 70 })
  assert.equal(state.tasks[0].allocations.b1, 80)
  unchanged(state, () => D.allocate(state, 'HC-0086', 'OR-1042', { b1: 1 }))
  unchanged(state, () => D.allocate(state, 'HC-0086', 'OR-1042', { a1: 500 }))
})

test('explicit append adds an independent output without rewriting any original output or allocation', () => {
  const state = D.createState(), original = structuredClone(state.tasks[0])
  const task = D.arrange(state, { lineId: 'a2', supplier: '青禾手作', qty: 10, planned: 30, targetId: 'HC-0086' })
  assert.equal(D.taskLabel(task), 'HC-0086')
  assert.notEqual(task.id, 'HC-0086')
  assert.equal(task.qty, 30)
  assert.deepEqual(task.allocations, { a2: 10 })
  assert.deepEqual(state.tasks[0], original)
  assert.equal(state.stock.earrings, 30)
  assert.equal(line(state, 'a2').reserved, 20)
})

test('excess production stays unallocated public plan, not physical inventory or reservation', () => {
  const state = D.createState()
  unchanged(state, () => D.arrange(state, { lineId: 'a1', supplier: 'X', qty: 20, planned: 10 }))
  const task = D.arrange(state, { lineId: 'a1', supplier: 'X', qty: 20, planned: 50 })
  assert.equal(task.qty - Object.values(task.allocations).reduce((a, b) => a + b, 0), 30)
  assert.equal(D.lineNumbers(state, line(state)).planned, 80)
  assert.equal(state.stock.necklace, 140)
  assert.equal(line(state).reserved, 40)
})

test('shipment confirms only selected lines and remains idempotent without mandatory production', () => {
  const state = D.createState()
  const draft = D.draftShipment(state, { orderId: 'OR-1042', lines: [{ lineId: 'a1', qty: 10 }] })
  assert.equal(state.stock.necklace, 140)
  D.confirm(state, draft.id)
  assert.equal(state.stock.necklace, 130)
  assert.equal(line(state).shipped, 30)
  assert.equal(line(state, 'a2').shipped, 0)
  const after = structuredClone(state)
  D.confirm(state, draft.id)
  assert.deepEqual(state, after)
})

test('historical verification requires explicit no-shipment confirmation and never creates stock movements', () => {
  const state = D.createState(), before = structuredClone(state)
  unchanged(state, () => D.draftShipment(state, { orderId: 'OR-1006', lines: [{ lineId: 'd1', qty: 1 }] }))
  unchanged(state, () => D.verifyNoShipment(state, 'OR-1006', false))
  unchanged(state, () => D.verifyNoShipment(state, 'OR-0988', true))
  D.verifyNoShipment(state, 'OR-1006', true)
  assert.equal(D.stage(D.currentOrder(state, 'OR-1006')), '待出货')
  assert.deepEqual(state.stock, before.stock)
  assert.deepEqual(state.shipments, before.shipments)
})

test('historical completed orders stay read-only and do not expose new writes', () => {
  const state = D.createState()
  unchanged(state, () => D.editPackaging(state, 'OR-0988', 10))
  unchanged(state, () => D.reserve(state, 'c1', 1))
  unchanged(state, () => D.arrange(state, { lineId: 'c1', supplier: 'X', qty: 1 }))
})
