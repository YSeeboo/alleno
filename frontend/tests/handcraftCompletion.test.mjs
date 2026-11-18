import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { handcraftCompletion } from '../src/utils/handcraftCompletion.js'

const order = { status: 'processing' }
const output = (received_qty, extra = {}) => ({ qty: 10, received_qty, ...extra })

test('settled outputs allow completion regardless of material and packaging balances', () => {
  const state = handcraftCompletion(order, [output(10)], [{ qty: 100, received_qty: 0 }])
  assert.equal(state.canComplete, true)
  assert.match(state.hint, /材料余额不影响/)
})

test('every source output must settle independently, including composite part outputs', () => {
  const rows = [output(11, { jewelry_id: 'SP-1' }), output(9, { part_id: 'PJ-1' })]
  assert.equal(handcraftCompletion(order, rows).canComplete, false)
  assert.equal(handcraftCompletion(order, rows).remaining, 1)
  rows[1].received_qty = 10
  assert.equal(handcraftCompletion(order, rows).canComplete, true)
})

test('confirmed losses are already included in received_qty and must not be counted twice', () => {
  assert.equal(handcraftCompletion(order, [output(8, { loss_qty: 2 })]).canComplete, false)
  assert.equal(handcraftCompletion(order, [output(10, { loss_qty: 2 })]).canComplete, true)
})

test('no-output orders preserve material-only settlement including actual quantity zero', () => {
  assert.equal(handcraftCompletion(order, [], [{ qty: 10, actual_qty: 8, received_qty: 8 }]).canComplete, true)
  assert.equal(handcraftCompletion(order, [], [{ qty: 10, actual_qty: 8, received_qty: 7 }]).canComplete, false)
  assert.equal(handcraftCompletion(order, [], [{ qty: 10, actual_qty: 0, received_qty: 0 }]).canComplete, true)
  assert.equal(handcraftCompletion(order, [], []).canComplete, false)
})

test('missing, pending, completed and archived orders cannot expose an active completion action', () => {
  for (const state of [null, { status: 'pending' }, { status: 'completed' }, { status: 'processing', archived_at: '2026-11-17' }]) {
    assert.equal(handcraftCompletion(state, [output(10)]).canComplete, false)
  }
})

test('invalid quantities cannot silently enable completion', () => {
  for (const value of [NaN, Infinity, 'invalid']) {
    assert.equal(handcraftCompletion(order, [output(value)]).canComplete, false)
    assert.equal(handcraftCompletion(order, [output(10, { qty: value })]).canComplete, false)
  }
})

test('detail action uses the safe handcraft status API rather than the old force-completion API', () => {
  const source = readFileSync(new URL('../src/views/handcraft/HandcraftDetail.vue', import.meta.url), 'utf8')
  assert.match(source, /@click="doComplete"/)
  assert.match(source, /:disabled="loading \|\| !outputsLoaded \|\| !completion.canComplete"/)
  assert.match(source, /await updateHandcraftStatus\(orderId, 'completed'\)/)
  assert.doesNotMatch(source, /changeOrderStatus|doChangeStatus/)
  assert.match(source, /待产出结清（回收＋确认损耗）/)
})
