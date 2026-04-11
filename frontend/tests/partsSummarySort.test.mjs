// Pure-function unit tests for src/utils/partsSummarySort.js.
// Self-contained: run with `node frontend/tests/partsSummarySort.test.mjs`.
// No external test runner is used (the frontend doesn't pull one in, and
// adding vitest just for this file would be overkill). Failures throw and
// exit non-zero so CI / manual runs surface them loudly.

import assert from 'node:assert/strict'
import {
  colorPriority,
  categoryPriority,
  classifyPartRow,
  sortPartsSummary,
} from '../src/utils/partsSummarySort.js'

const tests = []
const test = (name, fn) => tests.push({ name, fn })

// ---- helpers ----
const row = (overrides) => ({
  part_id: 'PJ-X-00001',
  remaining_qty: 0,
  globally_sufficient: true,
  ...overrides,
})

// ---- colorPriority ----
test('colorPriority: remaining_qty > 0 is red (0)', () => {
  assert.equal(colorPriority(row({ remaining_qty: 5 })), 0)
  assert.equal(colorPriority(row({ remaining_qty: 1 })), 0)
})

test('colorPriority: remaining=0 but globally_sufficient=false is orange (1)', () => {
  assert.equal(colorPriority(row({ remaining_qty: 0, globally_sufficient: false })), 1)
})

test('colorPriority: remaining=0 and globally_sufficient=true is green (2)', () => {
  assert.equal(colorPriority(row({ remaining_qty: 0, globally_sufficient: true })), 2)
})

test('colorPriority: orange takes precedence over reconstructed math (regression)', () => {
  // Even if someone passed ceiled stock/reserved/demand that would look
  // "sufficient" when reconstructed, the authoritative flag wins.
  const r = row({
    remaining_qty: 0,
    globally_sufficient: false,
    current_stock: 101,
    reserved_qty: 51,
    global_demand: 50, // reconstructed available = 50, demand = 50 → looks green
  })
  assert.equal(colorPriority(r), 1) // still orange because flag says so
})

// ---- categoryPriority ----
test('categoryPriority: LT = 0, X = 1, DZ = 2, other = 3', () => {
  assert.equal(categoryPriority({ part_id: 'PJ-LT-00001' }), 0)
  assert.equal(categoryPriority({ part_id: 'PJ-X-00001' }), 1)
  assert.equal(categoryPriority({ part_id: 'PJ-DZ-00001' }), 2)
  assert.equal(categoryPriority({ part_id: 'PJ-OTHER-00001' }), 3)
  assert.equal(categoryPriority({ part_id: '' }), 3)
  assert.equal(categoryPriority({}), 3)
})

// ---- classifyPartRow ----
test('classifyPartRow: null remaining_qty is unknown', () => {
  assert.equal(classifyPartRow(row({ remaining_qty: null })), 'unknown')
  assert.equal(classifyPartRow(row({ remaining_qty: undefined })), 'unknown')
})

test('classifyPartRow: red and orange both map to attention', () => {
  assert.equal(classifyPartRow(row({ remaining_qty: 5 })), 'attention')
  assert.equal(
    classifyPartRow(row({ remaining_qty: 0, globally_sufficient: false })),
    'attention',
  )
})

test('classifyPartRow: green maps to sufficient', () => {
  assert.equal(
    classifyPartRow(row({ remaining_qty: 0, globally_sufficient: true })),
    'sufficient',
  )
})

// ---- sortPartsSummary: primary by color ----
test('sortPartsSummary: red → orange → green', () => {
  const input = [
    row({ part_id: 'PJ-X-00003', remaining_qty: 0, globally_sufficient: true }), // green
    row({ part_id: 'PJ-X-00002', remaining_qty: 0, globally_sufficient: false }), // orange
    row({ part_id: 'PJ-X-00001', remaining_qty: 5 }), // red
  ]
  const out = sortPartsSummary(input).map((r) => r.part_id)
  assert.deepEqual(out, ['PJ-X-00001', 'PJ-X-00002', 'PJ-X-00003'])
})

// ---- sortPartsSummary: secondary by category within same color ----
test('sortPartsSummary: within same color, LT → X → DZ', () => {
  const allGreen = [
    row({ part_id: 'PJ-DZ-00001' }), // dz
    row({ part_id: 'PJ-X-00001' }),  // x
    row({ part_id: 'PJ-LT-00001' }), // lt
  ]
  const out = sortPartsSummary(allGreen).map((r) => r.part_id)
  assert.deepEqual(out, ['PJ-LT-00001', 'PJ-X-00001', 'PJ-DZ-00001'])
})

// ---- sortPartsSummary: full matrix ----
test('sortPartsSummary: full two-level ordering across colors + categories', () => {
  // Mix all 9 combinations (3 colors × 3 categories). Expect all red first
  // (by LT, X, DZ), then all orange (by LT, X, DZ), then all green (by LT, X, DZ).
  const mk = (category, color, n) => {
    const prefix = `PJ-${category}-0000${n}`
    if (color === 'red') return row({ part_id: prefix, remaining_qty: 10, globally_sufficient: false })
    if (color === 'orange') return row({ part_id: prefix, remaining_qty: 0, globally_sufficient: false })
    return row({ part_id: prefix, remaining_qty: 0, globally_sufficient: true })
  }
  const input = [
    mk('DZ', 'green', 1),   // last
    mk('LT', 'red', 2),     // first (red + LT)
    mk('X', 'orange', 3),
    mk('DZ', 'red', 4),
    mk('LT', 'green', 5),
    mk('X', 'red', 6),
    mk('LT', 'orange', 7),
    mk('X', 'green', 8),
    mk('DZ', 'orange', 9),
  ]
  const out = sortPartsSummary(input).map((r) => r.part_id)
  assert.deepEqual(out, [
    // reds
    'PJ-LT-00002',
    'PJ-X-00006',
    'PJ-DZ-00004',
    // oranges
    'PJ-LT-00007',
    'PJ-X-00003',
    'PJ-DZ-00009',
    // greens
    'PJ-LT-00005',
    'PJ-X-00008',
    'PJ-DZ-00001',
  ])
})

// ---- sortPartsSummary: tertiary by part_id, stable against duplicates ----
test('sortPartsSummary: ties broken by part_id lexicographic, stable', () => {
  const input = [
    row({ part_id: 'PJ-LT-00005' }),
    row({ part_id: 'PJ-LT-00001' }),
    row({ part_id: 'PJ-LT-00003' }),
  ]
  const out = sortPartsSummary(input).map((r) => r.part_id)
  assert.deepEqual(out, ['PJ-LT-00001', 'PJ-LT-00003', 'PJ-LT-00005'])
})

test('sortPartsSummary: does not mutate input array', () => {
  const input = [
    row({ part_id: 'PJ-DZ-00001' }),
    row({ part_id: 'PJ-LT-00001' }),
  ]
  const snapshot = input.map((r) => r.part_id)
  sortPartsSummary(input)
  assert.deepEqual(
    input.map((r) => r.part_id),
    snapshot,
  )
})

// ---- regression: ceiling-induced orange misclassification ----
test('sortPartsSummary: fractional-boundary row is orange, not green (regression)', () => {
  // Reviewer's concern: backend ceils current_stock / reserved_qty /
  // global_demand independently; the frontend used to reconstruct
  // available = stock - reserved and compare to demand, which could flip the
  // classification. Now we trust globally_sufficient from the backend.
  //
  // raw: stock=100.1, reserved=50.6 → available=49.5; demand=49.8 → ORANGE
  // ceiled independently: stock=101, reserved=51, demand=50
  //   reconstructed: (101 - 51) = 50 >= 50 → looks green ← WRONG
  const input = [
    row({
      part_id: 'PJ-LT-09999',
      remaining_qty: 0,
      globally_sufficient: false,    // authoritative: ORANGE
      current_stock: 101,            // ceiled from raw 100.1
      reserved_qty: 51,              // ceiled from raw 50.6
      global_demand: 50,             // ceiled from raw 49.8
    }),
    row({
      part_id: 'PJ-LT-00001',
      remaining_qty: 0,
      globally_sufficient: true,     // green
    }),
  ]
  const out = sortPartsSummary(input).map((r) => r.part_id)
  // Orange comes before green regardless of part_id ordering within LT.
  assert.deepEqual(out, ['PJ-LT-09999', 'PJ-LT-00001'])
})

// ---- runner ----
let passed = 0
let failed = 0
for (const { name, fn } of tests) {
  try {
    fn()
    passed++
    console.log(`  ✓ ${name}`)
  } catch (e) {
    failed++
    console.error(`  ✗ ${name}`)
    console.error(`    ${e.message}`)
  }
}
console.log(`\n${passed} passed, ${failed} failed`)
if (failed > 0) process.exit(1)
