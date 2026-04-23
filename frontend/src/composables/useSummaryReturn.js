import { computed } from 'vue'
import { useRouter } from 'vue-router'

export function useSummaryReturn() {
  const router = useRouter()

  const returnQuery = computed(() => {
    const raw = sessionStorage.getItem('plating-summary-return')
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  })

  function back() {
    const q = returnQuery.value
    if (q) {
      sessionStorage.removeItem('plating-summary-return')
      router.push({ path: '/plating-summary', query: q })
    } else {
      router.back()
    }
  }

  return { returnQuery, back }
}
