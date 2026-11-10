<template>
  <label class="image-file-picker" :class="{ 'is-disabled': disabled, 'is-compact': compact }">
    <n-icon :component="source === 'camera' ? CameraOutline : FolderOpenOutline" :size="compact ? 18 : 28" />
    <span>{{ label }}</span>
    <!-- Keep the native input inside the dialog and directly under the user's tap.
         An off-dialog/display:none input + scripted click is unreliable on mobile Chrome. -->
    <input
      type="file"
      accept="image/*"
      :capture="source === 'camera' ? 'environment' : undefined"
      :aria-label="label"
      :disabled="disabled"
      @click="resetSelection"
      @input="selectFile"
      @change="selectFile"
    />
  </label>
</template>

<script setup>
import { computed } from 'vue'
import { NIcon } from 'naive-ui'
import { CameraOutline, FolderOpenOutline } from '@vicons/ionicons5'

const props = defineProps({
  source: { type: String, default: 'local', validator: (value) => ['camera', 'local'].includes(value) },
  disabled: Boolean,
  compact: Boolean,
})
const emit = defineEmits(['select'])
const label = computed(() => props.source === 'camera' ? '拍照上传' : '本地上传')
let selectionHandled = false

function resetSelection(event) {
  // Reset before opening, not before the selected file has been read/uploaded.
  // This also lets users select the same photo again after a failure or cancellation.
  if (!props.disabled) {
    selectionHandled = false
    event.currentTarget.value = ''
  }
}

function selectFile(event) {
  if (props.disabled || selectionHandled) return
  const file = event.target.files?.[0]
  if (file) {
    // Accept either file-selection event, but never upload twice when both arrive.
    selectionHandled = true
    emit('select', file)
  }
}
</script>

<style scoped>
.image-file-picker { position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; min-width: 0; min-height: 120px; padding: 16px; box-sizing: border-box; border: 1px solid #D1D9D4; border-radius: 10px; background: #F7FAF8; color: #1E7A5A; font-size: 14px; font-weight: 600; cursor: pointer; overflow: hidden; }
.image-file-picker input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }
.image-file-picker:hover { background: #EDF5F0; border-color: #1E7A5A; }
.image-file-picker:focus-within { outline: 2px solid #1E7A5A; outline-offset: 2px; }
.image-file-picker.is-compact { flex-direction: row; min-height: 36px; padding: 6px 12px; gap: 6px; border-radius: 4px; font-size: 13px; white-space: nowrap; }
.image-file-picker.is-disabled { opacity: .55; cursor: not-allowed; }
.image-file-picker.is-disabled input { cursor: not-allowed; }
</style>
