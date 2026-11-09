import test from 'node:test'
import assert from 'node:assert/strict'
import { platingReceiptQuantities, summarizePlatingDetail, canLinkPlatingReceipt } from '../src/utils/platingDetail.js'

test('actual receipts exclude loss already included by API in received_qty', () => {
  const quantities = platingReceiptQuantities({ qty: 200, received_qty: 195, loss_qty: 5 })
  assert.equal(quantities.actual, 190)
  assert.equal(quantities.loss, 5)
  assert.equal(quantities.remaining, 5)
  assert.equal(quantities.receivedPercent, 95)
  assert.equal(quantities.lossPercent, 2.5)
})

test('completed with losses means settled, not fully actually received', () => {
  const item = { qty: 200, received_qty: 200, loss_qty: 5 }
  assert.equal(platingReceiptQuantities(item).actual, 195)
  assert.equal(platingReceiptQuantities(item).remaining, 0)
  assert.equal(summarizePlatingDetail([item]).settledCount, 1)
})

test('decimal API values and empty quantities are safe and rounded', () => {
  assert.equal(platingReceiptQuantities({ qty: '0.3', received_qty: '0.1', loss_qty: null }).remaining, 0.2)
  assert.deepEqual(platingReceiptQuantities({}), { qty: 0, actual: 0, loss: 0, remaining: 0, receivedPercent: 0, lossPercent: 0 })
})

test('summary keeps losses in different units separate and converts only weight', () => {
  const result = summarizePlatingDetail([
    { part_id: 'a', qty: 100, received_qty: 100, loss_qty: 5, unit: '个', weight: 500, weight_unit: 'g' },
    { part_id: 'a', qty: 5, received_qty: 2, loss_qty: 1, unit: '包', weight: 1, weight_unit: 'kg' },
    { part_id: 'b', qty: 20, received_qty: 3, loss_qty: 2, unit: '个' },
  ])
  assert.equal(result.partCount, 2)
  assert.equal(result.settledCount, 1)
  assert.equal(result.remainingCount, 2)
  assert.equal(result.weightKg, 1.5)
  assert.deepEqual(result.losses, [{ unit: '个', qty: 7 }, { unit: '包', qty: 1 }])
})

test('missing weight is not a misleading zero; legacy weight defaults to grams', () => {
  assert.equal(summarizePlatingDetail([]).weightKg, null)
  assert.equal(summarizePlatingDetail([{ weight: 120 }]).weightKg, 0.12)
  assert.equal(summarizePlatingDetail([{ weight: 0, weight_unit: 'kg' }]).weightKg, 0)
})

test('receipt linking is only offered for active processing items with a gap', () => {
  const item = { status: '电镀中', qty: 20, received_qty: 10 }
  assert.equal(canLinkPlatingReceipt({ status: 'processing' }, item), true)
  for (const order of [null, { status: 'pending' }, { status: 'completed' }, { status: 'processing', archived_at: '2026-11-08' }]) {
    assert.equal(canLinkPlatingReceipt(order, item), false)
  }
  assert.equal(canLinkPlatingReceipt({ status: 'processing' }, { ...item, received_qty: 20 }), false)
  assert.equal(canLinkPlatingReceipt({ status: 'processing' }, { ...item, status: '未送出' }), false)
})

test('archive does not fabricate receipts or change underlying quantities', () => {
  const item = { part_id: 'a', qty: 20, received_qty: 10, loss_qty: 2 }
  const before = { ...item }
  assert.equal(platingReceiptQuantities(item).actual, 8)
  assert.equal(summarizePlatingDetail([item]).remainingCount, 1)
  assert.deepEqual(item, before)
})
