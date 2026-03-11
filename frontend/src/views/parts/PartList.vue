<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px;">
      <n-space>
        <n-input v-model:value="searchName" placeholder="搜索配件名称" clearable style="width: 200px;" @update:value="load" />
        <n-input v-model:value="searchCategory" placeholder="筛选类目" clearable style="width: 160px;" @update:value="load" />
      </n-space>
      <n-button type="primary" @click="openCreate">新增配件</n-button>
    </n-space>

    <n-spin :show="loading">
      <n-data-table :columns="columns" :data="rows" :bordered="false" />
      <n-empty v-if="!loading && rows.length === 0" description="暂无数据" style="margin-top: 24px;" />
    </n-spin>

    <!-- Create / Edit Modal -->
    <n-modal v-model:show="showModal" preset="card" :title="editingId ? '编辑配件' : '新增配件'" style="width: 480px;">
      <n-form ref="formRef" :model="form" label-placement="left" label-width="100">
        <n-form-item label="名称" path="name" :rule="{ required: true, message: '请输入名称' }">
          <n-input v-model:value="form.name" />
        </n-form-item>
        <n-form-item label="类目"><n-input v-model:value="form.category" /></n-form-item>
        <n-form-item label="颜色"><n-input v-model:value="form.color" /></n-form-item>
        <n-form-item label="单位"><n-input v-model:value="form.unit" /></n-form-item>
        <n-form-item label="单件成本">
          <n-input-number v-model:value="form.unit_cost" :min="0" :precision="2" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="默认电镀工艺"><n-input v-model:value="form.plating_process" /></n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Quick Stock-In Modal -->
    <n-modal v-model:show="showStockModal" preset="card" title="快速入库" style="width: 360px;">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="数量">
          <n-input-number v-model:value="stockQty" :min="0.01" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="stockNote" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showStockModal = false">取消</n-button>
          <n-button type="primary" :loading="stocking" @click="doStock">入库</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NSpace, NButton, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NEmpty, NPopconfirm,
} from 'naive-ui'
import { listParts, createPart, updatePart, deletePart } from '@/api/parts'
import { getStock, addStock } from '@/api/inventory'

const router = useRouter()
const message = useMessage()

const loading = ref(false)
const rows = ref([])
const searchName = ref('')
const searchCategory = ref('')

// Modal state
const showModal = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({ name: '', category: '', color: '', unit: '', unit_cost: null, plating_process: '' })

// Stock modal state
const showStockModal = ref(false)
const stockingId = ref(null)
const stockQty = ref(1)
const stockNote = ref('')
const stocking = ref(false)

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (searchName.value) params.name = searchName.value
    if (searchCategory.value) params.category = searchCategory.value
    const { data: parts } = await listParts(params)
    const stocks = await Promise.all(
      parts.map((p) => getStock('part', p.id).then((r) => r.data.current).catch(() => 0))
    )
    rows.value = parts.map((p, i) => ({ ...p, stock: stocks[i] }))
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingId.value = null
  Object.assign(form, { name: '', category: '', color: '', unit: '', unit_cost: null, plating_process: '' })
  showModal.value = true
}

const openEdit = (row) => {
  editingId.value = row.id
  Object.assign(form, {
    name: row.name,
    category: row.category || '',
    color: row.color || '',
    unit: row.unit || '',
    unit_cost: row.unit_cost ?? null,
    plating_process: row.plating_process || '',
  })
  showModal.value = true
}

const save = async () => {
  await formRef.value?.validate()
  saving.value = true
  try {
    if (editingId.value) {
      await updatePart(editingId.value, form)
    } else {
      await createPart(form)
    }
    message.success('保存成功')
    showModal.value = false
    load()
  } finally {
    saving.value = false
  }
}

const openStock = (row) => {
  stockingId.value = row.id
  stockQty.value = 1
  stockNote.value = ''
  showStockModal.value = true
}

const doStock = async () => {
  stocking.value = true
  try {
    await addStock('part', stockingId.value, { qty: stockQty.value, reason: '采购入库', note: stockNote.value })
    message.success('入库成功')
    showStockModal.value = false
    load()
  } finally {
    stocking.value = false
  }
}

const doDelete = async (id) => {
  await deletePart(id)
  message.success('已删除')
  load()
}

const columns = [
  { title: '编号', key: 'id', width: 100 },
  { title: '名称', key: 'name' },
  { title: '类目', key: 'category' },
  { title: '颜色', key: 'color' },
  { title: '单位', key: 'unit', width: 60 },
  { title: '单件成本', key: 'unit_cost', width: 90, render: (r) => r.unit_cost?.toFixed(2) ?? '-' },
  {
    title: '当前库存',
    key: 'stock',
    width: 90,
    render: (r) => h('span', { style: { color: r.stock < 10 ? '#d03050' : undefined } }, r.stock),
  },
  { title: '默认电镀', key: 'plating_process' },
  {
    title: '操作',
    key: 'actions',
    width: 220,
    render: (row) =>
      h(NSpace, null, () => [
        h(NButton, { size: 'small', onClick: () => openEdit(row) }, () => '编辑'),
        h(NButton, { size: 'small', onClick: () => router.push(`/parts/${row.id}`) }, () => '详情'),
        h(NButton, { size: 'small', type: 'info', onClick: () => openStock(row) }, () => '入库'),
        h(
          NPopconfirm,
          { onPositiveClick: () => doDelete(row.id) },
          {
            trigger: () => h(NButton, { size: 'small', type: 'error' }, () => '删除'),
            default: () => `确认删除 ${row.name}？`,
          }
        ),
      ]),
  },
]

onMounted(load)
</script>
