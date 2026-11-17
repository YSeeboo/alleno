import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getHandcraftTab, normalizeHandcraftQuery } from '@/utils/handcraftNavigation'

export function useHandcraftPageQuery(key) {
  const route = useRoute()
  const router = useRouter()
  const active = computed(() => getHandcraftTab(route.path)?.key === key)
  const query = computed(() => normalizeHandcraftQuery(key, route.query))

  function updateQuery(patch, resetPage = true) {
    if (!active.value) return
    const next = { ...query.value, ...patch }
    if (key === 'summary' && resetPage) delete next[next.tab === 'in' ? 'in_page' : 'page']
    return router.replace({ path: route.path, query: normalizeHandcraftQuery(key, next) })
  }

  function field(name, fallback = null) {
    return computed({
      get: () => query.value[name] ?? fallback,
      set: (value) => { void updateQuery({ [name]: value }) },
    })
  }

  return { route, active, query, updateQuery, field }
}
