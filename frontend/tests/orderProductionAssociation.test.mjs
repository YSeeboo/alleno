import test from 'node:test'
import assert from 'node:assert/strict'
import { associatedSources, handcraftLinkSources, sourceQuantities } from '../src/utils/productionAllocation.js'
import { sortingPlaceholders, editableSortingIndex } from '../src/utils/handcraftBreakdown.js'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const pageSource = readFileSync(new URL('../src/views/orders/OrderProduction.vue', import.meta.url), 'utf8')
const { descriptor } = parse(pageSource)
const script = compileScript(descriptor, { id: 'production-association' })
const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const Production = (await import(moduleUrl(script.content
  .replace(/from ['"]vue['"]/g, `from ${JSON.stringify(moduleUrl(`export { ref, computed, nextTick } from ${JSON.stringify(import.meta.resolve('vue'))}; export const watch = () => {};`))}`)
  .replace(/import \{ useRoute, useRouter \} from ['"]vue-router['"]/, "const useRoute = () => ({ params: { id: 'OR-A' } }), useRouter = () => ({ push() {} })")
  .replace(/import \{ ([^}]+) \} from ['"]naive-ui['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = ${n.trim() === 'useMessage' ? '() => ({ success() {} })' : '{}'}`).join(', ')}`)
  .replace(/import (\w+) from ['"][^'"]+\.vue['"]/g, 'const $1 = {}')
  .replace(/import \{ useAuthStore \} from ['"]@\/stores\/auth['"]/, 'const useAuthStore = () => ({ hasPermission: () => true })')
  .replace(/import \{ ([^}]+) \} from ['"]@\/api\/[^'"]+['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = (...args) => globalThis.__association.api[${JSON.stringify(n.trim())}](...args)`).join(', ')}`)
  .replace(/from ['"]@\/utils\/productionAllocation['"]/, `from ${JSON.stringify(new URL('../src/utils/productionAllocation.js', import.meta.url).href)}`)
))).default

function setup(sources = [source()], api = {}) {
  const calls = [], data = { order_id: 'OR-A', editable: true, lines: structuredClone(lines), sources }
  globalThis.__association = { api: {
    getOrderProduction: async () => ({ data }), getOrder: async () => ({ data: { id: 'OR-A' } }),
    replaceOrderProduction: async (...args) => { calls.push(args) }, ...api,
  } }
  const ctx = Production.setup({}, { expose() {} })
  ctx.data.value = data
  return { ctx, calls }
}

const source = overrides => ({
  source_type: 'handcraft', source_item_id: 1, production_order_id: 'HC-A',
  product_type: 'jewelry', product_id: 'SP-1', status: 'processing', archived: false,
  planned: 40, allocated: 0, public_unallocated: 40, allocations: [], ...overrides,
})
const lines = [
  { id: 10, product_type: 'jewelry', product_id: 'SP-1', quantity: 30, allocated: 0 },
  { id: 11, product_type: 'jewelry', product_id: 'SP-1', quantity: 20, allocated: 0 },
]

test('the main handcraft table includes confirmed shares and exact historical links only', () => {
  const rows = [source({ source_item_id: 1 }),
    source({ source_item_id: 2, allocations: [{ order_id: 'OR-A', quantity: 30 }] }),
    source({ source_item_id: 3, allocations: [{ order_id: 'OR-B', quantity: 20 }] }),
    source({ source_item_id: 4, legacy_claim: true, linked_order_ids: ['OR-A'] }),
    source({ source_item_id: 5, legacy_claim: true, linked_order_ids: ['OR-B'] }),
    source({ source_item_id: 6, legacy_claim: true, customer_name: '相同客户' }),
  ]
  assert.deepEqual(associatedSources(rows, 'handcraft', 'OR-A').map(s => s.source_item_id), [2, 4])
  rows[1].allocations = []
  assert.deepEqual(associatedSources(rows, 'handcraft', 'OR-A').map(s => s.source_item_id), [4])
})

test('plating candidates keep their existing behavior; only handcraft main-list filtering changes', () => {
  const rows = [source({ source_type: 'plating' }), source()]
  assert.equal(associatedSources(rows, 'plating', 'OR-A').length, 1)
})

test('association candidates are existing active handcraft outputs, not completed or archived history', () => {
  const rows = [source(), source({ status: 'pending', source_item_id: 2 }),
    source({ status: 'completed' }), source({ archived: true }), source({ source_type: 'plating' })]
  assert.deepEqual(handcraftLinkSources(rows).map(s => s.source_item_id), [1, 2])
})

test('suggestions fill exact unmet order lines without exceeding shared production capacity', () => {
  assert.deepEqual(sourceQuantities(lines, source(), true), { 10: 30, 11: 10 })
  assert.deepEqual(sourceQuantities([{ ...lines[0], allocated: 25 }, lines[1]], source({ public_unallocated: 12 }), true), { 10: 5, 11: 7 })
  assert.deepEqual(sourceQuantities([{ ...lines[0], legacy_claim: true }, lines[1]], source(), true), { 10: 0, 11: 20 })
})

test('adjusting preserves existing shares and never silently expands another order line', () => {
  const row = source({ allocations: [{ order_id: 'OR-A', order_item_id: 10, quantity: 15 }], public_unallocated: 25 })
  assert.deepEqual(sourceQuantities(lines, row), { 10: 15, 11: 0 })
  assert.deepEqual(sourceQuantities(lines, row, true), { 10: 15, 11: 0 })
  assert.deepEqual(sourceQuantities(lines, source({ unit_mismatch: true }), true), { 10: 0, 11: 0 })
})

test('allocated 30 plus remaining 10 must not become a bulk-editable physical 40 row', () => {
  const groups = [{ kind: 'jewelry', jewelry_id: 'SP-1', quantity_managed: true, entries: [
    { hc_jewelry_item_id: 1, qty: 30, customer_name: '客户 a', is_locked: true, quantity_managed: true, source_allocation_id: 99 },
    { hc_jewelry_item_id: 1, qty: 10, customer_name: null, is_locked: false, quantity_managed: true, is_quantity_remainder: true },
  ] }]
  assert.deepEqual(sortingPlaceholders(groups), [])
  assert.equal(editableSortingIndex(groups).size, 0)
  assert.equal(groups[0].entries.reduce((total, entry) => total + entry.qty, 0), 40)
})

test('independent legacy manual placeholders remain editable beside allocated shares', () => {
  const group = { kind: 'jewelry', jewelry_id: 'SP-1', quantity_managed: true, entries: [
    { hc_jewelry_item_id: 1, qty: 30, customer_name: '客户 a', is_locked: true, quantity_managed: true },
    { hc_jewelry_item_id: 1, qty: 10, is_quantity_remainder: true },
    { hc_jewelry_item_id: 2, qty: 5, customer_name: ' ', is_locked: false },
    { hc_jewelry_item_id: 3, qty: 4, customer_name: '手填客户', is_locked: false },
  ] }
  assert.deepEqual(sortingPlaceholders([group]).map(row => row.hc_jewelry_item_id), [2])
  assert.deepEqual([...editableSortingIndex([group]).keys()], [2, 3])
})

test('real association modal renders grouped existing orders with output-level actions instead of dropdowns', () => {
  assert.doesNotMatch(pageSource, /linkOrderOptions|linkOutputOptions|selectLinkOrder/)
  assert.equal((pageSource.match(/<n-select\b/g) || []).length, 1, 'the only dropdown is the supplier filter, not output selection')
  assert.match(pageSource, /<n-select v-model:value="linkSupplier" :options="linkSupplierOptions" filterable clearable :disabled="saving"/)
  assert.match(pageSource, /v-for="group in linkGroups"/)
  assert.match(pageSource, /v-for="source in group.sources" :key="source.source_item_id"/)
  assert.match(pageSource, /@click="selectLinkOutput\(source.source_item_id\)"/)
  for (const text of ['分配给本单', '本单已分配', '未分配', '旧归属待核对', '没有找到匹配的手工单']) assert.ok(pageSource.includes(text))
  const template = compileTemplate({ source: descriptor.template.content, filename: 'OrderProduction.vue', id: 'production-association', compilerOptions: { bindingMetadata: script.bindings } })
  assert.deepEqual(template.errors, [])
})

test('grouping and search preserve separate matching outputs under the same handcraft order', () => {
  const { ctx } = setup([source({ supplier_name: '商家甲', product_name: '珍珠项链' }), source({ source_item_id: 2, supplier_name: '商家甲', product_name: '手链' }),
    source({ source_item_id: 3, production_order_id: 'HC-B', supplier_name: '商家乙' }), source({ status: 'completed' }), source({ archived: true })])
  assert.deepEqual(ctx.linkGroups.value.map(group => [group.id, group.sources.map(s => s.source_item_id)]), [['HC-B', [3]], ['HC-A', [1, 2]]])
  for (const keyword of [' hc-a ', '商家甲', 'sp-1']) {
    ctx.linkSearch.value = keyword
    assert.equal(ctx.linkGroups.value.find(group => group.id === 'HC-A').sources.length, 2)
  }
  ctx.linkSearch.value = '手链'
  assert.deepEqual(ctx.linkGroups.value[0].sources.map(s => s.source_item_id), [2])
  ctx.linkSearch.value = '不存在'
  assert.deepEqual(ctx.linkGroups.value, [])
})

test('selecting an exact output only edits a draft, preserves duplicate lines and waits for confirmation', async () => {
  const { ctx, calls } = setup([source(), source({ source_item_id: 2, public_unallocated: 12, revision: 8, allocations: [{ order_id: 'OR-B', order_item_id: 99, quantity: 28 }] })])
  ctx.openLinker()
  ctx.selectLinkOutput(2)
  assert.equal(ctx.selected.value.source_item_id, 2)
  assert.deepEqual(ctx.quantities.value, { 10: 12, 11: 0 })
  assert.deepEqual(calls, [])
  ctx.quantities.value = { 10: 5, 11: 7 }
  ctx.selectLinkOutput(2)
  assert.deepEqual(ctx.quantities.value, { 10: 5, 11: 7 }, 'clicking the selected row cannot reset its draft')
  await ctx.save()
  assert.deepEqual(calls, [['OR-A', { source_type: 'handcraft', source_item_id: 2, revision: 8, allocations: [{ order_item_id: 10, quantity: 5 }, { order_item_id: 11, quantity: 7 }] }]])
  assert.equal(ctx.showEditor.value, false)
  assert.deepEqual(ctx.selected.value.allocations, [{ order_id: 'OR-B', order_item_id: 99, quantity: 28 }])
})

test('existing shares are retained, switching outputs is exact and cancelling then reopening clears drafts', () => {
  const { ctx, calls } = setup([source({ allocations: [{ order_id: 'OR-A', order_item_id: 11, quantity: 8 }] }), source({ source_item_id: 2 })])
  ctx.openLinker(); ctx.selectLinkOutput(1)
  assert.deepEqual(ctx.quantities.value, { 10: 0, 11: 8 })
  ctx.selectLinkOutput(2)
  assert.deepEqual(ctx.quantities.value, { 10: 30, 11: 10 })
  ctx.quantities.value[10] = 6
  ctx.showEditor.value = false
  ctx.linkSearch.value = 'something'
  ctx.linkSupplier.value = '商家甲'
  ctx.openLinker()
  assert.equal(ctx.selected.value, null)
  assert.deepEqual(ctx.quantities.value, {})
  assert.equal(ctx.linkSearch.value, '')
  assert.equal(ctx.linkSupplier.value, null)
  assert.deepEqual(calls, [])
})

test('historical conflicts, unit mismatch, ineligible sources and closed orders cannot be selected or saved', async () => {
  for (const overrides of [{ legacy_claim: true }, { unit_mismatch: true }, { status: 'completed' }, { archived: true }, { source_type: 'plating' }, { product_id: 'no-match' }]) {
    const { ctx, calls } = setup([source(overrides)])
    ctx.openLinker(); ctx.selectLinkOutput(1)
    assert.equal(ctx.selected.value, null, JSON.stringify(overrides))
    await ctx.save()
    assert.deepEqual(calls, [])
  }
  const { ctx, calls } = setup()
  ctx.data.value.lines.forEach(line => { line.legacy_claim = true })
  ctx.openLinker(); ctx.selectLinkOutput(1)
  assert.equal(ctx.selected.value, null)
  ctx.data.value.lines.forEach(line => { line.legacy_claim = false })
  ctx.selectLinkOutput(1)
  ctx.data.value.editable = false
  await ctx.save()
  assert.deepEqual(calls, [])
  ctx.showEditor.value = false; ctx.openLinker()
  assert.equal(ctx.showEditor.value, false)
})

test('zero and invalid shares cannot confirm an association; failed saves keep selected output and draft', async () => {
  const { ctx, calls } = setup()
  ctx.openLinker(); ctx.selectLinkOutput(1)
  for (const quantities of [{ 10: 0, 11: 0 }, { 10: 1.5, 11: 0 }, { 10: null, 11: 0 }]) {
    ctx.quantities.value = quantities
    await ctx.save()
    assert.ok(ctx.saveError.value)
    assert.equal(ctx.showEditor.value, true)
    assert.deepEqual(calls, [])
  }
  globalThis.__association.api.replaceOrderProduction = async () => { throw { response: { data: { detail: '份额版本已变化，请刷新核对' } } } }
  ctx.quantities.value = { 10: 20, 11: 5 }
  await ctx.save()
  assert.equal(ctx.saveError.value, '份额版本已变化，请刷新核对')
  assert.deepEqual(ctx.quantities.value, { 10: 20, 11: 5 })
  assert.equal(ctx.showEditor.value, true)
  assert.equal(ctx.saving.value, false)
})

test('a pending confirmation freezes output selection and prevents duplicate writes', async () => {
  let finish
  const calls = []
  const { ctx } = setup([source(), source({ source_item_id: 2 })], { replaceOrderProduction: (...args) => { calls.push(args); return new Promise(resolve => { finish = resolve }) } })
  ctx.openLinker(); ctx.selectLinkOutput(1)
  const pending = ctx.save()
  assert.equal(ctx.saving.value, true)
  ctx.selectLinkOutput(2); ctx.openLinker()
  assert.equal(ctx.selected.value.source_item_id, 1)
  await ctx.save()
  assert.equal(calls.length, 1)
  finish(); await pending
  assert.equal(ctx.saving.value, false)
  assert.match(pageSource, /:close-on-esc="!saving"/)
})

test('handcraft orders sort by descending natural order number without changing output or input identities', () => {
  const sources = [source({ production_order_id: 'HC-9', source_item_id: 1 }), source({ production_order_id: 'HC-0010', source_item_id: 2 }),
    source({ production_order_id: 'HC-2', source_item_id: 3 }), source({ production_order_id: 'HC-0010', source_item_id: 4 })]
  const { ctx } = setup(sources)
  assert.deepEqual(ctx.linkGroups.value.map(group => group.id), ['HC-0010', 'HC-9', 'HC-2'])
  assert.deepEqual(ctx.linkGroups.value[0].sources.map(s => s.source_item_id), [2, 4])
  assert.deepEqual(sources.map(s => s.source_item_id), [1, 2, 3, 4], 'sorting must not mutate API data')
})

test('supplier filter uses exact names, composes with search and clears independently', () => {
  const { ctx, calls } = setup([source({ supplier_name: '商家甲', production_order_id: 'HC-1' }),
    source({ supplier_name: '商家甲', source_item_id: 2, production_order_id: 'HC-2' }),
    source({ supplier_name: '商家甲分店', source_item_id: 3, production_order_id: 'HC-3' }),
    source({ supplier_name: null, source_item_id: 4, production_order_id: 'HC-4' }),
    source({ supplier_name: '无关商家', source_item_id: 5, product_id: 'unrelated' })])
  assert.equal(ctx.linkSupplierOptions.value.length, 3, 'duplicate suppliers are deduplicated and unrelated suppliers excluded')
  assert.ok(ctx.linkSupplierOptions.value.some(option => option.value === '' && option.label === '未填写商家'))
  ctx.linkSupplier.value = '商家甲'
  assert.deepEqual(ctx.linkGroups.value.map(group => group.id), ['HC-2', 'HC-1'])
  ctx.linkSearch.value = 'hc-1'
  assert.deepEqual(ctx.linkGroups.value.map(group => group.id), ['HC-1'])
  assert.equal(ctx.linkSupplierOptions.value.length, 3, 'search must not erase other supplier options')
  ctx.linkSearch.value = 'HC-3'
  assert.deepEqual(ctx.linkGroups.value, [])
  ctx.linkSupplier.value = null
  assert.deepEqual(ctx.linkGroups.value.map(group => group.id), ['HC-3'])
  ctx.linkSearch.value = ''
  ctx.linkSupplier.value = ''
  assert.deepEqual(ctx.linkGroups.value.map(group => group.id), ['HC-4'])
  assert.deepEqual(calls, [])
})

test('unrelated products and product types are excluded before grouping even in a mixed handcraft order', () => {
  const { ctx } = setup([source({ source_item_id: 1, production_order_id: 'HC-1' }),
    source({ source_item_id: 2, production_order_id: 'HC-1', product_id: 'unrelated' }),
    source({ source_item_id: 3, production_order_id: 'HC-2', product_id: 'unrelated' }),
    source({ source_item_id: 4, production_order_id: 'HC-3', product_type: 'part', product_id: 'SP-1' }),
    source({ source_item_id: 5, production_order_id: 'HC-4', unit_mismatch: true }),
    source({ source_item_id: 6, production_order_id: 'HC-5', legacy_claim: true })])
  assert.deepEqual(ctx.linkGroups.value.map(group => [group.id, group.sources.map(s => s.source_item_id)]), [['HC-5', [6]], ['HC-4', [5]], ['HC-1', [1]]])
  ctx.openLinker(); ctx.selectLinkOutput(2)
  assert.equal(ctx.selected.value, null)
  ctx.data.value.lines = []
  assert.deepEqual(ctx.linkSources.value, [])
  assert.deepEqual(ctx.linkGroups.value, [])
  assert.deepEqual(ctx.linkSupplierOptions.value, [])
})

test('changing list filters preserves an explicit selected draft without creating writes', () => {
  const { ctx, calls } = setup([source({ supplier_name: '商家甲' }), source({ source_item_id: 2, supplier_name: '商家乙', production_order_id: 'HC-B' })])
  ctx.openLinker(); ctx.selectLinkOutput(1)
  ctx.quantities.value = { 10: 5, 11: 7 }
  ctx.linkSupplier.value = '商家乙'
  assert.deepEqual(ctx.linkGroups.value.map(group => group.id), ['HC-B'])
  assert.equal(ctx.selected.value.source_item_id, 1)
  assert.deepEqual(ctx.quantities.value, { 10: 5, 11: 7 })
  assert.deepEqual(calls, [])
})
