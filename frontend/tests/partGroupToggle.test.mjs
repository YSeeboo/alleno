import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'

// Compile the real component, rather than testing a duplicate rendering helper.
const filename = new URL('../src/components/PartGroupToggle.vue', import.meta.url)
const { descriptor } = parse(await readFile(filename, 'utf8'), { filename: filename.pathname })
const compiled = compileScript(descriptor, { id: 'part-group-toggle-test', inlineTemplate: true })
const code = compiled.content.replace(/from ['"]vue['"]/g, `from ${JSON.stringify(import.meta.resolve('vue'))}`)
const { default: PartGroupToggle } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const render = props => renderToString(createSSRApp({ render: () => h(PartGroupToggle, props) }))

test('a parent with children renders one native button including the complete part ID', async () => {
  const html = await render({ partId: 'PJ-DZ-00001', partName: '小花', childCount: 2 })
  assert.equal((html.match(/<button\b/g) || []).length, 1)
  assert.match(html, /type="button"/)
  assert.match(html, /aria-expanded="false"/)
  assert.match(html, /aria-label="展开 小花 的 2 个子配件"/)
  assert.match(html, /<svg\b/)
  assert.match(html, /<span>PJ-DZ-00001<\/span><\/button>/)
})

test('expanded parents expose their state and collapse action', async () => {
  const html = await render({ partId: 'PJ-ROOT', childCount: 1, expanded: true })
  assert.match(html, /is-expanded/)
  assert.match(html, /aria-expanded="true"/)
  assert.match(html, /aria-label="收起 PJ-ROOT 的 1 个子配件"/)
})

test('a leaf renders text only: no button, arrow, or expansion semantics', async () => {
  for (const props of [{}, { childCount: 0 }, { childCount: 0, expanded: true }]) {
    const html = await render({ partId: 'PJ-LEAF', ...props })
    assert.match(html, /PJ-LEAF/)
    assert.match(html, /class="part-group-spacer" aria-hidden="true"><\/span>/)
    assert.doesNotMatch(html, /<button\b|<svg\b|aria-expanded|▸|role="button"|tabindex/)
  }
})

test('IDs and names are rendered as escaped text, not interpreted as HTML', async () => {
  const html = await render({ partId: '<test>', partName: 'A"B', childCount: 1 })
  assert.match(html, /&lt;test&gt;/)
  assert.match(html, /A&quot;B/)
  assert.doesNotMatch(html, /<test>/)
})
