let nextRowKey = 0

export function createPlatingItem() {
  return {
    part_id: null, receive_part_id: null, qty: 1, unit: '个',
    weight: null, weight_unit: 'kg', plating_method: '金', note: '',
    _key: ++nextRowKey, _selectedColor: null, _variantInfo: null,
    _variantLoading: false, _creatingVariant: false, _reqSeq: 0, _showMore: false,
  }
}

export function copyPlatingItem(item) {
  return {
    ...item,
    _key: ++nextRowKey,
    // Variant responses are JSON data; detach nested state from the source row.
    _variantInfo: item._variantInfo ? JSON.parse(JSON.stringify(item._variantInfo)) : null,
    _variantLoading: false,
    _creatingVariant: false,
    _reqSeq: 0,
  }
}

export function platingItemPayload(item) {
  const { part_id, receive_part_id, qty, unit, weight, weight_unit, plating_method, note } = item
  return { part_id, receive_part_id, qty, unit, weight, weight_unit, plating_method, note }
}

export function summarizePlatingItems(items) {
  const quantities = new Map()
  let weightKg = 0
  for (const item of items) {
    if (!item.part_id) continue
    quantities.set(item.unit, (quantities.get(item.unit) || 0) + Number(item.qty || 0))
    weightKg += Number(item.weight || 0) / (item.weight_unit === 'g' ? 1000 : 1)
  }
  return {
    quantities: [...quantities].map(([unit, qty]) => ({ unit, qty })),
    weightKg: Number(weightKg.toFixed(4)),
  }
}
