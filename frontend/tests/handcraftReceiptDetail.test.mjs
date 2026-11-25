import assert from 'node:assert/strict'
import test from 'node:test'
import { additionalReceiptPayload, filterAddReceiptSources, handcraftReceiptSourceParams, summarizeHandcraftReceiptDetail } from '../src/utils/handcraftReceiptDetail.js'
import { createHandcraftReceiptInput, handcraftSourceKey } from '../src/utils/handcraftReceiptCreate.js'

const material = { id: 7, is_output: false, item_type: 'part', item_id: 'PJ-1', item_name: '金色链条', unit: '米', qty: 3, received_qty: 1, handcraft_order_id: 'HC-0002', created_at: '2026-11-22T09:00:00' }
const output = { ...material, is_output: true, item_id: 'PJ-2', item_name: '组合链条', unit: '个', received_qty: 3, handcraft_order_id: 'HC-0003', created_at: '2026-11-23T09:00:00' }

test('source request includes settled sources and excludes only rows already on the receipt', () => {
  assert.deepEqual(handcraftReceiptSourceParams({ supplier_name: '商家', items: [
    { handcraft_part_item_id: 3 }, { handcraft_jewelry_item_id: 7 },
  ] }), { supplier_name: '商家', include_settled: true, exclude_part_item_ids: [3], exclude_jewelry_item_ids: [7] })
})

test('filters distinguish material and part output even if their source IDs coincide', () => {
  const sources = [material, output]
  const selectedKeys = new Set([handcraftSourceKey(output)])
  assert.deepEqual(filterAddReceiptSources(sources, { kind: 'material', keyword: 'HC-0002 链条' }), [material])
  assert.deepEqual(filterAddReceiptSources(sources, { kind: 'all', dateOn: '2026-11-23' }), [output])
  assert.deepEqual(filterAddReceiptSources(sources, { kind: 'all', selectedOnly: true, selectedKeys }), [output])
  assert.deepEqual(filterAddReceiptSources(sources, { kind: 'output' }), [output])
})

test('one batch preserves both source types, allows actual overs and distinguishes free from unpriced', () => {
  const inputs = {
    [handcraftSourceKey(material)]: { ...createHandcraftReceiptInput(material), qty: 2.125, price: 0, weight: 42 },
    [handcraftSourceKey(output)]: { ...createHandcraftReceiptInput(output), qty: 4 },
  }
  assert.deepEqual(additionalReceiptPayload([material, output], inputs), { items: [
    { handcraft_part_item_id: 7, qty: 2.125, unit: '米', price: 0, weight: 42, weight_unit: 'g' },
    { handcraft_jewelry_item_id: 7, qty: 4, unit: '个', price: null, weight: null, weight_unit: null },
  ] })
  inputs[handcraftSourceKey(output)].qty = 1.5
  assert.throws(() => additionalReceiptPayload([output], inputs), /正整数/)
  inputs[handcraftSourceKey(material)].qty = 0.00001
  assert.throws(() => additionalReceiptPayload([material], inputs), /4 位小数/)
})

test('detail summary groups actual receipt quantities by unit and weights by kg', () => {
  assert.deepEqual(summarizeHandcraftReceiptDetail([
    { handcraft_part_item_id: 7, qty: 1.25, unit: '米', weight: 200 },
    { handcraft_jewelry_item_id: 7, qty: 3, unit: '个', weight: 0.8, weight_unit: 'kg' },
    { handcraft_jewelry_item_id: 8, qty: 2, unit: '个', weight: null },
  ]), { quantities: [{ qty: 1.25, unit: '米' }, { qty: 5, unit: '个' }], weightKg: 1, outputCount: 2, partCount: 1 })
})
