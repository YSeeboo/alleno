import test from 'node:test'
import assert from 'node:assert/strict'
import { groupMaterialRows, sumMaterialQuantities } from '../src/utils/orderMaterialGroups.js'

const source = (id, overrides = {}) => ({ key:`material:${id}:P`, part_id:'P', product_name:'配件 A', unit:'个', quantity:120, allocated:40,
  line:{ id, product_name:`商品 ${id}`, customer_code:`CODE-${id}` }, ...overrides })

test('same part and unit aggregate as 240 with independent exact-line source identities', () => {
  const rows = [source(1), source(2)], before = structuredClone(rows)
  const groups = groupMaterialRows(rows)
  assert.equal(groups.length, 1)
  assert.equal(groups[0].quantity, '240')
  assert.equal(groups[0].allocated, '80')
  assert.deepEqual(groups[0].sources.map(row => [row.line.id, row.quantity]), [[1, 120], [2, 120]])
  assert.equal(groups[0].sources[0], rows[0])
  assert.deepEqual(rows, before)
})

test('same names with different IDs, different units and missing units never merge', () => {
  const groups = groupMaterialRows([source(1), source(2, { part_id:'Q' }), source(3, { unit:'包' }), source(4, { unit:'' })])
  assert.equal(groups.length, 4)
  assert.equal(new Set(groups.map(row => row.key)).size, 4)
})

test('missing BOM rows remain separate while deleted requirements retain shares and both review flags', () => {
  const missing = { key:'3:missing', missing:true, line:{ id:3 } }
  const rows = [source(1, { demand_changed:true }), source(2, { quantity:0, allocated:5, legacy_claim:true, qty_per_unit:0 }), missing]
  const groups = groupMaterialRows(rows)
  assert.equal(groups.length, 2)
  assert.equal(groups[0].quantity, '120')
  assert.equal(groups[0].allocated, '45')
  assert.equal(groups[0].demand_changed, true)
  assert.equal(groups[0].legacy_claim, true)
  assert.equal(groups[0].sources[1].quantity, 0)
  assert.equal(groups[1], missing)
})

test('decimal totals stay exact at seven places, including large totals and scientific notation', () => {
  assert.equal(sumMaterialQuantities([0.1, 0.2]), '0.3')
  assert.equal(sumMaterialQuantities(['0.0000001', 1e-7]), '0.0000002')
  assert.equal(sumMaterialQuantities(['9999999999.1234567', '0.0000001']), '9999999999.1234568')
  assert.equal(sumMaterialQuantities(['120.0000', '120']), '240')
  assert.equal(sumMaterialQuantities([0, '0']), '0')
})

test('unknown or invalid source quantities never become a partial total or fabricated zero', () => {
  for (const invalid of [null, undefined, '', NaN, Infinity, -1, 'bad', '0.00000001', '1e-10000000']) assert.equal(sumMaterialQuantities([120, invalid]), null)
  const [group] = groupMaterialRows([source(1), source(2, { allocated:null })])
  assert.equal(group.quantity, '240')
  assert.equal(group.allocated, null)
})

test('empty rows stay empty and group keys remain stable across input order changes', () => {
  assert.deepEqual(groupMaterialRows([]), [])
  const rows = [source(1), source(2, { part_id:'Q' }), source(3)]
  assert.deepEqual(new Set(groupMaterialRows(rows).map(row => row.key)), new Set(groupMaterialRows([...rows].reverse()).map(row => row.key)))
})
