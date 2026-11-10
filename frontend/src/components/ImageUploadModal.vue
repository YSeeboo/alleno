<template>
  <n-modal v-model:show="visible" :mask-closable="!uploading" :close-on-esc="!uploading">
    <n-card
      title="上传图片"
      :style="{ width: isMobile ? '95vw' : '460px', maxWidth: '95vw' }"
      :bordered="false"
      role="dialog"
    >
      <div v-if="isMobileUpload" class="mobile-upload-choices">
        <ImageFilePicker source="camera" :disabled="uploading" @select="uploadFile" />
        <ImageFilePicker :disabled="uploading" @select="uploadFile" />
      </div>
      <div v-else class="paste-zone">
        <div class="paste-icon">
          <n-icon :component="ClipboardOutline" size="28" />
        </div>
        <div class="paste-text">Ctrl/Cmd + V 上传粘贴的图片</div>
      </div>
      <div v-if="uploading" class="upload-status" role="status" aria-live="polite">
        <n-spin size="small" />{{ uploadStatus }}
      </div>

      <template #footer>
        <n-space justify="end">
          <n-button :disabled="uploading" @click="visible = false">取消</n-button>
          <ImageFilePicker v-if="!isMobileUpload" compact :disabled="uploading" @select="uploadFile" />
        </n-space>
      </template>
    </n-card>
  </n-modal>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NModal, NCard, NButton, NSpace, NIcon, NSpin, useMessage } from 'naive-ui'
import { ClipboardOutline } from '@vicons/ionicons5'
import { uploadImageToOss } from '@/api/uploads'
import { useIsMobile } from '@/composables/useIsMobile'
import { useImageUploadMode } from '@/composables/useImageUploadMode'
import ImageFilePicker from '@/components/ImageFilePicker.vue'

const { isMobile } = useIsMobile()
const { isMobileUpload } = useImageUploadMode()

const props = defineProps({
  show: Boolean,
  kind: { type: String, required: true },
  entityId: { type: [String, Number], default: null },
  suppressSuccess: { type: Boolean, default: false },
})

const emit = defineEmits(['update:show', 'uploaded'])

const message = useMessage()
const uploading = ref(false)
const uploadStatus = ref('')

const visible = computed({
  get: () => props.show,
  set: (value) => emit('update:show', value),
})

const uploadFile = async (file) => {
  if (!file || uploading.value) return
  uploading.value = true
  try {
    const url = await uploadImageToOss({
      kind: props.kind,
      file,
      entityId: props.entityId,
      onStage: (stage) => { uploadStatus.value = stage },
    })
    emit('uploaded', url)
    if (!props.suppressSuccess) {
      message.success('图片上传成功')
    }
    visible.value = false
  } catch (error) {
    const detail = error.response?.data?.detail
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg).join('; ')
      : detail || error.message || '图片上传失败'
    message.error(msg)
  } finally {
    uploading.value = false
    uploadStatus.value = ''
  }
}

const handlePaste = async (event) => {
  if (!visible.value || isMobileUpload.value || uploading.value) return
  const file = [...(event.clipboardData?.items || [])]
    .find((item) => item.type?.startsWith('image/'))
    ?.getAsFile()
  if (!file) return
  event.preventDefault()
  await uploadFile(file)
}

watch(
  [visible, isMobileUpload],
  ([show, mobile]) => {
    if (show && !mobile) {
      window.addEventListener('paste', handlePaste)
    } else {
      window.removeEventListener('paste', handlePaste)
    }
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  window.removeEventListener('paste', handlePaste)
})
</script>

<style scoped>
.mobile-upload-choices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.upload-status { display: flex; align-items: center; justify-content: center; gap: 10px; padding-top: 16px; color: #718278; font-size: 13px; }
.paste-zone {
  min-height: 180px;
  border: 2px dashed #d9c9a1;
  border-radius: 18px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  background:
    linear-gradient(180deg, rgba(255, 251, 240, 0.95), rgba(250, 243, 221, 0.95));
}

.paste-icon {
  width: 68px;
  height: 68px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #b8842f;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(184, 132, 47, 0.18);
}

.paste-text {
  font-size: 15px;
  font-weight: 600;
  color: #57441d;
  text-align: center;
}
</style>
