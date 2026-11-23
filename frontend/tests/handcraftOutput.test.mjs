import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createMemoryHistory, createRouter } from 'vue-router'
import { normalizeOutputQuery, outputDateRange, outputFilters, outputDateError, outputItemKey, outputStatus, outputPercent, beijingToday, handcraftOutputLocation } from '../src/utils/handcraftOutput.js'
import { getHandcraftLocation, rememberHandcraftLocation, getHandcraftSummaryReturn, isHandcraftRoute } from '../src/utils/handcraftNavigation.js'
import { createHandcraftRoutes } from '../src/router/handcraft.js'

test('output query supports bounded multi-select typed product identities, not arbitrary return URLs', () => {
  assert.deepEqual(normalizeOutputQuery({ suppliers: ['A', 'B', 'A', null, ''], outputs: ['jewelry:X', 'part:X', 'bad', 'part:'], archive: 'all', progress: 'partial', view: 'product', page: '2', return: '//evil', id: 'hidden' }), {
    suppliers: ['A', 'B'], outputs: ['jewelry:X', 'part:X'], view: 'product', progress: 'partial', archive: 'all', page: '2',
  })
  assert.deepEqual(normalizeOutputQuery({ suppliers: 'A', outputs: 'part:X', page: '0', archive: 'active', view: 'merchant' }), { suppliers: ['A'], outputs: ['part:X'] })
  assert.equal(normalizeOutputQuery({ suppliers: Array.from({ length: 110 }, (_, i) => `A${i}`) }).suppliers.length, 100)
})
test('dates use Beijing calendar boundaries and Monday weeks, including year transitions', () => {
  assert.equal(beijingToday(new Date('2026-11-22T16:01:00Z')), '2026-11-23')
  assert.deepEqual(outputDateRange('week', '2026-11-22'), { date_from: '2026-11-16', date_to: '2026-11-22' })
  assert.deepEqual(outputDateRange('lastMonth', '2026-01-05'), { date_from: '2025-12-01', date_to: '2025-12-31' })
  assert.deepEqual(outputDateRange('month', '2024-02-10'), { date_from: '2024-02-01', date_to: '2024-02-29' })
  assert.deepEqual(outputDateRange('all'), {})
})
test('custom ranges are preserved but incomplete and reversed ranges block requests', () => {
  assert.deepEqual(normalizeOutputQuery({ date_from: '2026-02-30', date_to: '2026-11-17' }), { date_to: '2026-11-17', date_preset: 'custom' })
  assert.ok(outputDateError({ date_preset: 'custom', date_from: '2026-11-17' }))
  assert.ok(outputDateError({ date_preset: 'custom', date_from: '2026-11-18', date_to: '2026-11-17' }))
  assert.equal(outputDateError({ date_preset: 'custom', date_from: '2026-11-17', date_to: '2026-11-17' }), '')
  const filters = outputFilters({ suppliers: ['A', 'B'], outputs: ['part:X'], date_preset: 'lastMonth', archive: 'all', progress: 'settled' }, '2026-11-23')
  assert.deepEqual(filters, { supplier_names: ['A', 'B'], output_keys: ['part:X'], archive: 'all', progress: 'settled', date_from: '2026-10-01', date_to: '2026-10-31' })
  assert.deepEqual(normalizeOutputQuery({ date_preset: 'week', date_from: '2020-01-01' }), { date_preset: 'week' })
})
test('item keys do not merge product types, units or suppliers; settlement is not physical 100%', () => {
  const item = { supplier_name: 'A', output_key: 'jewelry:X', unit: '对', expected_qty: 100, actual_received_qty: 98, loss_total_qty: 2, unreceived_qty: 0 }
  assert.equal(outputStatus(item), 'settled')
  assert.equal(outputPercent(item), 98)
  const keys = [item, { ...item, unit: '只' }, { ...item, output_key: 'part:X' }, { ...item, supplier_name: 'B' }].map(outputItemKey)
  assert.equal(new Set(keys).size, 4)
})
test('output tab and safe explicit detail return preserve filters and page without touching other memories', async () => {
  const values = new Map(), store = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) }
  const storage = { session: store, preferences: store }
  const query = { suppliers: ['A', 'B'], outputs: ['part:X'], view: 'product', page: '3' }
  rememberHandcraftLocation({ path: '/handcraft-summary', query: { in_page: '2' } }, storage)
  rememberHandcraftLocation(handcraftOutputLocation(query), storage)
  assert.deepEqual(getHandcraftSummaryReturn({ from: 'handcraft-output' }, storage), handcraftOutputLocation(query))
  assert.equal(getHandcraftSummaryReturn({ from: ['handcraft-output'] }, storage), null)
  assert.deepEqual(getHandcraftLocation('summary', storage).query, { in_page: '2' })
  assert.ok(isHandcraftRoute('/handcraft-output'))
  const component = { render: () => null }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component, children: createHandcraftRoutes(() => component) }] })
  await router.push(handcraftOutputLocation(query))
  assert.equal(router.currentRoute.value.meta.perm, 'handcraft')
  assert.equal(router.currentRoute.value.matched[1].path, '/handcraft-management')
})
test('production overview never imports demo fixtures; all four API operations are GET-only', () => {
  const read = file => readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8')
  const api = read('api/handcraftOutput.js')
  assert.equal((api.match(/api\.get\(/g) || []).length, 4)
  assert.doesNotMatch(api, /api\.(post|patch|put|delete)\(/)
  assert.doesNotMatch(read('views/handcraft/HandcraftOutput.vue') + read('components/HandcraftOutputSources.vue'), /public\/demos|SOURCES|MERCHANTS|HR-DEMO/)
  for (const file of ['views/suppliers/SupplierList.vue', 'views/parts/PartDetail.vue', 'views/jewelries/JewelryDetail.vue']) {
    assert.match(read(file), /hasPermission\('handcraft'\)/)
    assert.match(read(file), /handcraftOutputLocation/)
  }
})
test('custom select fields do not wrap native labels that synthesize duplicate input clicks', () => {
  const source = readFileSync(new URL('../src/views/handcraft/HandcraftOutput.vue', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /<label>/)
  assert.equal((source.match(/class="ho-filter-field"/g) || []).length, 4)
  for (const label of ['手工商家', '产出商品', '回收进度', '单据范围']) assert.ok(source.includes(`aria-label="${label}"`))
})
