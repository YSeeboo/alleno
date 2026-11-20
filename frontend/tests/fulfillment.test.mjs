import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { shipmentEntries, stockWarnings, shipmentLabel, legacyNextStatus } from '../src/utils/fulfillment.js'
const lines = [
  { id: 1, product_type: 'part', product_id: 'gold', product_name: '金色链条', remaining: 50, reserved: 10, public_available: 20, unit: '条' },
  { id: 2, product_type: 'part', product_id: 'gold', product_name: '金色链条', remaining: 30, reserved: 0, public_available: 20, unit: '条' },
]
test('shipment selection is explicit and never prefills or includes unselected lines', () => {
  assert.throws(() => shipmentEntries(lines, {}, {}))
  assert.throws(() => shipmentEntries(lines, { 1: true }, {}))
  assert.deepEqual(shipmentEntries(lines, { 1: true }, { 1: 20, 2: 30 }), [{ order_item_id: 1, quantity: 20 }])
})
test('fractional, null, coerced, negative and excess entries are rejected', () => {
  for (const quantity of [null, undefined, '', '1', 0, -1, 1.5, 51, NaN, Infinity]) assert.throws(() => shipmentEntries(lines, { 1: true }, { 1: quantity }))
})
test('stock check aggregates same product public use, consumes only selected line reservations', () => {
  assert.equal(stockWarnings(lines, [{ order_item_id: 1, quantity: 20 }, { order_item_id: 2, quantity: 11 }]).length, 1)
  assert.equal(stockWarnings(lines, [{ order_item_id: 1, quantity: 20 }, { order_item_id: 2, quantity: 10 }]).length, 0)
  assert.equal(stockWarnings(lines, [{ order_item_id: 2, quantity: 25 }]).length, 1)
})
test('historical states never fabricate shipping completion', () => {
  assert.equal(shipmentLabel({ managed: false, completed_items: 2, total_items: 2 }), '历史待核对，不补记出货')
  assert.equal(shipmentLabel({ managed: true, completed_items: 0, total_items: 3 }), '已全部发货 0 / 3 项')
})
test('legacy controls never offer manual completion for managed or unverified orders', () => {
  assert.equal(legacyNextStatus('生产中', false), '已完成')
  for (const managed of [true, null, undefined]) assert.equal(legacyNextStatus('生产中', managed), null)
  assert.equal(legacyNextStatus('待生产', true), '生产中')
  for (const status of ['已完成', '已取消', undefined]) assert.equal(legacyNextStatus(status, false), null)
})
test('real modules and order-scoped tabs are routed independently, without Demo imports', () => {
  const router = readFileSync(new URL('../src/router/index.js', import.meta.url), 'utf8')
  for (const route of ['shipments', 'shipments/create', 'shipments/:id', 'stock-readiness', 'orders/:id/records']) assert.ok(router.includes(`path: '${route}'`))
  const view = readFileSync(new URL('../src/views/orders/OrderDetail.vue', import.meta.url), 'utf8')
  assert.match(view, /商品明细/)
  assert.match(view, /预留库存/)
  assert.match(view, /ShipmentTable/)
  assert.doesNotMatch(view, /public\/demos|domain\.js/)
})
