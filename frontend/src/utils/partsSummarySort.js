// Pure helpers for parts summary classification and sort.
// Extracted so the logic can be unit-tested in isolation from the Vue SFC.
//
// Classification uses the authoritative `globally_sufficient` flag from the
// backend (computed from raw floats before ceiling). Do NOT reconstruct that
// signal from `current_stock - reserved_qty` vs `global_demand` — those three
// fields are ceiled independently and can disagree with the raw comparison
// around fractional meter quantities.

/**
 * Color priority for a parts summary row (B 口径 / 全局视角):
 *   0 — red: 本单不够     (remaining_qty > 0)
 *   1 — orange: 全局紧张   (globally_sufficient === false)
 *   2 — green: 充足       (globally_sufficient === true)
 */
export function colorPriority(row) {
  if ((row.remaining_qty || 0) > 0) return 0
  if (row.globally_sufficient === false) return 1
  return 2
}

/**
 * Category priority based on part_id prefix:
 *   0 — 链条 LT
 *   1 — 小配件 X
 *   2 — 吊坠 DZ
 *   3 — other / unknown (sinks to the bottom)
 */
export function categoryPriority(row) {
  const id = row.part_id || ''
  if (id.includes('-LT-')) return 0
  if (id.includes('-X-')) return 1
  if (id.includes('-DZ-')) return 2
  return 3
}

/**
 * Classify a row into the filter bucket:
 *   'unknown'    — remaining_qty is null/undefined (rare; excluded from counts)
 *   'attention'  — red OR orange (needs action, colors 0 or 1)
 *   'sufficient' — green (color 2)
 */
export function classifyPartRow(row) {
  if (row.remaining_qty == null) return 'unknown'
  if (row.remaining_qty > 0) return 'attention'
  if (row.globally_sufficient === false) return 'attention'
  return 'sufficient'
}

/**
 * Sort a parts summary rows array. Three-level sort:
 *   1) colorPriority — red → orange → green
 *   2) categoryPriority — LT → X → DZ → other
 *   3) part_id lexicographic — stable tiebreaker (prevents row flicker)
 * Returns a new array; does not mutate the input.
 */
export function sortPartsSummary(rows) {
  return rows.slice().sort((a, b) => {
    const colorDiff = colorPriority(a) - colorPriority(b)
    if (colorDiff !== 0) return colorDiff
    const catDiff = categoryPriority(a) - categoryPriority(b)
    if (catDiff !== 0) return catDiff
    return (a.part_id || '').localeCompare(b.part_id || '')
  })
}
