import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import cssRenderSsr from '@css-render/vue3-ssr'

const filename = new URL('../src/components/fulfillment/HandcraftTargetPicker.vue', import.meta.url)
const source = await readFile(filename, 'utf8')
const { descriptor } = parse(source, { filename: filename.pathname })
const compiled = compileScript(descriptor, { id: 'handcraft-target-test', inlineTemplate: true })
const code = compiled.content
  .replace(/from ['"]vue['"]/g, `from ${JSON.stringify(import.meta.resolve('vue'))}`)
  .replace(/import \{ ([^}]+) \} from ['"]naive-ui['"]/, (_, names) => `import NaiveUI from ${JSON.stringify(import.meta.resolve('naive-ui'))}; const { ${names} } = NaiveUI`)
  .replace(/import \{ listHandcraft \} from ['"]@\/api\/handcraft['"]/, 'const listHandcraft = async () => ({ data: [] })')
const { default: Picker } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const render = props => {
  const app = createSSRApp({ render: () => h(Picker, props) })
  cssRenderSsr.setup(app)
  return renderToString(app)
}

test('real handcraft target picker defaults to a new independent order, not an eligible existing order', async () => {
  const html = await render({ supplierName: '', modelValue: null })
  assert.match(html, /新建独立手工单（默认）/)
  assert.match(html, /class="n-select"/)
  assert.doesNotMatch(html, /n-base-selection--disabled/)
  assert.match(html, /不会因为同商家、同一天而自动合单/)
  assert.doesNotMatch(html, /追加到 HC-/)
})

test('append selector is disabled while saving and does not promise to merge old rows', async () => {
  const html = await render({ supplierName: '', modelValue: 'HC-EXPLICIT', disabled: true })
  assert.match(html, /n-base-selection--disabled/)
  assert.match(html, /只追加本次新增明细，不合并或改写原明细/)
})

test('standalone and exact-line order creation both send the explicitly selected target', async () => {
  const create = await readFile(new URL('../src/views/handcraft/HandcraftCreate.vue', import.meta.url), 'utf8')
  const dialog = await readFile(new URL('../src/components/fulfillment/OrderHandcraftDialog.vue', import.meta.url), 'utf8')
  const payload = await readFile(new URL('../src/utils/orderProductionCreation.js', import.meta.url), 'utf8')
  assert.match(create, /append_to_order_id: appendToOrderId.value/)
  assert.match(create, /appendToOrderId = ref\(null\)/)
  assert.match(dialog, /HandcraftTargetPicker v-model="targetId"/)
  assert.match(payload, /append_to_order_id: targetId/)
  assert.doesNotMatch(create, /触发同日合并/)
})
