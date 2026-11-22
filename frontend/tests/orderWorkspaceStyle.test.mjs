import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'

const source = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('approved order workspace keeps the three tabs without a second floating navigation layer', () => {
  for (const page of ['OrderDetail', 'OrderProduction', 'OrderInfo']) {
    const view = source(`views/orders/${page}.vue`)
    assert.match(view, /class="fulfillment-page order-workspace"/)
    assert.match(view, /:status="/)
    assert.match(view, /:created-at="/)
    assert.doesNotMatch(view, /floating-action|floating-bar|public\/demos|order-detail-plating/)
  }
  const header = source('components/fulfillment/OrderWorkspaceHeader.vue')
  assert.match(header, /ow-head-actions/)
  assert.match(header, /getHandcraftSummaryReturn\(route.query\)/)
  assert.match(header, /query: route.query/)
  assert.deepEqual([...header.matchAll(/<n-tab name="([^\"]+)">([^<]+)</g)].map(match => match[2]), ['商品详情', '生产安排', '订单信息'])
})

test('real product page uses flat stats, contextual tools and preserves all business entry points', () => {
  const view = source('views/orders/OrderDetail.vue')
  const header = view.slice(0, view.indexOf('</OrderWorkspaceHeader>'))
  assert.match(header, /\/shipments\/create/)
  assert.match(view, /class="ow-stats"/)
  assert.doesNotMatch(view, /<n-statistic|class="wf-stats"/)
  const products = view.slice(view.indexOf('<OrderSection title="商品明细"'), view.indexOf('</OrderSection>'))
  for (const action of ['showMaterials = true', 'openLineEditor()', 'showBatchCode = true', 'removeLine(line)', 'editReservation(line, false)', 'editReservation(line, true)']) assert.ok(products.includes(action), action)
  assert.match(products, /<n-button v-if="canEdit"[^>]+:disabled="busy" @click="showBatchCode = true">客户货号<\/n-button>/)
  assert.doesNotMatch(products, /n-dropdown|···|查看商品详情|lineActions|handleLineAction/)
  const rowActions = products.slice(products.indexOf('<td><div v-if="canEdit" class="wf-actions ow-row-actions">'))
  assert.match(rowActions, /<n-popconfirm :disabled="busy \|\| !canDeleteLine" @positive-click="removeLine\(line\)"/)
  assert.match(rowActions, /:disabled="busy \|\| !canDeleteLine"[^>]+>删除<\/n-button>/)
  assert.doesNotMatch(rowActions, /查看生产安排|预留库存|取消预留/)
  assert.match(view, /<OrderMaterials[^>]+:lines="data.lines"/)
  assert.match(view, /<ShipmentTable[^>]+compact/)
  assert.match(view, /<OrderCosts[^>]+@busy="costBusy = \$event"/)
  for (const action of ['核对历史实发', '预留库存', '取消预留']) assert.ok(view.includes(action), action)
  assert.doesNotMatch(header, /更多操作|n-dropdown/)
  assert.doesNotMatch(view, /开始生产|取消订单|changeStatus|updateOrderStatus/)
  const production = source('views/orders/OrderProduction.vue')
  assert.match(production, /确认关联手工或电镀后，订单自动进入「生产中」/)
  assert.match(production, /订单须全部明细足量出货后才完成/)
})

test('order visuals are locally scoped and retain real control components and mobile table scrolling', () => {
  const css = source('styles/order-workspace.css')
  assert.doesNotMatch(css, /\.n-layout|\.sidebar|position:\s*fixed|padding-bottom:\s*(?:100|115)px/)
  assert.match(css, /\.order-workspace \.ow-stats/)
  assert.match(css, /\.order-workspace \.ow-product-table/)
  assert.match(css, /position: sticky; left: 0/)
  assert.match(css, /\.order-workspace \.ow-product-table \{[^}]*overflow: visible/)
  assert.match(css, /grid-template-columns: repeat\(2,minmax\(0,1fr\)\)/)
  const costs = source('components/fulfillment/OrderCosts.vue')
  assert.match(costs, /title="费用与成本"/)
  assert.match(costs, /<n-modal[^>]+:mask-closable="!saving"/)
  assert.doesNotMatch(costs, /snapshot\.profit|profit_rate/)
  const info = source('components/fulfillment/OrderInformation.vue')
  assert.match(info, /order\[entry.image\]/)
  assert.match(info, /order.note \|\| '未填写订单备注'/)
  for (const key of ['barcode_image', 'mark_image', 'has_barcode', 'ImageUploadModal']) assert.ok(info.includes(key), key)
})

test('production section header actions match the add-product secondary primary style without changing other material entry points', () => {
  const detail = source('views/orders/OrderDetail.vue')
  assert.match(detail, /<n-button[^>]*size="small" type="primary" secondary[^>]*>＋ 添加商品<\/n-button>/)
  const production = source('views/orders/OrderProduction.vue')
  assert.match(production, /<n-button v-if="data.editable" size="small" type="primary" secondary :disabled="loading \|\| saving" @click="openLinker">订单关联<\/n-button>/)
  assert.match(production, /<OrderMaterials[^>]* accent-actions \/>/)
  const materials = source('components/fulfillment/OrderMaterials.vue')
  const actions = materials.match(/<template #header-extra>(.*?)<\/template>/s)[1]
  assert.equal((actions.match(/size="small" :type="accentActions \? 'primary' : 'default'" :secondary="accentActions"/g) || []).length, 2)
  assert.match(actions, /@click="openCutting">裁剪统计/)
  assert.match(actions, /@click="showPicking = true">配货模拟 \/ PDF/)
  assert.doesNotMatch(detail, /<OrderMaterials[^>]*accent-actions/)
})

test('updated workspace templates compile with script bindings rather than relying only on source checks', () => {
  for (const path of ['views/orders/OrderDetail.vue', 'views/orders/OrderProduction.vue', 'views/orders/OrderInfo.vue', ...['OrderWorkspaceHeader', 'OrderSection', 'OrderInformation', 'OrderCosts', 'ProductCell', 'ShipmentTable', 'OrderMaterials'].map(name => `components/fulfillment/${name}.vue`)]) {
    const { descriptor, errors } = parse(source(path))
    assert.deepEqual(errors, [], path)
    const script = compileScript(descriptor, { id: path })
    const template = compileTemplate({ source: descriptor.template.content, filename: path, id: path, compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [], path)
  }
})
