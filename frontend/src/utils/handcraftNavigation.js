export const HANDCRAFT_TABS = [
  { key: 'summary', path: '/handcraft-summary', label: '手工汇总' },
  { key: 'dispatch', path: '/handcraft', label: '手工发出' },
  { key: 'receipt', path: '/handcraft-receipts', label: '手工回收' },
]

const LAST_TAB_KEY = 'handcraft-management:last-tab'
const QUERIES_KEY = 'handcraft-management:queries'

export function getHandcraftTab(path) {
  return HANDCRAFT_TABS.find((tab) => tab.path === path.replace(/\/$/, '')) || null
}

export function isHandcraftRoute(path) {
  path = path.replace(/\/$/, '')
  return path === '/handcraft-management' || !!getHandcraftTab(path)
    || path.startsWith('/handcraft/') || path.startsWith('/handcraft-receipts/')
}

// Keep the existing supplier_name links from handcraft detail pages working.
// Only list filters are remembered; scan codes, prefill payloads and IDs are not.
export function normalizeHandcraftQuery(key, query = {}) {
  if (!HANDCRAFT_TABS.some((tab) => tab.key === key) || !query || typeof query !== 'object') return {}
  const result = {}
  if (key === 'summary') {
    if (query.tab === 'in') result.tab = 'in'
    for (const prefix of ['', 'in_']) {
      for (const name of ['supplier_name', 'part_id', 'output_id', 'order_id']) {
        const value = query[prefix + name]
        if (typeof value === 'string' && value.trim()) result[prefix + name] = value.trim().slice(0, 200)
      }
      if (['archived', 'all'].includes(query[prefix + 'archive'])) result[prefix + 'archive'] = query[prefix + 'archive']
      for (const name of ['date_from', 'date_to']) {
        const value = query[prefix + name]
        if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
          const d = new Date(`${value}T00:00:00Z`)
          if (!Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === value) result[prefix + name] = value
        }
      }
      const page = query[prefix + 'page']
      if (typeof page === 'string' && /^[1-9]\d{0,5}$/.test(page) && Number(page) > 1) result[prefix + 'page'] = page
    }
    if (query.sort === 'days') result.sort = 'days'
    return result
  }
  if (typeof query.supplier_name === 'string' && query.supplier_name) result.supplier_name = query.supplier_name
  if (key === 'dispatch') {
    if (['archived', 'all'].includes(query.archive)) result.archive = query.archive
    if (['pending', 'processing', 'completed'].includes(query.status)) result.status = query.status
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
  try { storage?.setItem(key, value) } catch { /* Navigation works without storage. */ }
}

function storedQueries(storage) {
  try {
    const value = JSON.parse(read(storage, QUERIES_KEY))
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  } catch { return {} }
}

export function getHandcraftLocation(key, storage = {}) {
  const preferences = storage.preferences ?? browserStorage('localStorage')
  const session = storage.session ?? browserStorage('sessionStorage')
  const selected = key || read(preferences, LAST_TAB_KEY)
  const tab = HANDCRAFT_TABS.find((item) => item.key === selected) || HANDCRAFT_TABS[0]
  return { path: tab.path, query: normalizeHandcraftQuery(tab.key, storedQueries(session)[tab.key]) }
}

export function rememberHandcraftLocation(location, storage = {}) {
  const tab = getHandcraftTab(location.path)
  if (!tab) return
  const preferences = storage.preferences ?? browserStorage('localStorage')
  const session = storage.session ?? browserStorage('sessionStorage')
  write(preferences, LAST_TAB_KEY, tab.key)
  write(session, QUERIES_KEY, JSON.stringify({
    ...storedQueries(session),
    [tab.key]: normalizeHandcraftQuery(tab.key, location.query),
  }))
}

export function restoreHandcraftListQuery(to, from, storage = {}) {
  const tab = getHandcraftTab(to.path)
  // Explicit links win, and clearing filters on the current list must stay clear.
  if (!tab || to.path === from.path || Object.keys(to.query || {}).length) return null
  const saved = getHandcraftLocation(tab.key, storage)
  return Object.keys(saved.query).length ? { ...saved, hash: to.hash, replace: true } : null
}

// Explicit context only: a direct visit to a form/detail must never inherit a
// stale summary return. The remembered query contains no arbitrary return URL.
export function rememberHandcraftSummaryReturn(query, storage = {}) {
  rememberHandcraftLocation({ path: '/handcraft-summary', query }, storage)
}

export function getHandcraftSummaryReturn(query, storage = {}) {
  return query?.from === 'handcraft-summary' ? getHandcraftLocation('summary', storage) : null
}
