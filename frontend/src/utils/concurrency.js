// Run async fns with a max concurrency. Returns an array in the same order
// as `tasks`, where each entry is either { ok: true, value } or { ok: false, error }.
export const runWithConcurrency = async (tasks, limit = 5) => {
  const results = new Array(tasks.length)
  let i = 0
  const workers = Array.from({ length: Math.min(limit, tasks.length) }, async () => {
    while (i < tasks.length) {
      const idx = i++
      try {
        results[idx] = { ok: true, value: await tasks[idx]() }
      } catch (error) {
        results[idx] = { ok: false, error }
      }
    }
  })
  await Promise.all(workers)
  return results
}
