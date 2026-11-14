import test from 'node:test'
import assert from 'node:assert/strict'
import { validBomQuantity, bomSubtotal, filterJewelryBom, jewelryInfoPatch, jewelryPricePatch } from '../src/utils/jewelryDetail.js'

test('BOM quantities accept positive decimal quantities up to four places, below one million', () => {
  for (const value of [1, '2', 0.0001, '001.2300', '999999.9999']) assert.equal(validBomQuantity(value), true, String(value))
  for (const value of [null, undefined, '', ' ', 0, -1, '1e2', '1.00001', '1.', '.5', 'NaN', Infinity, '1,000', 1000000]) assert.equal(validBomQuantity(value), false, String(value))
})

test('row subtotals match seven-place ROUND_HALF_UP without binary floating point or double rounding', () => {
  assert.equal(bomSubtotal('0.1234567', '2.5'), '0.3086418')
  assert.equal(bomSubtotal('0.3333333', 3), '0.9999999')
  assert.equal(bomSubtotal('0.00000004', 3), '0.0000001')
  assert.equal(bomSubtotal('0.00000015', 3), '0.0000005')
  assert.equal(bomSubtotal('1.23456785', 1), '1.2345679')
  assert.equal(bomSubtotal('0.0005', '0.0001'), '0.0000001')
  assert.equal(bomSubtotal('1e-7', '1.5'), '0.0000002')
  assert.equal(bomSubtotal('2.5e+2', '0.0001'), '0.0250000')
  assert.equal(bomSubtotal(0, 3), '0.0000000')
})

test('missing and invalid row costs are not silently displayed as zero', () => {
  for (const value of [null, undefined, '', NaN, Infinity, -1, 'abc', '1e1000']) assert.equal(bomSubtotal(value, 1), null)
  assert.equal(bomSubtotal(1, 0), null)
})

test('BOM search is case-insensitive, combines name and exact text ID tokens, and does not mutate rows', () => {
  const rows = [{ part_name: '金色 链条', part_id: 'PJ-001' }, { part_name: '银色珠子', part_id: 'PJ-002' }]
  assert.deepEqual(filterJewelryBom(rows, ' pj-001 金色 '), [rows[0]])
  assert.deepEqual(filterJewelryBom(rows, '不存在'), [])
  assert.deepEqual(filterJewelryBom(rows, ''), rows)
  assert.equal(rows.length, 2)
})

test('unchanged legacy category/unit and blank optional values are preserved by sparse patches', () => {
  const original = { id: 'SP-PAIR-00001', name: '旧饰品', category: '单对', unit: '包', color: null, retail_price: 12 }
  assert.deepEqual(jewelryInfoPatch(original, { ...original, color: '' }), {})
  assert.deepEqual(jewelryInfoPatch(original, { ...original, name: ' 新名称 ' }), { name: '新名称' })
  assert.deepEqual(jewelryInfoPatch(original, { ...original, category: '耳饰' }), { category: '耳饰' })
  assert.deepEqual(jewelryInfoPatch(original, { ...original, unit: '卡' }), { unit: '卡' })
  assert.equal(original.category, '单对')
  assert.equal(original.id, 'SP-PAIR-00001')
})

test('metadata validation permits only explicit supported classifications and units', () => {
  const original = { name: '饰品', category: '项链', unit: '条', color: '金色' }
  assert.throws(() => jewelryInfoPatch(original, { ...original, name: ' ' }), /名称/)
  assert.throws(() => jewelryInfoPatch(original, { ...original, name: 'a'.repeat(121) }), /120/)
  assert.throws(() => jewelryInfoPatch(original, { ...original, category: '单对' }), /类型/)
  assert.throws(() => jewelryInfoPatch(original, { ...original, unit: '箱' }), /单位/)
  assert.deepEqual(jewelryInfoPatch(original, { ...original, color: ' ' }), { color: null })
  const legacy = { ...original, name: ' 旧名称 ', color: ' 旧颜色 ' }
  assert.deepEqual(jewelryInfoPatch(legacy, legacy), {})
})

test('price patches distinguish null/zero and only write changed editable prices', () => {
  const original = { retail_price: 10, wholesale_price: null, handcraft_cost: 0, material_cost: 99 }
  assert.deepEqual(jewelryPricePatch(original, { ...original }), {})
  assert.deepEqual(jewelryPricePatch(original, { ...original, wholesale_price: 0 }), { wholesale_price: 0 })
  assert.deepEqual(jewelryPricePatch(original, { ...original, retail_price: '', handcraft_cost: '1.2345678' }), { retail_price: null, handcraft_cost: 1.2345678 })
  assert.deepEqual(jewelryPricePatch({}, {}), {})
  for (const value of [-1, Infinity, NaN, 'abc']) assert.throws(() => jewelryPricePatch(original, { ...original, wholesale_price: value }), /不小于 0/)
})
