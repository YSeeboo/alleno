import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { orderHandcraftPayload } from '../src/utils/orderProductionCreation.js'

const values = { line: { id: 7, product_type: 'jewelry', product_id: 'same-code', unit: '条', quantity: 100, allocated: 60 },
  supplier: ' 手工商 ', planned: '50', allocated: '40', requestKey: 'unique-key', materials: [{ key: 1, part_id: 'gold', qty: '12.0001', unit: '个' }] }

test('creation keeps exact line identity, full output plan and customer share separate', () => {
  const data = orderHandcraftPayload(values)
  assert.equal(data.order_item_id, 7)
  assert.equal(data.allocated_quantity, 40)
  assert.equal(data.jewelries[0].qty, 50)
  assert.equal(data.supplier_name, '手工商')
  assert.equal(data.append_to_order_id, null)
  assert.deepEqual(data.parts, [{ part_id: 'gold', qty: 12.0001, unit: '个' }])
  assert.deepEqual(data.jewelries, [{ jewelry_id: 'same-code', qty: 50, unit: '条' }])
})

test('explicit append and direct part output never infer another line or product type', () => {
  const data = orderHandcraftPayload({ ...values, targetId: 'HC-exact', line: { ...values.line, id: 8, product_type: 'part', unit: '个' } })
  assert.equal(data.order_item_id, 8)
  assert.equal(data.append_to_order_id, 'HC-exact')
  assert.deepEqual(data.jewelries, [{ part_id: 'same-code', qty: 50, unit: '个' }])
})

test('creation rejects excess, blank, fractional, non-finite and oversized quantities before API writes', () => {
  for (const allocated of ['', null, undefined, 0, -1, '40.1', 41, Infinity, NaN]) assert.throws(() => orderHandcraftPayload({ ...values, allocated }))
  for (const planned of ['', 39, 2.5, 1000000000]) assert.throws(() => orderHandcraftPayload({ ...values, planned }))
  for (const qty of ['', null, -1, 0, Infinity, NaN, '0.00001', 1000000]) assert.throws(() => orderHandcraftPayload({ ...values, materials: [{ part_id: 'gold', unit: '个', qty }] }))
  assert.throws(() => orderHandcraftPayload({ ...values, materials: [] }))
})

test('real workspace opens creation per exact line and uncertain retries freeze the original request', () => {
  const page = readFileSync(new URL('../src/views/orders/OrderProduction.vue', import.meta.url), 'utf8')
  const dialog = readFileSync(new URL('../src/components/fulfillment/OrderHandcraftDialog.vue', import.meta.url), 'utf8')
  assert.match(page, /creatingLine = line/)
  assert.match(page, /:line="creatingLine"/)
  assert.match(dialog, /if \(!attempt\)/)
  assert.match(dialog, /createOrderHandcraft\(props.orderId, attempt\)/)
  assert.match(dialog, /onBeforeRouteLeave\(\(\) => !blocked.value\)/)
  assert.match(dialog, /onBeforeRouteUpdate\(\(\) => !blocked.value\)/)
  assert.match(dialog, /:close-on-esc="!blocked"/)
  assert.match(dialog, /!\$event && !blocked && \$emit\('close'\)/)
  assert.doesNotMatch(dialog, /public\/demos|domain\.js/)
})
