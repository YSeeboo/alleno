export const matchingLines = (lines, source) => lines.filter(line =>
  line.product_type === source.product_type && line.product_id === source.product_id)

export const productionDemandLines = data => [...(data?.lines || []), ...(data?.materials || [])]
export const allocationMatchesLine = (row, line) => row.order_item_id === (line.order_item_id || line.id) &&
  (row.material_part_id || null) === (line.material_part_id || null)

export const ownQuantity = (source, orderId) => (source.allocations || [])
  .filter(row => row.order_id === orderId).reduce((sum, row) => sum + Number(row.quantity), 0)

export const associatedSources = (sources, type, orderId) => sources.filter(source =>
  source.source_type === type && (type !== 'handcraft' || ownQuantity(source, orderId) > 0 ||
    (source.linked_order_ids || []).includes(orderId)))

export const handcraftLinkSources = sources => sources.filter(source =>
  source.source_type === 'handcraft' && !source.archived && ['pending', 'processing'].includes(source.status))

// Suggest only unmet demand and unclaimed production capacity. Repeated product
// lines remain independent, and existing shares are preserved when adjusting.
export function sourceQuantities(lines, source, suggest = false) {
  let remaining = Math.max(0, Number(source.public_unallocated || 0))
  const hasOwnShare = matchingLines(lines, source).some(line =>
    (source.allocations || []).some(row => allocationMatchesLine(row, line) && Number(row.quantity) > 0))
  return Object.fromEntries(matchingLines(lines, source).map(line => {
    const own = Number((source.allocations || []).find(row => allocationMatchesLine(row, line))?.quantity || 0)
    let quantity = own
    if (suggest && !hasOwnShare && !line.legacy_claim && !source.legacy_claim && !source.unit_mismatch) {
      let extra = Math.min(remaining, Math.max(0, Number(line.quantity) - Number(line.allocated || 0)))
      if (source.source_type === 'handcraft' || !line.material_part_id) extra = Math.floor(extra)
      else extra = Math.floor(extra * 10000 + 1e-7) / 10000
      quantity += extra
      remaining -= extra
    }
    return [line.id, quantity]
  }))
}

export const allocationPayload = (lines, source, quantities) => ({
  source_type: source.source_type,
  source_item_id: source.source_item_id,
  revision: source.revision,
  allocations: matchingLines(lines, source).map(line => {
    const quantity = quantities[line.id]
    const fractional = !!line.material_part_id && source.source_type === 'plating'
    if (typeof quantity !== 'number' || !Number.isFinite(quantity) || quantity < 0 ||
        (fractional ? Math.abs(quantity * 10000 - Math.round(quantity * 10000)) > 1e-7 : !Number.isSafeInteger(quantity))) {
      if (fractional) throw new Error('配件安排请填写最多四位小数的非负数')
      throw new Error('请填写非负整数，填 0 可取消本项安排')
    }
    return { order_item_id: line.order_item_id || line.id, quantity,
      ...(line.material_part_id ? { material_part_id: line.material_part_id, demand_revision: line.demand_revision } : {}) }
  }),
})

// Drafts are replacement shares for selected outputs only. Totals include all
// unselected production, and direct/BOM demand identities stay independent.
export function allocationBatchReview(lines, sources, drafts, orderId) {
  const sourceRows = sources.map(source => {
    const quantities = drafts[source.source_item_id] || {}
    const values = matchingLines(lines, source).map(line => quantities[line.id])
    const total = values.reduce((n, v) => n + Math.round(Number(v || 0) * 10000), 0) / 10000
    const limit = Math.round((Number(source.planned) - Number(source.allocated) + ownQuantity(source, orderId)) * 10000) / 10000
    return { source, total, limit, invalid: values.some(v => typeof v !== 'number' || !Number.isFinite(v) || v < 0) || total > limit }
  })
  const lineRows = lines.filter(line => sources.some(source => matchingLines([line], source).length)).map(line => {
    const old = sources.reduce((n, source) => n + (source.allocations || []).filter(row => row.order_id === orderId && allocationMatchesLine(row, line)).reduce((n, row) => n + Number(row.quantity), 0), 0)
    const next = sources.filter(source => matchingLines([line], source).length).reduce((n, source) => n + Number(drafts[source.source_item_id]?.[line.id] || 0), 0)
    const total = Math.round((Number(line.allocated || 0) - old + next) * 10000) / 10000
    return { line, total, limit: Number(line.quantity), invalid: total > Number(line.quantity) && next > 0 }
  })
  return { sources: sourceRows, lines: lineRows }
}

export function allocationBatchPayload(lines, sources, drafts, orderId) {
  if (!sources.length || sources.length > 100 || new Set(sources.map(s => `${s.source_type}:${s.source_item_id}`)).size !== sources.length) throw new Error('请选择 1 至 100 个不重复的产出')
  const payloads = sources.map(source => {
    if (source.archived || !['pending', 'processing'].includes(source.status) || source.legacy_claim) throw new Error('已归档、已结清或旧归属冲突的产出不可分配')
    const payload = allocationPayload(lines, source, drafts[source.source_item_id] || {})
    if (payload.allocations.some(r => r.quantity > 0) && source.unit_mismatch) throw new Error('单位不一致，不自动换算')
    if (matchingLines(lines, source).some(line => line.legacy_claim && Number(drafts[source.source_item_id]?.[line.id]) > 0)) throw new Error('订单明细旧归属待核对')
    return payload
  })
  const review = allocationBatchReview(lines, sources, drafts, orderId)
  if (review.sources.some(r => r.invalid)) throw new Error('所选产出分配后总量超过可分配容量，请核对同款各行合计')
  if (review.lines.some(r => r.invalid)) throw new Error('分配后合计超过本单明细需求（含未选产出），整批未保存')
  return payloads
}
