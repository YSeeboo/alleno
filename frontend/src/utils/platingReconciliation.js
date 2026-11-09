export function dateText(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function monthBounds(offset = 0, now = new Date()) {
  return {
    date_from: dateText(new Date(now.getFullYear(), now.getMonth() + offset, 1)),
    date_to: dateText(new Date(now.getFullYear(), now.getMonth() + offset + 1, 0)),
  }
}

export function reconciliationParams(query, now = new Date()) {
  const defaults = monthBounds(0, now)
  const params = {}
  if (query.supplier) params.vendor_name = query.supplier
  if (query.status) params.status = query.status
  for (const key of ['date_from', 'date_to']) {
    const value = query[key] ?? defaults[key]
    if (value) params[key] = value
  }
  return params
}

export function validOverride(value) {
  return value === '' || /^\d{1,11}(\.\d{1,7})?$/.test(value)
}
