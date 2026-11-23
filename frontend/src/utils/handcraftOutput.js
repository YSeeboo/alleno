export const OUTPUT_METRICS = [
  { key: 'expected_qty', label: '已发出制作', note: '预期产出，不是材料数量' },
  { key: 'actual_received_qty', label: '累计实收', note: '包含跨月的全部回收' },
  { key: 'loss_total_qty', label: '已确认损耗', note: '只计明确登记的损耗' },
  { key: 'unreceived_qty', label: '尚未收回', note: '逐来源扣除实收与损耗' },
]
export const OUTPUT_STATUS = { unreceived: '尚未收回', partial: '部分收回', settled: '已结清' }
export const outputItemKey = item => JSON.stringify([item.supplier_name, item.output_key, item.unit])
export const outputStatus = item => item.unreceived_qty <= 0 ? 'settled' : item.actual_received_qty > 0 ? 'partial' : 'unreceived'
export const outputPercent = item => item.expected_qty > 0 ? Math.round(item.actual_received_qty / item.expected_qty * 100) : 0
export const outputQuantity = value => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
export const outputUnit = value => value || '单位未填'
export const beijingToday = (now = new Date()) => new Date(now.getTime() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10)

export function outputDateRange(preset, today = beijingToday()) {
  const date = new Date(`${today}T00:00:00Z`)
  const iso = value => value.toISOString().slice(0, 10)
  const year = date.getUTCFullYear(), month = date.getUTCMonth()
  if (preset === 'month') return { date_from: iso(new Date(Date.UTC(year, month, 1))), date_to: iso(new Date(Date.UTC(year, month + 1, 0))) }
  if (preset === 'lastMonth') return { date_from: iso(new Date(Date.UTC(year, month - 1, 1))), date_to: iso(new Date(Date.UTC(year, month, 0))) }
  if (preset === 'week') {
    date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7)
    const date_from = iso(date)
    date.setUTCDate(date.getUTCDate() + 6)
    return { date_from, date_to: iso(date) }
  }
  return {}
}
export function validOutputDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value
}
export function normalizeOutputQuery(query = {}) {
  const result = {}
  const array = value => Array.isArray(value) ? value : typeof value === 'string' ? [value] : []
  for (const name of ['suppliers', 'outputs']) {
    const values = [...new Set(array(query[name]).filter(value => typeof value === 'string' && value.trim() && value.length <= (name === 'suppliers' ? 200 : 210)
      && (name !== 'outputs' || /^(jewelry|part):.+/.test(value))))].slice(0, 100)
    if (values.length) result[name] = values
  }
  if (query.view === 'product') result.view = 'product'
  if (['unreceived', 'partial', 'settled'].includes(query.progress)) result.progress = query.progress
  if (['archived', 'all'].includes(query.archive)) result.archive = query.archive
  if (['week', 'month', 'lastMonth', 'custom'].includes(query.date_preset)) result.date_preset = query.date_preset
  for (const name of ['date_from', 'date_to']) if (validOutputDate(query[name])) result[name] = query[name]
  if (!result.date_preset && (result.date_from || result.date_to)) result.date_preset = 'custom'
  if (result.date_preset !== 'custom') { delete result.date_from; delete result.date_to }
  if (typeof query.page === 'string' && /^[1-9]\d{0,5}$/.test(query.page) && Number(query.page) > 1) result.page = query.page
  return result
}
export function outputFilters(query, today = beijingToday()) {
  const normalized = normalizeOutputQuery(query)
  return {
    supplier_names: normalized.suppliers || [], output_keys: normalized.outputs || [],
    archive: normalized.archive || 'active', progress: normalized.progress || 'all',
    ...(normalized.date_preset === 'custom'
      ? { date_from: normalized.date_from, date_to: normalized.date_to }
      : outputDateRange(normalized.date_preset, today)),
  }
}
export function outputDateError(query) {
  if (query.date_preset !== 'custom') return ''
  if (!validOutputDate(query.date_from) || !validOutputDate(query.date_to)) return '请选择完整、有效的发出日期范围'
  return query.date_from > query.date_to ? '开始日期不能晚于结束日期' : ''
}
export const handcraftOutputLocation = (query = {}) => ({ path: '/handcraft-output', query: normalizeOutputQuery(query) })
