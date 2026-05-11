// Pure-function unit tests for src/utils/recentImports.js.
// Self-contained: run with `node frontend/tests/recentImports.test.mjs`.
// Follows the same pattern as partsSummarySort.test.mjs.

import assert from 'node:assert/strict'

// Polyfill localStorage for node (the util uses globalThis.localStorage).
const store = new Map()
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
}

const {
  STORAGE_KEY,
  MAX_BATCHES,
  MAX_AGE_MS,
  pushBatch,
  getActiveBatches,
  getBatchById,
  updateBatchPartImage,
} = await import('../src/utils/recentImports.js')

const tests = []
const test = (name, fn) => tests.push({ name, fn })
const reset = () => { localStorage.clear() }

const samplePart = (id, qty = 1) => ({
  part_id: id, name: `name-${id}`, image: null, unit: '个', imported_qty: qty,
})

// ---- pushBatch ----
test('pushBatch: returns a batch with batch_id, imported_at, parts', () => {
  reset()
  const batch = pushBatch([samplePart('PJ-DZ-00001')], { now: 1715332920000, operator: 'ycb' })
  assert.equal(typeof batch.batch_id, 'string')
  assert.match(batch.batch_id, /^imp-/)
  assert.equal(batch.imported_at, 1715332920000)
  assert.equal(batch.operator, 'ycb')
  assert.equal(batch.parts.length, 1)
  assert.equal(batch.parts[0].part_id, 'PJ-DZ-00001')
})

test('pushBatch: persists to localStorage and shows up in getActiveBatches', () => {
  reset()
  pushBatch([samplePart('PJ-DZ-00001')], { now: 1715332920000, operator: 'ycb' })
  const list = getActiveBatches({ now: 1715332920000 })
  assert.equal(list.length, 1)
  assert.equal(list[0].parts[0].part_id, 'PJ-DZ-00001')
})

test('pushBatch: newest first', () => {
  reset()
  pushBatch([samplePart('A')], { now: 1000, operator: 'x' })
  pushBatch([samplePart('B')], { now: 2000, operator: 'x' })
  const list = getActiveBatches({ now: 2000 })
  assert.equal(list[0].parts[0].part_id, 'B')
  assert.equal(list[1].parts[0].part_id, 'A')
})

// ---- getActiveBatches ----
test('getActiveBatches: empty when nothing stored', () => {
  reset()
  assert.deepEqual(getActiveBatches({ now: Date.now() }), [])
})

test('getActiveBatches: filters out batches older than MAX_AGE_MS', () => {
  reset()
  const now = 10_000_000
  pushBatch([samplePart('OLD')], { now: now - MAX_AGE_MS - 1, operator: 'x' })
  pushBatch([samplePart('NEW')], { now: now - 1000, operator: 'x' })
  const list = getActiveBatches({ now })
  assert.equal(list.length, 1)
  assert.equal(list[0].parts[0].part_id, 'NEW')
})

test('getActiveBatches: keeps at most MAX_BATCHES (FIFO)', () => {
  reset()
  // Push MAX_BATCHES + 3 batches with increasing timestamps: P0 (oldest) ... P7 (newest).
  for (let i = 0; i < MAX_BATCHES + 3; i++) {
    pushBatch([samplePart(`P${i}`)], { now: 1000 + i, operator: 'x' })
  }
  const list = getActiveBatches({ now: 9999 })
  assert.equal(list.length, MAX_BATCHES)
  // Newest first → list[0] = P(MAX+2) = P7
  assert.equal(list[0].parts[0].part_id, `P${MAX_BATCHES + 2}`)
  // Oldest kept = P3 (P0/P1/P2 dropped by FIFO), at the tail
  assert.equal(list[list.length - 1].parts[0].part_id, 'P3')
})

test('getActiveBatches: tolerates corrupt storage', () => {
  reset()
  localStorage.setItem(STORAGE_KEY, 'not-json{')
  assert.deepEqual(getActiveBatches({ now: Date.now() }), [])
})

// ---- getBatchById ----
test('getBatchById: returns the batch when present', () => {
  reset()
  const batch = pushBatch([samplePart('A')], { now: 5000, operator: 'x' })
  const found = getBatchById(batch.batch_id)
  assert.equal(found.parts[0].part_id, 'A')
})

test('getBatchById: returns null when absent', () => {
  reset()
  assert.equal(getBatchById('nope'), null)
})

// ---- updateBatchPartImage ----
test('updateBatchPartImage: writes the image URL into the matching part', () => {
  reset()
  const batch = pushBatch(
    [samplePart('A'), samplePart('B')],
    { now: 5000, operator: 'x' },
  )
  updateBatchPartImage(batch.batch_id, 'B', 'https://cdn/img.png')
  const after = getBatchById(batch.batch_id)
  assert.equal(after.parts[0].image, null)
  assert.equal(after.parts[1].image, 'https://cdn/img.png')
})

test('updateBatchPartImage: clears image when given null', () => {
  reset()
  const batch = pushBatch([samplePart('A')], { now: 5000, operator: 'x' })
  updateBatchPartImage(batch.batch_id, 'A', 'https://cdn/img.png')
  updateBatchPartImage(batch.batch_id, 'A', null)
  assert.equal(getBatchById(batch.batch_id).parts[0].image, null)
})

test('updateBatchPartImage: silently ignores unknown batch / part', () => {
  reset()
  // Should not throw.
  updateBatchPartImage('nope', 'X', 'https://cdn/img.png')
  const batch = pushBatch([samplePart('A')], { now: 5000, operator: 'x' })
  updateBatchPartImage(batch.batch_id, 'NOPE', 'https://cdn/img.png')
  assert.equal(getBatchById(batch.batch_id).parts[0].image, null)
})

// ---- runner ----
let failed = 0
for (const t of tests) {
  try {
    t.fn()
    console.log(`ok  ${t.name}`)
  } catch (e) {
    failed++
    console.error(`FAIL ${t.name}`)
    console.error(e)
  }
}
if (failed > 0) {
  console.error(`\n${failed} test(s) failed.`)
  process.exit(1)
}
console.log(`\n${tests.length} test(s) passed.`)
