import test from 'node:test'
import assert from 'node:assert/strict'
import { createMemoryHistory, createRouter } from 'vue-router'
import {
  PLATING_TABS, getPlatingTab, isPlatingRoute, normalizePlatingQuery,
  getPlatingLocation, rememberPlatingLocation, restorePlatingListQuery,
  rememberPlatingSummaryReturn, getPlatingCreateReturnLocation,
} from '../src/utils/platingNavigation.js'
import { createPlatingRoutes } from '../src/router/plating.js'

function memoryStorage() {
  const values = new Map()
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
}
function storage() { return { preferences: memoryStorage(), session: memoryStorage() } }

test('four independent tabs keep the existing URLs', () => {
  assert.deepEqual(PLATING_TABS.map((tab) => tab.path), ['/plating-summary', '/plating', '/plating-receipts', '/plating-reconciliation'])
  assert.equal(getPlatingTab('/plating/').key, 'dispatch')
  assert.equal(getPlatingTab('/plating/create'), null)
  assert.equal(getPlatingTab('/plating-receipts/EPR-1'), null)
})

test('one sidebar item remains selected for all plating lists, forms and details', () => {
  for (const path of ['/plating-management', '/plating-management/', '/plating', '/plating-summary', '/plating/create', '/plating/EP-1', '/plating-receipts', '/plating-receipts/create', '/plating-receipts/EPR-1', '/plating-reconciliation']) {
    assert.equal(isPlatingRoute(path), true, path)
  }
  for (const path of ['/handcraft', '/plating-summary-extra', '/plating-other', '/orders']) {
    assert.equal(isPlatingRoute(path), false, path)
  }
})

test('summary preserves its direction, supplier, dates, query, page and archive independently', () => {
  assert.deepEqual(normalizePlatingQuery('summary', {
    tab: 'in', supplier: '华盛电镀厂', archive: 'archived', q: '蝴蝶',
    date_from: '2026-10-01', date_to: '2026-11-09', page: '3', sort: 'days', status: 'pending',
  }), { supplier: '华盛电镀厂', archive: 'archived', tab: 'in', date_from: '2026-10-01', date_to: '2026-11-09', q: '蝴蝶', page: '3' })
  assert.deepEqual(normalizePlatingQuery('summary', { sort: 'days' }), { sort: 'days' })
})

test('dispatch and receipt queries never inherit summary or each other’s fields', () => {
  const query = { tab: 'in', supplier: 'A', status: 'pending', archive: 'all', q: 'part', page: '2', date_from: '2026-11-01', date_to: '2026-11-09' }
  assert.deepEqual(normalizePlatingQuery('dispatch', query), { supplier: 'A', archive: 'all', status: 'pending' })
  assert.deepEqual(normalizePlatingQuery('receipt', query), { supplier: 'A' })
})

test('invalid dates, repeated parameters, states, pages and foreign queries are rejected', () => {
  assert.deepEqual(normalizePlatingQuery('summary', { supplier: ['A', 'B'], archive: 'invalid', q: ['part'], tab: 'bad', page: '-1', date_from: '2026-02-30', date_to: '2026-03-01', next: 'https://example.com' }), {})
  for (const page of ['2oops', '1.5', 'Infinity', '9007199254740992', ['2'], ['2', '3']]) {
    assert.deepEqual(normalizePlatingQuery('summary', { page }), {})
  }
  assert.deepEqual(normalizePlatingQuery('summary', { date_from: '2026-11-10', date_to: '2026-11-01' }), {})
  assert.deepEqual(normalizePlatingQuery('dispatch', { status: 'unpaid' }), {})
  assert.deepEqual(normalizePlatingQuery('unknown', { supplier: 'A' }), {})
})

test('default values are omitted so clearing filters produces an empty query', () => {
  assert.deepEqual(normalizePlatingQuery('summary', { archive: 'active', tab: 'out', q: '', supplier: null, page: '1' }), {})
  assert.deepEqual(normalizePlatingQuery('dispatch', { archive: 'active', status: null, supplier: null }), {})
})

test('new entry defaults to summary, and remembers the last list, not a detail URL', () => {
  const stores = storage()
  assert.deepEqual(getPlatingLocation(undefined, stores), { path: '/plating-summary', query: {} })
  rememberPlatingLocation({ path: '/plating-receipts', query: { supplier: 'A' } }, stores)
  rememberPlatingLocation({ path: '/plating/EP-1', query: { highlight: '7' } }, stores)
  assert.deepEqual(getPlatingLocation(undefined, stores), { path: '/plating-receipts', query: { supplier: 'A' } })
})

test('each tab restores its own filters and clearing one does not erase others', () => {
  const stores = storage()
  rememberPlatingLocation({ path: '/plating-summary', query: { supplier: 'A', tab: 'in', q: '蝴蝶', page: '2' } }, stores)
  rememberPlatingLocation({ path: '/plating', query: { supplier: 'B', status: 'processing' } }, stores)
  rememberPlatingLocation({ path: '/plating-receipts', query: { supplier: 'C' } }, stores)
  assert.deepEqual(getPlatingLocation('summary', stores).query, { supplier: 'A', tab: 'in', q: '蝴蝶', page: '2' })
  assert.deepEqual(getPlatingLocation('dispatch', stores).query, { supplier: 'B', status: 'processing' })
  assert.deepEqual(getPlatingLocation('receipt', stores).query, { supplier: 'C' })
  rememberPlatingLocation({ path: '/plating', query: {} }, stores)
  assert.deepEqual(getPlatingLocation('dispatch', stores).query, {})
  assert.deepEqual(getPlatingLocation('receipt', stores).query, { supplier: 'C' })
})

test('blocked or malformed browser storage does not break navigation', () => {
  const blocked = { getItem() { throw Error('blocked') }, setItem() { throw Error('blocked') } }
  const stores = { preferences: blocked, session: blocked }
  assert.deepEqual(getPlatingLocation(undefined, stores), { path: '/plating-summary', query: {} })
  assert.doesNotThrow(() => rememberPlatingLocation({ path: '/plating', query: {} }, stores))
  const malformed = { preferences: { getItem: () => 'not-a-tab' }, session: { getItem: () => '{invalid' } }
  assert.deepEqual(getPlatingLocation(undefined, malformed), { path: '/plating-summary', query: {} })
})

test('returning from a detail or old link restores filters, but explicit queries take precedence', () => {
  const stores = storage()
  rememberPlatingLocation({ path: '/plating', query: { status: 'pending' } }, stores)
  assert.deepEqual(restorePlatingListQuery({ path: '/plating', query: {}, hash: '' }, { path: '/plating/EP-1' }, stores), {
    path: '/plating', query: { status: 'pending' }, hash: '', replace: true,
  })
  assert.equal(restorePlatingListQuery({ path: '/plating', query: { status: 'completed' } }, { path: '/plating/EP-1' }, stores), null)
  assert.equal(restorePlatingListQuery({ path: '/plating', query: {} }, { path: '/plating' }, stores), null)
})

function testRouter(stores = storage()) {
  const component = { render: () => null }
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component, children: createPlatingRoutes(() => component, () => getPlatingLocation(undefined, stores)) },
    { path: '/other', component },
  ] })
  router.beforeEach((to, from) => restorePlatingListQuery(to, from, stores) || true)
  router.afterEach((to, from, failure) => { if (!failure) rememberPlatingLocation(to, stores) })
  return router
}

test('actual route records wrap only list pages, inherit permissions and preserve old URLs', () => {
  const router = testRouter()
  for (const path of ['/plating-summary', '/plating', '/plating-receipts', '/plating-reconciliation']) {
    const route = router.resolve(path)
    assert.equal(route.meta.perm, 'plating')
    assert.equal(route.matched.length, 3)
    assert.equal(route.matched[1].path, '/plating-management')
    assert.deepEqual(route.matched[2].props.default, { embedded: true })
  }
  for (const path of ['/plating/create', '/plating/EP-1', '/plating-receipts/create', '/plating-receipts/EPR-1']) {
    const route = router.resolve(path)
    assert.equal(route.meta.perm, 'plating')
    assert.equal(route.matched.length, 2, path)
  }
})

test('entry redirect, filter restore and explicit reset work with real Vue Router navigation', async () => {
  const router = testRouter()
  await router.push('/plating-management')
  assert.equal(router.currentRoute.value.path, '/plating-summary')
  await router.replace('/plating-summary?tab=in&q=蝴蝶&page=2')
  await router.push('/plating?status=processing&supplier=A')
  await router.push('/plating/EP-1')
  await router.push('/plating')
  assert.deepEqual({ ...router.currentRoute.value.query }, { supplier: 'A', status: 'processing' })
  await router.replace('/plating')
  assert.deepEqual({ ...router.currentRoute.value.query }, {})
  await router.push('/other')
  await router.push('/plating-management')
  assert.equal(router.currentRoute.value.path, '/plating')
  assert.deepEqual({ ...router.currentRoute.value.query }, {})
  await router.push('/plating-summary')
  assert.deepEqual({ ...router.currentRoute.value.query }, { tab: 'in', q: '蝴蝶', page: '2' })
})

test('summary shortcuts remember all filters and reuse the detail return state', () => {
  const stores = storage()
  const query = { supplier: '甲厂', tab: 'in', archive: 'all', q: '桃心', page: '3', date_from: '2026-11-01', date_to: '2026-11-17', next: 'https://example.com' }
  rememberPlatingSummaryReturn(query, stores)
  const expected = normalizePlatingQuery('summary', query)
  assert.deepEqual(JSON.parse(stores.session.getItem('plating-summary-return')), expected)
  assert.deepEqual(getPlatingCreateReturnLocation({ from: 'summary' }, stores), { path: '/plating-summary', query: expected })
  assert.deepEqual(getPlatingLocation('summary', stores).query, expected)
})

test('ordinary create links do not inherit a stale summary origin', () => {
  const stores = storage()
  rememberPlatingSummaryReturn({ q: '旧搜索', page: '2' }, stores)
  for (const query of [{}, undefined, { from: 'receipt' }, { from: ['summary'] }, { from: 'https://example.com' }]) {
    assert.equal(getPlatingCreateReturnLocation(query, stores), null)
  }
  rememberPlatingSummaryReturn({}, stores)
  assert.deepEqual(getPlatingCreateReturnLocation({ from: 'summary' }, stores), { path: '/plating-summary', query: {} })
  assert.deepEqual(JSON.parse(stores.session.getItem('plating-summary-return')), {})
})

test('summary shortcut return works with missing, malformed or blocked storage', () => {
  const blocked = { getItem() { throw Error('blocked') }, setItem() { throw Error('blocked') } }
  const stores = { preferences: blocked, session: blocked }
  assert.doesNotThrow(() => rememberPlatingSummaryReturn({ page: '2' }, stores))
  assert.deepEqual(getPlatingCreateReturnLocation({ from: 'summary' }, stores), { path: '/plating-summary', query: {} })
  const malformed = { preferences: memoryStorage(), session: { getItem: () => '{broken' } }
  assert.deepEqual(getPlatingCreateReturnLocation({ from: 'summary' }, malformed), { path: '/plating-summary', query: {} })
})

test('both shortcut routes can cancel back to the same summary without disturbing list filters', async () => {
  const stores = storage()
  const router = testRouter(stores)
  await router.push('/plating?status=pending&supplier=B')
  await router.push('/plating-receipts?supplier=C')
  const query = { tab: 'in', supplier: 'A', q: '桃心', page: '3', archive: 'all' }
  await router.push({ path: '/plating-summary', query })
  for (const path of ['/plating/create', '/plating-receipts/create']) {
    rememberPlatingSummaryReturn(router.currentRoute.value.query, stores)
    await router.push({ path, query: { from: 'summary' } })
    assert.equal(router.currentRoute.value.meta.perm, 'plating')
    await router.push(getPlatingCreateReturnLocation(router.currentRoute.value.query, stores))
    assert.equal(router.currentRoute.value.path, '/plating-summary')
    assert.deepEqual({ ...router.currentRoute.value.query }, query)
  }
  assert.deepEqual(getPlatingLocation('dispatch', stores).query, { supplier: 'B', status: 'pending' })
  assert.deepEqual(getPlatingLocation('receipt', stores).query, { supplier: 'C' })
})
