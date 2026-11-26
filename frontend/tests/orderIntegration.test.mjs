import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { reactive } from 'vue'
import { makeBatchRow, batchPayload } from '../src/utils/batchAdd.js'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const runtime = moduleUrl(`
  export { ref, reactive, computed, h, nextTick } from ${JSON.stringify(import.meta.resolve('vue'))};
  export const watch = (source, action, options) => globalThis.__orderIntegration.watches.push({ source, action, options });
  export const onMounted = fn => globalThis.__orderIntegration.mounted.push(fn);
`)
const router = moduleUrl(`
  export const RouterLink = {};
  export const useRoute = () => globalThis.__orderIntegration.route;
  export const useRouter = () => ({ push: value => globalThis.__orderIntegration.navigation.push(value) });
  export const onBeforeRouteLeave = fn => globalThis.__orderIntegration.guards.push(fn);
  export const onBeforeRouteUpdate = onBeforeRouteLeave;
`)
const read = path => readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')
async function component(path) {
  const source = await read(path)
  const { descriptor } = parse(source)
  const compiled = compileScript(descriptor, { id: `integration-${path}` })
  const code = compiled.content
    .replace(/from ['"]vue['"]/g, `from ${JSON.stringify(runtime)}`)
    .replace(/from ['"]vue-router['"]/g, `from ${JSON.stringify(router)}`)
    .replace(/import \{ ([^}]+) \} from ['"]naive-ui['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = ${n.trim() === 'useMessage' ? '() => globalThis.__orderIntegration.message' : '{}'}`).join(', ')}`)
    .replace(/import \{ ([^}]+) \} from ['"]@\/api\/[^'"]+['"]/g, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = (...args) => globalThis.__orderIntegration.api[${JSON.stringify(n.trim())}](...args)`).join(', ')}`)
    .replace(/import (\w+) from ['"][^'"]+\.vue['"]/g, 'const $1 = {}')
    .replace(/import \{ useIsMobile \} from ['"][^'"]+['"]/, 'const useIsMobile = () => ({ isMobile: false })')
    .replace(/from ['"]@\/utils\/date['"]/, `from ${JSON.stringify(new URL('../src/utils/date.js', import.meta.url).href)}`)
    .replace(/from ['"]@\/utils\/orderReadinessFilter['"]/, `from ${JSON.stringify(new URL('../src/utils/orderReadinessFilter.js', import.meta.url).href)}`)
    .replace(/from ['"]@\/utils\/orderMaterialGroups['"]/, `from ${JSON.stringify(new URL('../src/utils/orderMaterialGroups.js', import.meta.url).href)}`)
    .replace(/import \{ ([^}]+) \} from ['"]@\/utils\/ui['"]/, (_, names) => `const ${names.split(',').map(n => `${n.trim()} = value => value`).join(', ')}`)
  return (await import(moduleUrl(code))).default
}
const Information = await component('components/fulfillment/OrderInformation.vue')
const Costs = await component('components/fulfillment/OrderCosts.vue')
const Editor = await component('components/fulfillment/OrderLineEditor.vue')
const Materials = await component('components/fulfillment/OrderMaterials.vue')
const Detail = await component('views/orders/OrderDetail.vue')
const InfoPage = await component('views/orders/OrderInfo.vue')

function setup(Component, props, api = {}) {
  const calls = [], events = [], notices = []
  const state = { api: new Proxy(api, { get: (target, name) => target[name] || (async (...args) => { calls.push([name, ...args]); return { data: [] } }) }),
    watches: [], mounted: [], guards: [], navigation: [], route: reactive({ params: { id: 'OR-1' }, query: {} }),
    message: Object.fromEntries(['warning', 'success', 'error'].map(name => [name, text => notices.push([name, text])])),
  }
  globalThis.__orderIntegration = state
  const ctx = Component.setup(props, { expose() {}, emit: (...e) => events.push(e) })
  return { ctx, state, calls, events, notices }
}
const order = { id: 'OR-1', customer_name: '客户', created_at: '2026-11-19T12:00:00', packaging_cost: 0 }
const line = { id: 7, product_type: 'jewelry', product_id: 'J', quantity: 10, unit_price: '0.1234567', customer_code: 'A01', remarks: '本行' }

test('real product-detail readiness toggle hides only prepared rows, retains unknown history and leaves summary intact', () => {
  const { ctx, state, calls } = setup(Detail, {})
  ctx.data.value = { total_items: 3, reserved_ready_items: 1, lines: [{ ...line, id: 1, gap: 0 }, { ...line, id: 2, gap: 4 }, { ...line, id: 3, gap: null }] }
  assert.deepEqual(ctx.visibleLines.value.map(l => l.id), [1, 2, 3])
  ctx.readinessFilter.value = 'pending'
  assert.deepEqual(ctx.visibleLines.value.map(l => l.id), [2, 3])
  assert.equal(ctx.pendingLineCount.value, 2)
  assert.equal(ctx.unknownGapCount.value, 1)
  assert.equal(ctx.data.value.total_items, 3)
  assert.equal(ctx.data.value.lines.length, 3)
  state.watches.find(w => w.source === ctx.orderId).action()
  assert.equal(ctx.readinessFilter.value, 'all')
  assert.deepEqual(calls, [])
})

test('workspace tabs put order information last; old URL preserves its query/hash', async () => {
  const header = await read('components/fulfillment/OrderWorkspaceHeader.vue')
  assert.deepEqual([...header.matchAll(/<n-tab name="([^"]+)">([^<]+)</g)].map(m => [m[1], m[2]]), [['fulfillment', '商品详情'], ['production', '生产安排'], ['information', '订单信息']])
  assert.match(header, /information: '\/information'/)
  assert.match(header, /getHandcraftSummaryReturn\(route.query\)/)
  assert.match(header, /query: route.query/)
  const routes = await read('router/index.js')
  assert.match(routes, /path: 'orders\/:id\/information'.*OrderInfo\.vue.*perm: 'orders'/)
  assert.match(routes, /orders\/:id\/records', redirect: to => \(\{ path: `\/orders\/\$\{to.params.id\}`, query: to.query, hash: to.hash/)
  await assert.rejects(read('views/orders/OrderLegacyDetail.vue'), { code: 'ENOENT' })
})

test('product details retains products/costs while metadata lives only in the information tab', async () => {
  const view = await read('views/orders/OrderDetail.vue')
  assert.equal((view.match(/<tr v-for="line in visibleLines"/g) || []).length, 1)
  for (const name of ['OrderCosts', 'OrderLineEditor', 'ReservationDialog', 'ShipmentTable']) assert.match(view, new RegExp(`<${name}`))
  assert.doesNotMatch(view, /OrderInformation|informationBusy/)
  const information = await read('views/orders/OrderInfo.vue')
  assert.match(information, /active="information"/)
  assert.match(information, /<OrderInformation[^>]+:editable="canEdit"[^>]+@saved="load"/)
  assert.doesNotMatch(information, /<OrderCosts|<ShipmentTable/)
  assert.match(view, /已全部发货/)
  assert.doesNotMatch(view, /changeStatus\('已完成'\)|订单资料与旧流程/)
})

test('closed information and packaging cannot start any writes', async () => {
  const info = setup(Information, { order, editable: false })
  await info.ctx.persist({ note: '禁止' })
  assert.deepEqual(info.calls, [])
  const costs = setup(Costs, { order, editable: false })
  await costs.ctx.save()
  assert.deepEqual(costs.calls, [])
})

test('metadata save emits busy until request resolves and keeps errors from becoming success', async () => {
  let reject
  const { ctx, events } = setup(Information, { order, editable: true }, { updateExtraInfo: () => new Promise((_, fail) => { reject = fail }) })
  const pending = ctx.persist({ note: '新要求' })
  assert.equal(ctx.saving.value, true)
  await ctx.persist({ note: '重复请求' })
  reject(new Error('failed')); await pending
  assert.deepEqual(events, [['busy', true], ['busy', false]])
  assert.equal(ctx.saving.value, false)
})

test('cost loading distinguishes missing snapshot from transport failure and ignores stale response', async () => {
  let resolve
  const { ctx, state } = setup(Costs, { order, editable: true }, { getCostSnapshot: () => new Promise(done => { resolve = done }) })
  const stale = ctx.load()
  state.api.getCostSnapshot = async () => { throw { response: { status: 503 } } }
  await ctx.load()
  resolve({ data: { total_cost: 0 } }); await stale
  assert.match(ctx.error.value, /不能当作无成本/)
  assert.equal(ctx.snapshot.value, null)
  state.api.getCostSnapshot = async () => { throw { response: { status: 404 } } }
  await ctx.load()
  assert.equal(ctx.error.value, '')
})

test('cost section does not show profit or treat theoretical BOM as settled cost', async () => {
  const source = await read('components/fulfillment/OrderCosts.vue')
  assert.doesNotMatch(source, /snapshot\.profit|profit_rate/)
  assert.match(source, /不代表本单实际成本已全部结清/)
})

test('line update sends exact identity, seven decimals, code and remarks without product replacement', async () => {
  const { ctx, calls, events } = setup(Editor, { orderId: order.id, line, canDelete: true })
  await ctx.save()
  assert.deepEqual(calls, [['updateOrderItem', 'OR-1', 7, { quantity: 10, unit_price: 0.1234567, customer_code: 'A01', remarks: '本行' }]])
  assert.deepEqual(events, [['busy', true], ['saved'], ['busy', false]])
})

test('part line update never sends jewelry customer code', async () => {
  const { ctx, calls } = setup(Editor, { orderId: order.id, line: { ...line, product_type: 'part' }, canDelete: true })
  await ctx.save()
  assert.equal('customer_code' in calls[0][3], false)
})

test('invalid line input does not create a write or busy state', async () => {
  const { ctx, calls } = setup(Editor, { orderId: order.id, line, canDelete: false })
  ctx.values.quantity = 1.5
  await ctx.save()
  assert.deepEqual(calls, [])
  assert.equal(ctx.saving.value, false)
})

test('pending and processing orders expose guarded add/edit/delete without a pending-only gate', async () => {
  const { ctx } = setup(Detail, {})
  for (const status of ['待生产', '生产中']) {
    ctx.data.value = { status, lines: [line, { ...line, id: 8 }] }
    ctx.openLineEditor()
    assert.equal(ctx.showLineEditor.value, true)
    assert.equal(ctx.selectedEdit.value, null)
    assert.equal(ctx.canDeleteLine.value, true)
    ctx.openLineEditor(ctx.data.value.lines[1])
    assert.equal(ctx.selectedEdit.value.id, 8)
    ctx.data.value.lines = [line]
    assert.equal(ctx.canDeleteLine.value, false)
  }
  const source = await read('views/orders/OrderDetail.vue')
  assert.match(source, /<n-button v-if="canEdit"[^>]+@click="openLineEditor\(\)">＋ 添加商品/)
  assert.match(source, /:can-delete="canDeleteLine"/)
  assert.doesNotMatch(source, /canEdit && data.status === '待生产'|:can-delete="data.status/)
})

test('closed, loading, failed or busy orders cannot open an item mutation', () => {
  const { ctx } = setup(Detail, {})
  for (const status of ['已完成', '已取消']) {
    ctx.data.value = { status, lines: [line, line] }
    ctx.openLineEditor()
    assert.equal(ctx.showLineEditor.value, false)
    assert.equal(ctx.canDeleteLine.value, false)
  }
  ctx.data.value.status = '生产中'
  for (const name of ['loading', 'lineBusy', 'reservationBusy']) {
    ctx[name].value = true
    ctx.openLineEditor(line)
    assert.equal(ctx.showLineEditor.value, false)
    ctx[name].value = false
  }
  ctx.error.value = '加载失败'
  ctx.openLineEditor()
  assert.equal(ctx.showLineEditor.value, false)
})

test('order addition delegates to batch picker and same-product drafts exclude customer codes', async () => {
  assert.match(await read('components/fulfillment/OrderLineEditor.vue'), /<BatchAddDialog v-if="!line" scene="order"/)
  for (const kind of ['jewelry', 'part']) {
    const row = { ...makeBatchRow('order', { id: 'SAME', kind }, 'one'), qty: 3, price: 0.1234567, note: '新增独立行' }
    assert.deepEqual(batchPayload('order', row), { quantity: 3, unit_price: 0.1234567, remarks: '新增独立行', [kind === 'jewelry' ? 'jewelry_id' : 'part_id']: 'SAME' })
    const copy = { ...row, key: 'two' }
    assert.notEqual(row.key, copy.key)
  }
})

test('deletion targets an exact line and cannot bypass the last-line guard', async () => {
  const editable = setup(Editor, { orderId: order.id, line: { ...line, id: 8 }, canDelete: true })
  await editable.ctx.remove()
  assert.deepEqual(editable.calls, [['deleteOrderItem', order.id, 8]])
  assert.deepEqual(editable.events, [['busy', true], ['saved'], ['busy', false]])
  for (const props of [{ orderId: order.id, line, canDelete: false }, { orderId: order.id, line: null, canDelete: true }]) {
    const blocked = setup(Editor, props)
    await blocked.ctx.remove()
    assert.deepEqual(blocked.calls, [])
  }
})

test('failed edit/delete retains the editor draft and does not emit a successful save', async () => {
  for (const operation of ['save', 'remove']) {
    const { ctx, events } = setup(Editor, { orderId: order.id, line, canDelete: true }, {
      updateOrderItem: async () => { throw new Error('offline') }, deleteOrderItem: async () => { throw new Error('protected') },
    })
    Object.assign(ctx.values, { product_id: 'J', quantity: 3, remarks: '保留内容' })
    await ctx[operation]()
    assert.deepEqual(events, [['busy', true], ['busy', false]])
    assert.equal(ctx.values.remarks, '保留内容')
    assert.equal(ctx.saving.value, false)
  }
})

test('same-product BOM rows remain separate by exact order line and customer code', async () => {
  const { ctx } = setup(Materials, { orderId: order.id, editable: true, lines: [line, { ...line, id: 8, quantity: 20, customer_code: 'A02' }] }, {
    getPartsSummary: async () => ({ data: [] }), listParts: async () => ({ data: [{ id: 'P', unit: '个' }] }), getBom: async () => ({ data: [{ part_id: 'P', qty_per_unit: 2 }] }),
  })
  await ctx.load()
  assert.deepEqual(ctx.bomRows.value.map(r => [r.key, r.line.id, r.line.customer_code, r.line.quantity * r.qty_per_unit]), [['7:P', 7, 'A01', 20], ['8:P', 8, 'A02', 40]])
  assert.equal(ctx.bomColumns.find(c => c.key === 'allocated').render(ctx.bomRows.value[0]), '—')
})

const demand = (orderItemId, overrides = {}) => ({ id:`material:${orderItemId}:P`, order_item_id:orderItemId, material_part_id:'P', qty_per_unit:2, quantity:20, allocated:6, unit:'个', ...overrides })

test('merged materials use authoritative exact-line demands and preserve changed/deleted BOM allocations', async () => {
  const materials = [demand(7, { quantity:'19.9999', demand_changed:true, legacy_claim:true, snapshot_quantity:30 }), demand(8, { qty_per_unit:0, quantity:0, allocated:9, demand_changed:true, snapshot_quantity:40 })]
  const { ctx, calls } = setup(Materials, { orderId:order.id, lines:[line, { ...line, id:8, quantity:20, customer_code:'A02' }, { ...line, id:9 }], materials })
  await ctx.load()
  const rows = ctx.bomRows.value
  assert.deepEqual(rows.map(r => [r.key, r.line.id, r.line.customer_code]), [['material:7:P', 7, 'A01'], ['material:8:P', 8, 'A02'], ['8:missing', 8, 'A02'], ['9:missing', 9, 'A01']])
  assert.equal(ctx.bomColumns.find(c => c.key === 'total').render(rows[0]), '19.9999 个')
  assert.equal(ctx.bomColumns.find(c => c.key === 'allocated').render(rows[1]), '9 个')
  assert.match(ctx.reviewText(rows[0]), /原需求 30.*旧归属待核对/)
  assert.match(ctx.reviewText(rows[2]), /尚未维护 BOM/)
  assert.deepEqual(calls.map(c => c[0]), ['listParts'])
})

test('display-only merge toggles exact source rows without any API write and preserves independent expansion', () => {
  const materials = [demand(7, { quantity:120, allocated:50 }), demand(8, { quantity:120, allocated:70 })]
  const before = structuredClone(materials)
  const { ctx, calls } = setup(Materials, { orderId:order.id, lines:[line, { ...line, id:8, customer_code:'A02' }], materials })
  assert.equal(ctx.mergeSameMaterials.value, false)
  ctx.mergeSameMaterials.value = true
  const [group] = ctx.materialGroups.value
  assert.equal(ctx.materialGroupColumns.find(c => c.key === 'quantity').render(group), '× 240 个')
  assert.equal(ctx.materialGroupColumns.find(c => c.key === 'allocated').render(group), '120 个')
  ctx.toggleMaterialGroup(group)
  assert.deepEqual(ctx.expandedMaterialGroups.value, [group.key])
  const content = ctx.renderMaterialSources(group)
  assert.deepEqual(content.children[1].props.data.map(row => [row.line.id, row.line.customer_code, row.quantity]), [[7, 'A01', 120], [8, 'A02', 120]])
  ctx.expandedBomRows.value = ['material:7:P']
  ctx.mergeSameMaterials.value = false
  ctx.mergeSameMaterials.value = true
  assert.deepEqual(ctx.expandedMaterialGroups.value, [group.key])
  assert.deepEqual(ctx.expandedBomRows.value, ['material:7:P'])
  assert.deepEqual(materials, before)
  assert.deepEqual(calls, [])
})

test('grouped row click and accessible part button avoid double toggles while preserving warnings', () => {
  const { ctx } = setup(Materials, { orderId:order.id, lines:[line], materials:[demand(7, { demand_changed:true, legacy_claim:true })] })
  const [group] = ctx.materialGroups.value
  assert.match(ctx.materialGroupReview(group), /1 项 BOM.*1 项旧归属待核对/)
  const rowProps = ctx.materialGroupRowProps(group)
  rowProps.onClick({ target:{ closest:() => null } })
  assert.deepEqual(ctx.expandedMaterialGroups.value, [group.key])
  rowProps.onClick({ target:{ closest:() => ({ tagName:'BUTTON' }) } })
  assert.deepEqual(ctx.expandedMaterialGroups.value, [group.key])
  ctx.toggleMaterialGroup(group)
  assert.deepEqual(ctx.expandedMaterialGroups.value, [])
  const missing = { missing:true, line }
  assert.deepEqual(ctx.materialGroupRowProps(missing), {})
  ctx.toggleMaterialGroup(missing)
  assert.deepEqual(ctx.expandedMaterialGroups.value, [])
})

test('standalone BOM groups show theoretical totals but do not invent production allocations', async () => {
  const { ctx } = setup(Materials, { orderId:order.id, lines:[line, { ...line, id:8, quantity:20 }] }, {
    listParts:async () => ({ data:[{ id:'P', unit:'个' }] }), getBom:async () => ({ data:[{ part_id:'P', qty_per_unit:0.1 }] }),
  })
  await ctx.load()
  const [group] = ctx.materialGroups.value
  assert.equal(group.quantity, '3')
  assert.equal(ctx.materialGroupColumns.find(c => c.key === 'allocated').render(group), '—')
  assert.match(ctx.materialGroupReview(group), /制作量请在生产安排中核对/)
})

test('same-order refresh retains merge mode; changing orders clears mode and old group expansion', () => {
  const props = { orderId:order.id, lines:[line], materials:[demand(7)] }
  const { ctx, state } = setup(Materials, props)
  ctx.mergeSameMaterials.value = true
  ctx.expandedMaterialGroups.value = [ctx.materialGroups.value[0].key]
  state.watches[0].action()
  assert.equal(ctx.mergeSameMaterials.value, true)
  assert.deepEqual(ctx.expandedMaterialGroups.value, [])
  props.orderId = 'OR-OTHER'
  state.watches[0].action()
  assert.equal(ctx.mergeSameMaterials.value, false)
  assert.deepEqual(ctx.expandedMaterialGroups.value, [])
})

test('estimate or catalog failures never hide current demands or turn allocated quantities into zero', async () => {
  const { ctx } = setup(Materials, { orderId:order.id, lines:[line], materials:[demand(7)] }, {
    getPartsSummary:async () => { throw new Error('estimate offline') }, listParts:async () => { throw new Error('catalog offline') },
  })
  await ctx.loadEstimates()
  assert.match(ctx.estimateError.value, /不影响当前生产需求/)
  assert.equal(ctx.error.value, '')
  await ctx.load()
  assert.ok(ctx.error.value)
  assert.equal(ctx.bomRows.value[0].allocated, 6)
  assert.equal(ctx.bomRows.value[0].quantity, 20)
})

test('inline composite BOM loads independently, deduplicates duplicate lines and supports retry', async () => {
  let resolve, count = 0
  const { ctx, state } = setup(Materials, { orderId:order.id, lines:[line, { ...line, id:8 }], materials:[demand(7), demand(8)] }, {
    listParts:async () => ({ data:[{ id:'P', is_composite:true }] }),
    getPartBom:() => { count++; return new Promise(done => { resolve = done }) },
  })
  await ctx.load()
  assert.equal(ctx.isComposite(ctx.bomRows.value[0]), true)
  ctx.expandBomRows(['material:7:P', 'material:8:P'])
  assert.equal(count, 1)
  assert.equal(ctx.childBoms.value.P.loading, true)
  resolve({ data:[{ child_part_id:'RAW', qty_per_unit:3 }] })
  await new Promise(done => setImmediate(done))
  assert.equal(ctx.childBoms.value.P.rows[0].child_part_id, 'RAW')
  state.api.getPartBom = async () => { throw new Error('offline') }
  await ctx.openChildren('Q')
  assert.match(ctx.childBoms.value.Q.error, /加载失败/)
  state.api.getPartBom = async () => ({ data:[] })
  await ctx.openChildren('Q')
  assert.equal(ctx.childBoms.value.Q.error, '')
  assert.equal(ctx.bomRows.value[0].quantity, 20)
})

test('changing order invalidates pending inline BOM requests and clears tool state', async () => {
  let resolve
  const { ctx, state } = setup(Materials, { orderId:order.id, lines:[line], materials:[demand(7)] }, {
    getPartBom:() => new Promise(done => { resolve = done }),
  })
  const pending = ctx.openChildren('P')
  ctx.showPicking.value = true
  ctx.showCutting.value = true
  state.watches[0].action()
  resolve({ data:[{ child_part_id:'OLD' }] })
  await pending
  assert.deepEqual(ctx.childBoms.value, {})
  assert.equal(ctx.showPicking.value, false)
  assert.equal(ctx.showCutting.value, false)
})

test('production mounts one unified material table, retains tools/history and defaults old estimates to collapsed', async () => {
  const page = await read('views/orders/OrderProduction.vue'), source = await read('components/fulfillment/OrderMaterials.vue')
  assert.equal((page.match(/<OrderMaterials\b/g) || []).length, 1)
  assert.match(page, /:materials="data.materials \|\| \[\]"/)
  assert.doesNotMatch(page, /title="配件备料需求"/)
  assert.match(source, /<OrderSection title="配件备料"/)
  for (const title of ['裁剪统计', '配货模拟 / PDF', '已有批次与生产关联记录', '原备料估算参考']) assert.ok(source.includes(title))
  assert.match(source, /<n-collapse style="margin-top:16px"><n-collapse-item title="原备料估算参考"/)
  const { descriptor } = parse(source), script = compileScript(descriptor, { id:'merged-materials' })
  assert.deepEqual(compileTemplate({ source:descriptor.template.content, filename:'OrderMaterials.vue', id:'merged-materials', compilerOptions:{ bindingMetadata:script.bindings } }).errors, [])
})

test('BOM errors are not an empty valid requirement and no history/movement write is called', async () => {
  const { ctx, calls } = setup(Materials, { orderId: order.id, editable: false, lines: [line] }, {
    getBom: async () => { throw new Error('offline') },
  })
  await ctx.load()
  assert.match(ctx.error.value, /不能当作没有需求/)
  assert.equal(calls.some(([name]) => /create|delete|update|mark/i.test(name)), false)
})

test('complete legacy history expands, scrolls and focuses without writing records', async () => {
  const { ctx, calls } = setup(Materials, { orderId: order.id, editable: false, lines: [line] })
  const actions = []
  ctx.historySection.value = { $el: {
    scrollIntoView: options => actions.push(['scroll', options]),
    focus: options => actions.push(['focus', options]),
  } }
  await ctx.openHistory()
  assert.deepEqual(ctx.historyExpanded.value, ['history'])
  assert.deepEqual(actions, [['scroll', { block: 'start', behavior: 'auto' }], ['focus', { preventScroll: true }]])
  assert.deepEqual(calls, [])
  ctx.historySection.value = null
  await ctx.openHistory()
})

test('detail guards navigation during each remaining kind of save and exposes no manual status mutation', async () => {
  const { ctx, state, calls } = setup(Detail, {})
  ctx.data.value = { status: '待生产' }
  for (const name of ['activating', 'costBusy', 'lineBusy', 'batchSaving', 'reservationBusy']) {
    ctx[name].value = true
    assert.ok(state.guards.every(guard => guard() === false), name)
    ctx[name].value = false
  }
  assert.equal(ctx.changeStatus, undefined)
  assert.equal(ctx.orderActions, undefined)
  assert.equal(ctx.handleOrderAction, undefined)
  assert.deepEqual(calls, [])
  assert.ok(state.guards.every(guard => guard() === true))
})

test('reservation column actions keep the exact line and cannot reserve a historical or closed order', () => {
  const { ctx, state, calls } = setup(Detail, {})
  const current = { ...line, reserved: 2 }, sibling = { ...line, id: 8, customer_code: 'A02' }
  ctx.data.value = { status: '生产中', editable: true, lines: [current, sibling] }
  ctx.editReservation(sibling, false)
  assert.equal(ctx.selectedLine.value.id, 8)
  assert.equal(ctx.release.value, false)
  ctx.editReservation(current, true)
  assert.equal(ctx.selectedLine.value.id, 7)
  assert.equal(ctx.release.value, true)
  ctx.showReservation.value = false
  ctx.data.value.editable = false
  ctx.editReservation(sibling, false)
  assert.equal(ctx.showReservation.value, false)
  ctx.editReservation(current, true)
  assert.equal(ctx.showReservation.value, false)
  ctx.openProduction()
  assert.deepEqual(state.navigation, [{ path: '/orders/OR-1/production', query: {} }])
  assert.deepEqual(calls, [])
})

test('automatic lifecycle removes the header status menu while row navigation still freezes during writes', async () => {
  const { ctx, calls, state } = setup(Detail, {})
  ctx.data.value = { status: '待生产', editable: true, lines: [] }
  const source = await read('views/orders/OrderDetail.vue')
  const header = source.slice(0, source.indexOf('</OrderWorkspaceHeader>'))
  assert.doesNotMatch(header, /更多操作|n-dropdown/)
  assert.doesNotMatch(source, /updateOrderStatus|开始生产|showCancel|changeStatus/)
  assert.match(header, /新建出货单/)
  ctx.reservationBusy.value = true
  ctx.editReservation(line, false)
  ctx.openProduction()
  assert.equal(ctx.showReservation.value, false)
  assert.deepEqual(state.navigation, [])
  ctx.openLineEditor(line)
  assert.equal(ctx.showLineEditor.value, false)
  ctx.reservationBusy.value = false
  assert.ok(state.guards.every(guard => guard() === true))
  assert.deepEqual(calls, [])
})

test('direct deletion targets the exact row, refreshes totals and blocks duplicate writes and navigation', async () => {
  let finishDelete, finishRefresh
  const deleted = [], refreshed = []
  const sibling = { ...line, id: 8 }
  const summary = { status: '待生产', editable: true, lines: [sibling], total_items: 1 }
  const { ctx, state, notices } = setup(Detail, {}, {
    deleteOrderItem: (...args) => { deleted.push(args); return new Promise(resolve => { finishDelete = resolve }) },
    getFulfillment: id => { refreshed.push(['fulfillment', id]); return new Promise(resolve => { finishRefresh = () => resolve({ data: summary }) }) },
    getOrder: async id => { refreshed.push(['order', id]); return { data: { ...order, total_amount: 20 } } },
    listShipments: async id => { refreshed.push(['shipments', id]); return { data: [] } },
  })
  ctx.data.value = { status: '待生产', editable: true, lines: [line, sibling] }
  ctx.selectedProduct.value = line
  const pending = ctx.removeLine(line)
  assert.deepEqual(deleted, [['OR-1', 7]])
  assert.equal(ctx.deletingLineId.value, 7)
  assert.equal(ctx.busy.value, true)
  assert.ok(state.guards.every(guard => guard() === false))
  await ctx.removeLine(line)
  await ctx.removeLine(sibling)
  ctx.openProduction()
  ctx.openLineEditor(sibling)
  ctx.editReservation(sibling, false)
  assert.deepEqual(state.navigation, [])
  assert.equal(ctx.showLineEditor.value, false)
  assert.equal(ctx.showReservation.value, false)
  assert.equal(deleted.length, 1)
  finishDelete()
  await Promise.resolve()
  assert.equal(ctx.busy.value, true)
  assert.equal(ctx.loading.value, true)
  assert.equal(ctx.selectedProduct.value, null)
  assert.deepEqual(refreshed, [['fulfillment', 'OR-1'], ['order', 'OR-1'], ['shipments', 'OR-1']])
  finishRefresh()
  await pending
  assert.equal(ctx.data.value.lines.length, 1)
  assert.equal(ctx.data.value.lines[0].id, 8)
  assert.equal(ctx.orderTotal.value, 20)
  assert.equal(ctx.canDeleteLine.value, false)
  assert.equal(ctx.deletingLineId.value, null)
  assert.equal(ctx.busy.value, false)
  assert.deepEqual(notices, [['success', '商品明细已删除']])
  assert.ok(state.guards.every(guard => guard() === true))
})

test('direct deletion keeps the final row and rejects closed, stale, loading, error and busy actions', async () => {
  const { ctx, calls } = setup(Detail, {})
  const sibling = { ...line, id: 8 }
  ctx.data.value = { status: '待生产', lines: [line] }
  await ctx.removeLine(line)
  ctx.data.value.lines.push(sibling)
  for (const status of ['已完成', '已取消']) {
    ctx.data.value.status = status
    await ctx.removeLine(line)
  }
  ctx.data.value.status = '生产中'
  await ctx.removeLine({ ...line, id: 999 })
  await ctx.removeLine(null)
  ctx.loading.value = true
  await ctx.removeLine(line)
  ctx.loading.value = false
  ctx.error.value = '加载失败'
  await ctx.removeLine(line)
  ctx.error.value = ''
  for (const name of ['activating', 'costBusy', 'lineBusy', 'batchSaving', 'reservationBusy']) {
    ctx[name].value = true
    await ctx.removeLine(line)
    ctx[name].value = false
  }
  assert.deepEqual(calls, [])
})

test('customer code dialog has selectable detail cards, three inline fields and a separate visible footer', async () => {
  const source = await read('views/orders/OrderDetail.vue')
  const { descriptor } = parse(source)
  const script = compileScript(descriptor, { id: 'customer-code-dialog' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: 'OrderDetail.vue', id: 'customer-code-dialog', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  assert.match(source, /class="customer-code-dialog"/)
  assert.match(source, /class="cc-line-list"/)
  assert.match(source, /class="cc-line" :class="\{ 'is-selected': batchIds.includes\(line.id\) \}"/)
  assert.match(source, /<template #footer>\s*<div class="cc-footer">/)
  assert.match(source, /所选明细已有货号会被覆盖，未选明细不变/)
  assert.match(source, /按明细编号从小到大生成，不按勾选顺序/)
  assert.match(source, /\.cc-fields \{ display: grid; grid-template-columns: minmax\(0,1.4fr\) repeat\(2,minmax\(0,1fr\)\)/)
  assert.match(source, /:global\(\.customer-code-dialog\) \{ max-height: calc\(100dvh - 32px\)/)
  assert.match(source, /:global\(\.customer-code-dialog \.n-card-content\) \{ min-height: 0; overflow-y: auto/)
})

test('customer code styling keeps jewelry-only eligibility, optional selection and the existing API payload', async () => {
  const written = []
  const summary = { status: '生产中', lines: [line, { ...line, id: 8 }, { ...line, id: 9, product_type: 'part' }] }
  const { ctx } = setup(Detail, {}, {
    batchFillCustomerCode: async (...args) => { written.push(args); return { data: { updated_count: 2 } } },
    getFulfillment: async () => ({ data: summary }), getOrder: async () => ({ data: order }), listShipments: async () => ({ data: [] }),
  })
  ctx.data.value = summary
  assert.deepEqual(ctx.customerCodeLines.value.map(line => line.id), [7, 8])
  assert.deepEqual(ctx.batchIds.value, [])
  ctx.batchIds.value = [8, 7]
  ctx.batchPrefix.value = ' KH- '
  ctx.batchStart.value = 5
  ctx.batchPadding.value = 3
  ctx.showBatchCode.value = true
  await ctx.saveBatchCode()
  assert.deepEqual(written, [['OR-1', { item_ids: [8, 7], prefix: 'KH-', start_number: 5, padding: 3 }]])
  assert.equal(ctx.showBatchCode.value, false)
  assert.equal(ctx.batchSaving.value, false)
})

test('customer code dialog retains drafts on failed save and preserves readonly and invalid-input guards', async () => {
  const written = []
  const { ctx } = setup(Detail, {}, { batchFillCustomerCode: async (...args) => { written.push(args); throw Error('offline') } })
  ctx.data.value = { status: '待生产', lines: [line] }
  ctx.showBatchCode.value = true
  ctx.batchPrefix.value = 'KH-'
  await ctx.saveBatchCode()
  assert.equal(written.length, 0)
  ctx.batchIds.value = [7]
  for (const status of ['已完成', '已取消']) {
    ctx.data.value.status = status
    await ctx.saveBatchCode()
  }
  assert.equal(written.length, 0)
  ctx.data.value.status = '待生产'
  ctx.batchSaving.value = true
  await ctx.saveBatchCode()
  assert.equal(written.length, 0)
  ctx.batchSaving.value = false
  await ctx.saveBatchCode()
  assert.equal(written.length, 1)
  assert.equal(ctx.showBatchCode.value, true)
  assert.deepEqual(ctx.batchIds.value, [7])
  assert.equal(ctx.batchPrefix.value, 'KH-')
})

test('failed direct deletion keeps the row, reports no success and releases the busy guard', async () => {
  const { ctx, calls, state, notices } = setup(Detail, {}, {
    deleteOrderItem: async () => { throw new Error('有关联业务，不可删除') },
  })
  ctx.data.value = { status: '生产中', lines: [line, { ...line, id: 8 }] }
  await ctx.removeLine(line)
  assert.equal(ctx.data.value.lines.length, 2)
  assert.equal(ctx.deletingLineId.value, null)
  assert.equal(ctx.busy.value, false)
  assert.deepEqual(calls, [])
  assert.deepEqual(notices, [])
  assert.ok(state.guards.every(guard => guard() === true))
})

test('requirement editing starts from persisted data and cancelling cannot leak draft text to the page', () => {
  const values = { ...order, has_barcode: true, barcode_text: '每件一贴', mark_text: '唛头', note: '已保存备注', barcode_image: '/barcode.png', mark_image: '/mark.png' }
  const { ctx, calls } = setup(Information, { order: values, editable: true })
  ctx.openRequirements()
  assert.equal(ctx.showRequirements.value, true)
  assert.equal(ctx.requirements.note, values.note)
  ctx.requirements.note = '未保存草稿'
  ctx.showRequirements.value = false
  assert.equal(values.note, '已保存备注')
  ctx.openRequirements()
  assert.equal(ctx.requirements.note, '已保存备注')
  ctx.showRequirements.value = false
  ctx.saving.value = true
  ctx.openRequirements()
  assert.equal(ctx.showRequirements.value, false)
  assert.deepEqual(calls, [])
  const readonly = setup(Information, { order: values, editable: false })
  readonly.ctx.openRequirements()
  assert.equal(readonly.ctx.showRequirements.value, false)
})

test('requirement modal only closes after a successful unchanged API contract save', async () => {
  const { ctx, calls, events } = setup(Information, { order, editable: true })
  ctx.showRequirements.value = true
  Object.assign(ctx.requirements, { has_barcode: true, barcode_text: '新条码', mark_text: '新唛头', note: '新备注' })
  await ctx.saveRequirements()
  assert.equal(ctx.showRequirements.value, false)
  assert.deepEqual(calls, [['updateExtraInfo', order.id, { has_barcode: true, barcode_text: '新条码', mark_text: '新唛头', note: '新备注' }]])
  assert.deepEqual(events, [['busy', true], ['saved'], ['busy', false]])
})

test('information tab preserves editing permissions and guards navigation during saves', async () => {
  const { ctx, state } = setup(InfoPage, {})
  ctx.order.value = order
  for (const status of ['待生产', '生产中']) {
    ctx.data.value = { status }
    assert.equal(ctx.canEdit.value, true)
  }
  for (const status of ['已完成', '已取消']) {
    ctx.data.value = { status }
    assert.equal(ctx.canEdit.value, false)
  }
  ctx.data.value = { status: '待生产' }
  ctx.loading.value = true
  assert.equal(ctx.canEdit.value, false)
  ctx.loading.value = false
  ctx.error.value = '加载失败'
  assert.equal(ctx.canEdit.value, false)
  ctx.busy.value = true
  assert.ok(state.guards.every(guard => guard() === false))
  ctx.busy.value = false
  assert.ok(state.guards.every(guard => guard() === true))
})

test('information tab reloads after save and ignores stale responses for another order', async () => {
  let resolveOldOrder
  const { ctx, state } = setup(InfoPage, {}, {
    getOrder: () => new Promise(resolve => { resolveOldOrder = resolve }),
    getFulfillment: async () => ({ data: { status: '待生产' } }),
  })
  const old = ctx.load()
  state.route.params.id = 'OR-2'
  state.api.getOrder = async id => ({ data: { ...order, id, customer_name: '新客户' } })
  await ctx.load()
  resolveOldOrder({ data: order }); await old
  assert.equal(ctx.order.value.id, 'OR-2')
  assert.equal(ctx.order.value.customer_name, '新客户')
  state.api.getOrder = async id => ({ data: { ...order, id, customer_name: '保存后的客户' } })
  await ctx.load()
  assert.equal(ctx.order.value.customer_name, '保存后的客户')
  state.api.getOrder = async () => { throw { response: { data: { detail: '读取失败' } } } }
  await ctx.load()
  assert.equal(ctx.error.value, '读取失败')
  assert.equal(ctx.canEdit.value, false)
})

test('history reload clears previous order records and ignores late old-order responses', async () => {
  let resolveBatch, resolveTodo
  const { ctx, state } = setup(Materials, { orderId: order.id, editable: false, lines: [line] }, {
    getTodoBatches: () => new Promise(resolve => { resolveBatch = resolve }),
    getTodo: () => new Promise(resolve => { resolveTodo = resolve }),
  })
  ctx.batches.value = [{ id: 1, items: [] }]
  const old = ctx.loadHistory()
  assert.deepEqual(ctx.batches.value, [])
  state.api.getTodoBatches = async () => ({ data: { batches: [{ id: 2, items: [] }] } })
  state.api.getTodo = async () => ({ data: [] })
  await ctx.loadHistory()
  resolveBatch({ data: { batches: [{ id: 3 }] } }); resolveTodo({ data: [{ id: 99 }] })
  await old
  assert.deepEqual(ctx.batches.value.map(b => b.id), [2])
  assert.deepEqual(ctx.todos.value, [])
})

test('cutting reference ignores a superseded response instead of overwriting the latest result', async () => {
  let resolve
  const { ctx, state } = setup(Materials, { orderId: order.id, editable: false, lines: [line] }, {
    getCuttingStats: () => new Promise(done => { resolve = done }),
  })
  const old = ctx.openCutting()
  state.api.getCuttingStats = async () => ({ data: { items: [{ part_id: 'CURRENT' }] } })
  await ctx.openCutting()
  resolve({ data: { items: [{ part_id: 'STALE' }] } }); await old
  assert.equal(ctx.cutting.value[0].part_id, 'CURRENT')
})
