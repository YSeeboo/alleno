// Display-only totals. Never replace the exact demand/source identities used for allocation.
const SCALE = 10000000n
function quantityUnits(value) {
  if (value == null || String(value).trim() === '' || !Number.isFinite(Number(value))) return null
  const match = String(value).trim().match(/^\+?(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i)
  if (!match) return null
  const fraction = match[2] || '', shift = 7 + Number(match[3] || 0) - fraction.length
  if (!Number.isSafeInteger(shift) || Math.abs(shift) > 1000) return null
  const digits = BigInt(match[1] + fraction)
  if (shift >= 0) return digits * 10n ** BigInt(shift)
  const divisor = 10n ** BigInt(-shift)
  return digits % divisor === 0n ? digits / divisor : null
}

export function sumMaterialQuantities(values) {
  let total = 0n
  for (const value of values) {
    const units = quantityUnits(value)
    if (units === null) return null
    total += units
  }
  const fraction = String(total % SCALE).padStart(7, '0').replace(/0+$/, '')
  return `${total / SCALE}${fraction ? `.${fraction}` : ''}`
}

export function groupMaterialRows(rows) {
  const groups = new Map(), result = []
  for (const row of rows) {
    if (row.missing) { result.push(row); continue }
    const unit = row.unit ?? row.part?.unit ?? ''
    const key = `material-group:${JSON.stringify([row.part_id, unit])}`
    if (!groups.has(key)) {
      const group = { ...row, key, unit, sources:[] }
      groups.set(key, group); result.push(group)
    }
    groups.get(key).sources.push(row)
  }
  for (const group of groups.values()) {
    group.quantity = sumMaterialQuantities(group.sources.map(row => row.quantity))
    group.allocated = sumMaterialQuantities(group.sources.map(row => row.allocated))
    group.demand_changed = group.sources.some(row => row.demand_changed)
    group.legacy_claim = group.sources.some(row => row.legacy_claim)
  }
  return result
}
