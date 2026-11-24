import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import { ref, nextTick, effectScope } from 'vue'

// Execute the actual production SFC handlers, substituting only APIs and the
// browser environment. Naive UI's blur-delayed number update is reproduced below.
const dataURL = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
const runtime = dataURL(`export { ref, reactive, computed, h, nextTick } from ${JSON.stringify(import.meta.resolve('vue'))};
export const onBeforeUnmount = fn => globalThis.__handcraftEditTest.unmount.push(fn);
export const onMounted = fn => globalThis.__handcraftEditTest.mounted.push(fn);`)
async function compile(name) {
  const source = readFileSync(new URL(`../src/views/handcraft/${name}.vue`, import.meta.url), 'utf8')
  const code = compileScript(parse(source).descriptor, { id: 'handcraft-edit-test' }).content.replace(/import ([\s\S]*?) from ['"]([^'"]+)['"]/g, (whole, bindings, path) => {
    if (path === 'vue') return `import ${bindings} from ${JSON.stringify(runtime)}`
    const names = bindings.replace(/[{}]/g, '').split(',').map(name => name.trim()).filter(Boolean)
    if (path === 'naive-ui') return `const ${names.map(name => `${name} = ${name === 'useMessage' ? '() => globalThis.__handcraftEditTest.message' : name === 'useDialog' ? '() => globalThis.__handcraftEditTest.dialog' : '{}'}`).join(', ')};`
    if (path === 'vue-router') return `const ${names.map(name => `${name} = ${name === 'useRoute' ? '() => globalThis.__handcraftEditTest.route' : name === 'useRouter' ? '() => ({ push() {} })' : name === 'onBeforeRouteLeave' ? 'fn => globalThis.__handcraftEditTest.guards.push(fn)' : '{}'}`).join(', ')};`
    if (path.includes('/api/')) return `const ${names.map(name => `${name} = (...args) => globalThis.__handcraftEditTest.api.${name}(...args)`).join(', ')};`
    if (path.endsWith('/useHandcraftSummaryReturn')) return 'const useHandcraftSummaryReturn = () => globalThis.__handcraftEditTest.navigation;'
    if (path.endsWith('/useIsMobile')) return 'const useIsMobile = () => ({ isMobile: ref(false) });'
    if (path.endsWith('/useSendWithStockSupplement')) return 'const useSendWithStockSupplement = () => ({ sending: ref(false), doSend() {} });'
    if (path.endsWith('/useProductionAllocations')) return `const useProductionAllocations = () => ({ productionUses: ref(null), allocationDialog: ref(null), canAllocate: ref(false), openAllocation() {}, refreshAllocations() {}, finishAllocation() {}, renderAllocationCell() {} });`
    if (path === '@/utils/ui') return `const ${names.map(name => `${name} = () => null`).join(', ')};`
    if (path.startsWith('@/utils/')) return `import ${bindings} from ${JSON.stringify(new URL(`../src/${path.slice(2)}.js`, import.meta.url).href)};`
    if (path.endsWith('.vue')) return `const ${bindings} = {};`
    if (path === '@vicons/ionicons5') return `const ${names.map(name => `${name} = {}`).join(', ')};`
    throw Error(`Unmocked import ${path}`)
  })
  return (await import(dataURL(code))).default
}
const Create = await compile('HandcraftCreate'), Detail = await compile('HandcraftDetail')
const reply = data => Promise.resolve({ data: structuredClone(data) })
const output = (id, qty = 37) => ({ id, jewelry_id: `SP-${id}`, qty, received_qty: 0, status: '未送出', unit: '对' })
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const tick = async () => { await nextTick(); await Promise.resolve(); await nextTick() }
function setup(component, overrides = {}) {
  const calls = [], warnings = [], errors = [], successes = [], dialogs = [], pushes = []
  const order = { id: 'HC-TEST', status: 'pending', supplier_name: 'A', delivery_images: [] }
  const defaults = {
    listParts: () => reply([]), listJewelries: () => reply([]),
    getHandcraft: () => reply(order), getHandcraftParts: () => reply([]),
    getHandcraftJewelries: () => reply([]), getHandcraftJewelryBreakdown: () => reply([]),
    getHandcraftPicking: () => reply({ groups: [] }), listHandcraftRestock: () => reply([]),
    deleteHandcraftJewelry: () => reply({}), createHandcraft: () => reply(order),
    getBom: () => reply([{ part_id: 'PJ-1', qty_per_unit: 2 }]), getPartBom: () => reply([{ child_part_id: 'PJ-1', qty_per_unit: 2 }]),
    listSuppliers: () => reply([{ name: 'A' }]), createSupplier: () => reply({}),
  }
  const state = { mounted: [], unmount: [], guards: [], route: { params: { id: order.id }, query: {} },
    message: { warning: text => warnings.push(text), error: text => errors.push(text), success: text => successes.push(text) },
    dialog: { warning: options => dialogs.push(options) },
    navigation: { summaryReturn: ref(null), goBack() {}, openCreated: path => pushes.push(path) },
    api: Object.fromEntries(Object.entries({ ...defaults, ...overrides }).map(([name, fn]) => [name, (...args) => { calls.push({ name, args }); return fn(...args) }])),
  }
  globalThis.__handcraftEditTest = state
  globalThis.document = { activeElement: null }
  const scope = effectScope()
  const ctx = scope.run(() => component.setup({}, { expose() {} }))
  if (component === Detail) ctx.order.value = order
  return { ctx, calls, warnings, errors, successes, dialogs, pushes, mounted: state.mounted, guards: state.guards, cleanup: () => { state.unmount.forEach(fn => fn()); scope.stop() } }
}
function prepareCreate(h, type = 'jewelry') {
  const c = h.ctx
  c.supplierName.value = 'A'
  c.supplierOptions.value = [{ value: 'A' }]
  c.groups.push({ output_type: type, jewelry_id: null, part_id: null, qty: 1, unit: '个', note: '', parts: [] })
  const group = c.groups[0]
  Object.assign(group, { output_type: type, jewelry_id: type === 'jewelry' ? 'SP-1' : null, part_id: type === 'part' ? 'PJ-2' : null })
  group.parts.push({ part_id: 'PJ-1', qty: 2, bom_qty: 2, _qty_per_unit: 2, unit: '个', note: '' })
  return group
}
function focusPendingQuantity(h, group, qty) {
  let blurred = 0
  const input = { blur() {
    blurred++
    // A precision-controlled NInputNumber emits its final value on blur.
    nextTick(() => { group.qty = qty; h.ctx.onOutputQtyChange(group, qty) })
  } }
  document.activeElement = input
  h.ctx.createForm.value = { contains: element => element === input }
  return () => blurred
}

for (const type of ['jewelry', 'part']) {
  test(`${type}: submit commits focused quantity before snapshotting outputs and BOM material quantities`, async () => {
    const h = setup(Create), group = prepareCreate(h, type)
    const blurred = focusPendingQuantity(h, group, 85)
    assert.equal(group.qty, 1)
    await h.ctx.submit()
    assert.equal(blurred(), 1)
    const payload = h.calls.find(call => call.name === 'createHandcraft').args[0]
    assert.equal(payload.jewelries[0].qty, 85)
    assert.equal(payload.jewelries[0][type === 'jewelry' ? 'jewelry_id' : 'part_id'], type === 'jewelry' ? 'SP-1' : 'PJ-2')
    assert.equal(payload.parts[0].qty, 170)
    assert.equal(payload.parts[0].bom_qty, 170)
    assert.deepEqual(h.pushes, ['/handcraft/HC-TEST'])
    h.cleanup()
  })
}
test('manual material quantities survive quantity commit, while BOM-linked rows follow the final output quantity', async () => {
  const h = setup(Create), group = prepareCreate(h)
  group.parts[0]._qty_per_unit = null
  group.parts[0].qty = 123
  focusPendingQuantity(h, group, 47)
  await h.ctx.submit()
  const payload = h.calls.find(call => call.name === 'createHandcraft').args[0]
  assert.equal(payload.jewelries[0].qty, 47)
  assert.equal(payload.parts[0].qty, 123)
  h.cleanup()
})
test('multiple output rows preserve independent quantities and explicit append target', async () => {
  const h = setup(Create), first = prepareCreate(h)
  first.qty = 12
  h.ctx.groups.push({ output_type: 'jewelry', jewelry_id: null, part_id: null, qty: 1, unit: '个', note: '', parts: [] })
  const second = h.ctx.groups[1]
  second.jewelry_id = 'SP-2'
  h.ctx.appendToOrderId.value = 'HC-APPEND'
  h.ctx.targetMode.value = 'append'
  focusPendingQuantity(h, second, 56)
  await h.ctx.submit()
  const payload = h.calls.find(call => call.name === 'createHandcraft').args[0]
  assert.deepEqual(payload.jewelries.map(row => row.qty), [12, 56])
  assert.equal(payload.append_to_order_id, 'HC-APPEND')
  h.cleanup()
})
test('commit-before-submit keeps double submission locked and preserves the committed quantity after API failure', async () => {
  const pending = deferred(), h = setup(Create, { createHandcraft: () => pending.promise }), group = prepareCreate(h)
  focusPendingQuantity(h, group, 23)
  const first = h.ctx.submit(), second = h.ctx.submit()
  await tick()
  assert.equal(h.calls.filter(call => call.name === 'createHandcraft').length, 1)
  assert.equal(h.ctx.submitting.value, true)
  pending.reject(Error('offline'))
  await first
  await second
  assert.equal(group.qty, 23)
  assert.equal(h.ctx.submitting.value, false)
  assert.equal(h.ctx.submitUncertain.value, true)
  await h.ctx.submit()
  assert.equal(h.calls.filter(call => call.name === 'createHandcraft').length, 1)
  assert.deepEqual(h.pushes, [])
  h.cleanup()
})
test('submission without a focused page input still works and does not blur unrelated controls', async () => {
  const h = setup(Create), group = prepareCreate(h)
  group.qty = 31
  document.activeElement = { blur() { assert.fail('unrelated input must not be blurred') } }
  h.ctx.createForm.value = { contains: () => false }
  await h.ctx.submit()
  assert.equal(h.calls.find(call => call.name === 'createHandcraft').args[0].jewelries[0].qty, 31)
  h.cleanup()
})
test('delete removes only the confirmed output immediately, then reloads outputs and breakdown without a page refresh', async () => {
  const deletion = deferred(), metadata = deferred()
  let outputs = [output(1), output(2, 19)]
  const h = setup(Detail, {
    deleteHandcraftJewelry: async () => { await deletion.promise; outputs = outputs.filter(row => row.id !== 1); return reply({}) },
    getHandcraft: () => metadata.promise,
    getHandcraftJewelries: () => reply(outputs),
    getHandcraftJewelryBreakdown: () => reply([{ total_qty: 19, entries: [{ hc_jewelry_item_id: 2, qty: 19 }] }]),
  })
  h.ctx.jewelryItems.value = structuredClone(outputs)
  h.ctx.doDeleteJewelryItem(outputs[0])
  assert.deepEqual(h.calls, []) // Opening/cancelling confirmation is not deletion.
  const confirmed = h.dialogs[0].onPositiveClick()
  assert.equal(h.ctx.jewelryItems.value.length, 2)
  deletion.resolve()
  await tick()
  assert.deepEqual(h.ctx.jewelryItems.value.map(row => row.id), [2])
  assert.equal(h.ctx.totalJewelryQty.value, 19)
  metadata.resolve({ data: h.ctx.order.value })
  await confirmed
  assert.equal(h.ctx.breakdownGroups.value[0].entries[0].hc_jewelry_item_id, 2)
  for (const name of ['getHandcraft', 'getHandcraftJewelries', 'getHandcraftJewelryBreakdown']) assert.ok(h.calls.some(call => call.name === name), name)
  assert.deepEqual(h.errors, [])
  h.cleanup()
})
test('deleting the last output clears the output list, totals and customer breakdown', async () => {
  const h = setup(Detail)
  h.ctx.jewelryItems.value = [output(1)]
  h.ctx.breakdownGroups.value = [{ total_qty: 37 }]
  h.ctx.doDeleteJewelryItem(output(1))
  await h.dialogs[0].onPositiveClick()
  assert.deepEqual(h.ctx.jewelryItems.value, [])
  assert.deepEqual(h.ctx.breakdownGroups.value, [])
  assert.equal(h.ctx.totalJewelryQty.value, 0)
  assert.equal(h.ctx.outputsLoaded.value, true)
  h.cleanup()
})
test('delete API failure retains all outputs and reports failure without reloading or reporting success', async () => {
  const h = setup(Detail, { deleteHandcraftJewelry: () => Promise.reject({ response: { data: { detail: '已有回收，不可删除' } } }) })
  h.ctx.jewelryItems.value = [output(1), output(2)]
  h.ctx.doDeleteJewelryItem(output(1))
  assert.equal(await h.dialogs[0].onPositiveClick(), false)
  assert.equal(h.ctx.jewelryItems.value.length, 2)
  assert.deepEqual(h.errors, ['已有回收，不可删除'])
  assert.deepEqual(h.successes, [])
  assert.deepEqual(h.calls.map(call => call.name), ['deleteHandcraftJewelry'])
  h.cleanup()
})
test('successful delete followed by refresh failure stays deleted and reports refresh failure, not delete failure', async () => {
  const h = setup(Detail, { getHandcraft: () => Promise.reject(Error('refresh offline')), getHandcraftJewelries: () => reply([output(2)]) })
  h.ctx.jewelryItems.value = [output(1), output(2)]
  h.ctx.doDeleteJewelryItem(output(1))
  await h.dialogs[0].onPositiveClick()
  assert.deepEqual(h.ctx.jewelryItems.value.map(row => row.id), [2])
  assert.deepEqual(h.successes, ['已删除'])
  assert.deepEqual(h.errors, [])
  assert.match(h.warnings[0], /已删除.*刷新失败/)
  h.cleanup()
})
test('create page binds the input commit boundary to its own form root', () => {
  const source = readFileSync(new URL('../src/views/handcraft/HandcraftCreate.vue', import.meta.url), 'utf8')
  assert.match(parse(source).descriptor.template.content, /<div ref="createForm"/)
})

const configureCatalog = h => {
  h.ctx.jewelryOptions.value = [{ value: 'SP-1', name: '耳环', unit: '对' }]
  h.ctx.partOptions.value = [{ value: 'PJ-1', name: '材料', unit: '个' }, { value: 'PJ-2', name: '组合件', unit: '条', is_composite: true }]
  return h.ctx.outputProducts.value
}
test('actual create batch confirmation is draft-only, loads both BOM kinds and preserves existing manual quantities', async () => {
  const h = setup(Create), products = configureCatalog(h)
  h.ctx.supplierName.value = 'A'
  await h.ctx.confirmOutputs(products.map((product, index) => ({ product, qty: index ? 63 : 85, unit: product.unit, note: '按款' })))
  assert.equal(h.ctx.groups.length, 2)
  assert.deepEqual(h.ctx.groups.map(group => group.parts[0].qty), [170, 126])
  assert.equal(h.calls.filter(call => call.name === 'createHandcraft').length, 0)
  const first = h.ctx.groups[0]
  h.ctx.setMaterialQty(first.parts[0], '200')
  const reads = h.calls.length
  await h.ctx.confirmOutputs(products.map(product => ({ product, qty: 50, unit: product.unit, note: '更新' })))
  assert.equal(h.calls.length, reads)
  assert.equal(h.ctx.groups[0].parts[0].qty, '200')
  assert.equal(h.ctx.groups[0].parts[0].bom_qty, 100)
  assert.equal(h.ctx.groups[1].parts[0].qty, 100)
  h.cleanup()
})
test('actual create BOM failure is explicit and blocks submission until retry succeeds', async () => {
  let fail = true
  const h = setup(Create, { getBom: () => fail ? Promise.reject(Error('offline')) : reply([{ part_id: 'PJ-1', qty_per_unit: 2 }]) })
  const products = configureCatalog(h)
  h.ctx.supplierName.value = 'A'; h.ctx.supplierOptions.value = [{ value: 'A' }]
  await h.ctx.confirmOutputs([{ product: products[0], qty: 85, unit: '对' }])
  assert.equal(h.ctx.groups[0].bomState, 'error')
  await h.ctx.submit()
  assert.equal(h.calls.filter(call => call.name === 'createHandcraft').length, 0)
  assert.match(h.warnings.at(-1), /重试/)
  fail = false
  await h.ctx.retryBom(h.ctx.groups[0])
  await h.ctx.submit()
  assert.equal(h.calls.find(call => call.name === 'createHandcraft').args[0].parts[0].qty, 170)
  h.cleanup()
})
test('batch BOM reads leave main draft unchanged until complete and late responses do not resurrect an unmounted page', async () => {
  const wait = deferred(), h = setup(Create, { getBom: () => wait.promise }), products = configureCatalog(h)
  const applying = h.ctx.confirmOutputs([{ product: products[0], qty: 85, unit: '对' }])
  assert.equal(h.ctx.groups.length, 0)
  assert.equal(h.ctx.applyingOutputs.value, true)
  h.cleanup()
  wait.resolve({ data: [{ part_id: 'PJ-1', qty_per_unit: 2 }] })
  await applying
  assert.equal(h.ctx.groups.length, 0)
})
test('picker cannot snapshot a BOM still being retried, and create waits for that read', async () => {
  const wait = deferred(), h = setup(Create, { getBom: () => wait.promise }), products = configureCatalog(h)
  const applying = h.ctx.confirmOutputs([{ product: products[0], qty: 85, unit: '对' }])
  wait.resolve({ data: [{ part_id: 'PJ-1', qty_per_unit: 2 }] }); await applying
  h.ctx.groups[0].bomState = 'loading'
  h.ctx.openOutputPicker()
  assert.equal(h.ctx.outputPickerVisible.value, false)
  assert.match(h.warnings.at(-1), /加载/)
  h.cleanup()
})
test('catalog failure is not treated as an empty catalog and retry keeps already-entered draft', async () => {
  let fail = true
  const h = setup(Create, { listParts: () => fail ? Promise.reject(Error('offline')) : reply([]) })
  prepareCreate(h)
  await h.ctx.loadCatalog()
  assert.equal(h.ctx.catalogError.value, true)
  await h.ctx.submit()
  assert.equal(h.calls.filter(call => call.name === 'createHandcraft').length, 0)
  fail = false; await h.ctx.loadCatalog()
  assert.equal(h.ctx.catalogError.value, false)
  assert.equal(h.ctx.groups[0].qty, 1)
  h.cleanup()
})
test('new/append mode requires an explicit target and switching merchant or mode clears the target', async () => {
  const h = setup(Create)
  prepareCreate(h)
  h.ctx.changeTargetMode('append')
  await h.ctx.submit()
  assert.equal(h.calls.length, 0)
  assert.match(h.warnings[0], /明确/)
  h.ctx.appendToOrderId.value = 'HC-OLD'
  h.ctx.onSupplierChange()
  assert.equal(h.ctx.appendToOrderId.value, null)
  h.ctx.appendToOrderId.value = 'HC-OLD'
  h.ctx.changeTargetMode('new')
  assert.equal(h.ctx.appendToOrderId.value, null)
  h.cleanup()
})
test('material-only drafts send separate source lines, dates apply only to new orders and confirmed failures remain retryable', async () => {
  let fail = true
  const h = setup(Create, { createHandcraft: () => fail ? Promise.reject({ response: { status: 422, data: { detail: '校验失败' } } }) : reply({ id: 'HC-TEST' }) })
  h.ctx.supplierName.value = 'A'; h.ctx.supplierOptions.value = [{ value: 'A' }]
  h.ctx.extras.push({ part_id: 'PJ-1', qty: '0.0001', unit: '米', note: '单独补充' })
  h.ctx.createdAtTs.value = new Date(2026, 10, 24).getTime()
  await h.ctx.submit()
  assert.equal(h.ctx.submitUncertain.value, false)
  assert.equal(h.ctx.createdOrderId.value, null)
  assert.match(h.errors[0], /校验失败/)
  fail = false; await h.ctx.submit()
  const payload = h.calls.filter(call => call.name === 'createHandcraft').at(-1).args[0]
  assert.deepEqual(payload.jewelries, [])
  assert.equal(payload.parts[0].qty, .0001)
  assert.equal(payload.created_at, '2026-11-24')
  assert.equal(h.ctx.createdOrderId.value, 'HC-TEST')
  await h.ctx.submit()
  assert.equal(h.calls.filter(call => call.name === 'createHandcraft').length, 2)
  h.cleanup()
})
test('review includes the latest input but does not save, then successful submission may navigate past the save guard', async () => {
  const h = setup(Create), output = prepareCreate(h)
  focusPendingQuantity(h, output, 85)
  await h.ctx.review()
  assert.equal(h.ctx.reviewVisible.value, true)
  assert.equal(h.calls.length, 0)
  assert.equal(output.parts[0].qty, 170)
  h.ctx.submitting.value = true
  assert.equal(h.guards[0](), false)
  h.ctx.createdOrderId.value = 'HC-TEST'
  assert.equal(h.guards[0](), undefined)
  h.cleanup()
})
