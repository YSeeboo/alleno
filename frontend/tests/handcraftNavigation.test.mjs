import test from 'node:test'
import assert from 'node:assert/strict'
import { createMemoryHistory, createRouter } from 'vue-router'
import {
  HANDCRAFT_TABS, getHandcraftTab, isHandcraftRoute, normalizeHandcraftQuery,
  getHandcraftLocation, rememberHandcraftLocation, restoreHandcraftListQuery,
  getHandcraftSummaryReturn, rememberHandcraftSummaryReturn,
} from '../src/utils/handcraftNavigation.js'
import { getPlatingLocation, rememberPlatingLocation } from '../src/utils/platingNavigation.js'
import { createHandcraftRoutes } from '../src/router/handcraft.js'

function memoryStorage() {
  const values = new Map()
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
}
function storage() { return { preferences: memoryStorage(), session: memoryStorage() } }

test('summary and output overview precede the two legacy list URLs', () => {
  assert.deepEqual(HANDCRAFT_TABS.map((tab) => tab.path), ['/handcraft-summary', '/handcraft-output', '/handcraft', '/handcraft-receipts'])
  assert.equal(getHandcraftTab('/handcraft-summary').key, 'summary')
  assert.equal(getHandcraftTab('/handcraft/').key, 'dispatch')
  assert.equal(getHandcraftTab('/handcraft-receipts').key, 'receipt')
  assert.equal(getHandcraftTab('/handcraft/create'), null)
  assert.equal(getHandcraftTab('/handcraft-receipts/HR-1'), null)
})

test('all handcraft lists, forms and details share the sidebar selection', () => {
  for (const path of ['/handcraft-management', '/handcraft-management/', '/handcraft', '/handcraft-receipts', '/handcraft/create', '/handcraft/HC-1', '/handcraft-receipts/create', '/handcraft-receipts/HR-1']) {
    assert.equal(isHandcraftRoute(path), true, path)
  }
  for (const path of ['/handcraft-other', '/handcraft-management-extra', '/plating', '/orders']) {
    assert.equal(isHandcraftRoute(path), false, path)
  }
})

test('only existing per-tab list filters are accepted, using supplier_name', () => {
  const query = { supplier_name: '甲手工厂', archive: 'archived', status: 'processing', receipt_code: 'ABCDE', prefill: 'payload', id: 'HC-1', supplier: 'wrong' }
  assert.deepEqual(normalizeHandcraftQuery('dispatch', query), { supplier_name: '甲手工厂', archive: 'archived', status: 'processing' })
  assert.deepEqual(normalizeHandcraftQuery('receipt', query), { supplier_name: '甲手工厂' })
  assert.deepEqual(normalizeHandcraftQuery('dispatch', { archive: 'all', status: 'completed' }), { archive: 'all', status: 'completed' })
})

test('invalid, repeated, default and cleared filters are omitted', () => {
  for (const query of [null, { supplier_name: ['A', 'B'], archive: ['all'], status: 'paid' }, { archive: 'active', status: null, supplier_name: '' }, { archive: 'bad', status: ['pending'] }]) {
    assert.deepEqual(normalizeHandcraftQuery('dispatch', query), {})
  }
  assert.deepEqual(normalizeHandcraftQuery('unknown', { supplier_name: 'A' }), {})
})

test('first entry defaults to summary and subsequent entries remember the last tab, not detail IDs', () => {
  const stores = storage()
  assert.deepEqual(getHandcraftLocation(undefined, stores), { path: '/handcraft-summary', query: {} })
  rememberHandcraftLocation({ path: '/handcraft-receipts', query: { supplier_name: 'B' } }, stores)
  for (const path of ['/handcraft/create', '/handcraft/HC-1', '/handcraft-receipts/create', '/handcraft-receipts/HR-1']) {
    rememberHandcraftLocation({ path, query: { id: 'secret', prefill: 'payload' } }, stores)
  }
  assert.deepEqual(getHandcraftLocation(undefined, stores), { path: '/handcraft-receipts', query: { supplier_name: 'B' } })
})

test('each handcraft tab remembers its own filters; clearing one preserves the other', () => {
  const stores = storage()
  rememberHandcraftLocation({ path: '/handcraft', query: { supplier_name: 'A', archive: 'all', status: 'pending' } }, stores)
  rememberHandcraftLocation({ path: '/handcraft-receipts', query: { supplier_name: 'B' } }, stores)
  assert.deepEqual(getHandcraftLocation('dispatch', stores).query, { supplier_name: 'A', archive: 'all', status: 'pending' })
  assert.deepEqual(getHandcraftLocation('receipt', stores).query, { supplier_name: 'B' })
  rememberHandcraftLocation({ path: '/handcraft', query: {} }, stores)
  assert.deepEqual(getHandcraftLocation('dispatch', stores).query, {})
  assert.deepEqual(getHandcraftLocation('receipt', stores).query, { supplier_name: 'B' })
})

test('blocked and malformed storage never break handcraft navigation', () => {
  const blocked = { getItem() { throw Error('blocked') }, setItem() { throw Error('blocked') } }
  const stores = { preferences: blocked, session: blocked }
  assert.deepEqual(getHandcraftLocation(undefined, stores), { path: '/handcraft-summary', query: {} })
  assert.doesNotThrow(() => rememberHandcraftLocation({ path: '/handcraft', query: {} }, stores))
  for (const value of ['{bad', 'null', '[]', '"string"', '{"dispatch":null}', '{"dispatch":{"supplier_name":["A"],"archive":"bad"}}']) {
    const malformed = { preferences: { getItem: () => 'unknown-tab' }, session: { getItem: () => value } }
    assert.deepEqual(getHandcraftLocation(undefined, malformed), { path: '/handcraft-summary', query: {} })
  }
})

test('old list links restore filters, explicit supplier links win and same-list clearing stays clear', () => {
  const stores = storage()
  rememberHandcraftLocation({ path: '/handcraft-receipts', query: { supplier_name: 'A' } }, stores)
  assert.deepEqual(restoreHandcraftListQuery({ path: '/handcraft-receipts', query: {}, hash: '#list' }, { path: '/handcraft-receipts/HR-1' }, stores), {
    path: '/handcraft-receipts', query: { supplier_name: 'A' }, hash: '#list', replace: true,
  })
  assert.equal(restoreHandcraftListQuery({ path: '/handcraft-receipts', query: { supplier_name: 'B' } }, { path: '/handcraft/HC-1' }, stores), null)
  assert.equal(restoreHandcraftListQuery({ path: '/handcraft-receipts', query: {} }, { path: '/handcraft-receipts' }, stores), null)
  assert.equal(restoreHandcraftListQuery({ path: '/handcraft/create', query: {} }, { path: '/handcraft' }, stores), null)
})

test('handcraft and plating tab memories are isolated even in the same storage', () => {
  const stores = storage()
  rememberPlatingLocation({ path: '/plating-summary', query: { tab: 'in', supplier: '电镀厂', q: '桃心', page: '3' } }, stores)
  rememberHandcraftLocation({ path: '/handcraft-receipts', query: { supplier_name: '手工厂' } }, stores)
  assert.deepEqual(getPlatingLocation(undefined, stores), { path: '/plating-summary', query: { supplier: '电镀厂', tab: 'in', q: '桃心', page: '3' } })
  assert.deepEqual(getHandcraftLocation(undefined, stores), { path: '/handcraft-receipts', query: { supplier_name: '手工厂' } })
})

function testRouter(stores = storage()) {
  const component = { render: () => null }
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component, children: createHandcraftRoutes(() => component, () => getHandcraftLocation(undefined, stores)) },
    { path: '/other', component },
  ] })
  router.beforeEach((to, from) => restoreHandcraftListQuery(to, from, stores) || true)
  router.afterEach((to, from, failure) => { if (!failure) rememberHandcraftLocation(to, stores) })
  return router
}

test('real route records share the shell only for lists, inherit permissions and keep standalone forms/details', () => {
  const router = testRouter()
  for (const path of ['/handcraft-summary', '/handcraft-output', '/handcraft', '/handcraft-receipts']) {
    const route = router.resolve(path)
    assert.equal(route.meta.perm, 'handcraft')
    assert.equal(route.matched.length, 3)
    assert.equal(route.matched[1].path, '/handcraft-management')
    assert.deepEqual(route.matched[2].props.default, { embedded: true })
  }
  for (const path of ['/handcraft/create', '/handcraft/HC-1', '/handcraft-receipts/create', '/handcraft-receipts/HR-1']) {
    const route = router.resolve(path)
    assert.equal(route.meta.perm, 'handcraft')
    assert.equal(route.matched.length, 2, path)
    assert.equal(route.matched.at(-1).path.endsWith('/create'), path.endsWith('/create'))
  }
})

test('real router entry, per-tab restore, explicit legacy supplier link and clearing compose correctly', async () => {
  const router = testRouter()
  await router.push('/handcraft-management')
  assert.equal(router.currentRoute.value.path, '/handcraft-summary')
  await router.replace('/handcraft?archive=all&status=processing&supplier_name=A')
  await router.push('/handcraft-receipts?supplier_name=B')
  await router.push('/handcraft/HC-1')
  await router.push('/handcraft-receipts?supplier_name=C')
  assert.deepEqual({ ...router.currentRoute.value.query }, { supplier_name: 'C' })
  await router.push('/handcraft')
  assert.deepEqual({ ...router.currentRoute.value.query }, { supplier_name: 'A', archive: 'all', status: 'processing' })
  await router.replace('/handcraft')
  assert.deepEqual({ ...router.currentRoute.value.query }, {})
  await router.push('/handcraft-receipts/create')
  await router.push('/handcraft-receipts')
  assert.deepEqual({ ...router.currentRoute.value.query }, { supplier_name: 'C' })
  await router.push('/other')
  await router.push('/handcraft-management')
  assert.equal(router.currentRoute.value.path, '/handcraft-receipts')
  assert.deepEqual({ ...router.currentRoute.value.query }, { supplier_name: 'C' })
})

test('summary normalizes separate direction filters and pages, rejects generic keyword and unsafe returns', () => {
  assert.deepEqual(normalizeHandcraftQuery('summary', {
    tab: 'in', supplier_name: '  A ', in_supplier_name: 'B', part_id: 'P1', in_output_id: 'J1',
    date_from: '2026-02-30', date_to: '2026-11-17', in_date_from: '2026-11-01',
    page: '4', in_page: '2', sort: 'days', archive: 'all', in_archive: 'archived',
    q: 'removed', keyword: 'removed', from: 'https://evil.test', return: '//evil.test', in_order_id: ['A'],
  }), { tab: 'in', supplier_name: 'A', part_id: 'P1', archive: 'all', date_to: '2026-11-17', page: '4',
    in_supplier_name: 'B', in_output_id: 'J1', in_archive: 'archived', in_date_from: '2026-11-01', in_page: '2', sort: 'days' })
})

test('summary return is explicit, safe and preserves both directions without altering legacy list filters', () => {
  const stores = storage()
  rememberHandcraftLocation({ path: '/handcraft', query: { status: 'pending' } }, stores)
  const query = { tab: 'in', part_id: 'P1', page: '3', in_output_id: 'J1', in_page: '2' }
  rememberHandcraftSummaryReturn(query, stores)
  assert.equal(getHandcraftSummaryReturn({}, stores), null)
  assert.equal(getHandcraftSummaryReturn({ from: ['handcraft-summary'] }, stores), null)
  assert.deepEqual(getHandcraftSummaryReturn({ from: 'handcraft-summary' }, stores), { path: '/handcraft-summary', query })
  assert.deepEqual(getHandcraftLocation('dispatch', stores).query, { status: 'pending' })
})
