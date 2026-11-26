import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { filterOrderLines } from '../src/utils/orderReadinessFilter.js'
import { orderHandcraftBatchPayload } from '../src/utils/orderProductionCreation.js'
import { allocationBatchReview, allocationBatchPayload } from '../src/utils/productionAllocation.js'

const lines = [
  { id: 1, product_type: 'part', product_id: 'P', unit: '个', quantity: 40, allocated: 25 },
  { id: 2, product_type: 'part', product_id: 'P', unit: '个', quantity: 20, allocated: 5 },
]
const output = (id, allocations = [], overrides = {}) => ({ source_type: 'handcraft', source_item_id: id, production_order_id: `HC-${id}`,
  product_type: 'part', product_id: 'P', status: 'pending', planned: 30, allocated: allocations.reduce((n, r) => n + r.quantity, 0), allocations,
  revision: 'r'.repeat(64), ...overrides })
const own = (id, quantity) => ({ order_id: 'OR-1', order_item_id: id, quantity })
const rows = lines.map(line => ({ line, planned: 20, allocated: 15, materials: [{ part_id: 'raw', unit: '个', qty: 10 }] }))
const values = { rows, supplier: ' 商家 ', requestKey: 'batch-test-key' }

test('readiness filter keeps every nonzero or unknown historical gap without mutating totals', () => {
  const all = [0, '0.0000', 4, -1, null, undefined, '', NaN].map((gap, id) => ({ id, gap }))
  assert.equal(filterOrderLines(all, 'all'), all)
  assert.deepEqual(filterOrderLines(all, 'pending').map(l => l.id), [2, 3, 4, 5, 6, 7])
  assert.equal(all.length, 8)
})

test('batch creation preserves duplicate product lines and unmerged per-line materials', () => {
  const result = orderHandcraftBatchPayload(values)
  assert.deepEqual(result.allocations, [{ order_item_id: 1, allocated_quantity: 15 }, { order_item_id: 2, allocated_quantity: 15 }])
  assert.equal(result.jewelries.length, 2)
  assert.deepEqual(result.parts, [{ part_id: 'raw', unit: '个', qty: 10 }, { part_id: 'raw', unit: '个', qty: 10 }])
  assert.equal(result.supplier_name, '商家')
  assert.equal(orderHandcraftBatchPayload({ ...values, targetId: 'HC-exact' }).append_to_order_id, 'HC-exact')
  for (const rows of [[], [values.rows[0], values.rows[0]], Array(101).fill(values.rows[0])]) assert.throws(() => orderHandcraftBatchPayload({ ...values, rows }))
  const legacy = [{ ...rows[0], line: { ...lines[0], legacy_batches: [{ id: 9 }] } }]
  assert.throws(() => orderHandcraftBatchPayload({ ...values, rows: legacy }), /确认/)
  assert.doesNotThrow(() => orderHandcraftBatchPayload({ ...values, rows: legacy, reviewed: true }))
  assert.throws(() => orderHandcraftBatchPayload({ ...values, rows: [{ ...rows[0], allocated: 16 }] }))
})

test('cross-source review counts unselected production and protects other customers capacity', () => {
  const sources = [output(10, [own(1, 10)]), output(20, [own(2, 5), { order_id: 'OR-other', order_item_id: 99, quantity: 12 }])]
  const drafts = { 10: { 1: 12, 2: 3 }, 20: { 1: 8, 2: 4 } }
  const review = allocationBatchReview(lines, sources, drafts, 'OR-1')
  assert.deepEqual(review.sources.map(r => [r.total, r.limit]), [[15, 30], [12, 18]])
  assert.deepEqual(review.lines.map(r => [r.total, r.limit]), [[35, 40], [7, 20]])
  const payload = allocationBatchPayload(lines, sources, drafts, 'OR-1')
  assert.equal(payload.length, 2)
  assert.equal(payload[1].source_item_id, 20)
  assert.ok(payload.every(s => s.allocations.every(a => [1, 2].includes(a.order_item_id))))
  assert.throws(() => allocationBatchPayload(lines, sources, { ...drafts, 20: { 1: 15, 2: 4 } }, 'OR-1'), /容量/)
  assert.throws(() => allocationBatchPayload(lines, sources, { ...drafts, 10: { 1: 20, 2: 3 } }, 'OR-1'), /需求/)
  assert.throws(() => allocationBatchPayload(lines, sources, { ...drafts, 10: { 1: 0.5, 2: 0 } }, 'OR-1'), /整数/)
})

test('batch replacement can move full shares across sources and release all shares with zero', () => {
  const line = { ...lines[0], quantity: 40, allocated: 40 }
  const sources = [output(1, [own(1, 40)], { planned: 40 }), output(2, [], { planned: 40 })]
  const payloads = allocationBatchPayload([line], sources, { 1: { 1: 0 }, 2: { 1: 40 } }, 'OR-1')
  assert.deepEqual(payloads.map(p => p.allocations[0].quantity), [0, 40])
  assert.doesNotThrow(() => allocationBatchPayload([line], sources, { 1: { 1: 0 }, 2: { 1: 0 } }, 'OR-1'))
})

test('direct and BOM demands stay separate and fractional capacity uses four-place arithmetic', () => {
  const demands = [{ ...lines[0], quantity: 0.3, allocated: 0 }, { ...lines[0], id: 'material:1:P', order_item_id: 1, material_part_id: 'P', demand_revision: 'd'.repeat(64), quantity: 0.3, allocated: 0 }]
  const source = output(1, [], { source_type: 'plating', planned: 0.3 })
  // Direct quantities still must be integers; review itself handles exact four-place totals.
  const review = allocationBatchReview(demands, [source], { 1: { 1: 0.1, 'material:1:P': 0.2 } }, 'OR-1')
  assert.equal(review.sources[0].invalid, false)
  const payload = allocationBatchPayload([demands[1]], [source], { 1: { 'material:1:P': 0.3 } }, 'OR-1')
  assert.deepEqual(payload[0].allocations[0], { order_item_id: 1, material_part_id: 'P', demand_revision: 'd'.repeat(64), quantity: 0.3 })
})

test('new real batch dialog and section templates compile, freeze uncertain requests and keep hidden state mounted', () => {
  for (const path of ['components/fulfillment/OrderHandcraftBatchDialog.vue', 'components/fulfillment/OrderSection.vue']) {
    const source = readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')
    const { descriptor } = parse(source), script = compileScript(descriptor, { id: path })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: path, id: path, compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
    if (path.includes('BatchDialog')) {
      assert.match(source, /if \(!attempt\) attempt = orderHandcraftBatchPayload/)
      assert.match(source, /createOrderHandcraftBatch\(props.orderId, attempt\)/)
      assert.match(source, /onBeforeRouteLeave\(\(\) => !blocked.value\)/)
      assert.match(source, /window.addEventListener\('beforeunload'/)
    } else {
      assert.match(source, /v-show="!collapsed"/)
      assert.match(source, /:aria-expanded="!collapsed"/)
    }
  }
})

test('collapse controls use consistent SVG icons, grouped existing buttons and reduced-motion support', () => {
  const section = readFileSync(new URL('../src/components/fulfillment/OrderSection.vue', import.meta.url), 'utf8')
  const page = readFileSync(new URL('../src/views/orders/OrderProduction.vue', import.meta.url), 'utf8')
  assert.match(section, /class="ow-section-chevron" aria-hidden="true"><svg/)
  assert.doesNotMatch(section, /collapsed \? '›' : '⌄'/)
  assert.match(section, /aria-expanded="true".*ow-section-chevron svg/)
  assert.match(section, /prefers-reduced-motion:reduce/)
  assert.match(page, /role="group" aria-label="模块展开与收起"/)
  assert.equal((page.match(/<n-button quaternary size="small" class="section-control-button"/g) || []).length, 2)
  assert.match(page, /@click="expandSections\(false\)"/)
  assert.match(page, /@click="expandSections\(true\)"/)
})
