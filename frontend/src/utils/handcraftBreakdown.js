// Allocation entries are projections of one physical output row, not editable
// handcraft rows. In particular, a remainder must never be PATCHed as the full
// output when using "一键剩余分给".
export function sortingPlaceholders(groups) {
  const entries = []
  for (const group of groups || []) {
    for (const entry of group.entries || []) {
      if (!(entry.customer_name || '').trim() && !entry.is_locked &&
          !entry.quantity_managed && !entry.is_quantity_remainder && !entry.source_allocation_id) {
        entries.push({ ...entry, _col_key: `${group.kind}:${group.jewelry_id}` })
      }
    }
  }
  return entries
}

export function editableSortingIndex(groups) {
  const index = new Map()
  for (const group of groups || []) {
    for (const entry of group.entries || []) {
      if (entry.quantity_managed || entry.source_allocation_id || entry.is_quantity_remainder) continue
      index.set(entry.hc_jewelry_item_id, {
        qty: Number(entry.qty), customer_name: entry.customer_name || null, is_locked: !!entry.is_locked,
      })
    }
  }
  return index
}
