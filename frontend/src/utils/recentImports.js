// Persisted "recent Excel-imported part batches" — the bridge between
// PartList.doImport and handcraft-order add-part flows.
//
// Storage shape (single localStorage key):
//   [
//     { batch_id, imported_at, operator,
//       parts: [{ part_id, name, image, unit, imported_qty }, ...] },
//     ...
//   ]
//
// Newest first. Pruned to MAX_BATCHES and MAX_AGE_MS on read.

export const STORAGE_KEY = 'allen_shop.recent_part_imports'
export const MAX_BATCHES = 5
export const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

const readRaw = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const writeRaw = (list) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
  } catch {
    // Quota exceeded or storage disabled — batch bridge silently degrades.
    // The Excel import itself succeeded; this only loses the convenience batch.
  }
}

const prune = (list, now) => {
  const fresh = list.filter((b) => now - (b.imported_at || 0) <= MAX_AGE_MS)
  fresh.sort((a, b) => (b.imported_at || 0) - (a.imported_at || 0))
  return fresh.slice(0, MAX_BATCHES)
}

export const pushBatch = (parts, opts = {}) => {
  const now = opts.now ?? Date.now()
  const operator = opts.operator ?? ''
  const batch = {
    batch_id: `imp-${now}-${Math.random().toString(36).slice(2, 7)}`,
    imported_at: now,
    operator,
    parts: parts.map((p) => ({
      part_id: p.part_id,
      name: p.name ?? '',
      image: p.image ?? null,
      unit: p.unit ?? '个',
      imported_qty: Number(p.imported_qty ?? 0),
    })),
  }
  const next = prune([batch, ...readRaw()], now)
  writeRaw(next)
  return batch
}

export const getActiveBatches = (opts = {}) => {
  const now = opts.now ?? Date.now()
  return prune(readRaw(), now)
}

export const getBatchById = (batchId) => {
  return readRaw().find((b) => b.batch_id === batchId) ?? null
}

export const updateBatchPartImage = (batchId, partId, imageUrl) => {
  const list = readRaw()
  const batch = list.find((b) => b.batch_id === batchId)
  if (!batch) return
  const part = batch.parts.find((p) => p.part_id === partId)
  if (!part) return
  part.image = imageUrl ?? null
  writeRaw(list)
}
