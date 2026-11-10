import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h } from 'vue'

// Mount the real picker with Vue's renderer. Stub only decorative icons: no DOM
// library is needed to test the native input's file-selection event lifecycle.
const source = readFileSync(new URL('../src/components/ImageFilePicker.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
let code = compileScript(descriptor, { id: 'image-picker-test', inlineTemplate: true }).content
code = code.replace(/from (['"])vue\1/g, `from ${JSON.stringify(import.meta.resolve('vue'))}`)
  .replace(/import .* from 'naive-ui'/, 'const NIcon = { render: () => null }')
  .replace(/import .* from '@vicons\/ionicons5'/, 'const CameraOutline = {}; const FolderOpenOutline = {}')
const { default: Picker } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

const renderer = createRenderer({
  createElement: (tag) => ({ tag, props: {}, children: [] }),
  createText: (text) => ({ text }), createComment: () => ({}),
  setText: (node, text) => { node.text = text },
  setElementText: (node, text) => { node.text = text },
  patchProp: (node, key, _previous, value) => { node.props[key] = value },
  insert: (child, parent) => { parent.children.push(child) },
  remove() {}, parentNode: () => null, nextSibling: () => null,
})

function mount(props = {}) {
  const root = { children: [] }
  const selected = []
  renderer.render(h(Picker, { ...props, onSelect: (file) => selected.push(file) }), root)
  const input = root.children[0].children.find((child) => child.tag === 'input')
  const target = { value: '', files: [] }
  const event = { currentTarget: target, target }
  return { input, target, event, selected }
}

test('camera and local entry are native image inputs; only camera requests capture', () => {
  const camera = mount({ source: 'camera' }).input.props
  const local = mount().input.props
  assert.equal(camera.type, 'file')
  assert.equal(camera.accept, 'image/*')
  assert.equal(camera.capture, 'environment')
  assert.equal(camera['aria-label'], '拍照上传')
  assert.equal(local.capture, undefined)
  assert.equal(local['aria-label'], '本地上传')
  assert.doesNotMatch(source.replace(/<!--[\s\S]*?-->/g, ''), /display:\s*none|\.click\(\)/)
})

test('input-only mobile return uploads once; input plus change never duplicates the upload', () => {
  const { input, target, event, selected } = mount()
  const file = new File(['photo'], 'same-photo.jpg', { type: 'image/jpeg' })
  input.props.onClick(event)
  target.files = [file]
  input.props.onInput(event)
  assert.deepEqual(selected, [file])
  input.props.onChange(event)
  assert.deepEqual(selected, [file])
})

test('change-only selection works, cancellation is silent, same photo can be reselected', () => {
  const { input, target, event, selected } = mount()
  input.props.onClick(event)
  input.props.onChange(event)
  assert.equal(selected.length, 0)
  const file = new File(['photo'], 'same-photo.jpg', { type: 'image/jpeg' })
  target.files = [file]
  target.value = 'selected-photo'
  input.props.onChange(event)
  assert.equal(target.value, 'selected-photo', 'do not clear the file before the upload reads it')
  input.props.onClick(event)
  assert.equal(target.value, '')
  input.props.onChange(event)
  assert.deepEqual(selected, [file, file])
})

test('busy picker disables native selection and ignores late file events', () => {
  const { input, target, event, selected } = mount({ disabled: true })
  assert.equal(input.props.disabled, true)
  target.files = [new File(['photo'], 'photo.jpg', { type: 'image/jpeg' })]
  input.props.onInput(event)
  input.props.onChange(event)
  assert.equal(selected.length, 0)
})
