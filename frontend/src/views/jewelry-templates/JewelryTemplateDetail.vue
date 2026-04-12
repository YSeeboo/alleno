<template>
  <div style="max-width: 900px;">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">饰品模板详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-card v-if="template" title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="编号">{{ template.id }}</n-descriptions-item>
          <n-descriptions-item label="名称">
            <n-input v-model:value="editForm.name" size="small" style="width: 200px;" />
          </n-descriptions-item>
          <n-descriptions-item label="图片">
            <n-space align="center">
              <n-image
                v-if="template.image"
                :src="template.image"
                :alt="template.name"
                :width="48"
                :height="48"
                object-fit="cover"
                style="border-radius: 8px; border: 1px solid #ffd6d6; overflow: hidden; display: block; cursor: zoom-in;"
              />
              <span v-else>无图</span>
              <n-button size="tiny" @click="showImageModal = true">更换</n-button>
            </n-space>
          </n-descriptions-item>
          <n-descriptions-item label="备注" :span="2">
            <n-input v-model:value="editForm.note" size="small" type="textarea" :rows="1" style="width: 300px;" />
          </n-descriptions-item>
          <n-descriptions-item label="创建时间">
            {{ template.created_at ? new Date(template.created_at).toLocaleString('zh-CN') : '-' }}
          </n-descriptions-item>
        </n-descriptions>
      </n-card>

      <n-card title="配件列表">
        <div v-for="(item, idx) in items" :key="idx" style="margin-bottom: 10px;">
          <n-space align="center">
            <n-select
              v-model:value="item.part_id"
              :options="partOptions"
              :render-label="renderOptionWithImage"
              filterable
              clearable
              placeholder="选择配件"
              style="width: 240px;"
            />
            <n-input-number v-model:value="item.qty_per_unit" :min="0.001" :precision="2" placeholder="每件用量" style="width: 140px;" />
            <n-button type="error" size="small" @click="items.splice(idx, 1)">删</n-button>
          </n-space>
        </div>
        <n-button dashed style="width: 100%; margin-bottom: 12px;" @click="items.push({ part_id: null, qty_per_unit: 1 })">
          + 添加配件行
        </n-button>
      </n-card>

      <n-space justify="end" style="margin-top: 16px;">
        <n-button type="primary" size="large" :loading="saving" @click="saveAll">保存</n-button>
      </n-space>
    </n-spin>

    <ImageUploadModal
      v-model:show="showImageModal"
      kind="jewelry-template"
      :entity-id="template?.id"
      @uploaded="onImageUploaded"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin,
  NSpace, NButton, NH2, NInput, NInputNumber, NSelect, NImage,
} from 'naive-ui'
import { getTemplate, updateTemplate } from '@/api/jewelryTemplates'
import { listParts } from '@/api/parts'
import { renderOptionWithImage } from '@/utils/ui'
import ImageUploadModal from '../../components/ImageUploadModal.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const loading = ref(true)
const saving = ref(false)
const showImageModal = ref(false)
const template = ref(null)
const editForm = reactive({ name: '', note: '', image: '' })
const items = reactive([])
const partOptions = ref([])

const loadTemplate = async () => {
  const { data } = await getTemplate(route.params.id)
  template.value = data
  editForm.name = data.name
  editForm.note = data.note || ''
  editForm.image = data.image || ''
  items.length = 0
  ;(data.items || []).forEach((i) => {
    items.push({ part_id: i.part_id, qty_per_unit: i.qty_per_unit })
  })
}

const saveAll = async () => {
  const validItems = items.filter((i) => i.part_id)
  if (validItems.length === 0) { message.warning('模板至少需要一个配件'); return }
  saving.value = true
  try {
    await updateTemplate(route.params.id, {
      name: editForm.name,
      note: editForm.note || null,
      image: editForm.image || null,
      items: validItems.map((i) => ({ part_id: i.part_id, qty_per_unit: i.qty_per_unit })),
    })
    message.success('已保存')
    await loadTemplate()
  } finally {
    saving.value = false
  }
}

const onImageUploaded = (url) => {
  editForm.image = url
  if (template.value) template.value.image = url
}

onMounted(async () => {
  try {
    const [_, partsRes] = await Promise.all([
      loadTemplate(),
      listParts(),
    ])
    partOptions.value = partsRes.data.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
    }))
  } finally {
    loading.value = false
  }
})
</script>
