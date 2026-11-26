// Business contracts stay separate even though the six entry points share a picker.
export const batchScenes = {
  order: { title: '批量添加商品', kinds: ['jewelry', 'part'], price: true, note: '同款可再加一行，不自动合并。客户货号之后在订单详情统一维护；单位沿用商品资料。' },
  plating: { title: '批量增加电镀配件', kinds: ['part'], weight: true, note: '仅增加待发出明细，不自动发出或扣减库存。颜色对应配件须核对，缺少时可确认新建。' },
  output: { title: '批量添加产出', kinds: ['jewelry', 'part'], weight: true, note: '新增产出沿用原有 BOM 材料追加规则，不覆盖手工维护的材料。' },
  material: { title: '批量添加配件', kinds: ['part'], weight: true, note: '仅增加手工材料明细；最近导入仍按原规则新增或累加。' },
  bom: { title: '批量添加 BOM 配件', kinds: ['part'], note: '每 1 单位饰品的用量，最多 4 位小数。已有配件请在原行修改；不改变库存。' },
  purchase: { title: '批量追加配件', kinds: ['part'], price: true, note: '单价可留空，0 表示明确为零；最多 7 位小数。仅追加采购明细。' },
}

export function batchCatalog(scene, jewelries, parts) {
  const config = batchScenes[scene]
  return [
    ...(config.kinds.includes('jewelry') ? jewelries.filter(p => p.status === 'active').map(p => ({ ...p, kind: 'jewelry', key: `jewelry:${p.id}` })) : []),
    ...(config.kinds.includes('part') ? parts.filter(p => scene !== 'output' || p.is_composite).map(p => ({ ...p, kind: 'part', key: `part:${p.id}` })) : []),
  ]
}

export function makeBatchRow(scene, product, key, colors = []) {
  const color = colors.find(c => c.label === product.color || product.name?.endsWith(`_${c.label}`))?.code || 'G'
  return { key, product, qty: 1, unit: product.unit || (product.kind === 'jewelry' ? '套' : '个'),
    price: scene === 'purchase' ? null : Number(product.wholesale_price || 0), note: '', weight: null, weightUnit: 'kg',
    color: scene === 'plating' ? (product.is_composite ? (color === 'G' && product.color === '金色' ? 'S' : 'G') : color) : null, variant: null, variantBusy: false, variantSeq: 0,
    status: 'draft', error: '', details: false }
}

function decimal(value, places) {
  if (value == null || value === '' || !Number.isFinite(Number(value))) return false
  const [coefficient, exponent = '0'] = String(value).toLowerCase().split('e')
  return Math.max(0, (coefficient.split('.')[1]?.length || 0) - Number(exponent)) <= places
}

export function batchRowError(scene, row, existing = []) {
  if (scene === 'bom') {
    if (existing.includes(row.product.id)) return '该配件已在 BOM 中，请直接修改原行'
    if (!decimal(row.qty, 4) || Number(row.qty) <= 0 || Number(row.qty) >= 1000000) return '用量须大于 0、小于 1000000，最多 4 位小数'
  } else if (!Number.isSafeInteger(row.qty) || row.qty < 1) return '数量须为正整数'
  if (!row.unit?.trim()) return '请填写单位'
  if (batchScenes[scene].price && !(scene === 'purchase' && row.price == null)) {
    if (!decimal(row.price, 7) || Number(row.price) < 0) return '单价须非负，最多 7 位小数'
  }
  if (batchScenes[scene].weight && row.weight != null && (!decimal(row.weight, 2) || Number(row.weight) < 0)) return '重量须非负，最多 2 位小数'
  if (scene === 'plating' && row.product.is_composite && !row.variant?.part?.id) return '请先确定收回组合件'
  if (scene === 'plating' && (row.variantBusy || (row.color && !row.variant?.part?.id))) return '请先核对颜色对应配件'
  return ''
}

export function batchPayload(scene, row, colors = []) {
  const identity = { [row.product.kind === 'jewelry' ? 'jewelry_id' : 'part_id']: row.product.id }
  if (scene === 'order') return { ...identity, quantity: row.qty, unit_price: row.price, remarks: row.note || null }
  if (scene === 'bom') return { part_id: row.product.id, qty_per_unit: Number(row.qty) }
  const payload = { ...identity, qty: row.qty, unit: row.unit.trim(), note: row.note || null }
  if (scene === 'purchase') return { ...payload, price: row.price }
  payload.weight = row.weight ?? null
  payload.weight_unit = row.weight == null ? null : row.weightUnit
  if (scene === 'plating') {
    payload.receive_part_id = row.color ? row.variant.part.id : null
    payload.plating_method = colors.find(c => c.code === row.color)?.method || '金'
  }
  return payload
}

export function batchFailure(error) {
  const status = error?.response?.status
  // A timeout / lost response / server error may occur after commit. Never resend it automatically.
  const confirmed = [400, 401, 403, 404, 409, 422].includes(status)
  const detail = error?.response?.data?.detail
  return { status: confirmed ? 'failed' : 'uncertain', error: confirmed
    ? (typeof detail === 'string' ? detail : '未添加，请修正后重试')
    : '保存结果未能确认。请先刷新核对，不要直接重试。' }
}

// Sequential writes preserve the existing business side effects (notably output BOM updates).
// Callers own the busy guard. Confirmed successes are immutable and never sent twice.
export async function submitBatchRows(rows, save, allowed = () => true) {
  if (rows.some(row => ['saving', 'uncertain'].includes(row.status))) return
  for (const row of rows) {
    if (!['draft', 'failed'].includes(row.status)) continue
    if (!allowed()) break
    row.status = 'saving'; row.error = ''
    try { await save(row); row.status = 'saved' }
    catch (error) {
      Object.assign(row, batchFailure(error))
      if (row.status === 'uncertain' || [401, 403, 404, 409].includes(error?.response?.status)) break
    }
  }
}
