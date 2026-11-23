import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import { reactive, ref, computed, nextTick, effectScope } from 'vue'
import { normalizeOutputQuery } from '../src/utils/handcraftOutput.js'

const url = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
const runtime = url(`export { ref, computed, watch } from ${JSON.stringify(import.meta.resolve('vue'))};
  export const onMounted = fn => globalThis.__outputTest.mounted.push(fn);
  export const onBeforeUnmount = fn => globalThis.__outputTest.cleanup.push(fn);`)
async function compile(file) {
  const source = readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8')
  const script = compileScript(parse(source).descriptor, { id: 'output-test' }).content
    .replace(/from ['"]vue['"]/g, `from ${JSON.stringify(runtime)}`)
    .replace(/import \{ ([^}]+) \} from ['"]naive-ui['"]/g, (_, names) => `const ${names.split(',').map(name => `${name.trim()} = {}`).join(', ')};`)
    .replace(/import \{ useRouter \} from ['"]vue-router['"]/g, 'const useRouter = () => globalThis.__outputTest.router;')
    .replace(/import \{ useHandcraftPageQuery \} from ['"]@\/composables\/useHandcraftPageQuery['"]/g, 'const useHandcraftPageQuery = () => globalThis.__outputTest.navigation;')
    .replace(/import \{ rememberHandcraftLocation \} from ['"]@\/utils\/handcraftNavigation['"]/g, 'const rememberHandcraftLocation = value => globalThis.__outputTest.remembered.push(value);')
    .replace(/from ['"]@\/utils\/handcraftOutput['"]/g, `from ${JSON.stringify(new URL('../src/utils/handcraftOutput.js', import.meta.url).href)}`)
    .replace(/import \{ ([^}]+) \} from ['"]@\/api\/handcraftOutput['"]/g, (_, names) => `const ${names.split(',').map(name => `${name.trim()} = (...args) => globalThis.__outputTest.api.${name.trim()}(...args)`).join(', ')};`)
    .replace(/import (\w+) from ['"][^'"]+\.vue['"]/g, 'const $1 = {};')
  return (await import(url(script))).default
}
const Overview = await compile('views/handcraft/HandcraftOutput.vue')
const Sources = await compile('components/HandcraftOutputSources.vue')
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const reply = data => Promise.resolve({ data })
const empty = { groups: [], total: 0, totals: [], source_count: 0, supplier_count: 0, output_count: 0, reference_date_count: 0 }
const tick = async () => { await nextTick(); await Promise.resolve(); await nextTick() }
function setup(component = Overview, props = {}, overrides = {}) {
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} }
  const scope = effectScope(), active = ref(true), route = reactive({ path: '/handcraft-output', fullPath: '/handcraft-output', query: {} })
  const query = computed(() => normalizeOutputQuery(route.query)), remembered = [], pushes = []
  const state = { mounted: [], cleanup: [], remembered, router: { push: value => pushes.push(value) }, api: {
    getHandcraftOutputOverview: () => reply(empty), getHandcraftOutputOptions: () => reply({ outputs: [], suppliers: [], has_more: false }),
    getHandcraftOutputSources: () => reply({ items: [], total: 0 }), getHandcraftOutputReceipts: () => reply({ items: [], total: 0 }), ...overrides,
  }, navigation: { route, active, query, updateQuery: async (patch, resetPage = true) => {
    const next = { ...query.value, ...patch }; if (resetPage) delete next.page
    route.query = normalizeOutputQuery(next); route.fullPath = '/handcraft-output?' + JSON.stringify(route.query)
  } } }
  globalThis.__outputTest = state
  const values = reactive(props)
  const ctx = scope.run(() => component.setup(values, { expose() {}, emit() {} }))
  const cleanup = () => { state.cleanup.forEach(fn => fn()); scope.stop() }
  return { ctx, state, active, route, props: values, pushes, cleanup }
}
test('old overview responses and errors cannot replace the current filters; failure never shows old totals', async () => {
  const requests = []
  const h = setup(Overview, {}, { getHandcraftOutputOverview: () => { const pending = deferred(); requests.push(pending); return pending.promise } })
  const first = h.ctx.load(), second = h.ctx.load()
  requests[1].resolve({ data: { ...empty, total: 2 } }); await second
  requests[0].reject(Error('old failure')); await first
  assert.equal(h.ctx.data.value.total, 2); assert.equal(h.ctx.error.value, '')
  const third = h.ctx.load()
  assert.equal(h.ctx.data.value, null)
  requests[2].reject(Error('network failure')); await third
  assert.equal(h.ctx.data.value, null); assert.match(h.ctx.error.value, /加载产出/)
  h.cleanup()
})
test('date/view/filter updates reset only the overview page and invalid custom ranges send no query', async () => {
  let requests = 0
  const h = setup(Overview, {}, { getHandcraftOutputOverview: () => { requests++; return reply(empty) } })
  h.route.query = { suppliers: ['A'], outputs: ['part:X'], page: '4' }
  h.ctx.setFilter('view', 'product'); await tick()
  assert.equal(h.route.query.page, undefined); assert.deepEqual(h.route.query.suppliers, ['A']); assert.deepEqual(h.route.query.outputs, ['part:X'])
  h.route.query = { date_preset: 'custom', date_from: '2026-11-22', date_to: '2026-11-01' }
  const before = requests; await h.ctx.load()
  assert.equal(requests, before); assert.equal(h.ctx.data.value, null)
  h.ctx.setSelection('suppliers', null); await tick()
  assert.equal(h.route.query.suppliers, undefined)
  h.ctx.setDateRange(null); await tick()
  assert.equal(h.route.query.date_preset, undefined)
  assert.equal(h.route.query.date_from, undefined)
  assert.equal(h.route.query.date_to, undefined)
  h.cleanup()
})
test('out-of-range group page corrects itself, and detail navigation has a safe explicit return', async () => {
  const h = setup()
  h.route.query = { suppliers: ['A'], page: '999' }
  await h.ctx.load(); await tick()
  assert.equal(h.route.query.page, undefined)
  await h.ctx.openPage('/handcraft/HC1', { highlight: '9', item_type: 'jewelry' })
  assert.equal(h.pushes[0].query.from, 'handcraft-output'); assert.equal(h.state.remembered[0].path, '/handcraft-output')
  h.cleanup()
})
test('unmounted or inactive overview cannot accept late data', async () => {
  const pending = deferred(), h = setup(Overview, {}, { getHandcraftOutputOverview: () => pending.promise })
  const request = h.ctx.load(); h.active.value = false; h.cleanup()
  pending.resolve({ data: { ...empty, total: 100 } }); await request
  assert.equal(h.ctx.data.value, null)
})
test('option failures preserve selected identities and newer search options win', async () => {
  const requests = [], h = setup(Overview, {}, { getHandcraftOutputOptions: () => { const pending = deferred(); requests.push(pending); return pending.promise } })
  h.route.query = { outputs: ['part:X'] }; await tick()
  const old = h.ctx.loadOptions(), latest = h.ctx.loadOptions()
  requests.at(-1).resolve({ data: { suppliers: ['B'], outputs: [{ output_key: 'part:Y', output_name: 'Y', output_id: 'Y', output_type: 'part' }], has_more: false } }); await latest
  requests.at(-2).reject(Error('old')); await old
  assert.deepEqual(h.ctx.suppliers.value, ['B']); assert.equal(h.ctx.optionsError.value, '')
  assert.ok(h.ctx.productOptions.value.some(option => option.value === 'part:X'))
  requests[0].resolve({ data: { suppliers: ['old'], outputs: [], has_more: false } }); await tick()
  assert.deepEqual(h.ctx.suppliers.value, ['B']); h.cleanup()
})
test('source and receipt pagination ignore old requests after filters change or unmount', async () => {
  const requests = [], receipts = []
  const item = { supplier_name: 'A', output_key: 'jewelry:X', unit: '对', source_count: 30 }
  const h = setup(Sources, { item, filters: { archive: 'active' } }, {
    getHandcraftOutputSources: params => { const pending = deferred(); requests.push({ ...pending, params }); return pending.promise },
    getHandcraftOutputReceipts: (id, params) => { const pending = deferred(); receipts.push({ ...pending, params }); return pending.promise },
  })
  const row = { handcraft_jewelry_item_id: 9, receipt_count: 30 }
  requests[0].resolve({ data: { items: [row], total: 30 } }); await tick()
  h.ctx.toggleBatches(row); assert.equal(receipts[0].params.skip, 0)
  h.ctx.setBatchPage(row, 2); assert.equal(receipts[1].params.skip, 20)
  receipts[1].resolve({ data: { items: [{ receipt_item_id: 21 }], total: 30 } }); await tick()
  receipts[0].resolve({ data: { items: [{ receipt_item_id: 1 }], total: 30 } }); await tick()
  assert.equal(h.ctx.batches.value[9].items[0].receipt_item_id, 21)
  h.ctx.setPage(2); assert.equal(requests[1].params.skip, 20)
  h.props.filters = { archive: 'archived' }; await tick()
  assert.equal(requests[2].params.skip, 0)
  requests[2].resolve({ data: { items: [], total: 0 } }); await tick()
  requests[1].resolve({ data: { items: [row], total: 30 } }); await tick()
  assert.deepEqual(h.ctx.rows.value, [])
  assert.deepEqual(h.ctx.batches.value, {})
  h.cleanup()
})
