import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const { descriptor } = parse(readFileSync(new URL('../src/components/fulfillment/OrderHandcraftBatchDialog.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'batch-dialog' })
const Dialog = (await import(moduleUrl(script.content
  .replace(/from ['"]vue['"]/g, `from ${JSON.stringify(moduleUrl(`export { computed, ref } from ${JSON.stringify(import.meta.resolve('vue'))}; export const onMounted = fn => globalThis.__batch.mounted.push(fn), onBeforeUnmount = fn => globalThis.__batch.unmounted.push(fn);`))}`)
  .replace(/import \{ [^}]+ \} from ['"]vue-router['"]/, 'const onBeforeRouteLeave = fn => globalThis.__batch.guards.push(fn), onBeforeRouteUpdate = onBeforeRouteLeave')
  .replace(/import \{ ([^}]+) \} from ['"]naive-ui['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = {}`).join(', ')}`)
  .replace(/import (\w+) from ['"][^'"]+\.vue['"]/g, 'const $1 = {}')
  .replace(/import \{ ([^}]+) \} from ['"]@\/api\/[^'"]+['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = (...args) => globalThis.__batch.api[${JSON.stringify(n.trim())}](...args)`).join(', ')}`)
  .replace(/from ['"]@\/utils\/orderProductionCreation['"]/, `from ${JSON.stringify(new URL('../src/utils/orderProductionCreation.js', import.meta.url).href)}`)
))).default

function setup(api = {}, lines = [1, 2].map(id => ({ id, product_type: 'jewelry', product_id: 'same', unit: '条', quantity: 30, allocated: 10 }))) {
  const events = [], calls = [], bomCalls = [], state = { mounted: [], unmounted: [], guards: [], api: {
    listParts: async () => ({ data: [{ id: 'raw', name: '原料', unit: '个' }] }),
    listSuppliers: async () => ({ data: [{ name: '商家' }] }),
    getBom: async id => { bomCalls.push(id); return { data: [{ part_id: 'raw', qty_per_unit: 2 }] } },
    createOrderHandcraftBatch: async (...args) => { calls.push(args); return { data: { production_order_id: 'HC-new', rows: [] } } }, ...api,
  } }
  globalThis.__batch = state
  const ctx = Dialog.setup({ orderId: 'OR-test', lines }, { expose() {}, emit: (...event) => events.push(event) })
  return { ctx, state, events, calls, bomCalls }
}

test('batch dialog deduplicates BOM requests but creates independent material drafts per repeated order line', async () => {
  const { ctx, bomCalls, calls } = setup()
  await ctx.load()
  assert.deepEqual(bomCalls, ['same'])
  assert.equal(ctx.rows.value.length, 2)
  assert.equal(ctx.rows.value[0].materials[0].qty, 40)
  ctx.rows.value[0].materials[0].qty = 17
  assert.equal(ctx.rows.value[1].materials[0].qty, 40)
  ctx.supplier.value = '商家'
  ctx.targetId.value = 'HC-exact'
  await ctx.save()
  assert.equal(calls.length, 1)
  assert.equal(calls[0][1].append_to_order_id, 'HC-exact')
  assert.deepEqual(calls[0][1].parts.map(r => r.qty), [17, 40])
})

test('BOM failures leave an explicit manual-material requirement, never an automatic material-free plan', async () => {
  const { ctx, calls } = setup({ getBom: async () => { throw Error('offline') } })
  await ctx.load(); ctx.supplier.value = '商家'
  assert.equal(ctx.loadError.value, '')
  assert.match(ctx.rows.value[0].bomNote, /读取失败/)
  await ctx.save()
  assert.equal(calls.length, 0)
  assert.match(ctx.error.value, /材料/)
  assert.equal(ctx.blocked.value, false)
})

test('catalog failure blocks submit until explicit retry succeeds', async () => {
  const { ctx, state, calls } = setup({ listParts: async () => { throw Error('offline') } })
  await ctx.load()
  assert.ok(ctx.loadError.value)
  assert.equal(ctx.fieldsLocked.value, true)
  await ctx.save()
  assert.equal(calls.length, 0)
  state.api.listParts = async () => ({ data: [{ id: 'raw', unit: '个' }] })
  await ctx.load()
  assert.equal(ctx.fieldsLocked.value, false)
})

test('uncertain save freezes the exact original request, blocks navigation and retries without another creation', async () => {
  const attempts = []
  const { ctx, state, events } = setup({ createOrderHandcraftBatch: async (id, data) => {
    attempts.push(data)
    if (attempts.length === 1) throw Error('connection lost')
    return { data: { production_order_id: 'HC-original', rows: [] } }
  } })
  await ctx.load(); ctx.supplier.value = '商家'
  await ctx.save()
  assert.equal(ctx.uncertain.value, true)
  assert.equal(ctx.fieldsLocked.value, true)
  assert.ok(state.guards.every(fn => fn() === false))
  ctx.supplier.value = 'programmatic change cannot replace frozen attempt'
  await ctx.save()
  assert.equal(attempts.length, 2)
  assert.equal(attempts[0], attempts[1])
  assert.equal(attempts[1].supplier_name, '商家')
  assert.equal(ctx.uncertain.value, false)
  assert.ok(events.some(e => e[0] === 'saved' && e[1].production_order_id === 'HC-original'))
})

test('definite rejection retains editable drafts, permits corrected retry and never closes as success', async () => {
  const { ctx, state, events, calls } = setup({ createOrderHandcraftBatch: async () => { throw { response: { status: 409, data: { detail: '目标已发出' } } } } })
  await ctx.load(); ctx.supplier.value = '商家'; ctx.rows.value[0].allocated = 12
  await ctx.save()
  assert.equal(ctx.error.value, '目标已发出')
  assert.equal(ctx.rows.value[0].allocated, 12)
  assert.equal(ctx.fieldsLocked.value, false)
  assert.ok(state.guards.every(fn => fn() === true))
  assert.equal(events.some(e => e[0] === 'saved'), false)
  state.api.createOrderHandcraftBatch = async (...args) => { calls.push(args); return { data: { rows: [] } } }
  ctx.rows.value[0].allocated = 11
  await ctx.save()
  assert.equal(calls[0][1].allocations[0].allocated_quantity, 11)
})

test('saving rejects duplicate clicks and route changes until the whole batch finishes', async () => {
  let finish
  const { ctx, state, calls } = setup({ createOrderHandcraftBatch: (...args) => { calls.push(args); return new Promise(resolve => { finish = resolve }) } })
  await ctx.load(); ctx.supplier.value = '商家'
  const pending = ctx.save()
  assert.equal(ctx.saving.value, true)
  assert.ok(state.guards.every(fn => fn() === false))
  await ctx.save()
  assert.equal(calls.length, 1)
  finish({ data: { rows: [] } }); await pending
  assert.equal(ctx.saving.value, false)
})
