export const matchingLines = (lines, source) => lines.filter(line =>
  line.product_type === source.product_type && line.product_id === source.product_id)

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
    (source.allocations || []).some(row => row.order_item_id === line.id && Number(row.quantity) > 0))
  return Object.fromEntries(matchingLines(lines, source).map(line => {
    const own = Number((source.allocations || []).find(row => row.order_item_id === line.id)?.quantity || 0)
    let quantity = own
    if (suggest && !hasOwnShare && !line.legacy_claim && !source.unit_mismatch) {
      const extra = Math.min(remaining, Math.max(0, Number(line.quantity) - Number(line.allocated || 0)))
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
    if (typeof quantity !== 'number' || !Number.isSafeInteger(quantity) || quantity < 0) {
      throw new Error('请填写非负整数，填 0 可取消本项安排')
    }
    return { order_item_id: line.id, quantity }
  }),
})
