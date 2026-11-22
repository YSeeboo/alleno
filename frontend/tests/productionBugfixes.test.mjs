import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { setupBatch, part } from './helpers/batchAddHarness.mjs'
import { makeBatchRow } from '../src/utils/batchAdd.js'

const view = (path) => readFileSync(new URL(`../src/views/${path}.vue`, import.meta.url), 'utf8')
const deferred = () => {
  let resolve
  const promise = new Promise(r => { resolve = r })
  return { promise, resolve }
}
const response = (data) => Promise.resolve({ data })

function partDetailHarness(overrides = {}) {
  const names = ['loading', 'part', 'stock', 'logs', 'costLogs', 'parentPartName', 'partBomList',
    'childPartOptions', 'variantFamily', 'familyStocks', 'staged', 'batchSelectVal', 'showCopyBom', 'showEdit', 'showImageModal']
  const state = Object.fromEntries(names.map(name => [name, { value: 'old' }]))
  let callback
  const deps = {
    ...state, partId: {}, watch: (_, cb, options) => { callback = cb; assert.equal(options.immediate, true) },
    getPart: id => response({ id, name: id, parent_part_id: id === 'root' ? null : 'root' }),
    getStock: (_, id) => response({ current: id === 'root' ? 10 : 25 }),
    getStockLog: (_, id) => response([{ item_id: id }]),
    listParts: () => response([{ id: 'root', name: '原色' }, { id: 'gold', name: '金色' }]),
    getPartBom: id => response([{ child_part_id: `${id}-child` }]),
    getPartCostLogs: id => response([{ part_id: id }]),
    getPartVariants: id => response(id === 'root' ? [{ id: 'gold' }] : [{ id: 'root' }, { id: 'gold' }]),
    batchGetStock: () => response({ root: 10, gold: 25 }), ...overrides,
  }
  const source = view('parts/PartDetail')
  const watcher = source.slice(source.indexOf('watch(partId,'), source.indexOf('</script>'))
  new Function(...Object.keys(deps), watcher)(...Object.values(deps))
  let cleanup = () => {}
  return {
    state,
    load(id) { cleanup(); return callback(id, null, fn => { cleanup = fn }) },
  }
}

test('variant navigation reloads basic information, inventory, costs, BOM, family and parent', async () => {
  const harness = partDetailHarness()
  await harness.load('root')
  assert.equal(harness.state.part.value.id, 'root')
  await harness.load('gold')
  const s = harness.state
  assert.equal(s.part.value.id, 'gold')
  assert.equal(s.stock.value, 25)
  assert.equal(s.logs.value[0].item_id, 'gold')
  assert.equal(s.costLogs.value[0].part_id, 'gold')
  assert.equal(s.partBomList.value[0].child_part_id, 'gold-child')
  assert.deepEqual(s.childPartOptions.value.map(row => row.value), ['root'])
  assert.deepEqual(s.familyStocks.value, { root: 10, gold: 25 })
  assert.equal(s.parentPartName.value, 'root root')
  assert.deepEqual(s.staged.value, [])
  assert.equal(s.showEdit.value, false)
  assert.equal(s.loading.value, false)
})

test('late responses cannot overwrite the latest variant, including A to B to A navigation', async () => {
  const first = deferred()
  let calls = 0
  const harness = partDetailHarness({ getPart: id => ++calls === 1 ? first.promise : response({ id, name: 'latest' }) })
  const old = harness.load('root')
  await harness.load('gold')
  await harness.load('root')
  first.resolve({ data: { id: 'root', name: 'stale' } })
  await old
  assert.equal(harness.state.part.value.name, 'latest')
})

test('a failed variant load clears the previous member instead of showing mismatched information', async () => {
  const harness = partDetailHarness({ getPart: id => id === 'missing' ? Promise.reject(new Error('404')) : response({ id }) })
  await harness.load('root')
  await harness.load('missing')
  assert.equal(harness.state.part.value, null)
  assert.deepEqual(harness.state.partBomList.value, [])
  assert.deepEqual(harness.state.costLogs.value, [])
  assert.equal(harness.state.loading.value, false)
})

for (const [path, scene] of [['handcraft/HandcraftDetail', 'material'], ['plating/PlatingDetail', 'plating']]) {
  function selectionHarness() {
    const fresh = deferred()
    assert.match(view(path), new RegExp(`scene="${scene}"`))
    const h = setupBatch({ scene }, { getPart: () => fresh.promise })
    h.ctx.toggleProduct(part, true)
    return { ...h, fresh, row: h.ctx.rows.value[0] }
  }

  test(`${path}: add modal defaults to selected part's latest unit`, async () => {
    const h = selectionHarness()
    assert.equal(h.row.unit, '米')
    h.fresh.resolve({ data: { unit: '条' } })
    await Promise.resolve()
    assert.equal(h.row.unit, '条')
  })

  test(`${path}: refreshing defaults never overwrites a manual unit change`, async () => {
    const h = selectionHarness()
    h.row.unit = '包'
    h.fresh.resolve({ data: { unit: '条' } })
    await Promise.resolve()
    assert.equal(h.row.unit, '包')
  })

  test(`${path}: stale selection responses cannot change another part's unit`, async () => {
    const h = selectionHarness()
    h.ctx.removeRow(h.row)
    h.ctx.toggleProduct({ ...part, id: 'bead', key: 'part:bead', unit: '个' }, true)
    const next = h.ctx.rows.value[0]
    next.unit = '个（手动）'
    h.fresh.resolve({ data: { unit: '米' } })
    await Promise.resolve()
    assert.equal(h.row.unit, '米')
    assert.equal(next.unit, '个（手动）')
  })

  test(`${path}: closing/reopening the modal isolates old unit refreshes`, async () => {
    const h = selectionHarness()
    h.state.cleanup.forEach(fn => fn())
    h.fresh.resolve({ data: { unit: '条' } })
    await Promise.resolve()
    assert.equal(h.row.unit, '米')
  })
}

test('receipt create requests only pending candidates for both vendor and source lists', () => {
  const source = view('plating-receipts/PlatingReceiptCreate')
  assert.doesNotMatch(source, /include_settled:\s*true/)
})

test('handcraft output selection adopts the correct part/jewelry unit and reloads material rows after saving', () => {
  const source = view('handcraft/HandcraftDetail')
  assert.equal(makeBatchRow('output', part, 'p').unit, '米')
  assert.equal(makeBatchRow('output', { id: 'J', kind: 'jewelry', unit: '对' }, 'j').unit, '对')
  assert.match(source, /scene="output"[^>]+:refresh="refreshAfterOutputBatch"/)
  const saveStart = source.indexOf('async function refreshAfterOutputBatch()')
  const saveEnd = source.indexOf('\n}\n', saveStart)
  assert.match(source.slice(saveStart, saveEnd), /Promise\.all\(\[loadData\(\), loadJewelries\(\), loadBreakdown\(\)\]\)/)
})
