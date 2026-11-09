import test from 'node:test'
import assert from 'node:assert/strict'
import { summarizePlatingReceipt } from '../src/utils/platingReceiptDetail.js'

test('receipt summary separates quantity units, counts distinct parts and converts weights', () => {
  const items = [
    { part_id: 'a', qty: '0.1', unit: '米', weight: '450', weight_unit: 'g', amount: '1' },
    { part_id: 'a', qty: '0.2', unit: '米', weight: '0.5', weight_unit: 'kg', amount: 0 },
    { part_id: 'b', qty: 20, unit: '个', amount: null },
  ]
  const before = structuredClone(items)
  assert.deepEqual(summarizePlatingReceipt(items), {
    partCount: 2, quantities: [{ unit: '米', qty: 0.3 }, { unit: '个', qty: 20 }],
    weightKg: 0.95, unpricedCount: 1,
  })
  assert.deepEqual(items, before)
})

test('receipt summary distinguishes missing values from real zero and defaults legacy weight to grams', () => {
  assert.deepEqual(summarizePlatingReceipt([]), { partCount: 0, quantities: [], weightKg: null, unpricedCount: 0 })
  assert.equal(summarizePlatingReceipt([{ weight: 120 }]).weightKg, 0.12)
  assert.equal(summarizePlatingReceipt([{ weight: 120, weight_unit: 'lb' }]).weightKg, null)
  assert.equal(summarizePlatingReceipt([{ weight: 0, amount: 0 }]).weightKg, 0)
  assert.equal(summarizePlatingReceipt([{ weight: 0, amount: 0 }]).unpricedCount, 0)
  assert.equal(summarizePlatingReceipt([{ weight: '0.0000001', weight_unit: 'g' }]).weightKg, 0.0000000001)
  assert.deepEqual(summarizePlatingReceipt([{ qty: 2 }]).quantities, [{ unit: '未标单位', qty: 2 }])
})

test('receipt summary ignores cumulative source receipts, losses and independent reconciliation prices', () => {
  const result = summarizePlatingReceipt([{ part_id: 'a', qty: 5, unit: '个', amount: null,
    source_qty: 100, source_received_qty: 90, loss_qty: 10, override_price: 3, settled_amount: 15 }])
  assert.deepEqual(result.quantities, [{ unit: '个', qty: 5 }])
  assert.equal(result.unpricedCount, 1)
})
