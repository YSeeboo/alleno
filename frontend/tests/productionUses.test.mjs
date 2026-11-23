import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const source = await readFile(new URL('../src/components/ProductionUses.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const vue = moduleUrl(`
  export { ref, computed } from ${JSON.stringify(import.meta.resolve('vue'))};
  export const watch = (source, action, options) => globalThis.__usesTest.watches.push({ source, action, options });
`)
const router = moduleUrl(`
  export const useRoute = () => globalThis.__usesTest.route;
  export const useRouter = () => ({ push: value => globalThis.__usesTest.navigation.push(value) });
`)
const script = compileScript(descriptor, { id: 'production-uses-test' })
const Component = (await import(moduleUrl(script.content
  .replace(/from 'vue'/g, `from ${JSON.stringify(vue)}`)
  .replace(/from 'vue-router'/g, `from ${JSON.stringify(router)}`)
  .replace(/import \{ NButton \} from 'naive-ui'/, 'const NButton = {}')
  .replace(/import \{ getProductionUses \} from '@\/api\/productionAllocation'/,
    'const getProductionUses = (...args) => globalThis.__usesTest.get(...args)')))).default

function setup(get = async () => ({ data: [] }), query = {}) {
  const state = { watches: [], navigation: [], route: { query }, get }
  globalThis.__usesTest = state
  const ctx = Component.setup({ type: 'plating', orderId: 'EP-1' }, { expose() {} })
  return { ctx, state }
}
const output = (id, allocations = [], extra = {}) => ({
  source_item_id: id, product_id: `P-${id}`, product_name: '链条', unit: '米',
  planned: 12, received: 1, loss: 0, allocated: 0, public_unallocated: 12,
  allocations, legacy_claim: false, unit_mismatch: false, risk: false, ...extra,
})
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { resolve, promise } }

test('compact panel template compiles, starts collapsed, keeps refresh outside the toggle and errors visible', () => {
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'ProductionUses.vue', id: 'production-uses-test', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  const { ctx } = setup()
  assert.equal(ctx.expanded.value, false)
  assert.equal(ctx.loaded.value, false)
  assert.match(source, /:aria-expanded="expanded"/)
  assert.match(source, /<\/button>\s*<div class="use-actions">/)
  assert.ok(source.indexOf('v-if="error"') < source.indexOf('v-if="expanded"'))
  assert.doesNotMatch(source, /<n-card|<n-alert/)
  assert.match(source, /\.use-sources \{ max-height: 420px; overflow-y: auto;/)
})

test('summary counts distinct orders and affected output rows, never sums mixed product quantities', async () => {
  const data = [
    output(1, [{ order_id: 'OR-1', order_item_id: 1 }, { order_id: 'OR-1', order_item_id: 2 }], { risk: true, unit_mismatch: true }),
    output(2, [{ order_id: 'OR-2', order_item_id: 3 }], { unit: '套', legacy_claim: true }),
    output(3),
  ]
  const { ctx } = setup(async () => ({ data }))
  await ctx.load()
  assert.equal(ctx.loaded.value, true)
  assert.equal(ctx.orderCount.value, 2)
  assert.equal(ctx.reviewCount.value, 2)
  assert.deepEqual(ctx.sources.value.map(row => row.unit), ['米', '套', '米'])
  assert.equal(ctx.expanded.value, false)
})

test('refresh preserves expansion; load errors preserve the previous snapshot rather than pretending no orders exist', async () => {
  const { ctx, state } = setup(async () => ({ data: [output(1, [], { legacy_claim: true })] }))
  ctx.expanded.value = true
  await ctx.load()
  assert.equal(ctx.expanded.value, true)
  state.get = async () => { throw Error('offline') }
  await ctx.load()
  assert.match(ctx.error.value, /用途加载失败/)
  assert.equal(ctx.loaded.value, true)
  assert.equal(ctx.sources.value.length, 1)
  assert.equal(ctx.reviewCount.value, 1)
  assert.equal(ctx.loading.value, false)
})

test('changing documents clears the previous summary and expansion, and ignores out-of-order responses', async () => {
  const old = deferred(), latest = deferred()
  const { ctx, state } = setup(() => old.promise)
  const pending = ctx.load()
  ctx.expanded.value = true
  state.get = () => latest.promise
  assert.equal(state.watches[0].options.immediate, true)
  state.watches[0].action()
  assert.equal(ctx.loaded.value, false)
  assert.equal(ctx.expanded.value, false)
  latest.resolve({ data: [output(2)] })
  await Promise.resolve()
  old.resolve({ data: [output(1)] }); await pending
  assert.equal(ctx.sources.value[0].source_item_id, 2)
})

test('order return and allocation links still open the production arrangement page with safe URL encoding', () => {
  const { ctx, state } = setup(undefined, { from_order: 'OR-1' })
  assert.equal(ctx.sourceOrder.value, 'OR-1')
  ctx.openOrder('OR/1')
  assert.deepEqual(state.navigation, ['/orders/OR%2F1/production'])
  assert.match(source, /row\.order_id === sourceOrder/)
  assert.match(source, /row\.customer_code \|\| '未填客户货号'/)
  assert.match(source, /未自动减少计划或分摊实收/)
  assert.match(source, /商品制作与 BOM 配件备料共用产出计划容量/)
  assert.match(source, /row\.material_part_id \? '配件备料' : '商品制作'/)
})
