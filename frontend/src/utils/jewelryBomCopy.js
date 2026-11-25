import { validBomQuantity } from './jewelryDetail.js'

export function makeBomCopyDraft(sourceRows, targetRows, partMap) {
  const target = new Map(targetRows.map(row => [row.part_id, row.qty_per_unit]))
  return sourceRows.map(({ part_id, qty_per_unit }) => ({
    partId: part_id,
    partName: partMap[part_id]?.name || part_id,
    color: partMap[part_id]?.color,
    partUnit: partMap[part_id]?.unit,
    sourceQty: qty_per_unit,
    targetQty: target.get(part_id),
    existing: target.has(part_id),
    selected: !target.has(part_id),
    quantity: String(qty_per_unit),
  }))
}

export function bomCopyNeedsUnitCheck(sourceUnit, targetUnit) {
  return !sourceUnit?.trim() || !targetUnit?.trim() || sourceUnit !== targetUnit
}

export function bomCopyPayload(preview, draft, unitConfirmed) {
  if (!preview || (bomCopyNeedsUnitCheck(preview.source.unit, preview.target_unit) && !unitConfirmed)) return null
  const selected = draft.filter(row => row.selected && !row.existing)
  if (!selected.length || selected.some(row => !validBomQuantity(row.quantity))) return null
  return {
    source_id: preview.source.id,
    source_unit: preview.source.unit,
    target_unit: preview.target_unit,
    unit_confirmed: unitConfirmed,
    items: selected.map(row => ({ part_id: row.partId, qty_per_unit: row.quantity })),
  }
}
