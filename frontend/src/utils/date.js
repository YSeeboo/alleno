/**
 * Convert a timestamp (milliseconds, as returned by n-date-picker type="date")
 * to a "YYYY-MM-DD" string in local time. Returns null if ts is falsy.
 */
export function tsToDateStr(ts) {
  if (ts == null) return null
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return null
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/**
 * Convert an ISO datetime string (e.g. "2024-01-15T08:00:00") to a
 * timestamp suitable for n-date-picker. Returns null if input is falsy.
 */
export function isoToTs(iso) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.getTime()
}
