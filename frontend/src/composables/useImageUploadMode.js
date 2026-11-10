import { computed, onUnmounted, ref } from 'vue'
import { useIsMobile } from './useIsMobile'

export function useImageUploadMode() {
  const { isMobile } = useIsMobile()
  // Include phones in landscape and touch tablets, not only narrow viewports.
  const media = typeof window !== 'undefined' ? window.matchMedia('(pointer: coarse)') : null
  const isTouch = ref(media?.matches || false)
  const update = (event) => { isTouch.value = event.matches }
  media?.addEventListener('change', update)
  onUnmounted(() => media?.removeEventListener('change', update))
  return { isMobileUpload: computed(() => isMobile.value || isTouch.value) }
}
