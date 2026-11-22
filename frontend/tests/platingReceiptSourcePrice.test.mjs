import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createReceiptInput, receiptItemPayload, summarizeReceiptDraft } from '../src/utils/platingReceiptCreate.js'

const source = readFileSync(new URL('../src/views/plating-receipts/PlatingReceiptCreate.vue', import.meta.url), 'utf8')
const item = { id: 1, part_id: 'P', part_name: '链条', supplier_name: '电镀厂', qty: 10, received_qty: 2, unit: '米' }

function harness() {
  const deps = {
    locked: { value: false }, loadingItems: { value: false }, itemInputs: {},
    selectedItems: { value: [] }, selectedIds: { value: new Set() }, createReceiptInput,
  }
  const extract = name => {
    const start = source.indexOf(`const ${name} =`)
    return source.slice(start, source.indexOf('\n}\n', start) + 3)
  }
  return {
    ...deps,
    ...new Function(...Object.keys(deps), `${extract('toggleItem')}\n${extract('updateSourcePrice')}\nreturn { toggleItem, updateSourcePrice }`)(...Object.values(deps)),
  }
}

test('source rows have a price column bound to the same draft as selected receipt rows', () => {
  const candidates = source.slice(source.indexOf('class="rc-source-table"'), source.indexOf('class="rc-detail-section"'))
  assert.match(candidates, /<span>回收单价<\/span>/)
  assert.match(candidates, /:value="itemInputs\[item.id\]\?\.price \?\? null"/)
  assert.match(candidates, /updateSourcePrice\(item, value\)/)
  assert.match(source, /v-model:value="itemInputs\[item.id\].price"/)
})

test('entering a source price preserves it on selection without implicitly selecting or charging the row', () => {
  const h = harness()
  h.updateSourcePrice(item, 1.2345678)
  assert.equal(h.selectedItems.value.length, 0)
  assert.equal(summarizeReceiptDraft(h.selectedItems.value, h.itemInputs).amount, '0.0000000')
  h.toggleItem(item, true)
  assert.equal(h.selectedItems.value.length, 1)
  assert.equal(h.itemInputs[item.id].price, 1.2345678)
  assert.equal(receiptItemPayload(item, h.itemInputs[item.id], item.supplier_name).price, 1.2345678)
  assert.equal(summarizeReceiptDraft(h.selectedItems.value, h.itemInputs).amount, '9.8765424')
})

test('editing price on selected rows preserves quantity/weight and supports free or unpriced rows', () => {
  const h = harness()
  h.toggleItem(item, true)
  Object.assign(h.itemInputs[1], { qty: 3, weight: 1.5 })
  h.updateSourcePrice(item, 0)
  assert.deepEqual(h.itemInputs[1], { qty: 3, weight: 1.5, unit: '米', price: 0 })
  assert.equal(summarizeReceiptDraft(h.selectedItems.value, h.itemInputs).unpricedCount, 0)
  h.updateSourcePrice(item, null)
  assert.equal(summarizeReceiptDraft(h.selectedItems.value, h.itemInputs).unpricedCount, 1)
})

test('prices remain independent for the same part in different source rows and reset safely after clearing', () => {
  const h = harness()
  h.updateSourcePrice(item, 2)
  h.updateSourcePrice({ ...item, id: 2 }, 3)
  assert.equal(h.itemInputs[1].price, 2)
  assert.equal(h.itemInputs[2].price, 3)
  delete h.itemInputs[1]
  h.updateSourcePrice(item, 4)
  assert.equal(h.itemInputs[1].price, 4)
})

test('source prices cannot change during submit or source refresh', () => {
  const h = harness()
  h.locked.value = true
  h.updateSourcePrice(item, 2)
  assert.deepEqual(h.itemInputs, {})
  h.locked.value = false
  h.loadingItems.value = true
  h.updateSourcePrice(item, 3)
  assert.deepEqual(h.itemInputs, {})
})
