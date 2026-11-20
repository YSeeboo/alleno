import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import * as D from '../src/utils/orderManagement.js'

const source = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')
const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const runtime = moduleUrl(`
  export { ref, reactive, computed, h } from ${JSON.stringify(import.meta.resolve('vue'))};
  export const onMounted = fn => globalThis.__orderPages.mounted.push(fn);
  export const watch = (...args) => globalThis.__orderPages.watches.push(args);
`)
const router = moduleUrl(`
  export const useRouter = () => ({ push: value => { globalThis.__orderPages.navigation.push(value); return globalThis.__orderPages.navigate?.(value); } });
  export const onBeforeRouteLeave = fn => globalThis.__orderPages.guards.push(fn);
`)
async function component(path) {
  const { descriptor } = parse(source(path))
  const code = compileScript(descriptor, { id: path }).content
    .replace(/from ['"]vue['"]/g, `from ${JSON.stringify(runtime)}`)
    .replace(/from ['"]vue-router['"]/g, `from ${JSON.stringify(router)}`)
    .replace(/import \{ ([^}]+) \} from ['"]naive-ui['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = ${n.trim() === 'useMessage' ? '() => globalThis.__orderPages.message' : n.trim() === 'useDialog' ? '() => globalThis.__orderPages.dialog' : '{}'}`).join(', ')}`)
    .replace(/import \{ ([^}]+) \} from ['"]@\/api\/[^'"]+['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = (...args) => globalThis.__orderPages.api[${JSON.stringify(n.trim())}](...args)`).join(', ')}`)
    .replace(/from ['"]@\/utils\/(orderManagement|fulfillment|date)['"]/g, (_, name) => `from ${JSON.stringify(new URL(`../src/utils/${name}.js`, import.meta.url).href)}`)
    .replace(/import \{ ([^}]+) \} from ['"]@\/utils\/ui['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = value => value`).join(', ')}`)
    .replace(/import \w+ from ['"][^'"]+\.vue['"]/g, 'const OrderCreateLines = {}')
    .replace(/import ['"][^'"]+\.css['"]/g, '')
  return (await import(moduleUrl(code))).default
}
const List = await component('views/orders/OrderList.vue')
const Create = await component('views/orders/OrderCreate.vue')
function setup(Component, api = {}) {
  const calls = [], notices = [], dialogs = []
  const state = {
    api: new Proxy(api, { get: (target, name) => target[name] || (async (...args) => { calls.push([name, ...args]); return { data: [] } }) }),
    message: Object.fromEntries(['warning', 'error', 'success'].map(type => [type, text => notices.push([type, text])])),
    dialog: { warning: options => dialogs.push(options) }, mounted: [], watches: [], navigation: [], guards: [],
  }
  globalThis.__orderPages = state
  const ctx = Component.setup({}, { expose() {} })
  return { ctx, state, calls, notices, dialogs }
}
const orders = [
  { id: 'OR-3', customer_name: 'MORI', status: '生产中', created_at: '2026-11-20', total_amount: 30 },
  { id: 'OR-2', customer_name: 'Mori', status: '已完成', created_at: '2026-11-18', total_amount: 100 },
  { id: 'OR-1', customer_name: '旧记录', status: '待生产', created_at: '2026-11-17', total_amount: 10 },
]
const summary = { order_id: 'OR-3', managed: true, completed_items: 1, total_items: 3, lines: [{ reserved: 20, unit: '条' }, { reserved: 5, unit: '条' }, { reserved: 10, unit: '个' }] }
const jewelry = { id: 'J-1', name: '项链', image: '/test.png', unit: '条', wholesale_price: 28.1234567 }
const part = { id: 'P-1', name: '扣头', unit: '个', wholesale_price: 0.1234567 }
const catalogs = { listJewelries: async () => ({ data: [jewelry] }), listParts: async () => ({ data: [part] }) }
async function draft(api = {}) {
  const result = setup(Create, { ...catalogs, ...api })
  await result.ctx.loadCatalog()
  result.ctx.customerName.value = '客户'
  result.ctx.addJewelryLine()
  const line = result.ctx.jewelryItems[0]
  line.jewelry_id = jewelry.id
  result.ctx.onJewelrySelect(line, jewelry.id)
  line.quantity = 100
  return result
}

test('real approved list/create templates compile and remain independent of the public demo and shell', () => {
  for (const path of ['views/orders/OrderList.vue', 'views/orders/OrderCreate.vue', 'components/fulfillment/OrderCreateLines.vue']) {
    const text = source(path), { descriptor, errors } = parse(text)
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: path })
    const template = compileTemplate({ source: descriptor.template.content, filename: path, id: path, compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [], path)
    assert.doesNotMatch(text, /public\/demos|order-management\/domain|填入示例|创建演示|清空表单|交货日期|交期|floating-bar/)
    assert.match(text, /<n-button/)
  }
  assert.match(source('views/orders/OrderList.vue'), /<n-data-table/)
  assert.match(source('views/orders/OrderCreate.vue'), /:loading="submitting"/)
  assert.match(source('components/fulfillment/OrderCreateLines.vue'), /:key="item.key"/)
  const css = source('styles/order-management.css')
  assert.doesNotMatch(css, /@import|\.n-layout|\.sidebar|position:\s*fixed/)
  assert.match(css, /\.order-management \.om-entry-table \{[^}]*overflow: visible/)
  assert.match(css, /position: sticky; left: 0/)
  assert.match(css, /\.order-management \.om-create-layout \{ display: grid/)
})

test('real filtering composes case-insensitive search, status, known history, and sorting without mutating orders', () => {
  const before = structuredClone(orders), summaries = { 'OR-2': { managed: false }, 'OR-3': summary }
  assert.deepEqual(D.filterOrderRows(orders, summaries, { search: '  mori ', status: '生产中' }).map(o => o.id), ['OR-3'])
  assert.deepEqual(D.filterOrderRows(orders, summaries, { history: true }).map(o => o.id), ['OR-2'])
  assert.deepEqual(D.filterOrderRows(orders, summaries, { history: true, status: '待生产' }), [])
  assert.deepEqual(D.filterOrderRows(orders, summaries, { sort: 'amount' }).map(o => o.id), ['OR-2', 'OR-3', 'OR-1'])
  assert.deepEqual(orders, before)
})

test('reserved units stay separate and missing summaries never become verified historical/deleteable records', () => {
  assert.equal(D.reservedOrderText(summary), '25 条 / 10 个')
  assert.match(D.reservedOrderText(undefined), /加载失败/)
  assert.equal(D.reservedOrderText({ managed: false }), '—')
  assert.equal(D.reservedOrderText({ managed: true, lines: [] }), '无待发预留')
  assert.equal(D.canDeleteOrder(orders[2], undefined), false)
  assert.equal(D.canDeleteOrder(orders[2], { managed: true }), false)
  assert.equal(D.canDeleteOrder(orders[1], { managed: false }), false)
  assert.equal(D.canDeleteOrder(orders[2], { managed: false }), true)
})

test('list loads summaries in batches, retains successful batches and clears stale eligibility on failed refresh', async () => {
  const data = Array.from({ length: 101 }, (_, i) => ({ ...orders[2], id: `OR-${i}` }))
  const sizes = []
  const { ctx, state } = setup(List, { listOrders: async () => ({ data }), getFulfillmentBatch: async ids => {
    sizes.push(ids.length)
    if (ids.length === 1) throw Error('offline')
    return { data: ids.map(order_id => ({ order_id, managed: false })) }
  } })
  await ctx.load()
  assert.deepEqual(sizes, [100, 1])
  assert.equal(Object.keys(ctx.summaries.value).length, 100)
  assert.match(ctx.error.value, /部分订单出货摘要加载失败/)
  ctx.historyOnly.value = true
  assert.equal(ctx.filtered.value.length, 100)
  state.api.listOrders = async () => { throw Error('offline') }
  await ctx.load()
  assert.equal(ctx.loaded.value, false)
  assert.deepEqual(ctx.summaries.value, {})
  assert.equal(ctx.filtered.value.length, 0)
})

test('list pagination/reset is local and unknown progress cannot start a delete preview', async () => {
  const { ctx, calls } = setup(List)
  ctx.orders.value = Array.from({ length: 9 }, (_, i) => ({ ...orders[0], id: `OR-${i}` }))
  assert.equal(ctx.pagedOrders.value.length, 7)
  ctx.page.value = 2
  assert.equal(ctx.pagedOrders.value.length, 2)
  ctx.search.value = 'not found'
  ctx.clearFilters()
  assert.equal(ctx.page.value, 1)
  assert.equal(ctx.filtered.value.length, 9)
  await ctx.confirmDelete(orders[2])
  assert.deepEqual(calls, [])
})

test('delete keeps server preview counts and requires explicit confirmation before an exact-id delete', async () => {
  const calls = []
  const { ctx, dialogs } = setup(List, {
    getOrderDeletePreview: async id => { calls.push(['preview', id]); return { data: { item_count: 3, batch_count: 2, link_count: 4 } } },
    deleteOrder: async id => { calls.push(['delete', id]); return { data: {} } },
  })
  ctx.summaries.value = { 'OR-1': { managed: false } }
  await ctx.confirmDelete(orders[2])
  assert.deepEqual(calls, [['preview', 'OR-1']])
  assert.match(dialogs[0].content, /3 个明细、2 个旧批次及 4 个旧生产关联/)
  await dialogs[0].onPositiveClick()
  assert.deepEqual(calls, [['preview', 'OR-1'], ['delete', 'OR-1']])
})

test('rejected delete preview opens no confirmation; rejected delete keeps dialog open and releases busy', async () => {
  const { ctx, dialogs, state } = setup(List, { getOrderDeletePreview: async () => { throw Error('guard') } })
  ctx.summaries.value = { 'OR-1': { managed: false } }
  await ctx.confirmDelete(orders[2])
  assert.equal(dialogs.length, 0)
  assert.equal(ctx.deleting.value, false)
  state.api.getOrderDeletePreview = async () => ({ data: {} })
  state.api.deleteOrder = async () => { throw Error('conflict') }
  await ctx.confirmDelete(orders[2])
  assert.equal(await dialogs[0].onPositiveClick(), false)
  assert.equal(ctx.deleting.value, false)
})

test('real exact totals retain seven decimal places and different units without importing demo arithmetic', () => {
  const line = { jewelry_id: 'J-1', quantity: 100, unit_price: 28.1234567 }
  const totals = D.orderDraftTotals([line], [{ part_id: 'P-1', quantity: 200, unit_price: 0.1234567 }], { 'J-1': jewelry }, { 'P-1': part })
  assert.equal(D.formatOrderAmount(totals.total), '2,837.03701')
  assert.equal(totals.units, '100 条 / 200 个')
  assert.equal(D.formatOrderAmount(D.orderPriceUnits(0.0000001)), '0.0000001')
  assert.throws(() => D.orderPriceUnits(0.00000001))
  assert.equal(D.orderDraftTotals([{ ...line, quantity: null }], [], { 'J-1': jewelry }, {}).invalid, true)
})

test('create loads active image-aware catalogs, prefills prices, and keeps duplicate row keys independent after deletion', async () => {
  const { ctx } = await draft()
  assert.equal(ctx.jewelryOptions.value[0].image, '/test.png')
  assert.equal(ctx.jewelryItems[0].unit_price, 28.1234567)
  ctx.addJewelryLine()
  ctx.jewelryItems[1].jewelry_id = jewelry.id
  ctx.onJewelrySelect(ctx.jewelryItems[1], jewelry.id)
  ctx.jewelryItems[1].remarks = '独立备注'
  ctx.removeLine(ctx.jewelryItems, ctx.jewelryItems[0].key)
  const key = ctx.jewelryItems[0].key
  ctx.addJewelryLine()
  assert.notEqual(ctx.jewelryItems[1].key, key)
  assert.equal(ctx.jewelryItems[0].remarks, '独立备注')
  ctx.onJewelrySelect(ctx.jewelryItems[0], null)
  assert.equal(ctx.jewelryItems[0].unit_price, 0)
})

test('create payload and success route preserve the API contract without sending client row keys', async () => {
  let payload
  const { ctx, state } = await draft({ createOrder: async data => { payload = data; return { data: { id: 'OR-NEW' } } } })
  ctx.addPartLine()
  Object.assign(ctx.partItems[0], { part_id: part.id, quantity: 200, unit_price: 0.1234567, remarks: '配件备注' })
  ctx.jewelryItems[0].remarks = '饰品备注'
  ctx.hasBarcode.value = true
  ctx.createdAtTs.value = new Date(2026, 10, 20).getTime()
  await ctx.submit()
  assert.deepEqual(payload, { customer_name: '客户', items: [{ jewelry_id: 'J-1', quantity: 100, unit_price: 28.1234567, remarks: '饰品备注' }, { part_id: 'P-1', quantity: 200, unit_price: 0.1234567, remarks: '配件备注' }], has_barcode: true, created_at: '2026-11-20' })
  assert.deepEqual(state.navigation, ['/orders/OR-NEW'])
  assert.equal(ctx.submitting.value, false)
})

test('blank customer, empty rows, missing product and invalid quantities/prices produce no create request', async () => {
  const cases = [ctx => { ctx.customerName.value = '  ' }, ctx => { ctx.jewelryItems.splice(0) }, ctx => { ctx.jewelryItems[0].jewelry_id = null }, ...[null, 0, -1, 1.5, Infinity].map(quantity => ctx => { ctx.jewelryItems[0].quantity = quantity }), ...[null, -1, Infinity, 0.12345678].map(price => ctx => { ctx.jewelryItems[0].unit_price = price })]
  for (const change of cases) {
    const { ctx, calls } = await draft()
    change(ctx); await ctx.submit()
    assert.equal(calls.some(([name]) => name === 'createOrder'), false)
    assert.ok(ctx.submitError.value)
    assert.equal(ctx.submitting.value, false)
  }
})

test('creation prevents duplicate submits, row edits and navigation while pending but allows successful detail navigation', async () => {
  let resolve, requests = 0
  const { ctx, state } = await draft({ createOrder: () => { requests++; return new Promise(done => { resolve = done }) } })
  const pending = ctx.submit()
  assert.equal(ctx.submitting.value, true)
  assert.equal(state.guards[0](), false)
  await ctx.submit(); ctx.addPartLine(); ctx.removeLine(ctx.jewelryItems, ctx.jewelryItems[0].key)
  assert.equal(requests, 1)
  assert.equal(ctx.partItems.length, 0)
  assert.equal(ctx.jewelryItems.length, 1)
  state.navigate = () => { assert.equal(state.guards[0](), true) }
  resolve({ data: { id: 'OR-NEW' } }); await pending
  assert.equal(ctx.submitting.value, false)
})

test('catalog and submit failures are visible and preserve entered data without inventing success', async () => {
  const { ctx, state, notices } = await draft({ createOrder: async () => { throw { response: { data: { detail: '服务暂不可用' } } } } })
  await ctx.submit()
  assert.equal(ctx.submitError.value, '服务暂不可用')
  assert.equal(ctx.jewelryItems.length, 1)
  assert.equal(ctx.customerName.value, '客户')
  assert.deepEqual(state.navigation, [])
  assert.equal(notices.some(([type]) => type === 'success'), false)
  state.api.listParts = async () => { throw Error('offline') }
  await ctx.loadCatalog()
  assert.match(ctx.catalogError.value, /商品加载失败/)
  assert.equal(ctx.editingDisabled.value, true)
  assert.equal(ctx.jewelryItems.length, 1)
  state.api.listParts = catalogs.listParts
  await ctx.loadCatalog()
  assert.equal(ctx.catalogError.value, '')
  assert.equal(ctx.editingDisabled.value, false)
})

test('part-only zero-price order is valid and optional creation date stays omitted', async () => {
  let payload
  const { ctx } = await draft({ createOrder: async data => { payload = data; return { data: { id: 'OR-PART' } } } })
  ctx.jewelryItems.splice(0); ctx.addPartLine()
  Object.assign(ctx.partItems[0], { part_id: part.id, quantity: 1, unit_price: 0 })
  await ctx.submit()
  assert.equal(payload.items.length, 1)
  assert.equal(payload.items[0].part_id, part.id)
  assert.equal(payload.items[0].unit_price, 0)
  assert.equal('created_at' in payload, false)
})
