import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { SCENES, PLANS, COLORS, PRODUCTS, sceneProducts, unavailable, makeRow, rowErrors, lineAmount, money, quantitySummary, productImage } from '../public/demos/batch-add/domain.js'

const source = file => readFileSync(new URL(`../public/demos/batch-add/${file}`, import.meta.url), 'utf8')
const scene = id => SCENES.find(item => item.id === id)
const part = PRODUCTS.find(item => item.id === 'P-2002')

test('batch selection demo stays isolated from business data, credentials and persistence', () => {
  const html = source('index.html')
  assert.match(html, /connect-src 'none'/)
  assert.match(html, /form-action 'none'/)
  assert.doesNotMatch(source('app.js') + source('domain.js'), /fetch\(|XMLHttpRequest|localStorage|sessionStorage|\/api\/|@\/|\.\.\/\.\.\/src/)
  assert.equal(PLANS.length, 3)
  assert.deepEqual(SCENES.map(item => item.id), ['order', 'plating', 'output', 'material', 'bom', 'purchase'])
})

test('each demo scene has at least two eligible fixtures with its own type and unit', () => {
  for (const current of SCENES) {
    const eligible = sceneProducts(current).filter(item => !unavailable(item, current))
    assert.ok(eligible.length >= 2, current.id)
    for (const item of eligible) {
      const row = makeRow(item, current, `test-${item.id}`)
      assert.equal(row.unit, item.unit)
      assert.deepEqual(rowErrors(row, current), [], `${current.id}/${item.id}`)
    }
  }
  assert.deepEqual(new Set(sceneProducts(scene('output')).map(item => item.kind)), new Set(['jewelry', 'assembly']))
  assert.ok(sceneProducts(scene('material')).every(item => item.kind === 'part'))
})

test('BOM excludes existing components and accepts only positive four-decimal usage', () => {
  const current = scene('bom'), existing = PRODUCTS.find(item => item.existingBom)
  assert.ok(unavailable(existing, current))
  assert.match(rowErrors(makeRow(existing, current, 'existing'), current).join(), /不可添加/)
  for (const qty of ['0.0001', '1.2500', '999999.9999']) assert.deepEqual(rowErrors({ ...makeRow(part, current, 'row'), qty }, current), [])
  for (const qty of ['', '0', '-1', '0.00001', '1000000']) assert.ok(rowErrors({ ...makeRow(part, current, 'row'), qty }, current).length, qty)
})

test('plating checks the selected color without creating a missing component', () => {
  const current = scene('plating'), limited = PRODUCTS.find(item => item.id === 'P-2003')
  const row = makeRow(limited, current, 'plating')
  assert.deepEqual(rowErrors(row, current), [])
  const before = structuredClone(limited)
  for (const color of ['S', 'RG']) assert.match(rowErrors({ ...row, color }, current).join(), /对应配件尚未建立/)
  assert.deepEqual(limited, before)
})

test('quantity and optional weight retain their different meanings by scene', () => {
  for (const id of ['order', 'plating', 'output', 'material', 'purchase']) {
    const current = scene(id), row = makeRow(sceneProducts(current)[0], current, 'row')
    for (const qty of ['', '0', '-1', '1.5', 'Infinity', 'NaN']) assert.ok(rowErrors({ ...row, qty }, current).length, `${id}/${qty}`)
  }
  const current = scene('material'), row = makeRow(part, current, 'row')
  for (const weight of ['', '0', '0.05']) assert.deepEqual(rowErrors({ ...row, weight }, current), [])
  for (const weight of ['-1', 'NaN', 'Infinity']) assert.match(rowErrors({ ...row, weight }, current).join(), /重量/)
})

test('order and purchase accept zero and seven decimal prices and reject missing or overprecision', () => {
  for (const id of ['order', 'purchase']) {
    const current = scene(id), row = makeRow(part, current, 'row')
    for (const price of ['0', '0.1234567', '128.5']) assert.deepEqual(rowErrors({ ...row, price }, current), [])
    for (const price of ['', '-1', '0.12345678', 'Infinity']) assert.match(rowErrors({ ...row, price }, current).join(), /单价/)
  }
})

test('demo prices sum fixed-point values without losing seventh decimal precision', () => {
  assert.equal(lineAmount({ qty: '100', price: '0.1234567' }), 123456700n)
  assert.equal(money(lineAmount({ qty: '100', price: '0.1234567' })), '12.35')
  assert.equal(money(lineAmount({ qty: '100000', price: '0.0000001' })), '0.01')
  assert.equal(money(lineAmount({ qty: '4', price: '0' })), '0.00')
  assert.equal(lineAmount({ qty: '', price: '3' }), null)
})

test('mixed units stay separate and same-product drafts retain independent row identity', () => {
  assert.equal(quantitySummary([{ qty: '100', unit: '条' }, { qty: '40', unit: '对' }, { qty: '50', unit: '条' }]), '150 条 / 40 对')
  const first = makeRow(part, scene('order'), 'one')
  const second = { ...first, key: 'two' }
  second.qty = '30'
  second.price = '2'
  assert.equal(first.qty, '100')
  assert.notEqual(first.key, second.key)
  assert.notEqual(first.price, second.price)
})

test('order addition omits customer codes and selected fields use a single row for up to three inputs', () => {
  assert.deepEqual(scene('order').fields, ['qty', 'unit', 'price'])
  assert.equal(Object.hasOwn(makeRow(part, scene('order'), 'one'), 'code'), false)
  assert.deepEqual(scene('plating').fields, ['qty', 'unit', 'color'])
  assert.ok(SCENES.every(current => current.fields.length <= 3))
  const app = source('app.js'), css = source('styles.css')
  assert.match(app, /class="selected-fields fields-\$\{scene\(\)\.fields\.length\}/)
  assert.doesNotMatch(app, /class="wide"|data-field="code"|row\.code|code: '客户货号'/)
  for (const count of [2, 3]) assert.ok(css.includes(`.selected-fields.fields-${count}{grid-template-columns:repeat(${count},minmax(0,1fr))}`))
})

test('plating uses the original common and more color chips rather than a color select', () => {
  assert.deepEqual(COLORS.filter(color => color.common).map(color => color.value), ['G', 'S', 'RG'])
  assert.deepEqual(COLORS.filter(color => !color.common).map(color => color.value), ['K14', 'SV'])
  assert.equal(makeRow(part, scene('plating'), 'row').color, 'G')
  const app = source('app.js')
  assert.match(app, /if \(field === 'color'\) return colorPicker\(row\)/)
  assert.match(app, /data-color-more=/)
  assert.match(app, /aria-pressed=/)
  assert.doesNotMatch(app, /<select id="batch-color"|if \(field === 'color'\) return `<select/)
  const oldColorConfig = readFileSync(new URL('../../services/part.py', import.meta.url), 'utf8')
  for (const color of COLORS) assert.ok(oldColorConfig.includes(`"code": "${color.value}"`))
})

test('every fixture has a self-contained product image and scene guidance stays specific', () => {
  for (const item of PRODUCTS) assert.match(decodeURIComponent(productImage(item)), /^data:image\/svg\+xml,<svg/)
  assert.match(source('index.html'), /采购单 → 追加配件/)
  assert.match(source('index.html'), /已有批量能力/)
  assert.match(scene('output').impact, /BOM/)
  assert.match(scene('bom').impact, /不调整库存/)
  assert.match(source('styles.css'), /@media\(max-width:700px\)/)
})
