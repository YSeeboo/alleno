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
