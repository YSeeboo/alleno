import { runWithConcurrency } from '@/utils/concurrency'
import {
  getHandcraft,
  getHandcraftParts,
  addHandcraftPart,
  updateHandcraftPart,
} from '@/api/handcraft'

// Attach a batch of parts to a pending handcraft order.
// - parts: [{ part_id, qty, unit }]
// - Always re-fetches the order's items to compute add vs update (defends
//   against stale state from another tab).
// - Throws err with code='NOT_PENDING' if the order isn't pending — caller
//   should catch and surface the message.
// Returns: { okNew, okUpd, failures: [{ part_id, detail }] }
export const attachPartsToOrder = async (orderId, parts) => {
  const { data: latest } = await getHandcraft(orderId)
  if (latest.status !== 'pending') {
    const err = new Error(`手工单已是 ${latest.status} 状态，无法再添加配件`)
    err.code = 'NOT_PENDING'
    throw err
  }

  const { data: currentItems } = await getHandcraftParts(orderId)

  const tasks = parts.map((p) => async () => {
    const existing = currentItems.find((it) => it.part_id === p.part_id)
    if (existing) {
      await updateHandcraftPart(orderId, existing.id, {
        qty: (Number(existing.qty) || 0) + p.qty,
        unit: p.unit,
      })
      return { action: 'update' }
    }
    await addHandcraftPart(orderId, p)
    return { action: 'add' }
  })

  const results = await runWithConcurrency(tasks, 5)

  let okNew = 0
  let okUpd = 0
  const failures = []
  results.forEach((r, idx) => {
    if (r.ok) {
      if (r.value.action === 'add') okNew++
      else okUpd++
    } else {
      const detail = r.error?.response?.data?.detail || r.error?.message || '未知错误'
      failures.push({ part_id: parts[idx].part_id, detail })
    }
  })

  return { okNew, okUpd, failures }
}
