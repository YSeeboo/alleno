<template>
  <n-modal v-model:show="visible" :mask-closable="!uploading">
    <n-card
      title="上传图片"
      :style="{ width: isMobile ? '95vw' : '460px', maxWidth: '95vw' }"
      :bordered="false"
      role="dialog"
    >
      <div class="paste-zone">
        <div class="paste-icon">
          <n-icon :component="ClipboardOutline" size="28" />
        </div>
        <div class="paste-text">Ctrl/Cmd + V 上传粘贴的图片</div>
      </div>

      <template #footer>
        <n-space justify="end">
          <n-button :disabled="uploading" @click="visible = false">取消</n-button>
          <n-button type="primary" :loading="uploading" @click="triggerLocalUpload">本地上传</n-button>
        </n-space>
      </template>
    </n-card>
  </n-modal>

  <input
    ref="fileInputRef"
    type="file"
    accept="image/*"
    style="display: none;"
    @change="handleFileChange"
  />
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { NModal, NCard, NButton, NSpace, NIcon, useMessage } from 'naive-ui'
import { ClipboardOutline } from '@vicons/ionicons5'
import { uploadImageToOss } from '@/api/uploads'
import { useIsMobile } from '@/composables/useIsMobile'

const { isMobile } = useIsMobile()

const props = defineProps({
  show: Boolean,
  kind: { type: String, required: true },
  entityId: { type: [String, Number], default: null },
  suppressSuccess: { type: Boolean, default: false },
})

const emit = defineEmits(['update:show', 'uploaded'])

const message = useMessage()
const fileInputRef = ref(null)
const uploading = ref(false)

const visible = computed({
  get: () => props.show,
  set: (value) => emit('update:show', value),
})

const uploadFile = async (file) => {
  if (!file) return
  uploading.value = true
  try {
    const url = await uploadImageToOss({
      kind: props.kind,
      file,
      entityId: props.entityId,
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
  }
}

const handleFileChange = async (event) => {
  const file = event.target.files?.[0]
  event.target.value = ''
  await uploadFile(file)
}

const triggerLocalUpload = () => {
  fileInputRef.value?.click()
}

const handlePaste = async (event) => {
  if (!visible.value || uploading.value) return
  const file = [...(event.clipboardData?.items || [])]
    .find((item) => item.type?.startsWith('image/'))
    ?.getAsFile()
  if (!file) return
  event.preventDefault()
  await uploadFile(file)
}

watch(
  () => visible.value,
  (show) => {
    if (show) {
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
