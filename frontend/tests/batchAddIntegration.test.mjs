import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { batchScenes, batchCatalog, makeBatchRow, batchRowError, batchPayload } from '../src/utils/batchAdd.js'
import { setupBatch, part, jewelry, colors, deferred, response } from './helpers/batchAddHarness.mjs'

test('six real entries use the shared picker and all modified templates compile', async () => {
  const entries = {
    'components/fulfillment/OrderLineEditor.vue': ['order'],
    'views/plating/PlatingDetail.vue': ['plating'],
    'views/handcraft/HandcraftDetail.vue': ['material', 'output'],
    'views/jewelries/JewelryDetail.vue': ['bom'],
    'views/purchase-orders/PurchaseOrderDetail.vue': ['purchase'],
  }
  for (const [file, scenes] of Object.entries(entries)) {
    const source = await readFile(new URL(`../src/${file}`, import.meta.url), 'utf8')
    for (const scene of scenes) assert.match(source, new RegExp(`<BatchAddDialog[^>]+scene="${scene}"`))
    const { descriptor } = parse(source)
    const script = compileScript(descriptor, { id: file })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: file, compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  }
})

test('catalog identity separates kinds and only active jewelry and composite outputs are eligible', () => {
  const jewels = [jewelry, { ...jewelry, id: 'inactive', status: 'inactive' }]
  const parts = [part, { ...part, id: 'simple', is_composite: false }]
  assert.deepEqual(batchCatalog('output', jewels, parts).map(p => p.id), ['J', 'P'])
  assert.equal(batchCatalog('order', jewels, parts).length, 3)
  assert.equal(batchCatalog('bom', jewels, parts).length, 2)
  assert.deepEqual(Object.keys(batchScenes), ['order', 'plating', 'output', 'material', 'bom', 'purchase'])
})

test('per-scene validation retains BOM precision, integer quantities, optional purchase price and 7-place prices', () => {
  const row = makeBatchRow('bom', part, 'a')
  for (const qty of [0.0001, 999999.9999]) assert.equal(batchRowError('bom', { ...row, qty }), '')
  for (const qty of [0, 0.00001, 1000000, null, NaN]) assert.ok(batchRowError('bom', { ...row, qty }))
  assert.match(batchRowError('bom', row, ['P']), /已在 BOM/)
  for (const scene of ['order', 'output', 'material', 'plating', 'purchase']) assert.match(batchRowError(scene, { ...row, qty: 1.5 }), /正整数/)
  for (const scene of ['order', 'purchase']) {
    for (const price of [0, 0.0000001, 1.1234567]) assert.equal(batchRowError(scene, { ...row, price }), '')
    for (const price of [-1, NaN, Infinity, 0.12345678, '']) assert.ok(batchRowError(scene, { ...row, price }))
  }
  assert.equal(batchRowError('purchase', { ...row, price: null }), '')
  assert.ok(batchRowError('order', { ...row, price: null }))
})

test('same-product order rows are independent and never send customer codes or unsupported unit edits', async () => {
  const h = setupBatch({ scene: 'order' })
  h.ctx.toggleProduct(jewelry, true)
  h.ctx.duplicate(h.ctx.rows.value[0])
  h.ctx.rows.value[1].qty = 3
  assert.notEqual(h.ctx.rows.value[0].key, h.ctx.rows.value[1].key)
  await h.ctx.submit()
  assert.equal(h.calls.length, 2)
  assert.deepEqual(h.calls.map(c => c[2]), [1, 3].map(quantity => ({ jewelry_id: 'J', quantity, unit_price: 1.1234567, remarks: null })))
  assert.equal(h.events.filter(e => e[0] === 'saved').length, 1)
})

test('selection filters preserve drafts, select-all is scoped and BOM cannot add an existing part', async () => {
  const h = setupBatch({ scene: 'bom', existingPartIds: ['existing'] })
  h.ctx.products.value = [part, { ...part, id: 'existing', key: 'part:existing' }, { ...part, id: 'other', key: 'part:other', name: 'other' }]
  h.ctx.query.value = '链条'
  h.ctx.selectAll(true)
  assert.equal(h.ctx.rows.value.length, 1)
  h.ctx.rows.value[0].qty = 0.25
  h.ctx.query.value = 'other'; h.ctx.selectAll(true)
  h.ctx.query.value = ''; h.ctx.selectAll(false)
  assert.equal(h.ctx.rows.value.length, 0)
  h.ctx.toggleProduct(part, true)
  h.ctx.query.value = 'no match'
  await h.ctx.submit()
  assert.equal(h.calls.length, 1)
  assert.equal(h.calls[0][2].part_id, 'P')
})

test('optional weight and note remain distinct and payloads follow each original business contract', () => {
  const row = { ...makeBatchRow('output', part, 'a'), qty: 7, weight: 0, weightUnit: 'g', note: '独立材料' }
  assert.deepEqual(batchPayload('output', row), { part_id: 'P', qty: 7, unit: '米', weight: 0, weight_unit: 'g', note: '独立材料' })
  assert.equal(batchPayload('material', { ...row, weight: null }).weight_unit, null)
  assert.equal(batchPayload('purchase', { ...row, price: null }).price, null)
  assert.equal(batchRowError('material', { ...row, weight: 0.001 }), '重量须非负，最多 2 位小数')
})

test('partial validation failure retains failed rows and retries never resend successful siblings', async () => {
  let fail = true
  const sent = []
  const h = setupBatch({ scene: 'order' }, { saveBatchRow: async (scene, id, payload) => {
    sent.push(payload)
    if (payload.part_id && fail) throw { response: { status: 422, data: { detail: '数量不符' } } }
  } })
  h.ctx.toggleProduct(jewelry, true); h.ctx.toggleProduct(part, true)
  await h.ctx.submit()
  assert.deepEqual(h.ctx.rows.value.map(r => r.status), ['saved', 'failed'])
  assert.match(h.ctx.rows.value[1].error, /数量不符/)
  h.ctx.removeRow(h.ctx.rows.value[0])
  assert.equal(h.ctx.rows.value.length, 2)
  fail = false; await h.ctx.submit()
  assert.deepEqual(sent.map(p => p.jewelry_id || p.part_id), ['J', 'P', 'P'])
})

test('transport/5xx uncertainty halts the queue, blocks all retries and keeps drafts for manual verification', async () => {
  for (const error of [new Error('timeout'), { response: { status: 500 } }]) {
    let writes = 0
    const h = setupBatch({ scene: 'order' }, { saveBatchRow: async () => { writes++; throw error } })
    h.ctx.toggleProduct(jewelry, true); h.ctx.toggleProduct(part, true)
    await h.ctx.submit(); await h.ctx.submit(); await h.ctx.refreshOnly(); await h.ctx.submit()
    assert.equal(writes, 1)
    assert.deepEqual(h.ctx.rows.value.map(r => r.status), ['uncertain', 'draft'])
    assert.equal(h.ctx.uncertain.value, true)
    assert.ok(h.events.some(e => e[0] === 'uncertain'))
  }
})

test('save and refresh phases block duplicate writes, close, edits, navigation and page unload', async () => {
  const saving = deferred(), refresh = deferred()
  const h = setupBatch({ scene: 'order', refresh: () => refresh.promise }, { saveBatchRow: () => saving.promise })
  h.ctx.toggleProduct(jewelry, true)
  const pending = h.ctx.submit()
  assert.equal(h.ctx.busy.value, true)
  h.ctx.requestClose(); h.ctx.removeRow(h.ctx.rows.value[0]); h.ctx.duplicate(h.ctx.rows.value[0]); await h.ctx.submit()
  assert.equal(h.ctx.rows.value.length, 1)
  assert.ok(h.state.guards.every(guard => guard() === false))
  let prevented = false
  h.ctx.beforeUnload({ preventDefault() { prevented = true } })
  assert.equal(prevented, true)
  saving.resolve(); await Promise.resolve(); await Promise.resolve()
  assert.equal(h.ctx.busy.value, true)
  refresh.resolve(true); await pending
  assert.equal(h.ctx.busy.value, false)
})

test('successful writes plus refresh failure do not close or become retryable; refresh-only never adds', async () => {
  let ok = false
  const h = setupBatch({ scene: 'order', refresh: async () => ok })
  h.ctx.toggleProduct(jewelry, true); await h.ctx.submit()
  assert.equal(h.ctx.refreshError.value, true)
  assert.equal(h.events.some(e => e[0] === 'close'), false)
  await h.ctx.submit()
  ok = true; await h.ctx.refreshOnly(); await h.ctx.submit()
  assert.equal(h.calls.length, 1)
  assert.equal(h.ctx.rows.value[0].status, 'saved')
})

test('permission/status changes, invalid fields and failed catalogs never write', async () => {
  const h = setupBatch({ scene: 'order' })
  h.ctx.toggleProduct(jewelry, true)
  h.props.allowed = false; await h.ctx.submit()
  h.props.allowed = true; h.ctx.rows.value[0].qty = 0; await h.ctx.submit()
  h.ctx.rows.value[0].qty = 1; h.ctx.loadError.value = 'failed'; await h.ctx.submit()
  assert.equal(h.calls.length, 0)
  h.ctx.loadError.value = ''; h.props.externalBusy = true; await h.ctx.submit()
  assert.equal(h.calls.length, 0)
})

test('plating color resolution is per-row, ignores stale responses and deselection clears the target', async () => {
  const old = deferred()
  const h = setupBatch({ scene: 'plating' }, { findOrCreateVariant: (id, { color_code }) => color_code === 'G' ? old.promise : response({ part: { id: `${id}-S` } }) })
  h.ctx.colors.value = colors; h.ctx.toggleProduct({ ...part, is_composite: false }, true)
  const row = h.ctx.rows.value[0]
  await h.ctx.selectColor(row, 'S')
  old.resolve({ data: { part: { id: 'stale-G' } } }); await Promise.resolve()
  assert.equal(row.variant.part.id, 'P-S')
  assert.equal(batchPayload('plating', row, colors).plating_method, '白K')
  await h.ctx.selectColor(row, null)
  assert.equal(batchPayload('plating', row, colors).receive_part_id, null)
  assert.equal(row.variantBusy, false)
})

test('missing plating variants require explicit confirmation and only the matching draft can create', async () => {
  const h = setupBatch({ scene: 'plating' }, { findOrCreateVariant: () => response({ suggested_name: '链条_金色' }) })
  h.ctx.colors.value = colors; h.ctx.toggleProduct(part, true)
  const row = h.ctx.rows.value[0]
  await h.ctx.selectColor(row, 'G')
  await h.ctx.submit(); assert.equal(h.calls.length, 0)
  h.ctx.confirmVariant(row)
  assert.equal(row.variant.part, undefined)
  await h.confirmations[0].onPositiveClick()
  assert.equal(row.variant.part.id, 'P-G')
  await h.ctx.submit()
  assert.equal(h.calls[0][2].receive_part_id, 'P-G')
})

test('whole-composite batch rows cannot be saved without a target and reuse a resolved SKU with its unit', async () => {
  const h = setupBatch({ scene: 'plating' }, {
    lookupPlatingTarget: async () => ({ part: { id: 'P-EP-G' }, unit: '个' }),
    createPlatingTarget: () => assert.fail('Do not recreate an existing SKU'),
  })
  h.ctx.colors.value = colors; h.ctx.toggleProduct(part, true)
  const row = h.ctx.rows.value[0]
  await h.ctx.selectColor(row, null)
  await h.ctx.submit()
  assert.match(row.error, /收回组合件/)
  assert.equal(h.calls.length, 0)
  await h.ctx.selectColor(row, 'G')
  await h.ctx.submit()
  assert.deepEqual(h.calls[0][2], { part_id: 'P', receive_part_id: 'P-EP-G', qty: 1, unit: '个', plating_method: '金', note: null, weight: null, weight_unit: null })
})

test('closing dirty drafts requires confirmation while successful rows cannot be discarded or resent', () => {
  const h = setupBatch({ scene: 'order' })
  h.ctx.toggleProduct(jewelry, true); h.ctx.requestClose()
  assert.equal(h.events.some(e => e[0] === 'close'), false)
  h.confirmations[0].onPositiveClick()
  assert.ok(h.events.some(e => e[0] === 'close'))
})

test('business adapter dispatches all six scenes to their original APIs, including BOM arguments', async () => {
  const source = await readFile(new URL('../src/api/batchAdd.js', import.meta.url), 'utf8')
  const calls = []
  const code = source.replace(/import \{ ([^}]+) \} from ['"]([^'"]+)['"]/g, (_, names, path) => path.includes('utils') ? '' : `const ${names.split(',').map(n => `${n.trim()} = (...args) => invoke('${n.trim()}', args)`).join(', ')}`)
    .replace(/export /g, '')
  const api = new Function('batchCatalog', 'invoke', `${code}; return { saveBatchRow, loadBatchCatalog }`)(batchCatalog, async (name, args) => {
    calls.push([name, ...args])
    return { data: name === 'listParts' ? [part] : name === 'listJewelries' ? [jewelry] : colors }
  })
  for (const [scene, name] of Object.entries({ order: 'addOrderItem', plating: 'addPlatingItem', output: 'addHandcraftJewelry', material: 'addHandcraftPart', purchase: 'addPurchaseOrderItem' })) {
    const payload = { part_id: 'P', qty: 2 }
    await api.saveBatchRow(scene, 'id', payload)
    assert.deepEqual(calls.pop(), [name, 'id', payload])
  }
  await api.saveBatchRow('bom', 'J', { part_id: 'P', qty_per_unit: 0.1234 })
  assert.deepEqual(calls.pop(), ['setBom', 'J', 'P', 0.1234])
  assert.equal((await api.loadBatchCatalog('output')).products.length, 2)
})

test('catalog load failures remain visible and late superseded responses cannot overwrite newer data', async () => {
  const old = deferred()
  let attempts = 0
  const h = setupBatch({}, { loadBatchCatalog: () => ++attempts === 1 ? old.promise : Promise.resolve({ products: [jewelry], colors: [] }) })
  const stale = h.ctx.loadCatalog()
  await h.ctx.loadCatalog()
  old.resolve({ products: [part], colors }); await stale
  assert.equal(h.ctx.products.value[0].id, 'J')
  h.state.api.loadBatchCatalog = async () => { throw Error('offline') }
  await h.ctx.loadCatalog()
  assert.match(h.ctx.loadError.value, /加载失败/)
})

test('status changes during a queue stop later writes instead of reusing the starting permission', async () => {
  const first = deferred()
  const h = setupBatch({ scene: 'order' }, { saveBatchRow: () => first.promise })
  h.ctx.toggleProduct(jewelry, true); h.ctx.toggleProduct(part, true)
  const sending = h.ctx.submit()
  h.props.allowed = false; first.resolve(); await sending
  assert.deepEqual(h.ctx.rows.value.map(row => row.status), ['saved', 'draft'])
})
