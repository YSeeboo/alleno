import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'

const dataURL = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const source = readFileSync(new URL('../src/components/fulfillment/OrderLegacyProductionReview.vue', import.meta.url), 'utf8')
const code = compileScript(parse(source).descriptor, { id: 'legacy-review', inlineTemplate: true }).content
const runtime = dataURL(`import { h } from ${JSON.stringify(import.meta.resolve('vue'))};
const wrap = { setup(props, { slots }) { return () => h('section', slots.default?.()) } };
export const NAlert = wrap, NButton = wrap, NModal = wrap, NSpace = wrap;`)
const Review = (await import(dataURL(code
  .replace(/from ["']vue["']/g, `from ${JSON.stringify(import.meta.resolve('vue'))}`)
  .replace(/from ["']naive-ui["']/g, `from ${JSON.stringify(runtime)}`)))).default
const line = overrides => ({ id: 1, product_id: 'SP-test', product_name: '测试商品', quantity: 60, unit: '卡', legacy_claim: false,
  legacy_batches: [{ batch_id: 15, quantity: 50, production_order_id: null, source_item_id: null, blocks_allocation: false }], ...overrides })
async function render(value) {
  const app = createSSRApp({ render: () => h(Review, { orderId: 'OR-test', line: value }) })
  app.component('RouterLink', { props: ['to'], setup(props, { slots }) { return () => h('a', { href: props.to.path }, slots.default?.()) } })
  return renderToString(app)
}

test('actual review template distinguishes estimate-only batches and changed quantities', async () => {
  const html = await render(line())
  for (const text of ['旧批次 #15', '原批次数量 50 卡', '当前订购 60 卡', '不再阻止安排制作', '原批次数量与当前订购量不同', '查看完整历史关联', '不代表从未生产']) assert.ok(html.includes(text), text)
  assert.ok(!html.includes('href="/handcraft/'))
  assert.doesNotMatch(source, /@\/api|fetch\(|localStorage/)
})

test('bound history keeps its source link and protection; no guessed allocation is offered', async () => {
  const html = await render(line({ legacy_claim: true, legacy_batches: [{ batch_id: 16, quantity: 60,
    production_order_id: 'HC-test', source_item_id: 9, blocks_allocation: true }] }))
  assert.ok(html.includes('不能直接新增份额'))
  assert.ok(html.includes('href="/handcraft/HC-test"'))
  assert.ok(html.includes('原产出明细 #9'))
  assert.ok(!html.includes('原批次数量与当前订购量不同'))
})

test('old direct links without batch records still explain where to review; names are escaped', async () => {
  const html = await render(line({ legacy_claim: true, legacy_batches: [], product_name: '<script>alert(1)</script>' }))
  assert.ok(html.includes('此明细有旧关联'))
  assert.ok(html.includes('&lt;script&gt;'))
  assert.ok(!html.includes('<script>'))
})
