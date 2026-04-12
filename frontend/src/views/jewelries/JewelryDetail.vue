<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">饰品详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-card v-if="jewelry" title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="编号">{{ jewelry.id }}</n-descriptions-item>
          <n-descriptions-item label="饰品">{{ jewelry.name }}</n-descriptions-item>
          <n-descriptions-item label="图片">
            <n-space align="center">
              <n-image
                v-if="jewelry.image"
                :src="jewelry.image"
                :alt="jewelry.name"
                :width="48"
                :height="48"
                object-fit="cover"
                style="border-radius: 8px; border: 1px solid #ffd6d6; overflow: hidden; display: block; cursor: zoom-in;"
              />
              <span v-else>无图</span>
              <n-button size="tiny" @click="showImageModal = true">更换</n-button>
            </n-space>
          </n-descriptions-item>
          <n-descriptions-item label="结构图">
            <n-space align="center">
              <n-image
                v-if="jewelry.structure_image"
                :src="jewelry.structure_image"
                :alt="jewelry.name + ' 结构图'"
                :width="48"
                :height="48"
                object-fit="cover"
                style="border-radius: 8px; border: 1px solid #ffd6d6; overflow: hidden; display: block; cursor: zoom-in;"
              />
              <span v-else>无图</span>
              <n-button size="tiny" @click="showStructureImageModal = true">更换</n-button>
            </n-space>
          </n-descriptions-item>
          <n-descriptions-item label="类目">{{ jewelry.category || '-' }}</n-descriptions-item>
          <n-descriptions-item label="颜色">{{ jewelry.color || '-' }}</n-descriptions-item>
          <n-descriptions-item label="零售价">{{ jewelry.retail_price != null ? fmtMoney(jewelry.retail_price) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="批发价">{{ jewelry.wholesale_price != null ? fmtMoney(jewelry.wholesale_price) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="手工费">{{ jewelry.handcraft_cost != null ? fmtMoney(jewelry.handcraft_cost) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="状态">{{ jewelry.status }}</n-descriptions-item>
          <n-descriptions-item label="当前库存">{{ stock }}</n-descriptions-item>
        </n-descriptions>
      </n-card>

      <n-card title="BOM 配置">
        <template #header-extra>
          <n-button v-if="canUseTemplates" size="small" @click="showTemplateModal = true">导入模板</n-button>
        </template>
        <n-data-table v-if="bomRows.length > 0" :columns="bomColumns" :data="bomRows" :bordered="false" />
        <n-empty v-else description="暂无BOM配置" style="margin: 16px 0;" />

        <!-- Add BOM row -->
        <n-divider>添加配件</n-divider>
        <n-space align="center">
          <n-select
            v-model:value="newPartId"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            clearable
            placeholder="选择配件"
            style="width: 240px;"
          />
          <n-input-number v-model:value="newQty" :min="0.01" :precision="4" placeholder="每件用量" style="width: 140px;" />
          <n-button type="primary" :loading="adding" @click="addBom">确认添加</n-button>
        </n-space>
      </n-card>
    </n-spin>

    <!-- Template import modal -->
    <n-modal v-model:show="showTemplateModal" preset="card" title="导入饰品模板" style="width: 520px;">
      <n-alert type="info" style="margin-bottom: 12px;">
        导入会覆盖已有相同配件的用量
      </n-alert>
      <n-spin :show="loadingTemplates">
        <n-empty v-if="!loadingTemplates && templates.length === 0" description="暂无模板" />
        <div v-for="tpl in templates" :key="tpl.id" style="display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f0f0f0;">
          <div>
            <div style="font-weight: 600;">{{ tpl.name }}</div>
            <div style="color: #999; font-size: 12px;">{{ tpl.item_count || 0 }} 个配件</div>
          </div>
          <n-button size="small" type="primary" :loading="applyingTemplate === tpl.id" @click="doApplyTemplate(tpl)">导入</n-button>
        </div>
      </n-spin>
    </n-modal>

    <ImageUploadModal
      v-model:show="showImageModal"
      kind="jewelry"
      :entity-id="jewelry?.id"
      suppress-success
      @uploaded="onImageUploaded"
    />
    <ImageUploadModal
      v-model:show="showStructureImageModal"
      kind="jewelry"
      :entity-id="jewelry?.id ? jewelry.id + '-structure' : null"
      suppress-success
      @uploaded="onStructureImageUploaded"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NEmpty, NDivider, NSelect, NInputNumber, NPopconfirm, NImage,
  NModal, NAlert,
} from 'naive-ui'
import { getJewelry, updateJewelry } from '@/api/jewelries'
import { getBom, setBom, deleteBom } from '@/api/bom'
import { getStock } from '@/api/inventory'
import { listParts } from '@/api/parts'
import { listTemplates, applyTemplate } from '@/api/jewelryTemplates'
import { renderNamedImage, renderOptionWithImage, fmtMoney } from '@/utils/ui'
import ImageUploadModal from '../../components/ImageUploadModal.vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()
const canUseTemplates = authStore.hasPermission('parts')

const loading = ref(true)
const jewelry = ref(null)
const stock = ref(0)
const bomRows = ref([])
const partOptions = ref([])
const newPartId = ref(null)
const newQty = ref(1)
const adding = ref(false)

// Image modal
const showImageModal = ref(false)
const showStructureImageModal = ref(false)

// Template modal
const showTemplateModal = ref(false)
const loadingTemplates = ref(false)
const templates = ref([])
const applyingTemplate = ref(null)

// Map part_id -> name for display
const partMap = ref({})

const loadBom = async () => {
  const { data } = await getBom(route.params.id)
  bomRows.value = data.map((b) => ({
    ...b,
    part_name: partMap.value[b.part_id]?.name || b.part_id,
    part_image: partMap.value[b.part_id]?.image || '',
    part_unit: partMap.value[b.part_id]?.unit || '',
    part_is_composite: partMap.value[b.part_id]?.is_composite || false,
    editQty: null,
  }))
}

const loadTemplateList = async () => {
  loadingTemplates.value = true
  try {
    const { data } = await listTemplates()
    templates.value = data
  } finally {
    loadingTemplates.value = false
  }
}

const doApplyTemplate = async (tpl) => {
  applyingTemplate.value = tpl.id
  try {
    await applyTemplate(tpl.id, route.params.id)
    message.success('模板已导入')
    showTemplateModal.value = false
    await loadBom()
  } finally {
    applyingTemplate.value = null
  }
}

onMounted(async () => {
  const id = route.params.id
  try {
    const [jRes, sRes, partsRes] = await Promise.all([
      getJewelry(id),
      getStock('jewelry', id),
      listParts(),
    ])
    jewelry.value = jRes.data
    stock.value = sRes.data.current
    partsRes.data.forEach((p) => { partMap.value[p.id] = p })
    partOptions.value = partsRes.data.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
    }))
    await loadBom()
    if (canUseTemplates) await loadTemplateList()
  } finally {
    loading.value = false
  }
})

const onImageUploaded = async (url) => {
  if (jewelry.value) {
    jewelry.value.image = url
    try {
      await updateJewelry(jewelry.value.id, { image: url })
      message.success('图片已更新')
    } catch {
      message.error('图片保存失败，请刷新页面重试')
    }
  }
}

const onStructureImageUploaded = async (url) => {
  if (jewelry.value) {
    jewelry.value.structure_image = url
    try {
      await updateJewelry(jewelry.value.id, { structure_image: url })
      message.success('结构图已更新')
    } catch {
      message.error('结构图保存失败，请刷新页面重试')
    }
  }
}

const addBom = async () => {
  if (!newPartId.value || !newQty.value) return
  adding.value = true
  try {
    await setBom(route.params.id, newPartId.value, newQty.value)
    message.success('添加成功')
    newPartId.value = null
    newQty.value = 1
    await loadBom()
  } finally {
    adding.value = false
  }
}

const saveQty = async (row) => {
  if (!row.editQty || row.editQty === row.qty_per_unit) { row.editQty = null; return }
  await setBom(route.params.id, row.part_id, row.editQty)
  message.success('已更新')
  row.qty_per_unit = row.editQty
  row.editQty = null
}

const doDeleteBom = async (row) => {
  await deleteBom(route.params.id, row.part_id)
  message.success('已删除')
  await loadBom()
}

const bomColumns = [
  { title: '配件编号', key: 'part_id', width: 110 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name, 40, row.part_is_composite ? '组合' : null),
  },
  {
    title: '每件用量',
    key: 'qty_per_unit',
    render: (row) =>
      h('input', {
        value: row.editQty ?? row.qty_per_unit,
        type: 'number',
        min: 0.001,
        step: 0.001,
        style: 'width: 80px; border: 1px solid #ccc; border-radius: 4px; padding: 2px 6px;',
        onInput: (e) => { row.editQty = parseFloat(e.target.value) },
        onBlur: () => saveQty(row),
      }),
  },
  {
    title: '单位',
    key: 'part_unit',
    width: 60,
    render: (row) => row.part_unit || '-',
  },
  {
    title: '操作',
    key: 'actions',
    render: (row) =>
      h(NPopconfirm, { onPositiveClick: () => doDeleteBom(row) }, {
        trigger: () => h(NButton, { size: 'small', type: 'error' }, () => '删除'),
        default: () => `确认删除 ${row.part_name} 的BOM配置？`,
      }),
  },
]
</script>
