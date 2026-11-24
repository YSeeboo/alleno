import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import { handcraftOutputKey, handcraftInteger, handcraftQuantity, handcraftUnitTotals, makeHandcraftGroup, handcraftBomRows, updateHandcraftGroupQuantity, restoreHandcraftMaterial, handcraftSuggestedQty, handcraftCreateError } from '../src/utils/handcraftCreate.js'

const jewelry = { id: 'SP-1', name: '耳环', kind: 'jewelry', key: 'jewelry:SP-1', unit: '对' }
const composite = { id: 'PJ-OUT', name: '连接链', kind: 'part', key: 'part:PJ-OUT', unit: '条' }
const part = { id: 'PJ-1', name: '圆环', unit: '个', size_tier: 'small' }
function group(product = jewelry, qty = 100) {
  const result = makeHandcraftGroup(product, { qty })
  result.parts = handcraftBomRows(result, [{ part_id: part.id, child_part_id: part.id, qty_per_unit: 2 }], [part])
  result.bomState = 'ready'
  return result
}
const validate = (groups, extra = {}) => handcraftCreateError({ supplier: 'A', groups, ...extra })
test('production create treats jewelry and composite identities independently', () => {
  const first = group(), second = group(composite)
  assert.equal(handcraftOutputKey(first), jewelry.key)
  assert.equal(handcraftOutputKey(second), composite.key)
  assert.equal(first.part_id, null)
  assert.equal(second.jewelry_id, null)
  assert.equal(validate([first, second]), '')
  assert.match(validate([first, first]), /同款/)
})
test('BOM material quantities follow final output quantity for both output kinds', () => {
  for (const product of [jewelry, composite]) {
    const output = group(product)
    updateHandcraftGroupQuantity(output, '85')
    assert.equal(output.parts[0].qty, 170)
    assert.equal(output.parts[0].bom_qty, 170)
    updateHandcraftGroupQuantity(output, '')
    assert.equal(output.parts[0].qty, null)
    assert.equal(output.parts[0].bom_qty, null)
    assert.match(validate([output]), /正整数/)
  }
})
test('manual actual quantities remain while theoretical use follows the current quantity; restore uses current BOM', () => {
  const output = group()
  output.parts[0]._manualQty = true
  output.parts[0].qty = '230'
  updateHandcraftGroupQuantity(output, 63)
  assert.equal(output.parts[0].qty, '230')
  assert.equal(output.parts[0].bom_qty, 126)
  output.parts[0].qty = ''
  updateHandcraftGroupQuantity(output, 50)
  assert.equal(output.parts[0].qty, '')
  assert.match(validate([output]), /实际发出/)
  restoreHandcraftMaterial(output, output.parts[0])
  assert.equal(output.parts[0].qty, 100)
  assert.equal(output.parts[0]._manualQty, false)
})
test('BOM load rejects broken references and invalid ratios instead of generating an empty BOM', () => {
  for (const bom of [[{ part_id: 'MISSING', qty_per_unit: 1 }], [{ part_id: part.id, qty_per_unit: 0 }], [{ part_id: part.id, qty_per_unit: NaN }]]) {
    assert.throws(() => handcraftBomRows(group(), bom, [part]), /不可用|无效/)
  }
})
test('fractional BOM values are rounded to four decimals without changing the source definition', () => {
  const output = makeHandcraftGroup(composite, { qty: 63 })
  const bom = [{ child_part_id: part.id, qty_per_unit: .45 }]
  const rows = handcraftBomRows(output, bom, [part])
  assert.equal(rows[0].qty, 28.35)
  assert.equal(bom[0].qty_per_unit, .45)
})
test('material-only drafts and missing BOM with explicitly added material are valid', () => {
  const extra = { part_id: part.id, qty: .0001, unit: '个' }
  assert.equal(validate([], { extras: [extra] }), '')
  const output = makeHandcraftGroup(jewelry)
  output.bomState = 'empty'
  assert.match(validate([output]), /至少/)
  assert.equal(validate([output], { extras: [extra] }), '')
})
test('loading or failed BOM cannot be silently submitted even when extra materials exist', () => {
  const output = group(), extras = [{ part_id: part.id, qty: 1, unit: '个' }]
  output.bomState = 'loading'
  assert.match(validate([output], { extras }), /加载/)
  output.bomState = 'error'
  assert.match(validate([output], { extras }), /重试/)
})
test('supplier, append target, units, integer output and every material are validated', () => {
  assert.match(validate([group()], { supplier: ' ' }), /商家/)
  assert.match(validate([group()], { mode: 'append' }), /明确/)
  assert.equal(validate([group()], { mode: 'append', target: 'HC-1' }), '')
  for (const value of ['', null, 0, -1, 1.5, Infinity, 'bad']) assert.equal(handcraftInteger(value), false)
  for (const value of ['', null, 0, -1, .00001, 1000000, Infinity]) assert.equal(handcraftQuantity(value), false)
  for (const value of [.0001, '999999.9999', '1.2345']) assert.equal(handcraftQuantity(value), true)
  const output = group(); output.unit = ' '
  assert.match(validate([output]), /单位/)
  assert.match(validate([], { extras: [{ qty: 1, unit: '个' }] }), /配件/)
})
test('buffer suggestions retain tier defaults, per-part overrides and floating-point ceiling safeguards', () => {
  assert.equal(handcraftSuggestedQty({ bom_qty: 200 }, part), 250)
  assert.equal(handcraftSuggestedQty({ bom_qty: 200 }, { size_tier: 'medium' }), 215)
  assert.equal(handcraftSuggestedQty({ bom_qty: 100 }, { buffer_ratio_override: .01, buffer_floor_override: 0 }), 101)
  assert.equal(handcraftSuggestedQty({ bom_qty: 100.00000000000001 }, { buffer_ratio_override: .01, buffer_floor_override: 0 }), 101)
  assert.equal(handcraftSuggestedQty({ bom_qty: null }, part), null)
})
test('totals group by unit instead of adding mixed units and avoid decimal drift', () => {
  assert.deepEqual(handcraftUnitTotals([{ qty: 85, unit: '对' }, { qty: 63, unit: '条' }, { qty: 2, unit: '条' }, { qty: '', unit: '条' }, { qty: .1, unit: '米' }, { qty: .2, unit: '米' }]), [{ unit: '对', qty: 85 }, { unit: '条', qty: 65 }, { unit: '米', qty: .3 }])
})

// Execute the real draft-only picker script. Only UI rendering is substituted.
const pickerSource = readFileSync(new URL('../src/components/handcraft/HandcraftOutputPicker.vue', import.meta.url), 'utf8')
const pickerCode = compileScript(parse(pickerSource).descriptor, { id: 'hc-output-picker' }).content
  .replace(/from ['"]vue['"]/g, `from ${JSON.stringify(import.meta.resolve('vue'))}`)
  .replace(/import \{ ([^}]+) \} from ['"]naive-ui['"]/g, (_, names) => `const ${names.split(',').map(name => `${name.trim()} = {}`).join(', ')};`)
  .replace(/import \{ useIsMobile \} from ['"]@\/composables\/useIsMobile['"]/, 'const useIsMobile = () => ({ isMobile: ref(false) });')
  .replace(/from ['"]@\/utils\/handcraftCreate['"]/, `from ${JSON.stringify(new URL('../src/utils/handcraftCreate.js', import.meta.url).href)}`)
const Picker = (await import(`data:text/javascript;base64,${Buffer.from(pickerCode).toString('base64')}`)).default
function picker(initial = []) {
  const emitted = []
  const props = { products: [jewelry, composite], initial, busy: false, applyError: '' }
  return { props, emitted, ctx: Picker.setup(props, { expose() {}, emit: (...args) => emitted.push(args) }) }
}
test('real picker copies initial editable values and does not mutate the main draft when cancelled', () => {
  const initial = [group()], { ctx } = picker(initial)
  ctx.rows.value[0].qty = '85'
  ctx.rows.value[0].note = 'test'
  ctx.toggle(composite, true)
  assert.equal(initial[0].qty, 100)
  assert.equal(initial[0].note, '')
  assert.equal(initial.length, 1)
})
test('real picker filtering and bulk selection keep drafts, reject zero and commit final integer values', () => {
  const { ctx, emitted } = picker()
  ctx.toggle(jewelry, true)
  ctx.kind.value = 'part'
  ctx.selectAll(true)
  assert.equal(ctx.rows.value.length, 2)
  ctx.batchQty.value = '0'; ctx.applyQuantity()
  assert.match(ctx.error.value, /正整数/)
  ctx.batchQty.value = '85'; ctx.applyQuantity()
  ctx.rows.value[1].qty = '63'
  ctx.confirm()
  assert.deepEqual(emitted[0][1].map(row => row.qty), [85, 63])
  assert.doesNotMatch(pickerSource, /@\/api\/|saveBatchRow|createHandcraft|addHandcraft/)
})
test('real picker clear-new does not silently remove existing outputs and refuses invalid focused values', () => {
  const { ctx, emitted } = picker([group()])
  ctx.toggle(jewelry, false)
  ctx.toggle(composite, true)
  ctx.clearNew()
  assert.equal(ctx.rows.value.length, 1)
  ctx.rows.value[0].qty = ''
  ctx.confirm()
  assert.equal(emitted.length, 0)
  assert.equal(ctx.tab.value, 'drafts')
})
