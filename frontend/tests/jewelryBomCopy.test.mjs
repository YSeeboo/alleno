import assert from 'node:assert/strict'
import test from 'node:test'
import { bomCopyNeedsUnitCheck, bomCopyPayload, makeBomCopyDraft } from '../src/utils/jewelryBomCopy.js'

const partMap = { p1: { name: '珍珠', color: '白', unit: '颗', price: 3 }, p2: { name: '链条', unit: '米' } }
const source = [{ part_id: 'p1', qty_per_unit: 48 }, { part_id: 'p2', qty_per_unit: 0.5 }, { part_id: 'p3', qty_per_unit: 2 }]
const target = [{ part_id: 'p1', qty_per_unit: 36 }]
const preview = { source: { id: 'source', unit: '条' }, target_unit: '条' }

test('draft defaults to new parts only and shows both quantities for existing parts', () => {
  const draft = makeBomCopyDraft(source, target, partMap)
  assert.deepEqual(draft.map(row => [row.partId, row.selected, row.existing]), [['p1', false, true], ['p2', true, false], ['p3', true, false]])
  assert.equal(draft[0].targetQty, 36)
  assert.equal(draft[0].sourceQty, 48)
  assert.equal(draft[1].quantity, '0.5')
  assert.equal(draft[2].partName, 'p3')
})

test('payload contains only selected missing parts and edited quantities', () => {
  const draft = makeBomCopyDraft(source, target, partMap)
  draft[0].selected = true // Even if an existing row is accidentally selected, never include it.
  draft[1].quantity = '0.1250'
  draft[2].selected = false
  assert.deepEqual(bomCopyPayload(preview, draft, false), {
    source_id: 'source', source_unit: '条', target_unit: '条', unit_confirmed: false,
    items: [{ part_id: 'p2', qty_per_unit: '0.1250' }],
  })
  draft[1].quantity = '0.00001'
  assert.equal(bomCopyPayload(preview, draft, false), null)
  draft[1].selected = false
  assert.equal(bomCopyPayload(preview, draft, false), null)
  assert.equal(bomCopyPayload(preview, [], false), null)
})

test('unequal or unknown units need a confirmation, without conversion', () => {
  assert.equal(bomCopyNeedsUnitCheck('条', '条'), false)
  assert.equal(bomCopyNeedsUnitCheck(null, null), true)
  assert.equal(bomCopyNeedsUnitCheck(' ', '条'), true)
  const mismatch = { ...preview, target_unit: '对' }
  const draft = makeBomCopyDraft(source, [], partMap)
  assert.equal(bomCopyPayload(mismatch, draft, false), null)
  const confirmed = bomCopyPayload(mismatch, draft, true)
  assert.deepEqual(confirmed.items.map(row => row.qty_per_unit), ['48', '0.5', '2'])
  assert.equal(confirmed.target_unit, '对')
})
