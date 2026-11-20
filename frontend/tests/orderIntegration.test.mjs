import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { parse, compileScript } from '@vue/compiler-sfc'
import { reactive } from 'vue'

const moduleUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const runtime = moduleUrl(`
  export { ref, reactive, computed, h } from ${JSON.stringify(import.meta.resolve('vue'))};
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
  assert.equal((view.match(/<tr v-for="line in data.lines"/g) || []).length, 1)
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

test('adding duplicate jewelry and part items sends the existing contract without merging identities', async () => {
  for (const kind of ['jewelry', 'part']) {
    const { ctx, calls, events } = setup(Editor, { orderId: order.id, line: null, canDelete: false })
    ctx.kind.value = kind
    Object.assign(ctx.values, { product_id: 'SAME', quantity: 3, unit_price: 0.1234567, customer_code: 'A03', remarks: '新增独立行' })
    await ctx.save()
    assert.deepEqual(calls, [['addOrderItem', order.id, { quantity: 3, unit_price: 0.1234567, remarks: '新增独立行', ...(kind === 'jewelry' ? { customer_code: 'A03', jewelry_id: 'SAME' } : { part_id: 'SAME' }) }]])
    assert.deepEqual(events, [['busy', true], ['saved'], ['busy', false]])
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

test('failed add/delete retains the editor draft and does not emit a successful save', async () => {
  for (const operation of ['save', 'remove']) {
    const { ctx, events } = setup(Editor, { orderId: order.id, line: operation === 'remove' ? line : null, canDelete: true }, {
      addOrderItem: async () => { throw new Error('offline') }, deleteOrderItem: async () => { throw new Error('protected') },
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
})

test('BOM errors are not an empty valid requirement and no history/movement write is called', async () => {
  const { ctx, calls } = setup(Materials, { orderId: order.id, editable: false, lines: [line] }, {
    getBom: async () => { throw new Error('offline') },
  })
  await ctx.load()
  assert.match(ctx.error.value, /不能当作没有需求/)
  assert.equal(calls.some(([name]) => /create|delete|update|mark/i.test(name)), false)
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

test('relocated row actions keep the exact line and cannot reserve a historical or closed order', () => {
  const { ctx, state, calls } = setup(Detail, {})
  const current = { ...line, reserved: 2 }, sibling = { ...line, id: 8, customer_code: 'A02' }
  ctx.data.value = { status: '生产中', editable: true, lines: [current, sibling] }
  assert.deepEqual(ctx.lineActions(current).map(action => action.key), ['product', 'production', 'reserve', 'release'])
  ctx.handleLineAction('reserve', sibling)
  assert.equal(ctx.selectedLine.value.id, 8)
  assert.equal(ctx.release.value, false)
  ctx.handleLineAction('release', current)
  assert.equal(ctx.selectedLine.value.id, 7)
  assert.equal(ctx.release.value, true)
  ctx.showReservation.value = false
  ctx.data.value.editable = false
  assert.deepEqual(ctx.lineActions(current).map(action => action.key), ['product', 'production'])
  ctx.handleLineAction('reserve', sibling)
  assert.equal(ctx.showReservation.value, false)
  ctx.handleLineAction('product', sibling)
  assert.equal(ctx.selectedProduct.value.id, 8)
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
  ctx.handleLineAction('reserve', line)
  ctx.openProduction()
  assert.equal(ctx.showReservation.value, false)
  assert.deepEqual(state.navigation, [])
  assert.ok(ctx.lineActions(line).every(action => action.disabled))
  ctx.reservationBusy.value = false
  assert.ok(state.guards.every(guard => guard() === true))
  assert.deepEqual(calls, [])
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
