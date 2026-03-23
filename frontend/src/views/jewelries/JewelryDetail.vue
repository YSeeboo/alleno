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
          </n-descriptions-item>
          <n-descriptions-item label="类目">{{ jewelry.category || '-' }}</n-descriptions-item>
          <n-descriptions-item label="颜色">{{ jewelry.color || '-' }}</n-descriptions-item>
          <n-descriptions-item label="零售价">{{ jewelry.retail_price != null ? fmtMoney(jewelry.retail_price) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="批发价">{{ jewelry.wholesale_price != null ? fmtMoney(jewelry.wholesale_price) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="状态">{{ jewelry.status }}</n-descriptions-item>
          <n-descriptions-item label="当前库存">{{ stock }}</n-descriptions-item>
        </n-descriptions>
      </n-card>

      <n-card title="BOM 配置">
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
            placeholder="选择配件"
            style="width: 240px;"
          />
          <n-input-number v-model:value="newQty" :min="0.01" :precision="4" placeholder="每件用量" style="width: 140px;" />
          <n-button type="primary" :loading="adding" @click="addBom">确认添加</n-button>
        </n-space>
      </n-card>
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NEmpty, NDivider, NSelect, NInputNumber, NPopconfirm, NImage,
} from 'naive-ui'
import { getJewelry } from '@/api/jewelries'
import { getBom, setBom, deleteBom } from '@/api/bom'
import { getStock } from '@/api/inventory'
import { listParts } from '@/api/parts'
import { renderNamedImage, renderOptionWithImage, fmtMoney } from '@/utils/ui'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const loading = ref(true)
const jewelry = ref(null)
const stock = ref(0)
const bomRows = ref([])
const partOptions = ref([])
const newPartId = ref(null)
const newQty = ref(1)
const adding = ref(false)

// Map part_id -> name for display
const partMap = ref({})

const loadBom = async () => {
  const { data } = await getBom(route.params.id)
  bomRows.value = data.map((b) => ({
    ...b,
    part_name: partMap.value[b.part_id]?.name || b.part_id,
    part_image: partMap.value[b.part_id]?.image || '',
    editQty: null,
  }))
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
  } finally {
    loading.value = false
  }
})

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
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
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
