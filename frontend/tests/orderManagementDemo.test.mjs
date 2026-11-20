import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as D from '../public/demos/order-management/domain.js'
import * as V from '../public/demos/order-management/views.js'

const source = file => readFileSync(new URL(`../public/demos/order-management/${file}`, import.meta.url), 'utf8')
const filters = { search: '', status: '', history: false, sort: 'date' }
const unchanged = (state, action) => { const before = structuredClone(state); assert.throws(action); assert.deepEqual(state, before) }

test('list/create demo is isolated, blocks network and forms, and never imports real business modules', () => {
  const html = source('index.html'), js = ['domain.js', 'views.js', 'app.js'].map(source).join('\n')
  assert.match(html, /connect-src 'none'/)
  assert.match(html, /form-action 'none'/)
  assert.doesNotMatch(js, /fetch\(|XMLHttpRequest|localStorage|sessionStorage|\/api\/|@\/|\/src\//)
  assert.match(source('styles.css'), /@import url\('\.\.\/order-detail-plating\/styles.css'\)/)
  assert.doesNotMatch(source('styles.css'), /position:\s*fixed|position:\s*sticky[^}]*bottom/)
})

test('list keeps the approved branding and separates status, exact-line delivery and reservation units', () => {
  const state = D.createState(), html = V.shell(V.listPage(state, filters), false)
  for (const text of ['ALLENOP', '订单管理', '新建订单', '订单总数', '足量交付', '待发预留', '80 条 / 40 对', '商品金额', '不含后续包装费', '仅历史待核对']) assert.ok(html.includes(text), text)
  assert.doesNotMatch(html, /利润|交期|交货日期|批量发货|标记完成/)
  assert.equal((html.match(/aria-label="查看 OR-/g) || []).length, 7)
  assert.match(V.listPage(state, filters, 2), /历史待核对/)
})

test('search, status and history filters compose without mutating the original records', () => {
  const state = D.createState(), before = structuredClone(state)
  assert.deepEqual(D.filterOrders(state.orders, { ...filters, search: '  mori  ', status: '生产中' }).map(o => o.id), ['OR-1049'])
  assert.deepEqual(D.filterOrders(state.orders, { ...filters, history: true }).map(o => o.id), ['OR-0988', 'OR-0972'])
  assert.deepEqual(D.filterOrders(state.orders, { ...filters, history: true, status: '生产中' }), [])
  assert.equal(D.filterOrders(state.orders, { ...filters, sort: 'amount' })[0].id, 'OR-1045')
  assert.deepEqual(state, before)
})

test('empty filtering and pagination give a usable reset and do not show fabricated matches', () => {
  const state = D.createState()
  const empty = V.listPage(state, { ...filters, search: 'not-a-customer' })
  assert.match(empty, /没有找到符合条件的订单/)
  assert.match(empty, /data-action="clear-filters"/)
  assert.doesNotMatch(empty, /data-action="inspect"/)
  const lastPage = V.listPage(state, filters, 900)
  assert.match(lastPage, /OR-0988/)
  assert.doesNotMatch(lastPage, /OR-1050/)
})

test('creation retains existing fields, separate jewelry/part entries and a non-floating summary', () => {
  const html = V.createPage(D.exampleDraft())
  for (const text of ['基本资料', '客户名称', '创建日期', '需要贴条码', '饰品明细', '配件明细', '本次订单', '单价', '明细备注', '不含后续包装费用', '创建演示订单', '填入示例', '清空表单']) assert.ok(html.includes(text), text)
  assert.match(html, /form="create-form"/)
  assert.doesNotMatch(html, /交期|交货日期|预留数量|生产数量|上传图片|保存草稿|floating-bar/)
  assert.match(V.createPage(D.emptyDraft()), /还没有饰品明细/)
  assert.match(V.createPage(D.emptyDraft()), /还没有配件明细/)
})

test('money and subtotals retain all seven decimal places with exact arithmetic', () => {
  const draft = D.exampleDraft(), totals = D.draftTotals(draft)
  assert.equal(D.money(D.lineTotal(draft.lines[0])), '¥2,812.34567')
  assert.equal(D.money(totals.groups.jewelry), '¥4,132.34567')
  assert.equal(D.money(totals.groups.part), '¥24.69134')
  assert.equal(D.money(totals.total), '¥4,157.03701')
  assert.equal(totals.units, '100 条 / 60 对 / 200 个')
  assert.equal(D.money(D.priceUnits('0.0000001')), '¥0.0000001')
  assert.equal(D.money(D.priceUnits('0')), '¥0.00')
})

test('new duplicate product rows keep independent identities and changing a selection prefills only its own price', () => {
  const state = D.createState(), original = structuredClone(state.draft.lines[0])
  D.addLine(state, 'jewelry')
  const line = state.draft.lines.at(-1)
  D.selectProduct(line, original.product)
  assert.notEqual(line.key, original.key)
  assert.equal(line.price, '28.1234567')
  assert.deepEqual(state.draft.lines[0], original)
  assert.throws(() => D.selectProduct(line, 'PJ-0901'))
  D.selectProduct(line, '')
  assert.equal(line.price, '0')
  state.draft.lines.splice(1, 1)
  D.addLine(state, 'part')
  assert.equal(new Set(state.draft.lines.map(l => l.key)).size, state.draft.lines.length)
})

test('invalid price and quantity never turn into a valid order or partially mutate state', () => {
  for (const value of ['', '-1', '1.2', 'Infinity', '1e2', '1000000000']) {
    const state = D.createState(); state.draft.lines[0].quantity = value
    unchanged(state, () => D.createDemoOrder(state))
  }
  for (const value of ['', '-1', '1.12345678', 'NaN', 'Infinity', '1e-7', '1000000000']) {
    const state = D.createState(); state.draft.lines[0].price = value
    unchanged(state, () => D.createDemoOrder(state))
    assert.equal(D.draftTotals(state.draft).invalid, true)
  }
})

test('customer, product and actual calendar dates are validated before any creation', () => {
  for (const action of [s => { s.draft.customer = '   ' }, s => { s.draft.lines = [] }, s => { s.draft.lines[0].product = '' }, s => { s.draft.date = '2026-02-30' }, s => { s.draft.date = 'bad-date' }, s => { s.draft.lines[0].kind = 'part' }]) {
    const state = D.createState(); action(state)
    unchanged(state, () => D.createDemoOrder(state))
  }
})

test('creating only adds an independent pending demo order, with no stock, production or shipment invention', () => {
  const state = D.createState(), previous = structuredClone(state.orders), lines = structuredClone(state.draft.lines)
  state.draft.date = ''
  const order = D.createDemoOrder(state, '2026-11-20')
  assert.equal(order.id, 'OR-DEMO-1051')
  assert.equal(order.amount, '4157.0370100')
  assert.equal(order.status, '待生产')
  assert.equal(order.completed, 0)
  assert.equal(order.reserved, '无待发预留')
  assert.equal(order.date, '2026-11-20')
  assert.deepEqual(order.lines, lines)
  assert.deepEqual(state.orders.slice(1), previous)
  assert.deepEqual(state.draft, D.emptyDraft())
  assert.doesNotMatch(JSON.stringify(state), /inventory|shipment|production/)
})

test('very large valid line totals remain displayable without reusing the unit-price limit', () => {
  const state = D.createState()
  state.draft.lines[0].quantity = '999999999'; state.draft.lines[0].price = '999999999.9999999'
  const record = D.createDemoOrder(state)
  assert.ok(D.amountUnits(record.amount) > D.priceUnits('999999999.9999999'))
  assert.doesNotThrow(() => V.listPage(state, filters))
})

test('historical completed orders never get invented shipment progress and all typed text is escaped', () => {
  const state = D.createState(), historical = state.orders.find(o => o.id === 'OR-0988')
  assert.equal(historical.completed, null)
  const preview = V.inspectOrder(historical)
  assert.match(preview, /不根据旧状态补造出货数量/)
  assert.doesNotMatch(preview, /3 \/ 3 项/)
  state.draft.customer = '<img src=x onerror=alert(1)>'
  state.draft.lines[0].remarks = '"><script>alert(1)</script>'
  const html = V.createPage(state.draft)
  assert.doesNotMatch(html, /<script>|<img src=x/)
  assert.match(html, /&lt;script&gt;/)
  historical.customer = '<b>unsafe</b>'
  assert.match(V.inspectOrder(historical), /&lt;b&gt;unsafe&lt;\/b&gt;/)
})
