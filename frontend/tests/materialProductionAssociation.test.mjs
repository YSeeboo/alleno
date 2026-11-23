import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { productionDemandLines, sourceQuantities, allocationPayload } from '../src/utils/productionAllocation.js'

const source = readFileSync(new URL('../src/components/fulfillment/ProductionOrderLinkDialog.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const script = compileScript(descriptor, { id: 'material-production' })
const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const Dialog = (await import(moduleUrl(script.content
  .replace(/from ['"]vue['"]/g, `from ${JSON.stringify(moduleUrl(`
    export { ref, computed } from ${JSON.stringify(import.meta.resolve('vue'))};
    export const onMounted = fn => globalThis.__material.mounted.push(fn);
    export const onBeforeUnmount = fn => globalThis.__material.unmounted.push(fn);
  `))}`)
  .replace(/import \{ ([^}]+) \} from ['"]vue-router['"]/g, 'const onBeforeRouteLeave = fn => globalThis.__material.guards.push(fn), onBeforeRouteUpdate = onBeforeRouteLeave')
  .replace(/import \{ ([^}]+) \} from ['"]naive-ui['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = {}`).join(', ')}`)
  .replace(/import \{ ([^}]+) \} from ['"]@\/api\/[^'"]+['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = (...args) => globalThis.__material.api[${JSON.stringify(n.trim())}](...args)`).join(', ')}`)
  .replace(/from ['"]@\/utils\/productionAllocation['"]/, `from ${JSON.stringify(new URL('../src/utils/productionAllocation.js', import.meta.url).href)}`)
))).default

const demand = (id = 10, qty = 20) => ({ id: `material:${id}:A`, order_item_id: id, material_part_id: 'A',
  demand_revision: 'd'.repeat(64), product_type: 'part', product_id: 'A', quantity: qty, allocated: 0 })
const output = (id = 501, overrides = {}) => ({ source_type: 'handcraft', source_item_id: id,
  production_order_id: 'HC-A', product_type: 'part', product_id: 'A', planned: 40,
  public_unallocated: 40, allocations: [], revision: 'r'.repeat(64), status: 'processing', ...overrides })
const data = (overrides = {}) => ({ order_id: 'OR-0015', editable: true, lines: [], materials: [demand()], sources: [output()], ...overrides })
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
function setup(response = data(), api = {}) {
  const calls = [], emitted = []
  const state = globalThis.__material = { mounted: [], unmounted: [], guards: [], api: {
    listOrders: async () => ({ data: [] }), getOrderProduction: async () => ({ data: response }),
    replaceOrderProductionBatch: async (...args) => { calls.push(args) }, ...api,
  } }
  const ctx = Dialog.setup({ productionOrderId: 'HC-A' }, { expose() {}, emit: (...args) => emitted.push(args) })
  ctx.orderId.value = 'OR-0015'
  return { ctx, calls, emitted, state }
}

test('real batch dialog compiles and handcraft integration no longer sends issued-input IDs', () => {
  const template = compileTemplate({ source: descriptor.template.content, filename: 'ProductionOrderLinkDialog.vue', id: 'material-production', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
  const handcraft = readFileSync(new URL('../src/views/handcraft/HandcraftDetail.vue', import.meta.url), 'utf8')
  assert.match(handcraft, /<ProductionOrderLinkDialog/)
  assert.doesNotMatch(handcraft, /handcraft_part_item_ids|doBatchLink/)
  assert.match(handcraft, /loadJewelries\(\), loadBreakdown\(\), loadJewelryItemOrderLinks\(\)/)
})

test('material identities preserve parent order lines and do not overwrite direct-product quantities', () => {
  const direct = { id: 10, product_type: 'part', product_id: 'A', quantity: 5, allocated: 2 }
  const lines = productionDemandLines({ lines: [direct], materials: [demand(10), demand(11)] })
  const s = output(501, { allocations: [{ order_item_id: 10, quantity: 2 },
    { order_item_id: 10, material_part_id: 'A', quantity: 7 }] })
  const quantities = sourceQuantities(lines, s)
  assert.deepEqual(quantities, { 10: 2, 'material:10:A': 7, 'material:11:A': 0 })
  const rows = allocationPayload(lines, s, quantities).allocations
  assert.deepEqual(rows[0], { order_item_id: 10, quantity: 2 })
  assert.deepEqual(rows[1], { order_item_id: 10, quantity: 7, material_part_id: 'A', demand_revision: 'd'.repeat(64) })
})

test('preview matches actual outputs and shares one demand ledger across outputs without writing', async () => {
  const { ctx, calls } = setup(data({ sources: [output(501, { public_unallocated: 12 }), output(502),
    output(503, { production_order_id: 'HC-B' }), output(504, { status: 'completed' }),
    output(505, { archived: true }), output(506, { product_id: 'raw' }), output(507, { source_type: 'plating' })] }))
  await ctx.load()
  assert.deepEqual(ctx.sources.value.map(row => row.source_item_id), [501, 502])
  assert.deepEqual(ctx.quantities.value, { 501: { 'material:10:A': 12 }, 502: { 'material:10:A': 8 } })
  assert.deepEqual(calls, [])
  await ctx.save()
  assert.deepEqual(calls[0][1].map(row => [row.source_item_id, row.allocations[0].quantity]), [[501, 12], [502, 8]])
  assert.equal(calls[0][1][0].allocations[0].order_item_id, 10)
})

test('conflicted sources do not consume suggested demand or silently clear their old shares', async () => {
  const { ctx, calls } = setup(data({ sources: [output(501, { legacy_claim: true }),
    output(502, { unit_mismatch: true }), output(503)] }))
  await ctx.load()
  assert.equal(ctx.quantities.value[501]['material:10:A'], 0)
  assert.equal(ctx.quantities.value[502]['material:10:A'], 0)
  assert.equal(ctx.quantities.value[503]['material:10:A'], 20)
  await ctx.save()
  assert.deepEqual(calls[0][1].map(row => row.source_item_id), [503])
})

test('existing mixed-purpose shares are preserved without auto-expanding any demand', async () => {
  const direct = { id: 11, product_type: 'part', product_id: 'A', quantity: 5, allocated: 3 }
  const { ctx, calls } = setup(data({ lines: [direct], materials: [{ ...demand(), allocated: 7 }],
    sources: [output(501, { allocations: [{ order_id: 'OR-0015', order_item_id: 10, material_part_id: 'A', quantity: 7 },
      { order_id: 'OR-0015', order_item_id: 11, quantity: 3 }, { order_id: 'OR-B', order_item_id: 99, quantity: 4 }] })] }))
  await ctx.load(); await ctx.save()
  assert.deepEqual(calls[0][1][0].allocations.map(row => row.quantity), [3, 7])
  assert.equal(ctx.data.value.sources[0].allocations[2].quantity, 4)
})

test('zero unlinks existing material shares, including obsolete demand or changed units', async () => {
  const { ctx, calls } = setup(data({ materials: [{ ...demand(10, 0), allocated: 7, demand_changed: true }],
    sources: [output(501, { unit_mismatch: true, allocations: [{ order_id: 'OR-0015', order_item_id: 10, material_part_id: 'A', quantity: 7 }] })] }))
  await ctx.load()
  assert.equal(ctx.quantities.value[501]['material:10:A'], 7)
  ctx.quantities.value[501]['material:10:A'] = 0
  await ctx.save()
  assert.equal(calls[0][1][0].allocations[0].quantity, 0)
})

test('invalid values and failed saves retain drafts and can be corrected or retried without reloading', async () => {
  const { ctx, calls, state } = setup()
  await ctx.load()
  for (const invalid of [0, null, -1, 1.5, NaN]) {
    ctx.quantities.value[501]['material:10:A'] = invalid
    await ctx.save()
    assert.ok(ctx.saveError.value)
    assert.deepEqual(calls, [])
  }
  ctx.quantities.value[501]['material:10:A'] = 8
  state.api.replaceOrderProductionBatch = async () => { throw { response: { data: { detail: '容量已变化，请刷新核对' } } } }
  await ctx.save()
  assert.equal(ctx.saveError.value, '容量已变化，请刷新核对')
  assert.equal(ctx.quantities.value[501]['material:10:A'], 8)
  state.api.replaceOrderProductionBatch = async (...args) => calls.push(args)
  await ctx.save()
  assert.equal(ctx.saveError.value, '')
  assert.equal(calls.length, 1)
})

test('load failure blocks confirmation, retry restores data and stale responses cannot replace a new order', async () => {
  const first = deferred(), second = deferred()
  const { ctx, calls, state } = setup(undefined, { getOrderProduction: () => first.promise })
  const old = ctx.load()
  ctx.orderId.value = 'OR-B'
  state.api.getOrderProduction = () => second.promise
  const current = ctx.load()
  second.resolve({ data: data({ order_id: 'OR-B' }) }); await current
  first.reject(new Error('old failure')); await old
  assert.equal(ctx.data.value.order_id, 'OR-B')
  assert.equal(ctx.loadError.value, '')
  state.api.getOrderProduction = async () => { throw new Error('offline') }
  await ctx.load(); await ctx.save()
  assert.ok(ctx.loadError.value)
  assert.equal(ctx.data.value, null)
  assert.deepEqual(calls, [])
  state.api.getOrderProduction = async () => ({ data: data() })
  await ctx.load()
  assert.equal(ctx.loadError.value, '')
})

test('saving freezes reload, navigation and duplicate submission until confirmation resolves', async () => {
  const done = deferred()
  const { ctx, calls, emitted, state } = setup(undefined, { replaceOrderProductionBatch: (...args) => { calls.push(args); return done.promise } })
  await ctx.load()
  const saving = ctx.save()
  assert.equal(ctx.saving.value, true)
  assert.ok(state.guards.every(guard => guard() === false))
  await ctx.load(); await ctx.save()
  assert.equal(calls.length, 1)
  assert.equal(ctx.quantities.value[501]['material:10:A'], 20)
  done.resolve(); await saving
  assert.equal(ctx.saving.value, false)
  assert.ok(state.guards.every(guard => guard() === true))
  assert.deepEqual(emitted, [['saved']])
  assert.match(source, /:mask-closable="!saving" :closable="!saving" :close-on-esc="!saving"/)
})

test('closed orders cannot write and clearing order selection invalidates pending loads', async () => {
  const { ctx, calls, state } = setup(data({ editable: false }))
  await ctx.load(); await ctx.save()
  assert.deepEqual(calls, [])
  const late = deferred()
  state.api.getOrderProduction = () => late.promise
  const pending = ctx.load()
  ctx.orderId.value = null; await ctx.load()
  late.resolve({ data: data() }); await pending
  assert.equal(ctx.data.value, null)
  assert.deepEqual(ctx.quantities.value, {})
})

test('plating BOM quantities support four decimals while handcraft and final products remain integers', () => {
  const lines = [demand(10, 1.23456)]
  const plated = output(501, { source_type: 'plating' })
  assert.equal(sourceQuantities(lines, plated, true)['material:10:A'], 1.2345)
  assert.equal(allocationPayload(lines, plated, { 'material:10:A': 1.2345 }).allocations[0].quantity, 1.2345)
  assert.throws(() => allocationPayload(lines, plated, { 'material:10:A': 1.23456 }))
  assert.throws(() => allocationPayload(lines, output(), { 'material:10:A': 1.5 }))
  assert.equal(sourceQuantities(lines, output(), true)['material:10:A'], 1)
})
