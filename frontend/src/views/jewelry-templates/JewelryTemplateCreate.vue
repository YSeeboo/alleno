<template>
  <div class="create-page">
    <!-- Header -->
    <div style="margin-bottom: 6px;">
      <n-button text @click="router.back()" style="color: #8B9096; font-size: 13px;">← 返回</n-button>
    </div>
    <div class="page-breadcrumb" style="margin-bottom: 10px;">商品 / 饰品模板 / 新建</div>
    <h1 class="page-title" style="margin-bottom: 24px;">新建饰品模板</h1>

    <!-- Basic info form -->
    <div class="form-wrap">
      <n-form label-placement="top" style="margin-bottom: 24px;">
        <div class="form-sec-h">基本信息</div>

        <n-form-item label="模板名称">
          <n-input v-model:value="form.name" placeholder="输入模板名称" style="width: 100%;" />
        </n-form-item>

        <n-form-item label="备注">
          <n-input v-model:value="form.note" type="textarea" :rows="2" style="width: 100%;" />
        </n-form-item>

        <div class="form-sec-h" style="margin-top: 20px;">图片</div>

        <n-form-item label="">
          <div class="image-row">
            <div class="image-preview">
              <n-image
                v-if="form.image"
                :src="form.image"
                width="56"
                height="56"
                object-fit="cover"
                style="border-radius: 8px; display: block;"
              />
              <div v-else class="image-placeholder"></div>
            </div>
            <n-input
              v-model:value="form.image"
              placeholder="上传后自动填充，也可手动输入 URL"
              style="flex: 1;"
            />
            <n-button @click="showImageModal = true">上传图片</n-button>
          </div>
        </n-form-item>
      </n-form>
    </div>

    <!-- Parts list -->
    <n-card title="配件列表" style="margin-bottom: 16px; max-width: 560px;">
      <div v-for="(item, idx) in items" :key="idx" style="margin-bottom: 10px;">
        <n-space align="center">
          <n-select
            v-model:value="item.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            clearable
            placeholder="选择配件"
            :style="{ width: isMobile ? '100%' : '240px' }"
          />
          <n-input-number v-model:value="item.qty_per_unit" :min="0.001" :precision="4" placeholder="每件用量" style="width: 140px;" />
          <n-button type="error" size="small" @click="items.splice(idx, 1)">删</n-button>
        </n-space>
      </div>
      <n-button dashed style="width: 100%;" @click="items.push({ part_id: null, qty_per_unit: 1 })">
        + 添加配件行
      </n-button>
    </n-card>

    <!-- Floating action bar -->
    <floating-action-bar>
      <n-button quaternary style="color: #C0C6CD;" @click="router.back()">取消</n-button>
      <n-button type="primary" :loading="submitting" @click="submit">提交</n-button>
    </floating-action-bar>

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
import { NSpace, NButton, NInput, NInputNumber, NForm, NFormItem, NCard, NSelect, NImage } from 'naive-ui'
import { listParts } from '@/api/parts'
import { createTemplate } from '@/api/jewelryTemplates'
import { renderOptionWithImage } from '@/utils/ui'
import ImageUploadModal from '../../components/ImageUploadModal.vue'
import FloatingActionBar from '@/components/FloatingActionBar.vue'
import { useIsMobile } from '@/composables/useIsMobile'

const router = useRouter()
const message = useMessage()
const { isMobile } = useIsMobile()
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

<style scoped>
.create-page {
  padding: 24px 20px 0;
}

.page-breadcrumb {
  font-size: 12px;
  color: #8B9096;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.4px;
  margin: 0;
  color: #1A1D21;
  line-height: 1.2;
}

.form-wrap {
  max-width: 560px;
}

.form-sec-h {
  font-size: 11px;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: #8B9096;
  font-weight: 600;
  margin: 0 0 11px;
}

.image-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.image-preview {
  flex-shrink: 0;
}

.image-placeholder {
  width: 56px;
  height: 56px;
  border-radius: 8px;
  background: #ECEDEF;
  border: 1px dashed #C0C6CD;
}
</style>
