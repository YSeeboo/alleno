import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import * as D from '../public/demos/order-detail-plating/domain.js'

const source = file => readFileSync(new URL(`../public/demos/order-detail-plating/${file}`, import.meta.url), 'utf8')
function render(hash = '#OR-1042/details', state = D.createState()) {
  const app = { innerHTML: '', querySelectorAll: () => [] }, modal = { addEventListener() {} }
  runInNewContext(source('app.js').replace(/^import \* as D from ['"][^'"]+['"]/, 'const D = demoDomain'), {
    demoDomain: { ...D, createState: () => state },
    document: { querySelector: s => s === '#app' ? app : modal, addEventListener() {}, body: { classList: { remove() {} } } },
    location: { hash }, window: { addEventListener() {} },
  })
  return app.innerHTML
}
const unchanged = (state, action) => {
  const before = structuredClone(state)
  assert.throws(action)
  assert.deepEqual(state, before)
}

test('new visual variant is isolated and preserves the existing demo and shell', () => {
  assert.match(source('index.html'), /connect-src 'none'/)
  assert.match(source('index.html'), /form-action 'none'/)
  assert.doesNotMatch(source('app.js') + source('domain.js'), /fetch\(|XMLHttpRequest|localStorage|sessionStorage|\/api\/|@\/|\.\.\/\.\.\/src/)
  assert.match(source('styles.css'), /width: 240px/)
  assert.match(source('styles.css'), /background: #10141A/)
  const html = render()
  assert.match(html, /ALLENOP/)
  assert.match(html, /\.\.\/order-integration\/index.html/)
  assert.match(html, /商品明细，可横向滚动/)
  assert.match(html, /QW-N018 更多操作/)
})

test('detail keeps the current three tabs and focuses on products, inventory, shipment and costs', () => {
  const html = render()
  assert.equal((html.match(/role="tab"/g) || []).length, 3)
  for (const label of ['商品详情', '生产安排', '订单信息', '商品明细', '费用与成本', '出货记录', '操作记录', '物料工具']) assert.ok(html.includes(label), label)
  assert.match(html, /¥4,330.00/)
  assert.match(html, /足量交付/)
  assert.doesNotMatch(html, /交货日期|交期|历史实发数量待核对|标记完成|启用逐笔履约|条码要求|唛头要求|编辑资料|编辑订单要求|订单要求与参考图片/)
  assert.ok(D.createState().orders.every(o => !Object.hasOwn(o, 'due')))
})

test('information has its own selected tab, complete metadata, requirements, notes and references', () => {
  const html = render('#OR-1042/information')
  assert.match(html, /id="tab-information" role="tab" aria-selected="true"/)
  assert.match(html, /role="tabpanel" aria-labelledby="tab-information"/)
  for (const label of ['基本信息', '编辑资料', '订单要求', '条码要求', '唛头要求', '订单备注', '编辑订单要求', '包装参考示意图', '创建日期', '订单金额（含包装费）']) assert.ok(html.includes(label), label)
  assert.match(html, /分批发货；项链独立装袋，耳饰一对一卡。/)
  assert.doesNotMatch(html, /class="stats"|class="product-table"|交货日期|交期/)
  assert.match(render('#OR-1043/information'), /MORI STUDIO/)
  assert.doesNotMatch(render('#OR-1043/information'), /栖物生活/)
  assert.match(render('#OR-1042/unknown'), /id="tab-details" role="tab" aria-selected="true"/)
})

test('all three tabs remove the floating action layer and keep contextual section actions', () => {
  assert.doesNotMatch(source('styles.css'), /floating-wrap|floating-bar/)
  for (const id of ['OR-1042', 'OR-0988', 'OR-1006']) {
    for (const tab of ['details', 'production', 'information']) {
      const html = render(`#${id}/${tab}`)
      assert.doesNotMatch(html, /floating-wrap|floating-bar|订单快捷操作/)
      assert.equal((html.match(/role="tab"/g) || []).length, 3)
      if (tab !== 'details') assert.doesNotMatch(html, /data-action="new-shipment"/)
      if (tab === 'information') {
        assert.equal((html.match(/data-action="edit-info"/g) || []).length, 1)
        assert.equal((html.match(/data-action="requirements"/g) || []).length, 2)
      }
      if (tab === 'production') assert.match(html, /配件用量与 BOM/)
    }
  }
})

test('shipment is a product header primary action while materials and add stay by the table', () => {
  for (const id of ['OR-1042', 'OR-0988', 'OR-1006']) {
    const html = render(`#${id}/details`)
    const header = html.match(/<header class="head">[\s\S]*?<\/header>/)[0]
    const productHeading = html.slice(html.indexOf('<h2>商品明细</h2>'), html.indexOf('<div class="table-frame">'))
    assert.match(header, /class="primary" data-action="new-shipment"/)
    assert.match(productHeading, /data-action="materials"/)
    assert.match(productHeading, /data-action="add-line"/)
    assert.equal((html.match(/data-action="materials"/g) || []).length, 1)
    assert.doesNotMatch(header, /data-action="materials"|data-action="add-line"/)
    assert.doesNotMatch(productHeading, /data-action="new-shipment"/)
    if (id !== 'OR-1042') {
      assert.match(header, /data-action="new-shipment"[^>]*disabled/)
      assert.match(productHeading, /data-action="add-line"[^>]*disabled/)
    }
  }
})

test('historical information stays contextual and all metadata mutation entries are disabled', () => {
  for (const id of ['OR-0988', 'OR-1006']) {
    const html = render(`#${id}/information`)
    assert.match(html, /历史实发未核实/)
    assert.match(html, /data-action="edit-info"[^>]*disabled/)
    assert.match(html, /data-action="requirements"[^>]*disabled/)
    assert.doesNotMatch(html, /data-action="verify"|data-action="new-shipment"/)
  }
})

test('production maintains clear plan, actual and historical-reference boundaries', () => {
  const html = render('#OR-1042/production')
  for (const text of ['本单制作需求', '关联生产任务', '配件备料', '实收不等于本单可用库存', '早期关联记录待核对', '不并入当前计划', '不代表库存缺口']) assert.ok(html.includes(text), text)
  assert.doesNotMatch(render('#OR-1043/production'), /早期关联记录待核对/)
})

test('historical completion never gets invented actual shipment values or writable controls', () => {
  for (const id of ['OR-0988', 'OR-1006']) {
    const html = render(`#${id}/details`)
    assert.match(html, /实发数量未核实|历史实发数量待核对/)
    assert.match(html, /足量交付<\/div><div class="stat-value ">待核对/)
    assert.match(html, /data-action="new-shipment"[^>]*disabled/)
    assert.match(html, /不自动补记/)
    assert.doesNotMatch(html, /data-action="verify"/)
  }
})

test('price editing retains seven decimals and exact line identity without changing stock or production', () => {
  const state = D.createState(), before = structuredClone(state)
  const original = state.orders[0].lines[0]
  D.editLine(state, 'OR-1042', 'a1', { qty: 100, code: 'QW-N018', price: '28.1234567' })
  assert.equal(original, state.orders[0].lines[0])
  assert.equal(original.price, 28.1234567)
  assert.match(render('#OR-1042/details', state), /28.1234567/)
  for (const key of ['stock', 'tasks', 'shipments', 'materialSources']) assert.deepEqual(state[key], before[key])
  unchanged(state, () => D.editLine(state, 'OR-1042', 'a1', { qty: 100, code: 'BAD', price: '28.12345678' }))
  unchanged(state, () => D.editLine(state, 'OR-1042', 'a1', { qty: 1, code: 'BAD', price: '28.1234567' }))
  unchanged(state, () => D.editLine(state, 'OR-1042', 'a1', { qty: 100, code: 'BAD', price: '28', product: 'chain' }))
})

test('adding same-product lines preserves independent identities and seven-decimal prices', () => {
  const state = D.createState()
  D.addLine(state, 'OR-1042', { product: 'necklace', qty: 10, code: 'SECOND-CODE', price: '1.1234567' })
  const lines = state.orders[0].lines
  assert.equal(lines.length, 4)
  assert.equal(lines[0].qty, 100)
  assert.notEqual(lines[0].id, lines[3].id)
  assert.equal(lines[3].price, 1.1234567)
  assert.equal(lines[3].code, 'SECOND-CODE')
})

test('customer editing does not invent a due date or affect business ledgers', () => {
  const state = D.createState(), before = structuredClone(state)
  D.editCustomer(state, 'OR-1042', '新演示客户')
  assert.equal(state.orders[0].customer, '新演示客户')
  assert.equal(Object.hasOwn(state.orders[0], 'due'), false)
  for (const key of ['stock', 'tasks', 'shipments', 'materialSources']) assert.deepEqual(state[key], before[key])
  unchanged(state, () => D.editCustomer(state, 'OR-1042', ' '))
  unchanged(state, () => D.editCustomer(state, 'OR-0988', '禁止修改'))
})

test('information editing validates all metadata before mutation and leaves product ledgers untouched', () => {
  const state = D.createState(), before = structuredClone(state)
  for (const date of ['', '2026-02-30', '2026-13-01', null]) unchanged(state, () => D.editInfo(state, 'OR-1042', { customer: '未保存客户', date }))
  unchanged(state, () => D.editInfo(state, 'OR-1042', { customer: ' ', date: '2026-11-20' }))
  unchanged(state, () => D.editInfo(state, 'OR-0988', { customer: '历史只读', date: '2026-11-20' }))
  D.editInfo(state, 'OR-1042', { customer: '修改后的演示客户', date: '2026-11-20' })
  assert.equal(state.orders[0].date, '2026-11-20')
  assert.equal(state.orders[0].customer, '修改后的演示客户')
  assert.equal(Object.hasOwn(state.orders[0], 'due'), false)
  assert.deepEqual(state.orders[0].lines, before.orders[0].lines)
  for (const key of ['stock', 'tasks', 'shipments', 'materialSources']) assert.deepEqual(state[key], before[key])
  const html = render('#OR-1042/information', state)
  assert.match(html, /修改后的演示客户/)
  assert.match(html, /2026-11-20/)
})

test('reservation, production append and shipment draft remain separate in-memory operations', () => {
  const state = D.createState(), stock = structuredClone(state.stock), initial = structuredClone(state.tasks[0])
  D.reserve(state, 'a1', 10)
  assert.equal(state.orders[0].lines[0].reserved, 50)
  const task = D.arrange(state, { lineId: 'a1', supplier: '青禾手作', qty: 10, planned: 30, targetId: 'HC-0086' })
  assert.equal(D.taskLabel(task), 'HC-0086')
  assert.notEqual(task.id, 'HC-0086')
  assert.deepEqual(state.tasks[0], initial)
  const draft = D.draftShipment(state, { orderId: 'OR-1042', lines: [{ lineId: 'a1', qty: 10 }] })
  assert.equal(draft.status, 'draft')
  assert.equal(state.orders[0].lines[0].shipped, 20)
  assert.deepEqual(state.stock, stock)
})

test('typed metadata is escaped instead of being interpreted as markup', () => {
  const state = D.createState()
  state.orders[0].customer = '<img src=x onerror=alert(1)>'
  state.orders[0].lines[0].code = '"><svg onload=alert(1)>'
  const html = render('#OR-1042/details', state)
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/)
  assert.doesNotMatch(html, /<img src=x|<svg onload/)
})
