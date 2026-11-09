export const PLATING_TABS = [
  { key: 'summary', path: '/plating-summary', label: '电镀汇总' },
  { key: 'dispatch', path: '/plating', label: '电镀发出' },
  { key: 'receipt', path: '/plating-receipts', label: '电镀回收' },
  { key: 'reconciliation', path: '/plating-reconciliation', label: '电镀商家对账' },
]

const LAST_TAB_KEY = 'plating-management:last-tab'
const QUERIES_KEY = 'plating-management:queries'

export function getPlatingTab(path) {
  return PLATING_TABS.find((tab) => tab.path === path.replace(/\/$/, '')) || null
}

export function isPlatingRoute(path) {
  path = path.replace(/\/$/, '')
  return path === '/plating-management' || !!getPlatingTab(path)
    || path.startsWith('/plating/') || path.startsWith('/plating-receipts/')
}

function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const date = new Date(`${value}T00:00:00`)
  return !Number.isNaN(date.getTime())
    && date.getFullYear() === Number(value.slice(0, 4))
    && date.getMonth() + 1 === Number(value.slice(5, 7))
    && date.getDate() === Number(value.slice(8, 10))
}

// Store only each page's own filters, never detail IDs, arbitrary URLs or foreign queries.
export function normalizePlatingQuery(key, query = {}) {
  if (!PLATING_TABS.some((tab) => tab.key === key) || !query || typeof query !== 'object') return {}
  const result = {}
  if (typeof query.supplier === 'string' && query.supplier) result.supplier = query.supplier
  if (['summary', 'dispatch'].includes(key) && ['archived', 'all'].includes(query.archive)) result.archive = query.archive
  if (key === 'dispatch' && ['pending', 'processing', 'completed'].includes(query.status)) result.status = query.status
  if (key === 'reconciliation') {
    if (['未付款', '已付款'].includes(query.status)) result.status = query.status
    // Empty dates explicitly mean unlimited; missing dates mean current month.
    for (const name of ['date_from', 'date_to']) {
      if (query[name] === '' || validDate(query[name])) result[name] = query[name]
    }
    if (['string', 'number'].includes(typeof query.page) && /^[1-9]\d*$/.test(String(query.page)) && Number.isSafeInteger(Number(query.page)) && Number(query.page) > 1) result.page = String(query.page)
  }
  if (key === 'summary') {
    if (query.tab === 'in') result.tab = 'in'
    if (validDate(query.date_from) && validDate(query.date_to) && query.date_from <= query.date_to) {
      result.date_from = query.date_from
      result.date_to = query.date_to
    }
    if (typeof query.q === 'string' && query.q) result.q = query.q
    if (query.sort === 'days' && query.tab !== 'in') result.sort = 'days'
    if (['string', 'number'].includes(typeof query.page) && /^[1-9]\d*$/.test(String(query.page)) && Number.isSafeInteger(Number(query.page)) && Number(query.page) > 1) {
      result.page = String(query.page)
    }
  }
  return result
}

function browserStorage(name) {
  try { return globalThis[name] } catch { return null }
}

function read(storage, key) {
  try { return storage?.getItem(key) || null } catch { return null }
}

function write(storage, key, value) {
  try { storage?.setItem(key, value) } catch { /* Navigation still works without storage. */ }
}

function storedQueries(storage) {
  try {
    const value = JSON.parse(read(storage, QUERIES_KEY))
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  } catch { return {} }
}

export function getPlatingLocation(key, storage = {}) {
  const preferences = storage.preferences ?? browserStorage('localStorage')
  const session = storage.session ?? browserStorage('sessionStorage')
  const selected = key || read(preferences, LAST_TAB_KEY)
  const tab = PLATING_TABS.find((item) => item.key === selected) || PLATING_TABS[0]
  return { path: tab.path, query: normalizePlatingQuery(tab.key, storedQueries(session)[tab.key]) }
}

export function rememberPlatingLocation(location, storage = {}) {
  const tab = getPlatingTab(location.path)
  if (!tab) return
  const preferences = storage.preferences ?? browserStorage('localStorage')
  const session = storage.session ?? browserStorage('sessionStorage')
  write(preferences, LAST_TAB_KEY, tab.key)
  write(session, QUERIES_KEY, JSON.stringify({
    ...storedQueries(session),
    [tab.key]: normalizePlatingQuery(tab.key, location.query),
  }))
}

export function restorePlatingListQuery(to, from, storage = {}) {
  const tab = getPlatingTab(to.path)
  // An explicit URL query wins. Clearing filters on the current page must not restore them.
  if (!tab || to.path === from.path || Object.keys(to.query || {}).length) return null
  const saved = getPlatingLocation(tab.key, storage)
  return Object.keys(saved.query).length ? { ...saved, hash: to.hash, replace: true } : null
}
