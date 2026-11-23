import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getHandcraftSummaryReturn } from '@/utils/handcraftNavigation'

export function useHandcraftSummaryReturn() {
  const route = useRoute()
  const router = useRouter()
  const summaryReturn = computed(() => getHandcraftSummaryReturn(route.query))
  function goBack() {
    if (summaryReturn.value) return router.push(summaryReturn.value)
    router.back()
  }
  function openCreated(path) {
    return router.push(summaryReturn.value ? { path, query: { from: route.query.from } } : path)
  }
  return { summaryReturn, goBack, openCreated }
}
