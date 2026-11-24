// Draft-only helpers. Creating a handcraft order remains one explicit API write.
export const handcraftOutputKey = row => `${row.output_type}:${row.output_type === 'part' ? row.part_id : row.jewelry_id}`
export const handcraftInteger = value => value != null && value !== '' && Number.isSafeInteger(Number(value)) && Number(value) > 0
export const handcraftQuantity = value => value != null && value !== '' && Number.isFinite(Number(value)) && Number(value) > 0 && Number(value) < 1000000 && Math.abs(Number(value) * 10000 - Math.round(Number(value) * 10000)) < 0.000001
export const handcraftRound = value => Math.round(value * 10000) / 10000
export function handcraftUnitTotals(rows) {
  const totals = new Map()
  for (const row of rows) {
    if (row.qty == null || row.qty === '' || !Number.isFinite(Number(row.qty)) || Number(row.qty) <= 0) continue
    const unit = row.unit?.trim() || '个'
    totals.set(unit, handcraftRound((totals.get(unit) || 0) + Number(row.qty)))
  }
  return [...totals].map(([unit, qty]) => ({ unit, qty }))
}
export function makeHandcraftGroup(product, input = {}) {
  return {
    output_type: product.kind,
    jewelry_id: product.kind === 'jewelry' ? product.id : null,
    part_id: product.kind === 'part' ? product.id : null,
    qty: input.qty ?? 1, unit: input.unit ?? product.unit ?? '个', note: input.note || '',
    parts: [], bomState: 'loading', bomError: '',
  }
}
export function handcraftBomRows(group, bom, parts) {
  return bom.map((row, index) => {
    const partId = group.output_type === 'part' ? row.child_part_id : row.part_id
    const part = parts.find(p => (p.id || p.value) === partId)
    const ratio = Number(row.qty_per_unit)
    if (!partId || !part || !Number.isFinite(ratio) || ratio <= 0) throw Error('BOM 含不可用配件或无效用量')
    const total = handcraftInteger(group.qty) ? handcraftRound(ratio * Number(group.qty)) : null
    return { _key: `${partId}:${index}`, part_id: partId, qty: total, unit: part.unit || '个', bom_qty: total, _qty_per_unit: ratio, _manualQty: false, note: '' }
  })
}
export function updateHandcraftGroupQuantity(group, value) {
  group.qty = value
  for (const item of group.parts) {
    if (item._qty_per_unit == null) continue
    const total = handcraftInteger(value) ? handcraftRound(item._qty_per_unit * Number(value)) : null
    item.bom_qty = total
    if (!item._manualQty) item.qty = total
  }
}
export function restoreHandcraftMaterial(group, item) {
  if (item._qty_per_unit == null) return
  item._manualQty = false
  item.qty = handcraftInteger(group.qty) ? handcraftRound(item._qty_per_unit * Number(group.qty)) : null
  item.bom_qty = item.qty
}

// Mirrors services/handcraft.py::HANDCRAFT_BUFFER_RULES, including per-part overrides.
export function handcraftBufferRule(part) {
  const tier = part?.size_tier || 'small'
  const defaults = tier === 'medium' ? { ratio: 0.01, floor: 15 } : { ratio: 0.02, floor: 50 }
  return { tier, ratio: Number(part?.buffer_ratio_override ?? defaults.ratio), floor: Number(part?.buffer_floor_override ?? defaults.floor), overridden: part?.buffer_ratio_override != null || part?.buffer_floor_override != null }
}
export function handcraftSuggestedQty(item, part) {
  if (item.bom_qty == null || Number(item.bom_qty) <= 0) return null
  const { ratio, floor } = handcraftBufferRule(part)
  const theoretical = handcraftRound(Number(item.bom_qty))
  return Math.ceil(theoretical) + Math.ceil(Math.max(floor, handcraftRound(theoretical * ratio)))
}
export function handcraftCreateError({ supplier, mode = 'new', target, groups, extras = [] }) {
  if (!supplier?.trim()) return '请输入手工商家名称'
  if (mode === 'append' && !target) return '请明确选择要追加的待发出手工单'
  const keys = new Set()
  for (const group of groups) {
    if (!['jewelry', 'part'].includes(group.output_type) || !(group.output_type === 'part' ? group.part_id : group.jewelry_id)) return '请先选择有效产出'
    if (!handcraftInteger(group.qty)) return '产出数量必须为正整数，请检查待填写的数量'
    if (!group.unit?.trim()) return '请填写产出单位'
    if (keys.has(handcraftOutputKey(group))) return '同款产出已存在，请在原行修改数量'
    keys.add(handcraftOutputKey(group))
    if (group.bomState === 'loading') return '正在加载 BOM，请稍候再核对'
    if (group.bomState === 'error') return '部分 BOM 加载失败，请先重试，不可按无 BOM 提交'
  }
  const rows = [...groups.flatMap(group => group.parts), ...extras]
  if (!rows.length) return '请至少添加一条实际发出的材料'
  for (const item of rows) {
    if (!item.part_id) return '请选择补充材料中的配件，或移除未填写的行'
    if (!handcraftQuantity(item.qty)) return '实际发出数量须大于 0、小于 1000000，最多 4 位小数'
    if (!item.unit?.trim()) return '请填写材料单位'
    if (item.bom_qty != null && (!Number.isFinite(Number(item.bom_qty)) || Number(item.bom_qty) < 0 || Number(item.bom_qty) >= 1000000)) return 'BOM 理论用量超出范围，请减少制作数量后再核对'
  }
  return ''
}
