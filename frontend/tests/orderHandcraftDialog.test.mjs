import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { parse, compileScript } from '@vue/compiler-sfc'

// Execute the real component's setup and save methods. Only lifecycle/router
// registration and API transport are mocked; refs, computed and payloads are real.
const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const vueRuntime = moduleUrl(`
  export { ref, computed } from ${JSON.stringify(import.meta.resolve('vue'))};
  export const useId = () => 'test-suppliers';
  export const onMounted = fn => globalThis.__creationDialogTest.mounted.push(fn);
  export const onBeforeUnmount = fn => globalThis.__creationDialogTest.unmounted.push(fn);
`)
const routerRuntime = moduleUrl(`
  export const onBeforeRouteLeave = fn => globalThis.__creationDialogTest.leave.push(fn);
  export const onBeforeRouteUpdate = fn => globalThis.__creationDialogTest.update.push(fn);
`)
const filename = new URL('../src/components/fulfillment/OrderHandcraftDialog.vue', import.meta.url)
const source = await readFile(filename, 'utf8')
const { descriptor } = parse(source, { filename: filename.pathname })
const compiled = compileScript(descriptor, { id: 'creation-dialog-test' })
const code = compiled.content
  .replace(/from ['"]vue['"]/g, `from ${JSON.stringify(vueRuntime)}`)
  .replace(/from ['"]vue-router['"]/g, `from ${JSON.stringify(routerRuntime)}`)
  .replace(/import \{ ([^}]+) \} from ['"]naive-ui['"]/, (_, names) => `const ${names.split(',').map(name => `${name.trim()} = {}`).join(', ')}`)
  .replace(/import \{ listParts, getPartBom \} from ['"]@\/api\/parts['"]/, 'const listParts = async () => ({data:[]}), getPartBom = async () => ({data:[]})')
  .replace(/import \{ listSuppliers \} from ['"]@\/api\/suppliers['"]/, 'const listSuppliers = async () => ({data:[]})')
  .replace(/import \{ getBom \} from ['"]@\/api\/bom['"]/, 'const getBom = async () => ({data:[]})')
  .replace(/import \{ createOrderHandcraft \} from ['"]@\/api\/productionAllocation['"]/, 'const createOrderHandcraft = (...args) => globalThis.__creationDialogTest.send(...args)')
  .replace(/from ['"]@\/utils\/orderProductionCreation['"]/, `from ${JSON.stringify(new URL('../src/utils/orderProductionCreation.js', import.meta.url).href)}`)
  .replace(/import HandcraftTargetPicker from ['"].\/HandcraftTargetPicker.vue['"]/, 'const HandcraftTargetPicker = {}')
const { default: Dialog } = await import(moduleUrl(code))

function setup(send) {
  const hooks = { mounted: [], unmounted: [], leave: [], update: [], events: [], send }
  globalThis.__creationDialogTest = hooks
  const ctx = Dialog.setup({ orderId: 'OR-1', line: { id: 7, product_id: 'necklace', product_type: 'jewelry', quantity: 30, allocated: 10, unit: '条' } }, {
    expose() {}, emit: (...event) => hooks.events.push(event),
  })
  ctx.loading.value = false
  ctx.supplier.value = '手工商'
  ctx.planned.value = 25; ctx.allocated.value = 20
  ctx.materials.value = [{ part_id: 'raw', unit: '个', qty: 25 }]
  return { ctx, hooks }
}

test('pending and uncertain creation block leaving, changing order and reloading; retry keeps exact payload', async () => {
  const calls = []
  let reject
  const { ctx, hooks } = setup((order, data) => {
    calls.push({ order, data: structuredClone(data) })
    return new Promise((_, fail) => { reject = fail })
  })
  const pending = ctx.save()
  assert.equal(ctx.saving.value, true)
  assert.equal(ctx.fieldsLocked.value, true)
  assert.equal(hooks.leave[0](), false)
  assert.equal(hooks.update[0](), false)
  await ctx.save()
  assert.equal(calls.length, 1)
  reject(new Error('connection lost'))
  await pending
  assert.equal(ctx.uncertain.value, true)
  assert.equal(ctx.fieldsLocked.value, true)
  assert.equal(hooks.update[0](), false)
  const event = { preventDefault() { this.prevented = true } }
  ctx.beforeUnload(event)
  assert.equal(event.prevented, true)
  assert.equal(event.returnValue, '')
  // Even accidental reactive changes cannot alter an uncertain retry.
  ctx.supplier.value = '不得改写'; ctx.materials.value[0].qty = 99
  hooks.send = async (order, data) => { calls.push({ order, data: structuredClone(data) }); return { data: { production_order_id: 'HC-1' } } }
  await ctx.save()
  assert.deepEqual(calls[1], calls[0])
  assert.deepEqual(hooks.events, [['saved', { production_order_id: 'HC-1' }]])
  assert.equal(hooks.leave[0](), true)
  assert.equal(hooks.update[0](), true)
  assert.equal(ctx.fieldsLocked.value, false)
  const settledEvent = { preventDefault() { throw new Error('must not block settled action') } }
  ctx.beforeUnload(settledEvent)
})

test('definitive validation failure unlocks editing and corrected creation gets a new request key', async () => {
  const calls = []
  const { ctx, hooks } = setup(async (order, data) => {
    calls.push(structuredClone(data))
    throw { response: { status: 400, data: { detail: '目标已发出' } } }
  })
  await ctx.save()
  assert.equal(ctx.error.value, '目标已发出')
  assert.equal(ctx.blocked.value, false)
  assert.equal(hooks.update[0](), true)
  ctx.note.value = '重新核对'
  hooks.send = async (_, data) => { calls.push(structuredClone(data)); return { data: {} } }
  await ctx.save()
  assert.notEqual(calls[1].request_key, calls[0].request_key)
  assert.equal(calls[1].note, '重新核对')
})

test('local input errors never start a transport request or lock navigation', async () => {
  const { ctx, hooks } = setup(() => { throw new Error('must not send') })
  ctx.allocated.value = 21
  await ctx.save()
  assert.match(ctx.error.value, /剩余需求/)
  assert.equal(ctx.blocked.value, false)
  assert.equal(hooks.leave[0](), true)
})
