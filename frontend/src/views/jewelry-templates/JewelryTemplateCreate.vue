<template>
  <div style="max-width: 900px;">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建饰品模板</n-h2>
    </n-space>

    <n-form label-placement="left" label-width="100" style="margin-bottom: 16px;">
      <n-form-item label="模板名称">
        <n-input v-model:value="form.name" placeholder="输入模板名称" style="width: 300px;" />
      </n-form-item>
      <n-form-item label="图片">
        <n-space align="center">
          <n-input v-model:value="form.image" placeholder="上传后自动填充，也可手动输入 URL" style="width: 300px;" />
          <n-button @click="showImageModal = true">上传图片</n-button>
        </n-space>
      </n-form-item>
      <n-form-item label="备注">
        <n-input v-model:value="form.note" type="textarea" :rows="2" style="width: 300px;" />
      </n-form-item>
    </n-form>

    <n-card title="配件列表" style="margin-bottom: 16px;">
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
          <n-input-number v-model:value="item.qty_per_unit" :min="0.001" :precision="4" placeholder="每件用量" style="width: 140px;" />
          <n-button type="error" size="small" @click="items.splice(idx, 1)">删</n-button>
        </n-space>
      </div>
      <n-button dashed style="width: 100%;" @click="items.push({ part_id: null, qty_per_unit: 1 })">
        + 添加配件行
      </n-button>
    </n-card>

    <n-space justify="end">
      <n-button type="primary" :loading="submitting" @click="submit">提交</n-button>
    </n-space>

    <ImageUploadModal
      v-model:show="showImageModal"
      kind="jewelry-template"
      :entity-id="null"
      @uploaded="(url) => form.image = url"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NSpace, NButton, NInput, NInputNumber, NForm, NFormItem, NCard, NH2, NSelect } from 'naive-ui'
import { listParts } from '@/api/parts'
import { createTemplate } from '@/api/jewelryTemplates'
import { renderOptionWithImage } from '@/utils/ui'
import ImageUploadModal from '../../components/ImageUploadModal.vue'

const router = useRouter()
const message = useMessage()
const submitting = ref(false)
const showImageModal = ref(false)
const partOptions = ref([])

const form = reactive({ name: '', image: '', note: '' })
const items = reactive([{ part_id: null, qty_per_unit: 1 }])

const submit = async () => {
  if (!form.name?.trim()) { message.warning('请输入模板名称'); return }
  const validItems = items.filter((i) => i.part_id)
  if (validItems.length === 0) { message.warning('请至少添加一个配件'); return }
  submitting.value = true
  try {
    const { data } = await createTemplate({
      name: form.name,
      image: form.image || null,
      note: form.note || null,
      items: validItems.map((i) => ({ part_id: i.part_id, qty_per_unit: i.qty_per_unit })),
    })
    message.success('模板创建成功')
    router.push(`/jewelry-templates/${data.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const { data } = await listParts()
  partOptions.value = data.map((p) => ({
    label: `${p.id} ${p.name}`,
    value: p.id,
    code: p.id,
    name: p.name,
    image: p.image,
  }))
})
</script>
