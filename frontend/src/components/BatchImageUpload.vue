<template>
  <n-modal
    :show="show"
    preset="card"
    title="批量上传配件图片"
    style="width: 680px; max-height: 80vh;"
    :mask-closable="false"
    @update:show="$emit('update:show', $event)"
  >
    <div style="max-height: 60vh; overflow-y: auto;">
      <n-table size="small" :bordered="false">
        <thead>
          <tr>
            <th style="width: 120px;">配件编号</th>
            <th>配件名称</th>
            <th style="width: 100px; text-align: center;">图片</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="part in parts" :key="part.part_id">
            <td>{{ part.part_id }}</td>
            <td>{{ part.name }}</td>
            <td style="text-align: center;">
              <!-- Uploaded image -->
              <div v-if="uploadedImages[part.part_id]" style="position: relative; display: inline-block;">
                <n-image
                  :src="uploadedImages[part.part_id]"
                  width="64"
                  height="64"
                  object-fit="cover"
                  style="border-radius: 4px;"
                />
                <n-button
                  circle
                  size="tiny"
                  type="error"
                  style="position: absolute; top: -6px; right: -6px;"
                  @click="removeImage(part.part_id)"
                >
                  <template #icon><n-icon :component="CloseOutline" /></template>
                </n-button>
              </div>
              <!-- Upload area -->
              <div
                v-else
                :class="['upload-area', { 'upload-focus': focusedPartId === part.part_id, 'upload-loading': uploadingPartId === part.part_id }]"
                tabindex="0"
                @click="setFocus(part.part_id, $event)"
                @focus="focusedPartId = part.part_id"
                @paste="handlePaste($event, part.part_id)"
              >
                <n-spin v-if="uploadingPartId === part.part_id" size="small" />
                <span v-else style="font-size: 11px; color: #999;">点击后粘贴</span>
              </div>
            </td>
          </tr>
        </tbody>
      </n-table>
    </div>
    <template #footer>
      <n-space justify="end">
        <n-button type="primary" @click="$emit('update:show', false)">完成</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup>
import { ref } from 'vue'
import { NModal, NTable, NImage, NButton, NIcon, NSpin, NSpace, useMessage } from 'naive-ui'
import { CloseOutline } from '@vicons/ionicons5'
import { uploadImageToOss } from '@/api/uploads'
import { updatePart } from '@/api/parts'

const props = defineProps({
  show: Boolean,
  parts: { type: Array, default: () => [] },  // [{ part_id, name }]
})

const emit = defineEmits(['update:show', 'done'])

const message = useMessage()
const uploadedImages = ref({})
const focusedPartId = ref(null)
const uploadingPartId = ref(null)

function setFocus(partId, event) {
  focusedPartId.value = partId
  event?.currentTarget?.focus()
}

async function handlePaste(event, partId) {
  if (uploadingPartId.value) return
  const file = [...(event.clipboardData?.items || [])]
    .find(item => item.type?.startsWith('image/'))
    ?.getAsFile()
  if (!file) return
  event.preventDefault()

  uploadingPartId.value = partId
  try {
    const url = await uploadImageToOss({
      kind: 'part',
      file,
      entityId: partId,
    })
    await updatePart(partId, { image: url })
    uploadedImages.value[partId] = url
    message.success(`${partId} 图片上传成功`)
  } catch (err) {
    message.error(`${partId} 上传失败: ${err.message || '未知错误'}`)
  } finally {
    uploadingPartId.value = null
  }
}

async function removeImage(partId) {
  try {
    await updatePart(partId, { image: null })
    delete uploadedImages.value[partId]
  } catch (err) {
    message.error(`删除失败: ${err.message || '未知错误'}`)
  }
}
</script>

<style scoped>
.upload-area {
  width: 64px;
  height: 64px;
  border: 1px dashed #d9d9d9;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.2s;
  outline: none;
}
.upload-area:hover {
  border-color: #1890ff;
}
.upload-focus {
  border-color: #1890ff;
  border-style: solid;
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}
.upload-loading {
  border-color: #1890ff;
}
</style>
