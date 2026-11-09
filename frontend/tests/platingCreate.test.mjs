import test from 'node:test'
import assert from 'node:assert/strict'
import { createPlatingItem, copyPlatingItem, platingItemPayload, summarizePlatingItems } from '../src/utils/platingCreate.js'

test('new and copied rows have stable unique keys, including after removing a row', () => {
  const first = createPlatingItem()
  const second = createPlatingItem()
  const rows = [first, second]
  const copy = copyPlatingItem(first)
  rows.splice(1, 0, copy)
  assert.deepEqual(rows.map(row => row._key), [first._key, copy._key, second._key])
  rows.splice(0, 1)
  const next = createPlatingItem()
  assert.equal(new Set([first._key, second._key, copy._key, next._key]).size, 4)
  assert.equal(rows[1], second)
})

test('copy retains all entered values, color and nested variant data without sharing state', () => {
  const source = {
    ...createPlatingItem(), part_id: 'PJ-DZ-00033', receive_part_id: 'PJ-DZ-00033-G',
    qty: 300, unit: '个', weight: .45, weight_unit: 'kg', plating_method: '金', note: '按样板',
    _selectedColor: 'G', _showMore: true, _reqSeq: 8,
    _variantInfo: { part: { id: 'PJ-DZ-00033-G', name: '蝴蝶吊坠_金色' }, created: false },
  }
  const copy = copyPlatingItem(source)
  assert.deepEqual(platingItemPayload(copy), platingItemPayload(source))
  assert.equal(copy._selectedColor, 'G')
  assert.equal(copy._showMore, true)
  assert.equal(copy._reqSeq, 0)
  assert.equal(copy._variantLoading, false)
  assert.equal(copy._creatingVariant, false)
  copy.note = '单独修改'
  copy.qty = 20
  copy._selectedColor = 'S'
  copy._variantInfo.part.name = '复制行的配件'
  assert.equal(source.note, '按样板')
  assert.equal(source.qty, 300)
  assert.equal(source._selectedColor, 'G')
  assert.equal(source._variantInfo.part.name, '蝴蝶吊坠_金色')
})

test('empty rows and suggested variants can be copied', () => {
  const empty = createPlatingItem()
  assert.deepEqual(platingItemPayload(copyPlatingItem(empty)), platingItemPayload(empty))
  const source = { ...empty, _variantInfo: { suggested_name: '蝴蝶吊坠_古金色' } }
  const copy = copyPlatingItem(source)
  copy._variantInfo.suggested_name = '修改后的建议名'
  assert.equal(source._variantInfo.suggested_name, '蝴蝶吊坠_古金色')
})

test('create and merge payloads exclude every UI-only field', () => {
  const item = { ...copyPlatingItem(createPlatingItem()), _futureInternalField: true }
  assert.deepEqual(Object.keys(platingItemPayload(item)).sort(), [
    'part_id', 'receive_part_id', 'qty', 'unit', 'weight', 'weight_unit', 'plating_method', 'note',
  ].sort())
})

test('summary keeps quantities in separate units and converts g to kg', () => {
  const rows = [
    { ...createPlatingItem(), part_id: 'A', qty: 300, weight: .45 },
    { ...createPlatingItem(), part_id: 'B', qty: 200, unit: '条', weight: 800, weight_unit: 'g' },
    { ...createPlatingItem(), part_id: 'C', qty: 500, weight: .32 },
    { ...createPlatingItem(), qty: 999, weight: 100 }, // Unselected rows are not totals.
  ]
  assert.deepEqual(summarizePlatingItems(rows), {
    quantities: [{ unit: '个', qty: 800 }, { unit: '条', qty: 200 }], weightKg: 1.57,
  })
  rows.splice(1, 0, copyPlatingItem(rows[0]))
  assert.equal(summarizePlatingItems(rows).weightKg, 2.02)
  rows.splice(1, 1)
  assert.equal(summarizePlatingItems(rows).weightKg, 1.57)
})

test('summary handles empty lists, missing optional weights and decimal quantities', () => {
  assert.deepEqual(summarizePlatingItems([]), { quantities: [], weightKg: 0 })
  assert.deepEqual(summarizePlatingItems([
    { ...createPlatingItem(), part_id: 'A', qty: null },
    { ...createPlatingItem(), part_id: 'B', qty: 1.5, unit: '米', weight: .1 },
    { ...createPlatingItem(), part_id: 'C', qty: 2.5, unit: '米', weight: .2 },
  ]), { quantities: [{ unit: '个', qty: 0 }, { unit: '米', qty: 4 }], weightKg: .3 })
})

test('package unit survives copying, payload serialization and separate quantity totals', () => {
  const item = { ...createPlatingItem(), part_id: 'A', qty: 5, unit: '包' }
  const copy = copyPlatingItem(item)
  assert.equal(copy.unit, '包')
  assert.equal(platingItemPayload(copy).unit, '包')
  assert.deepEqual(summarizePlatingItems([
    item, copy, { ...createPlatingItem(), part_id: 'B', qty: 20 },
  ]).quantities, [{ unit: '包', qty: 10 }, { unit: '个', qty: 20 }])
})
