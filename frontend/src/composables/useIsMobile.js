import { ref, onUnmounted } from 'vue'

export function useIsMobile(breakpoint = 768) {
  const mql = typeof window !== 'undefined'
    ? window.matchMedia(`(max-width: ${breakpoint}px)`)
    : null
  const isMobile = ref(mql ? mql.matches : false)

  function update(e) {
    isMobile.value = e.matches
  }

  if (mql) {
    mql.addEventListener('change', update)
    onUnmounted(() => {
      mql.removeEventListener('change', update)
    })
  }

  return { isMobile }
}
