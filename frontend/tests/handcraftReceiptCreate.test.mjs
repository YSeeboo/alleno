import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import { reactive, ref, nextTick, effectScope } from 'vue'
import { handcraftSourceKey, createHandcraftReceiptInput, filterHandcraftReceiptSources, handcraftReceiptLineAmount, summarizeHandcraftReceipt, handcraftReceiptItemPayload } from '../src/utils/handcraftReceiptCreate.js'

const output = (id = 1, extra = {}) => ({ id, is_output: true, item_type: 'jewelry', item_id: 'J1', item_name: '耳环', handcraft_order_id: `HC${id}`, supplier_name: 'A', qty: 10, received_qty: 2, unit: '对', created_at: '2026-11-22T23:00:00Z', ...extra })
const material = (id = 1, extra = {}) => output(id, { is_output: false, item_type: 'part', item_id: 'P1', item_name: '链条', unit: '米', ...extra })
test('same product and overlapping output/material ids have independent source keys and drafts', () => {
  const rows = [output(), output(2), material()]
  assert.deepEqual(rows.map(handcraftSourceKey), ['output_1', 'output_2', 'material_1'])
  assert.deepEqual(createHandcraftReceiptInput(rows[0]), { qty: 8, price: null, weight: null, weight_unit: 'g', unit: '对' })
  assert.equal(createHandcraftReceiptInput(output(3, { received_qty: 10 })).qty, null)
  assert.equal(createHandcraftReceiptInput(output(3, { received_qty: 12 })).qty, null)
})
test('local search/date/progress use document date and settlement balance without mutating selection', () => {
  const rows = [output(), output(2, { received_qty: 12 }), output(3, { item_name: '手链', created_at: '2026-11-23' })]
  const selectedKeys = new Set(['output_2'])
  assert.equal(filterHandcraftReceiptSources(rows).length, 3)
  assert.deepEqual(filterHandcraftReceiptSources(rows, { keyword: '耳环 HC2', dateOn: '2026-11-22', selectedKeys, progress: 'selected' }), [rows[1]])
  assert.deepEqual(filterHandcraftReceiptSources(rows, { progress: 'remaining' }), [rows[0], rows[2]])
  assert.equal(selectedKeys.size, 1)
})
test('seven-place fees round each line, preserve blank versus zero, and keep quantity units separate', () => {
  assert.equal(handcraftReceiptLineAmount({ qty: 3, price: .12345675 }), '0.3703704')
  assert.equal(handcraftReceiptLineAmount({ qty: 1, price: 0 }), '0.0000000')
  assert.equal(handcraftReceiptLineAmount({ qty: 1, price: null }), null)
  const rows = [output(), output(2), output(3, { unit: '个' })]
  const result = summarizeHandcraftReceipt(rows, { output_1: { qty: 3, price: .12345675 }, output_2: { qty: 9, price: 0 }, output_3: { qty: 1, price: null } })
  assert.deepEqual(result, { amount: '0.3703704', quantities: [{ unit: '对', qty: 12 }, { unit: '个', qty: 1 }], unpricedCount: 1, overCount: 1 })
})
test('output part uses jewelry source id; materials have neither fee nor weight and allow four decimals', () => {
  assert.deepEqual(handcraftReceiptItemPayload(output(1, { item_type: 'part' }), { qty: 20, price: 0, weight: .5, weight_unit: 'kg' }, 'A'), { handcraft_jewelry_item_id: 1, qty: 20, unit: '对', price: 0, weight: .5, weight_unit: 'kg' })
  assert.deepEqual(handcraftReceiptItemPayload(material(), { qty: 20.1234, price: 99, weight: 99 }, 'A'), { handcraft_part_item_id: 1, qty: 20.1234, unit: '米' })
})
test('invalid quantities, prices, weights, supplier and unavailable sources cannot become payloads', () => {
  for (const qty of [null, '', 0, -1, 1.5, Infinity, NaN]) assert.throws(() => handcraftReceiptItemPayload(output(), { qty }, 'A'))
  for (const qty of [.00001, 1.12345]) assert.throws(() => handcraftReceiptItemPayload(material(), { qty }, 'A'), /4 位/)
  for (const key of ['price', 'weight']) for (const value of ['', -1, Infinity, NaN]) assert.throws(() => handcraftReceiptItemPayload(output(), { qty: 1, [key]: value }, 'A'))
  assert.throws(() => handcraftReceiptItemPayload(output(), { qty: 1, weight: 0, weight_unit: '吨' }, 'A'))
  assert.throws(() => handcraftReceiptItemPayload(output(), { qty: 1 }, 'B'), /不属于/)
  assert.throws(() => handcraftReceiptItemPayload(output(1, { _unavailable: true }), { qty: 1 }, 'A'), /不可用/)
})

// Compile the actual SFC setup, replacing only environment dependencies and APIs.
// These tests exercise the production refs, computed values, watchers and handlers.
const dataURL = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
const runtime = dataURL(`export { ref, reactive, computed, watch, h } from ${JSON.stringify(import.meta.resolve('vue'))};
export const onMounted = fn => globalThis.__receiptTest.mounted.push(fn);
export const onBeforeUnmount = fn => globalThis.__receiptTest.cleanup.push(fn);`)
async function compile(name) {
  const text = readFileSync(new URL(`../src/views/handcraft-receipts/${name}.vue`, import.meta.url), 'utf8')
  const script = compileScript(parse(text).descriptor, { id: 'receipt-test' }).content.replace(/import ([\s\S]*?) from ['"]([^'"]+)['"]/g, (whole, bindings, path) => {
    if (path === 'vue') return `import ${bindings} from ${JSON.stringify(runtime)}`
    if (path === 'vue-router') return 'const onBeforeRouteLeave = fn => globalThis.__receiptTest.guards.push(fn)'
    if (path === 'naive-ui') return `const ${bindings.replace(/[{}]/g, '').split(',').map(n => n.trim()).filter(Boolean).map(n => `${n} = ${n === 'useMessage' ? '() => globalThis.__receiptTest.message' : n === 'useDialog' ? '() => globalThis.__receiptTest.dialog' : '{}'}`).join(', ')}`
    if (path.includes('/api/')) return `const ${bindings.replace(/[{}]/g, '').split(',').map(n => `${n.trim()} = (...args) => globalThis.__receiptTest.api.${n.trim()}(...args)`).join(', ')}`
    if (path.endsWith('/useHandcraftSummaryReturn')) return 'const useHandcraftSummaryReturn = () => globalThis.__receiptTest.navigation'
    if (path.endsWith('/useIsMobile')) return 'const useIsMobile = () => ({ isMobile: globalThis.__receiptTest.isMobile })'
    if (path === '@/utils/ui') return 'const fmtMoney = v => Number(v).toFixed(7), fmtPrice = fmtMoney, parseNum = v => Number(v)'
    if (path.startsWith('@/utils/')) return `import ${bindings} from ${JSON.stringify(new URL(`../src/${path.slice(2)}.js`, import.meta.url).href)}`
    if (path === '@vicons/ionicons5') return 'const SearchOutline = {}, CubeOutline = {}'
    if (path.endsWith('.vue')) return `const ${bindings} = {}`
    throw Error(`Unmocked import ${path}`)
  })
  return (await import(dataURL(script))).default
}
const Create = await compile('HandcraftReceiptCreate'), Return = await compile('PartReturnModal')
const reply = data => Promise.resolve({ data })
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const tick = async () => { await nextTick(); await Promise.resolve(); await nextTick() }
function setup(overrides = {}, component = Create, props = {}) {
  globalThis.window ??= { addEventListener() {}, removeEventListener() {} }
  const scope = effectScope(), events = [], warnings = [], dialogs = [], pushes = []
  const state = { mounted: [], cleanup: [], guards: [], isMobile: ref(false), message: { warning: v => warnings.push(v), error: v => warnings.push(v), success() {} }, dialog: { warning: v => dialogs.push(v) }, navigation: { summaryReturn: ref({ path: '/handcraft-output' }), goBack() {}, openCreated: async value => pushes.push(value) }, api: {
    getHandcraftSuppliers: () => reply(['A', 'B']), listHandcraftPendingReceiveItems: () => reply([output(), output(2), material()]), getHandcraftByReceiptCode: () => reply({ supplier_name: 'B' }), createHandcraftReceipt: () => reply({ id: 'R1' }), batchUpdatePartCosts: () => reply({}), ...overrides,
  } }
  globalThis.__receiptTest = state
  const values = reactive(props)
  const ctx = scope.run(() => component.setup(values, { expose() {}, emit: (...event) => events.push(event) }))
  const cleanup = () => { state.cleanup.forEach(fn => fn()); scope.stop() }
  return { ctx, state, props: values, events, warnings, dialogs, pushes, cleanup }
}
async function loaded(overrides) {
  const h = setup(overrides)
  h.ctx.onSupplierChange('A'); await tick()
  return h
}
test('production SFC filters and pages locally without losing selected inputs or refetching', async () => {
  const calls = [], rows = Array.from({ length: 25 }, (_, i) => output(i + 1))
  const h = await loaded({ listHandcraftPendingReceiveItems: params => { calls.push(params); return reply(rows) } }), c = h.ctx
  c.toggleOutput(rows[0], true); c.itemInputs.output_1.price = .125; c.itemInputs.output_1.weight = .2
  c.sourcePage.value = 2; c.togglePage(true)
  assert.equal(c.selectedOutputs.value.length, 6)
  c.filterKeyword.value = 'HC25'; await tick()
  assert.equal(c.sourcePage.value, 1); assert.equal(c.pageOutputs.value.length, 1)
  assert.equal(c.hiddenSelectedCount.value, 5); assert.equal(c.itemInputs.output_1.price, .125)
  c.filterDateOn.value = new Date(2026, 10, 22).getTime(); await tick()
  c.showSelected(); await tick(); assert.equal(c.filteredOutputs.value.length, 6)
  assert.deepEqual(calls, [{ supplier_name: 'A', include_settled: true }]); h.cleanup()
})
test('refresh failure preserves draft, missing sources block submission, reappearing sources recover', async () => {
  let mode = 'ok'
  const h = await loaded({ listHandcraftPendingReceiveItems: () => mode === 'fail' ? Promise.reject(Error('offline')) : reply(mode === 'missing' ? [] : [output()]) }), c = h.ctx
  c.toggleOutput(c.pendingOutputs.value[0], true); c.itemInputs.output_1.price = 3
  mode = 'fail'; await c.fetchPendingItems()
  assert.equal(c.fetchError.value, true); assert.equal(c.canReview.value, false); assert.equal(c.itemInputs.output_1.price, 3)
  mode = 'missing'; await c.fetchPendingItems()
  assert.equal(c.unavailableCount.value, 1); assert.equal(c.canReview.value, false); assert.throws(c.buildPayload, /不可用/)
  mode = 'ok'; await c.fetchPendingItems()
  assert.equal(c.unavailableCount.value, 0); assert.equal(c.canReview.value, true); assert.equal(c.itemInputs.output_1.price, 3); h.cleanup()
})
test('out-of-order source responses and unmounted responses never replace current scope', async () => {
  const requests = [], h = setup({ listHandcraftPendingReceiveItems: params => { const d = deferred(); requests.push({ ...d, params }); return d.promise } }), c = h.ctx
  c.onSupplierChange('A'); c.onSupplierChange('B')
  requests[1].resolve({ data: [output(2, { supplier_name: 'B' })] }); await tick()
  requests[0].reject(Error('old')); await tick()
  assert.equal(c.pendingOutputs.value[0].id, 2); assert.equal(c.fetchError.value, false)
  const pending = c.fetchPendingItems(); h.cleanup(); requests[2].resolve({ data: [] }); await pending
  assert.equal(c.pendingOutputs.value[0].id, 2)
})
test('supplier changes confirm, cancellation retains everything, confirmation resets only source-specific fields', async () => {
  const h = await loaded(), c = h.ctx
  c.toggleOutput(c.pendingOutputs.value[0], true); c.onPartConfirm({ 1: .1234 }); c.itemInputs.output_1.price = 5
  c.note.value = '保留备注'; c.createdAtTs.value = new Date(2026, 10, 22).getTime(); c.status.value = '已付款'
  c.onSupplierChange('B'); assert.equal(c.supplierName.value, 'A'); assert.equal(c.switchPending.value, true)
  h.dialogs[0].onNegativeClick(); assert.equal(c.itemInputs.output_1.price, 5); assert.equal(c.selectedParts.value.length, 1)
  c.onSupplierChange('B'); h.dialogs[1].onPositiveClick(); await tick()
  assert.equal(c.supplierName.value, 'B'); assert.equal(c.selectedOutputs.value.length, 0); assert.equal(c.selectedParts.value.length, 0); assert.deepEqual(Object.keys(c.itemInputs), [])
  assert.equal(c.note.value, '保留备注'); assert.equal(c.status.value, '已付款'); assert.ok(c.createdAtTs.value); h.cleanup()
})
test('receipt lookup handles invalid/failed codes, input edits, competing lookups and merchant races', async () => {
  const requests = [], h = setup({ getHandcraftByReceiptCode: code => { const d = deferred(); requests.push({ ...d, code }); return d.promise } }), c = h.ctx
  c.receiptCode.value = 'x'; await c.applyReceiptCode(); assert.match(c.codeError.value, /5 位/); assert.equal(requests.length, 0)
  c.receiptCode.value = 'aaaaa'; const a = c.applyReceiptCode()
  c.receiptCode.value = 'bbbbb'; const b = c.applyReceiptCode()
  requests[1].resolve({ data: { supplier_name: 'B' } }); await b; await tick()
  requests[0].resolve({ data: { supplier_name: 'A' } }); await a
  assert.equal(c.supplierName.value, 'B'); assert.equal(c.scopeCode.value, 'BBBBB')
  c.receiptCode.value = 'CCCCC'; const edited = c.applyReceiptCode(); c.receiptCode.value = 'DDDDD'
  requests[2].resolve({ data: { supplier_name: 'A' } }); await edited
  assert.equal(c.scopeCode.value, 'BBBBB')
  const merchant = c.applyReceiptCode(); c.clearReceiptScope(); await tick(); c.onSupplierChange('A'); await tick()
  requests[3].resolve({ data: { supplier_name: 'B' } }); await merchant
  assert.equal(c.supplierName.value, 'A'); assert.equal(c.scopeCode.value, null)
  c.receiptCode.value = 'EEEEE'; const failure = c.applyReceiptCode(); requests[4].reject(Error('bad code')); await failure
  assert.match(c.codeError.value, /定位失败/); assert.equal(c.supplierName.value, 'A'); h.cleanup()
})
test('receipt scope changes confirm before clearing a selected draft and pass code only after approval', async () => {
  const calls = [], h = await loaded({ listHandcraftPendingReceiveItems: params => { calls.push(params); return reply([output()]) }, getHandcraftByReceiptCode: () => reply({ supplier_name: 'A' }) }), c = h.ctx
  c.toggleOutput(c.pendingOutputs.value[0], true); c.receiptCode.value = 'ABCDE'; await c.applyReceiptCode()
  assert.equal(c.scopeCode.value, null); assert.equal(calls.length, 1)
  h.dialogs[0].onPositiveClick(); await tick()
  assert.equal(c.scopeCode.value, 'ABCDE'); assert.equal(calls[1].receipt_code, 'ABCDE'); assert.equal(c.selectedOutputs.value.length, 0); h.cleanup()
})
test('return-only receipt submits material id with no fees and keeps date/payment/note', async () => {
  const h = await loaded(), c = h.ctx
  c.onPartConfirm({ 1: 1.2345 }); c.status.value = '已付款'; c.note.value = '仅退料'; c.createdAtTs.value = new Date(2026, 10, 22).getTime()
  assert.equal(c.draftSummary.value.amount, '0.0000000'); c.review(); assert.equal(c.reviewVisible.value, true)
  assert.deepEqual(c.buildPayload(), { supplier_name: 'A', status: '已付款', note: '仅退料', created_at: '2026-11-22', items: [{ handcraft_part_item_id: 1, qty: 1.2345, unit: '米' }] }); h.cleanup()
})
test('review validates incomplete settled output; preview locks source changes and retains weight', async () => {
  const row = output(1, { received_qty: 10 }), h = await loaded({ listHandcraftPendingReceiveItems: () => reply([row]) }), c = h.ctx
  c.toggleOutput(row, true); c.review(); assert.equal(c.reviewVisible.value, false); assert.match(h.warnings.at(-1), /实际回收数量/)
  Object.assign(c.itemInputs.output_1, { qty: 2, price: 0, weight: .5, weight_unit: 'kg' }); c.review()
  assert.equal(c.reviewVisible.value, true); c.onSupplierChange('B'); c.toggleOutput(row, false)
  assert.equal(c.supplierName.value, 'A'); assert.equal(c.selectedOutputs.value.length, 1)
  assert.equal(c.buildPayload().items[0].weight_unit, 'kg'); h.cleanup()
})
test('create failure is retryable, double clicks create once, success locks without depending on navigation', async () => {
  const requests = [], h = await loaded({ createHandcraftReceipt: payload => { const d = deferred(); requests.push({ ...d, payload }); return d.promise } }), c = h.ctx
  h.state.navigation.openCreated = async () => { throw Error('router') }
  c.toggleOutput(c.pendingOutputs.value[0], true); c.review()
  const first = c.submit(); await c.submit(); assert.equal(requests.length, 1); assert.equal(c.locked.value, true)
  assert.equal(h.state.guards[0]({ path: '/other' }), false)
  requests[0].reject(Error('failed')); await first
  assert.equal(c.reviewVisible.value, true); assert.equal(c.locked.value, false); assert.equal(c.selectedOutputs.value.length, 1)
  const retry = c.submit(); requests[1].resolve({ data: { id: 'R2' } }); await retry
  assert.equal(c.createdReceiptId.value, 'R2'); assert.equal(c.locked.value, true); assert.equal(c.reviewVisible.value, false)
  await c.submit(); assert.equal(requests.length, 2); assert.match(h.warnings.at(-1), /单据已创建/)
  assert.equal(h.state.guards[0]({ path: '/handcraft-receipts/R2' }), true); h.cleanup()
})
test('shortfall warning and cost failure/retry never recreate receipt or lose created id', async () => {
  let creates = 0, updates = 0; const sent = []
  const h = await loaded({ createHandcraftReceipt: () => { creates++; return reply({ id: 'R3', parts_shortfall: [{ part_name: '链条', shortfall_qty: 2 }], cost_diffs: [{ part_id: 'P1', field: 'handcraft_cost', new_value: 2 }] }) }, batchUpdatePartCosts: payload => { sent.push(payload); return ++updates === 1 ? Promise.reject(Error('cost')) : reply({}) } }), c = h.ctx
  c.toggleOutput(c.pendingOutputs.value[0], true); c.review(); await c.submit()
  assert.equal(c.costDiffVisible.value, true); assert.match(h.warnings[0], /链条：缺 2/); assert.equal(h.pushes.length, 0)
  assert.equal(h.state.guards[0]({ path: '/other' }), false)
  await c.confirmCostUpdate(); assert.equal(c.costDiffVisible.value, true); assert.equal(c.createdReceiptId.value, 'R3')
  await c.confirmCostUpdate(); assert.equal(c.costDiffVisible.value, false); assert.equal(creates, 1); assert.deepEqual(h.pushes, ['/handcraft-receipts/R3'])
  assert.equal(sent[1].updates[0].source_id, 'R3'); h.cleanup()
})
test('cost update cannot be duplicated or skipped while in flight, and explicit skip navigates safely', async () => {
  const pending = deferred(); let count = 0
  const h = await loaded({ batchUpdatePartCosts: () => { count++; return pending.promise } }), c = h.ctx
  c.createdReceiptId.value = 'R4'; c.costDiffVisible.value = true
  const update = c.confirmCostUpdate(); await c.confirmCostUpdate(); c.skipCostUpdate()
  assert.equal(count, 1); assert.equal(c.costDiffVisible.value, true)
  pending.reject(Error('failed')); await update; c.skipCostUpdate(); await tick()
  assert.deepEqual(h.pushes, ['/handcraft-receipts/R4']); assert.equal(c.locked.value, true); h.cleanup()
})
test('return modal has isolated draft, blank checked rows, precision validation and non-writing cancel', async () => {
  const part = material(1, { received_qty: 10 }), h = setup({}, Return, { show: true, parts: [part], selections: {}, isMobile: true }), c = h.ctx
  c.togglePart(part, true); assert.equal(c.isSelected(part), true); assert.equal(c.localSel.value['1'], null)
  c.onConfirm(); assert.equal(h.events.length, 0)
  c.setQty(part, .12345); c.onConfirm(); assert.match(h.warnings.at(-1), /4 位/)
  c.setQty(part, 1.2345); c.filterText.value = 'missing'; assert.equal(c.filteredParts.value.length, 0)
  c.onCancel(); assert.equal(h.props.selections['1'], undefined); assert.deepEqual(h.events.map(e => e[0]), ['cancel', 'update:show'])
  h.props.show = false; await tick(); h.props.show = true; await tick(); assert.equal(c.selectedCount.value, 0)
  c.togglePart(part, true); c.setQty(part, 1.2345); c.onConfirm()
  assert.deepEqual(h.events.at(-1), ['confirm', { 1: 1.2345 }]); assert.equal(h.props.selections['1'], undefined); h.cleanup()
})
test('return modal source search distinguishes identical products and rejects disappeared selections', async () => {
  const h = setup({}, Return, { show: true, parts: [material(), material(2)], selections: { 1: 2 }, isMobile: false }), c = h.ctx
  c.filterText.value = 'HC2'; assert.equal(c.filteredParts.value.length, 1); assert.equal(c.selectedCount.value, 1)
  h.props.parts = [material(2)]; c.onConfirm(); assert.match(h.warnings.at(-1), /不可用/); assert.equal(h.events.length, 0); h.cleanup()
})
test('deselection preserves local input; refreshed source units match preview and payload without changing actual inputs', async () => {
  let unit = '对'
  const h = await loaded({ listHandcraftPendingReceiveItems: () => reply([output(1, { unit })]) }), c = h.ctx
  c.toggleOutput(c.pendingOutputs.value[0], true); Object.assign(c.itemInputs.output_1, { qty: 12, price: 2, weight: .5 })
  c.toggleOutput(c.pendingOutputs.value[0], false); c.toggleOutput(c.pendingOutputs.value[0], true)
  assert.equal(c.itemInputs.output_1.qty, 12); assert.equal(c.itemInputs.output_1.weight, .5)
  unit = '个'; await c.fetchPendingItems()
  assert.deepEqual(c.draftSummary.value.quantities, [{ unit: '个', qty: 12 }]); assert.equal(c.buildPayload().items[0].unit, '个'); assert.equal(c.itemInputs.output_1.price, 2); h.cleanup()
})
test('missing material sources are preserved and must be explicitly removed, never silently omitted', async () => {
  let rows = [material()]
  const h = await loaded({ listHandcraftPendingReceiveItems: () => reply(rows) }), c = h.ctx
  c.onPartConfirm({ 1: 2 }); rows = []; await c.fetchPendingItems()
  assert.equal(c.selectedParts.value[0]._unavailable, true); assert.equal(c.partReturnSel['1'], 2)
  assert.equal(c.canReview.value, false); assert.throws(c.buildPayload, /不可用/)
  c.removePart(c.selectedParts.value[0]); assert.equal(c.selectedParts.value.length, 0); assert.equal(c.partReturnSel['1'], undefined); h.cleanup()
})
test('supplier loading can retry and late receipt lookup cannot mutate an unmounted page', async () => {
  let attempts = 0
  const pending = deferred(), h = setup({ getHandcraftSuppliers: () => ++attempts === 1 ? Promise.reject(Error('offline')) : reply(['A']), getHandcraftByReceiptCode: () => pending.promise }), c = h.ctx
  await c.loadSuppliers(); assert.equal(c.supplierLoadError.value, true)
  await c.loadSuppliers(); assert.equal(c.supplierLoadError.value, false); assert.deepEqual(c.supplierOptions.value, [{ label: 'A', value: 'A' }])
  c.receiptCode.value = 'ABCDE'; const lookup = c.applyReceiptCode(); h.cleanup()
  pending.resolve({ data: { supplier_name: 'A' } }); await lookup
  assert.equal(c.supplierName.value, null); assert.equal(c.scopeCode.value, null)
})
