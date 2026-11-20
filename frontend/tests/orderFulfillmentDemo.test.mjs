import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import * as demoDomain from '../public/demos/order-fulfillment/domain.js'
import { createState, integer, balance, locateLine, lineNumbers, orderStage, taskStage, materialNeeds, materialAvailability, materialPlatingUsed, saveMaterialSourcing, reserveLine, releaseLine, saveAllocation, saveOrderAllocation, arrangeHandcraft, receiveStock, receiveTask, saveDraft, confirmShipment, voidDraft } from '../public/demos/order-fulfillment/domain.js'

const draft = (s, lines, orderId = 'OR-1042') => saveDraft(s, { orderId, lines })
const line = (s, id) => locateLine(s, id).line
const unchanged = (s, fn) => { const before = structuredClone(s); assert.throws(fn); assert.deepEqual(s, before) }
const renderPage = (route, state = createState()) => {
  const app = { innerHTML: '' }, modal = { addEventListener() {} }
  const source = readFileSync(new URL('../public/demos/order-fulfillment/app.js', import.meta.url), 'utf8')
    .replace(/^import \{([^}]+)\} from '[^']+'/, 'const {$1} = demoDomain')
  runInNewContext(source, {
    demoDomain: { ...demoDomain, createState: () => state },
    document: { querySelector: selector => selector === '#app' ? app : modal, addEventListener() {} },
    window: { addEventListener() {} }, location: { hash: `#/${route}` },
  })
  return app.innerHTML
}

test('quantity validation rejects missing, malformed, nonpositive and oversized input', () => {
  for (const value of ['', ' ', null, undefined, true, [], {}, 0, -1, 1.5, NaN, Infinity, 1000001]) assert.throws(() => integer(value))
  assert.equal(integer('20'), 20)
  assert.equal(integer(0, '分配', true), 0)
})

test('public inventory excludes all order reservations', () => {
  const s = createState()
  assert.deepEqual(balance(s, 'necklace', 'OR-1042'), { physical: 140, reserved: 100, own: 40, others: 60, free: 40 })
  unchanged(s, () => reserveLine(s, 'a1', 41))
  reserveLine(s, 'a1', 40)
  assert.equal(balance(s, 'necklace').free, 0)
  assert.equal(s.stock.necklace, 140)
  unchanged(s, () => reserveLine(s, 'b1', 1))
})

test('release changes reservation only and cannot exceed the exact line', () => {
  const s = createState()
  unchanged(s, () => releaseLine(s, 'a1', 41))
  const expected = structuredClone(s)
  line(expected, 'a1').reserved = 20
  releaseLine(s, 'a1', 20)
  assert.deepEqual({ ...s, events: [] }, { ...expected, events: [] })
  assert.deepEqual(balance(s, 'necklace'), { physical: 140, reserved: 80, own: 0, others: 80, free: 60 })
  assert.equal(line(s, 'a1').reserved, 20)
  releaseLine(s, 'a1', 20)
  assert.equal(line(s, 'a1').reserved, 0)
  assert.equal(balance(s, 'necklace').free, 80)
  reserveLine(s, 'b1', 20)
  assert.equal(line(s, 'b1').reserved, 80)
  assert.deepEqual(s.stock, expected.stock)
  assert.deepEqual(s.tasks, expected.tasks)
  assert.deepEqual(s.shipments, expected.shipments)
})

test('reservation events and validation distinguish inventory from production allocation', () => {
  const s = createState()
  assert.throws(() => reserveLine(s, 'a1', 41), /最多还需预留 40 条/)
  assert.throws(() => releaseLine(s, 'a1', 41), /取消预留数量不能超过本行已预留数量/)
  reserveLine(s, 'a1', 10)
  assert.equal(s.events[0].title, '库存已预留')
  assert.match(s.events[0].detail, /实物库存不变/)
  releaseLine(s, 'a1', 10)
  assert.equal(s.events[0].title, '已取消库存预留')
  assert.match(s.events[0].detail, /恢复公共可用；实物库存不变/)
})

test('inventory UI uses reservation labels and explains cancellation without renaming production allocation', () => {
  const source = readFileSync(new URL('../public/demos/order-fulfillment/app.js', import.meta.url), 'utf8')
  assert.match(source, /textButton\('预留库存', 'reserve'/)
  assert.match(source, /textButton\('取消预留', 'release'/)
  assert.match(source, /确认取消预留/)
  assert.match(source, /可取消部分或全部待发预留/)
  assert.match(source, /实物库存、生产安排和已出货数量均不变；这不是出库或退货/)
  assert.match(source, /正常出货会自动消耗预留，无需先取消/)
  assert.match(source, /生产需求分配/)
  assert.doesNotMatch(source, /分配库存|库存分配|释放分配|确认释放|已分配待发/)
})

test('manual public-stock shipment works with no production association or prior reservation', () => {
  const s = createState()
  s.tasks = []
  const d = draft(s, [{ lineId: 'a3', qty: 50 }])
  assert.equal(s.stock.chain, 80)
  confirmShipment(s, d.id)
  assert.equal(s.stock.chain, 30)
  assert.equal(line(s, 'a3').shipped, 50)
  assert.equal(orderStage(s.orders[0]), '部分出货')
})

test('shipment consumes own line reservation first and leaves others protected', () => {
  const s = createState()
  const d = draft(s, [{ lineId: 'a1', qty: 60 }])
  confirmShipment(s, d.id)
  assert.equal(s.stock.necklace, 80)
  assert.equal(line(s, 'a1').reserved, 0)
  assert.equal(line(s, 'b1').reserved, 60)
  assert.equal(balance(s, 'necklace').free, 20)
  assert.equal(line(s, 'a1').shipped, 80)
})

test('confirmation is idempotent and never double deducts', () => {
  const s = createState(), d = draft(s, [{ lineId: 'a1', qty: 20 }])
  confirmShipment(s, d.id)
  const before = structuredClone(s)
  confirmShipment(s, d.id)
  assert.deepEqual(s, before)
})

test('all shipment rows validate before mutation, including stock shortages', () => {
  const s = createState(), d = draft(s, [{ lineId: 'a1', qty: 20 }, { lineId: 'a2', qty: 60 }])
  unchanged(s, () => confirmShipment(s, d.id))
  assert.equal(d.status, 'draft')
})

test('duplicate, foreign and excess order-line quantities cannot create a draft', () => {
  const s = createState()
  for (const entries of [[], [{ lineId: 'a1', qty: 0 }], [{ lineId: 'a1', qty: 81 }], [{ lineId: 'b1', qty: 1 }], [{ lineId: 'a1', qty: 1 }, { lineId: 'a1', qty: 2 }]]) unchanged(s, () => draft(s, entries))
})

test('stale drafts revalidate inventory reserved since draft creation', () => {
  const s = createState(), d = draft(s, [{ lineId: 'a1', qty: 80 }])
  reserveLine(s, 'b1', 20)
  unchanged(s, () => confirmShipment(s, d.id))
})

test('stale drafts revalidate remaining demand after a different shipment', () => {
  const s = createState(), d1 = draft(s, [{ lineId: 'a1', qty: 60 }]), d2 = draft(s, [{ lineId: 'a1', qty: 60 }])
  confirmShipment(s, d1.id)
  unchanged(s, () => confirmShipment(s, d2.id))
})

test('same-product rows aggregate public consumption and retain independent reservations', () => {
  const s = createState()
  s.orders[0].lines.push({ id: 'a4', product: 'necklace', qty: 50, shipped: 0, reserved: 20, code: 'OTHER-CODE' })
  // physical140 - a1:40 - a4:20 - b1:60 = 20 free
  let d = draft(s, [{ lineId: 'a1', qty: 60 }, { lineId: 'a4', qty: 21 }])
  unchanged(s, () => confirmShipment(s, d.id))
  d = draft(s, [{ lineId: 'a1', qty: 60 }, { lineId: 'a4', qty: 20 }])
  confirmShipment(s, d.id)
  assert.equal(s.stock.necklace, 60)
  assert.equal(line(s, 'a4').shipped, 20)
  assert.equal(line(s, 'b1').reserved, 60)
})

test('unselected sibling reservations cannot be silently reassigned', () => {
  const s = createState()
  s.orders[0].lines.push({ id: 'a4', product: 'necklace', qty: 50, shipped: 0, reserved: 30, code: 'OTHER-CODE' })
  const d = draft(s, [{ lineId: 'a1', qty: 60 }])
  unchanged(s, () => confirmShipment(s, d.id))
})

test('true inbound is independent, requires provenance, and does not auto ship', () => {
  const s = createState(), d = draft(s, [{ lineId: 'a3', qty: 120 }])
  unchanged(s, () => receiveStock(s, { product: 'chain', qty: 40, reason: '历史现货补录', note: '' }))
  unchanged(s, () => receiveStock(s, { product: 'chain', qty: 40, reason: '自动补缺', note: '不允许' }))
  receiveStock(s, { product: 'chain', qty: 40, reason: '历史现货补录', note: '实物盘点确认40条' })
  assert.equal(d.status, 'draft')
  assert.equal(line(s, 'a3').shipped, 0)
  assert.equal(s.receipts.length, 1)
  confirmShipment(s, d.id)
  assert.equal(s.stock.chain, 0)
})

test('only full shipment completes order, and historical production plans are not added', () => {
  const s = createState()
  receiveStock(s, { product: 'earrings', qty: 30, reason: '外购成品', note: '实际收货30对' })
  receiveStock(s, { product: 'chain', qty: 40, reason: '盘点补录', note: '实际盘点40条' })
  confirmShipment(s, draft(s, [{ lineId: 'a1', qty: 80 }, { lineId: 'a2', qty: 60 }, { lineId: 'a3', qty: 120 }]).id)
  assert.equal(orderStage(s.orders[0]), '已完成')
  assert.equal(lineNumbers(s, line(s, 'a1')).gap, 0)
  assert.equal(line(s, 'a1').reserved, 0)
  assert.equal(lineNumbers(s, line(s, 'a1')).planned, 60)
  assert.equal(s.stock.necklace, 60) // other customer's exact reserve retained
})

test('void drafts have no inventory effect and cannot be confirmed; confirmed records cannot void', () => {
  const s = createState(), d = draft(s, [{ lineId: 'a1', qty: 20 }])
  voidDraft(s, d.id)
  assert.equal(s.stock.necklace, 140)
  unchanged(s, () => confirmShipment(s, d.id))
  unchanged(s, () => voidDraft(s, 'SH-0001'))
})

test('production allocation supports multiple orders, retains public remainder and is atomic', () => {
  const s = createState()
  saveAllocation(s, 'HC-0086', { a1: 50, b1: 70 })
  assert.deepEqual(s.tasks[0].allocations, { a1: 50, b1: 70 })
  assert.equal(s.stock.necklace, 140)
  unchanged(s, () => saveAllocation(s, 'HC-0086', { a1: 20, b1: 81 }))
  unchanged(s, () => saveAllocation(s, 'HC-0086', { a2: 10 }))
  unchanged(s, () => saveAllocation(s, 'HC-0086', { c1: 10 }))
  s.tasks[0].qty = 100
  unchanged(s, () => saveAllocation(s, 'HC-0086', { a1: 60, b1: 60 }))
})

test('handcraft defaults to new despite eligible pending task, merge requires explicit matching target', () => {
  const s = createState()
  const task = arrangeHandcraft(s, { lineId: 'a1', qty: 10, supplier: '青禾手作' })
  assert.notEqual(task.id, 'HC-0086')
  assert.equal(s.tasks[0].qty, 300)
  assert.equal(s.stock.necklace, 140)
  arrangeHandcraft(s, { lineId: 'a1', qty: 10, supplier: '青禾手作', targetId: 'HC-0086' })
  assert.equal(s.tasks[0].qty, 310)
  assert.equal(s.tasks[0].allocations.a1, 70)
  unchanged(s, () => arrangeHandcraft(s, { lineId: 'b2', qty: 10, supplier: '拾光工坊', targetId: 'HC-0087' }))
})

test('order-scoped allocation changes only that order and preserves other customer quantities', () => {
  const s = createState()
  saveOrderAllocation(s, 'HC-0086', 'OR-1042', { a1: 50 })
  assert.deepEqual(s.tasks[0].allocations, { a1: 50, b1: 80 })
  saveOrderAllocation(s, 'HC-0086', 'OR-1042', { a1: 0 })
  assert.deepEqual(s.tasks[0].allocations, { b1: 80 })
  assert.equal(s.stock.necklace, 140)
})

test('order-scoped allocation rejects foreign line changes and product mismatches atomically', () => {
  const s = createState()
  unchanged(s, () => saveOrderAllocation(s, 'HC-0086', 'OR-1042', { a1: 50, b1: 70 }))
  unchanged(s, () => saveOrderAllocation(s, 'HC-0086', 'OR-1042', { a2: 10 }))
  unchanged(s, () => saveOrderAllocation(s, 'HC-0086', 'OR-0988', { c1: 10 }))
  unchanged(s, () => saveOrderAllocation(s, 'missing-task', 'OR-1042', { a1: 10 }))
})

test('order-scoped allocation includes fixed other orders in shared task capacity validation', () => {
  const s = createState()
  s.tasks[0].qty = 140
  unchanged(s, () => saveOrderAllocation(s, 'HC-0086', 'OR-1042', { a1: 70 }))
  saveOrderAllocation(s, 'HC-0086', 'OR-1042', { a1: 60 })
  assert.deepEqual(s.tasks[0].allocations, { a1: 60, b1: 80 })
})

test('order list has no cross-module fake child tabs and detail tabs retain order scope', () => {
  const source = readFileSync(new URL('../public/demos/order-fulfillment/app.js', import.meta.url), 'utf8')
  const list = source.slice(source.indexOf('function ordersPage()'), source.indexOf('function eventsCard()'))
  assert.doesNotMatch(list, /\btabs\(/)
  assert.match(source, /`orders\/\$\{order\.id\}\/production`/)
  assert.match(source, /source === 'production' \? orderProductionPage\(id\)/)
  assert.match(source, /aria-label="相关模块快捷入口"/)
})

test('shipment progress uses plain-language completed items and excludes partially shipped items', () => {
  const s = createState()
  for (const route of ['orders', 'orders/OR-1042']) {
    const html = renderPage(route, s)
    assert.match(html, /已全部发货 0 \/ 3 项/)
    assert.match(html, /部分发货的商品不计入已完成项/)
    assert.doesNotMatch(html, /行足量/)
  }
  line(s, 'a1').shipped = 100
  assert.match(renderPage('orders/OR-1042', s), /已全部发货 1 \/ 3 项/)
  assert.doesNotMatch(renderPage('orders/OR-0988', s), /已全部发货/)
})

test('order production separates direct plating from upstream component sourcing', () => {
  const html = renderPage('orders/OR-1042/production')
  assert.match(html, /手工生产安排/)
  assert.match(html, /电镀生产安排/)
  const start = html.indexOf('<h2>电镀生产安排</h2>')
  const plating = html.slice(start, html.indexOf('</section>', start))
  assert.match(plating, /#\/plating\/EP-0128\/OR-1042/)
  assert.match(plating, /PJ-0816 原色 → PJ-0816-G 金色/)
  assert.match(plating, /已关联本单/)
  assert.match(plating, /EP-0128:OR-1042/)
  assert.doesNotMatch(plating, /HC-0086/)
  const otherOrder = renderPage('orders/OR-1043/production')
  assert.match(otherOrder, /电镀生产安排/)
  assert.match(otherOrder, /暂无直接匹配本单商品的电镀产出/)
  assert.match(otherOrder, /上游配件备料/)
  assert.match(otherOrder, /EP-0131/)
  assert.doesNotMatch(otherOrder, /EP-0128/)
})

test('upstream BOM converts finished units to component pieces without counting them as finished plans', () => {
  const s = createState(), before = structuredClone(s)
  const [clasp, hook] = materialNeeds(s, 'OR-1042')
  assert.equal(clasp.required, 60)
  assert.equal(clasp.ready, 20)
  assert.equal(clasp.waiting, 40)
  assert.equal(clasp.planned, 40)
  assert.equal(clasp.uncovered, 0)
  assert.equal(clasp.stage, '等待电镀回收')
  assert.equal(hook.required, 80) // two hooks per pair of earrings
  assert.equal(hook.source.issued, 80)
  assert.equal(hook.waiting, 0)
  assert.equal(hook.stage, '已发料')
  assert.equal(lineNumbers(s, line(s, 'a1')).planned, 60)
  assert.equal(lineNumbers(s, line(s, 'a2')).planned, 40)
  assert.deepEqual(s, before)
})

test('shared component stock and plating plans protect other orders and report uncovered demand', () => {
  const s = createState(), b = materialNeeds(s, 'OR-1043')[0]
  assert.equal(b.required, 80)
  assert.equal(b.uncovered, 20)
  assert.equal(b.waiting, 70)
  assert.equal(materialAvailability(s, 'clasp'), 0)
  assert.equal(materialAvailability(s, 'clasp', 'HC-0086:a1:clasp'), 20)
  assert.equal(materialPlatingUsed(s, 'EP-0131'), 90)
  unchanged(s, () => saveMaterialSourcing(s, 'OR-1043', b.id, { stock: 11, plating: { 'EP-0131': 50 } }))
  s.materialTasks[0].qty = 100
  unchanged(s, () => saveMaterialSourcing(s, 'OR-1043', b.id, { stock: 0, plating: { 'EP-0131': 61 } }))
})

test('component sourcing changes only the exact demand and never receives, issues or ships goods', () => {
  const s = createState(), before = structuredClone(s)
  saveMaterialSourcing(s, 'OR-1042', 'HC-0086:a1:clasp', { stock: 10, plating: { 'EP-0131': 50 } })
  assert.deepEqual(s.materialSources['HC-0086:b1:clasp'], before.materialSources['HC-0086:b1:clasp'])
  const expected = structuredClone(before)
  expected.materialSources['HC-0086:a1:clasp'] = { stock: 10, issued: 0, plating: { 'EP-0131': 50 } }
  assert.deepEqual({ ...s, events: [] }, { ...expected, events: [] })
  assert.equal(materialAvailability(s, 'clasp'), 10)
  assert.equal(materialNeeds(s, 'OR-1042')[0].waiting, 50)
})

test('component sourcing validates all quantities and target identities before mutating', () => {
  const s = createState(), id = 'HC-0086:a1:clasp'
  for (const values of [
    { stock: -1 }, { stock: 1.5 }, { stock: '' },
    { stock: 20, plating: { 'EP-0131': 41 } },
    { stock: 20, plating: { 'EP-0131': 20, 'EP-0132': 1 } },
    { stock: 20, plating: { 'EP-missing': 1 } },
    { stock: 20, plating: { 'EP-0131': -1 } },
  ]) unchanged(s, () => saveMaterialSourcing(s, 'OR-1042', id, values))
  unchanged(s, () => saveMaterialSourcing(s, 'OR-1043', id, { stock: 0 }))
  unchanged(s, () => saveMaterialSourcing(s, 'OR-0988', id, { stock: 0 }))
  unchanged(s, () => saveMaterialSourcing(s, 'OR-1042', 'HC-0087:a2:hook', { stock: 0 }))
})

test('new handcraft expands component demand but does not silently link a matching plating task', () => {
  const s = createState()
  const task = arrangeHandcraft(s, { lineId: 'b2', qty: 10, supplier: '拾光工坊' })
  const need = materialNeeds(s, 'OR-1043').find(n => n.task.id === task.id)
  assert.equal(need.required, 20)
  assert.equal(need.uncovered, 20)
  assert.deepEqual(need.source.plating, {})
  saveMaterialSourcing(s, 'OR-1043', need.id, { stock: 20 })
  const ready = materialNeeds(s, 'OR-1043').find(n => n.id === need.id)
  assert.equal(ready.stage, '现货已备齐')
  assert.deepEqual(ready.source.plating, {})
  assert.equal(s.materialStock.hook, 50)
  assert.equal(s.materialTasks.length, 2)
})

test('production-plan changes recalculate BOM and flag old sourcing instead of silently reallocating it', () => {
  const s = createState()
  saveOrderAllocation(s, 'HC-0086', 'OR-1042', { a1: 30 })
  let need = materialNeeds(s, 'OR-1042')[0]
  assert.equal(need.required, 30)
  assert.equal(need.review, true)
  assert.equal(need.stage, '安排有变，需核对')
  assert.equal(materialPlatingUsed(s, 'EP-0131'), 90)
  saveMaterialSourcing(s, 'OR-1042', need.id, { stock: 20, plating: { 'EP-0131': 10 } })
  assert.equal(materialNeeds(s, 'OR-1042')[0].review, false)
  saveOrderAllocation(s, 'HC-0086', 'OR-1042', { a1: 0 })
  need = materialNeeds(s, 'OR-1042')[0]
  assert.equal(need.required, 0)
  assert.equal(need.review, true)
  saveMaterialSourcing(s, 'OR-1042', need.id, { stock: 0 })
  assert.equal(materialNeeds(s, 'OR-1042').some(n => n.id === need.id), false)
  assert.equal(materialAvailability(s, 'clasp'), 20)
  assert.equal(materialPlatingUsed(s, 'EP-0131'), 50)
})

test('upstream views show own shares, actual processing stages and reversible order context', () => {
  const html = renderPage('orders/OR-1042/production')
  assert.match(html, /上游配件备料/)
  assert.match(html, /每对用 2 个/)
  assert.match(html, /本项计划使用 <b>40 个/)
  assert.match(html, /#\/plating\/EP-0131\/OR-1042/)
  assert.match(html, /使用现货或已发料，无需新增电镀单/)
  assert.match(html, /不是实物批次追溯/)
  const task = renderPage('plating/EP-0131/OR-1042')
  assert.match(task, /返回本单配件备料/)
  assert.match(task, /href="#\/orders\/OR-1042\/production"/)
  assert.match(task, /PJ-0901 原色 → PJ-0901-G/)
  assert.match(task, /QW-N018/)
  assert.match(task, /MR-N018/)
  assert.match(task, /class="row-highlight"/)
  assert.match(renderPage('plating'), /上游配件电镀/)
  const handcraft = renderPage('handcraft/HC-0086/OR-1042')
  assert.match(handcraft, /OR-1042 · 上游配件备料/)
  assert.match(handcraft, /EP-0131/)
  assert.doesNotMatch(handcraft, /OR-1043 · 上游配件备料/)
})

test('finished-stock shipping is not blocked by upstream planning gaps or historical records', () => {
  const s = createState()
  confirmShipment(s, draft(s, [{ lineId: 'a1', qty: 20 }]).id)
  assert.equal(line(s, 'a1').shipped, 40)
  assert.equal(materialNeeds(s, 'OR-1042')[0].waiting, 40)
  for (const l of s.orders[0].lines) l.shipped = l.qty
  assert.match(renderPage('orders/OR-1042', s), /生产备料记录仅供追溯，不影响订单完成状态/)
  assert.deepEqual(materialNeeds(s, 'OR-0988'), [])
  assert.doesNotMatch(renderPage('orders/OR-0988'), /生产备料提醒|上游配件备料/)
})

test('actual overreceipt changes physical stock only and preserves plan and customer progress', () => {
  const s = createState(), t = s.tasks[1]
  const allocation = { ...t.allocations }
  receiveTask(s, t.id, 30)
  assert.equal(t.qty, 40)
  assert.equal(t.received, 45)
  assert.equal(t.loss, 5)
  assert.equal(taskStage(t), '任务结清')
  assert.equal(s.stock.earrings, 60)
  assert.equal(line(s, 'a2').shipped, 0)
  assert.equal(line(s, 'a2').reserved, 20)
  assert.deepEqual(t.allocations, allocation)
  unchanged(s, () => receiveTask(s, 'HC-0086', 10))
})

test('loss can settle a task but never fulfill the customer', () => {
  const s = createState(), t = s.tasks[1]
  t.loss = 25
  assert.equal(taskStage(t), '任务结清')
  assert.equal(orderStage(s.orders[0]), '部分出货')
  assert.equal(lineNumbers(s, line(s, 'a2')).gap, 40)
})

test('historical completed orders remain read only without fabricated shipment or stock', () => {
  const s = createState()
  assert.equal(orderStage(s.orders[2]), '历史已完成')
  unchanged(s, () => reserveLine(s, 'c1', 1))
  unchanged(s, () => releaseLine(s, 'c1', 1))
  unchanged(s, () => arrangeHandcraft(s, { lineId: 'c1', qty: 1, supplier: '青禾手作' }))
  unchanged(s, () => draft(s, [{ lineId: 'c1', qty: 1 }], 'OR-0988'))
})

test('static demo blocks connections and has no API or persistent storage dependencies', () => {
  const root = new URL('../public/demos/order-fulfillment/', import.meta.url)
  const html = readFileSync(new URL('index.html', root), 'utf8')
  assert.match(html, /connect-src 'none'/)
  for (const name of ['app.js', 'domain.js']) {
    const source = readFileSync(new URL(name, root), 'utf8')
    assert.doesNotMatch(source, /\b(fetch|axios|localStorage|sessionStorage|indexedDB|XMLHttpRequest|WebSocket)\b/)
    assert.doesNotMatch(source, /from ['"](?:@|\/api)/)
  }
})
