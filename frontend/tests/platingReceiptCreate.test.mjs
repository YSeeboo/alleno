import test from 'node:test'
import assert from 'node:assert/strict'
import {
  remainingReceiptQuantity, createReceiptInput, filterPendingReceiptItems,
  receiptLineAmount, summarizeReceiptDraft, receiptItemPayload,
} from '../src/utils/platingReceiptCreate.js'

const source = (overrides = {}) => ({
  id: 1, supplier_name: '甲电镀厂', part_id: 'PJ-001', part_name: '桃心',
  receive_part_id: 'PJ-001-G', receive_part_name: '桃心_金色', qty: 10, received_qty: 2,
  unit: '包', weight_unit: 'kg', created_at: '2026-11-14T08:00:00', ...overrides,
})

test('default receipt inputs use only remaining quantities and preserve source units', () => {
  assert.deepEqual(createReceiptInput(source()), { qty: 8, unit: '包', price: null, weight: null })
  assert.equal(remainingReceiptQuantity(source({ qty: .3, received_qty: .1 })), .2)
  assert.equal(createReceiptInput(source({ unit: null })).unit, '个')
})

test('pending filters match all tokens across source/target IDs/names and the source date', () => {
  const rows = [source(), source({ id: 2, part_name: '蝴蝶', receive_part_name: '蝴蝶_银色', created_at: '2026-11-13T08:00:00' })]
  assert.deepEqual(filterPendingReceiptItems(rows, 'pj-001　金色', '2026-11-14'), [rows[0]])
  assert.deepEqual(filterPendingReceiptItems(rows, '蝴蝶', '2026-11-14'), [])
  assert.equal(filterPendingReceiptItems(rows, '', null).length, 2)
})

test('filtering candidates never changes selected rows, entered values or draft totals', () => {
  const selected = [source(), source({ id: 2 })]
  const inputs = { 1: { qty: 2, price: 3, unit: '包' }, 2: { qty: 1, price: 2, unit: '个' } }
  const before = structuredClone({ selected, inputs })
  filterPendingReceiptItems(selected, '不存在', null)
  assert.deepEqual(summarizeReceiptDraft(selected, inputs), {
    quantities: [{ unit: '包', qty: 2 }, { unit: '个', qty: 1 }], amount: '8.0000000', unpricedCount: 0,
  })
  assert.deepEqual({ selected, inputs }, before)
})

test('preview amounts distinguish no price, free lines, invalid values and exact tiny prices', () => {
  assert.equal(receiptLineAmount({ qty: 3, price: null }), null)
  assert.equal(receiptLineAmount({ qty: 3, price: 0 }), '0.0000000')
  assert.equal(receiptLineAmount({ qty: 0, price: 1 }), null)
  assert.equal(receiptLineAmount({ qty: 2, price: -1 }), null)
  assert.equal(receiptLineAmount({ qty: Infinity, price: 1 }), null)
  assert.equal(receiptLineAmount({ qty: 1.5, price: 1e-7 }), '0.0000002')
  assert.equal(receiptLineAmount({ qty: 3, price: 0.1234567 }), '0.3703701')
  assert.equal(receiptLineAmount({ qty: 3, price: 0.00000005 }), '0.0000003')
})

test('summary sums rounded line amounts and keeps unknown prices separate', () => {
  const rows = [source(), source({ id: 2 }), source({ id: 3 })]
  const inputs = { 1: { qty: 1.5, price: 1e-7 }, 2: { qty: 1.5, price: 1e-7 }, 3: { qty: 1, price: null } }
  assert.equal(summarizeReceiptDraft(rows, inputs).amount, '0.0000004')
  assert.equal(summarizeReceiptDraft(rows, inputs).unpricedCount, 1)
  assert.deepEqual(summarizeReceiptDraft([], {}), { quantities: [], amount: '0.0000000', unpricedCount: 0 })
})

test('payload preserves source linkage, receive variant, unit and optional weight/price', () => {
  const item = source()
  const input = { ...createReceiptInput(item), qty: 3, price: 0, weight: 0 }
  assert.deepEqual(receiptItemPayload(item, input, item.supplier_name), {
    plating_order_item_id: 1, part_id: 'PJ-001-G', qty: 3, unit: '包', price: 0, weight: 0, weight_unit: 'kg',
  })
  const plain = source({ receive_part_id: null, weight_unit: null })
  const payload = receiptItemPayload(plain, createReceiptInput(plain), plain.supplier_name)
  assert.equal(payload.part_id, 'PJ-001')
  assert.equal(payload.weight_unit, null)
  assert.equal(payload.price, null)
  assert.equal(receiptItemPayload(plain, { ...createReceiptInput(plain), weight: 1 }, plain.supplier_name).weight_unit, 'g')
})

test('payload rejects missing, nonfinite, too precise and excessive quantities', () => {
  const item = source()
  for (const qty of [null, '', 0, -1, NaN, Infinity, .00001, 8.0001]) {
    assert.throws(() => receiptItemPayload(item, { ...createReceiptInput(item), qty }, item.supplier_name))
  }
  assert.equal(receiptItemPayload(item, { ...createReceiptInput(item), qty: .0001 }, item.supplier_name).qty, .0001)
})

test('payload rejects unavailable and foreign-vendor sources without silently dropping them', () => {
  assert.throws(() => receiptItemPayload(source({ _unavailable: true }), createReceiptInput(source()), '甲电镀厂'), /已不在待回收/)
  assert.throws(() => receiptItemPayload(source(), createReceiptInput(source()), '乙电镀厂'), /不属于当前商家/)
})

test('payload rejects invalid optional values rather than converting them to free/zero', () => {
  for (const key of ['price', 'weight']) {
    for (const value of ['', -1, NaN, Infinity]) {
      assert.throws(() => receiptItemPayload(source(), { ...createReceiptInput(source()), [key]: value }, '甲电镀厂'))
    }
  }
})
