import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { matchingLines, ownQuantity, allocationPayload } from '../src/utils/productionAllocation.js'

const lines = [
  { id: 1, product_type: 'part', product_id: 'gold' },
  { id: 2, product_type: 'part', product_id: 'gold' },
  { id: 3, product_type: 'jewelry', product_id: 'gold' },
  { id: 4, product_type: 'part', product_id: 'raw' },
]
const source = { source_type: 'plating', source_item_id: 10, product_type: 'part', product_id: 'gold',
  revision: 'revision', allocations: [{ order_id: 'OR-1', order_item_id: 1, quantity: '20' },
    { order_id: 'OR-2', order_item_id: 99, quantity: 30 }] }

test('match exact target and product type, keeping repeated product lines separate', () => {
  assert.deepEqual(matchingLines(lines, source).map(row => row.id), [1, 2])
})
test('own quantity never includes another customer or the full production batch', () => {
  assert.equal(ownQuantity(source, 'OR-1'), 20)
  assert.equal(ownQuantity(source, 'OR-2'), 30)
  assert.equal(ownQuantity(source, 'OR-3'), 0)
})
test('save payload is scoped to exact current order lines, carrying optimistic revision', () => {
  assert.deepEqual(allocationPayload(lines, source, { 1: 0, 2: 15, 99: 999 }), {
    source_type: 'plating', source_item_id: 10, revision: 'revision',
    allocations: [{ order_item_id: 1, quantity: 0 }, { order_item_id: 2, quantity: 15 }],
  })
})
test('invalid input is not coerced to zero or silently rounded', () => {
  for (const value of [undefined, null, '', '2', -1, 1.2, NaN, Infinity]) {
    assert.throws(() => allocationPayload(lines, source, { 1: value, 2: 0 }))
  }
})
test('real module has scoped routing, no Demo imports and explicit stage boundaries', () => {
  const view = readFileSync(new URL('../src/views/orders/OrderProduction.vue', import.meta.url), 'utf8')
  const routes = readFileSync(new URL('../src/router/index.js', import.meta.url), 'utf8')
  assert.match(routes, /orders\/:id\/production/)
  assert.match(view, /不是预留库存/)
  assert.match(view, /<OrderMaterials/)
  const materials = readFileSync(new URL('../src/components/fulfillment/OrderMaterials.vue', import.meta.url), 'utf8')
  assert.match(materials, /不是生产时点快照/)
  assert.doesNotMatch(view, /public\/demos|domain\.js/)
})
