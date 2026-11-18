import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { remainingQuantity, excessQuantity, sourceBalance } from '../src/utils/receiptQuantity.js'
import { createReceiptInput, receiptItemPayload } from '../src/utils/platingReceiptCreate.js'

test('settled sources default to blank rather than inventing a receipt quantity', () => {
  for (const received_qty of [10, 12]) {
    const source = { id: 1, part_id: 'P', supplier_name: 'A', qty: 10, received_qty }
    assert.equal(remainingQuantity(source), 0)
    assert.equal(createReceiptInput(source).qty, null)
    assert.throws(() => receiptItemPayload(source, createReceiptInput(source), 'A'))
    assert.equal(receiptItemPayload(source, { ...createReceiptInput(source), qty: 3 }, 'A').qty, 3)
  }
})

test('source balances clamp remaining and explicitly label settlement excess', () => {
  assert.equal(remainingQuantity({ qty: .3, received_qty: .1 }), .2)
  assert.equal(excessQuantity({ qty: .1, received_qty: .3 }), .2)
  assert.equal(sourceBalance({ qty: 10, received_qty: 12 }), '0 · 结清超出 2')
  assert.equal(sourceBalance({ qty: 10, received_qty: 8 }), 2)
})

test('all canonical receipt forms opt into settled sources and have no remaining-quantity max', () => {
  for (const name of ['plating', 'handcraft']) {
    for (const view of ['Create', 'Detail']) {
      const title = name[0].toUpperCase() + name.slice(1)
      const source = readFileSync(new URL(`../src/views/${name}-receipts/${title}Receipt${view}.vue`, import.meta.url), 'utf8')
      assert.match(source, /include_settled: true/)
      assert.doesNotMatch(source, /(?::max="|max: )get(?:Add)?Remaining/)
    }
  }
})

test('material return selections retain checked blank rows and reject incomplete confirmation', () => {
  const source = readFileSync(new URL('../src/views/handcraft-receipts/PartReturnModal.vue', import.meta.url), 'utf8')
  assert.match(source, /Object.hasOwn/)
  assert.match(source, /remainingQuantity\(part\) \|\| null/)
  assert.match(source, /请为每项已选配件填写/)
  assert.doesNotMatch(source, /:max="getRemaining/)
})
