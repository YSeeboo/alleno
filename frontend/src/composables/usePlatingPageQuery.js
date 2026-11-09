import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getPlatingTab, normalizePlatingQuery } from '@/utils/platingNavigation'

export function usePlatingPageQuery(key) {
  const route = useRoute()
  const router = useRouter()
  const active = computed(() => getPlatingTab(route.path)?.key === key)
  const query = computed(() => normalizePlatingQuery(key, route.query))

  function updateQuery(patch, resetPage = true) {
    if (!active.value) return
    const next = { ...query.value, ...patch }
    if (resetPage) delete next.page
    return router.replace({ path: route.path, query: normalizePlatingQuery(key, next) })
  }

  function field(name, fallback = null) {
    return computed({
      get: () => query.value[name] ?? fallback,
      set: (value) => { void updateQuery({ [name]: value }) },
    })
  }

  return { route, active, query, updateQuery, field }
}
