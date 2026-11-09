import test from 'node:test'
import assert from 'node:assert/strict'
import { monthBounds, reconciliationParams, validOverride } from '../src/utils/platingReconciliation.js'
import { normalizePlatingQuery, getPlatingLocation, rememberPlatingLocation } from '../src/utils/platingNavigation.js'

test('reconciliation defaults to current month but explicit empty dates mean unlimited', () => {
  const now = new Date(2026, 10, 9)
  assert.deepEqual(monthBounds(0, now), { date_from: '2026-11-01', date_to: '2026-11-30' })
  assert.deepEqual(monthBounds(-1, new Date(2026, 0, 2)), { date_from: '2025-12-01', date_to: '2025-12-31' })
  assert.deepEqual(reconciliationParams({}, now), monthBounds(0, now))
  assert.deepEqual(reconciliationParams({ date_from: '', date_to: '' }, now), {})
  assert.deepEqual(reconciliationParams({ supplier: 'A', status: '已付款', date_from: '', date_to: '2026-11-09' }, now), { vendor_name: 'A', status: '已付款', date_to: '2026-11-09' })
})

test('reconciliation query is independent and preserves unlimited dates and payment status', () => {
  assert.deepEqual(normalizePlatingQuery('reconciliation', { supplier: 'A', status: '已付款', date_from: '', date_to: '', page: '2', archive: 'all', q: 'part', tab: 'in' }), { supplier: 'A', status: '已付款', date_from: '', date_to: '', page: '2' })
  assert.deepEqual(normalizePlatingQuery('reconciliation', { status: 'pending', date_from: '2026-02-30', date_to: ['2026-11-09'], page: '-1' }), {})
  const values = new Map()
  const memory = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) }
  const storage = { preferences: memory, session: memory }
  rememberPlatingLocation({ path: '/plating-reconciliation', query: { date_from: '', date_to: '', status: '未付款' } }, storage)
  assert.deepEqual(getPlatingLocation(undefined, storage), { path: '/plating-reconciliation', query: { status: '未付款', date_from: '', date_to: '' } })
})

test('override accepts blank, zero and seven decimal places without float conversion', () => {
  for (const value of ['', '0', '0.0000001', '99999999999.9999999']) assert.equal(validOverride(value), true, value)
  for (const value of ['-1', 'NaN', 'Infinity', '1e3', '1.00000001', '100000000000', '=1+1']) assert.equal(validOverride(value), false, value)
})
