<template>
  <div>
    <n-space justify="space-between" align="center" style="margin-bottom: 16px;">
      <n-select
        v-model:value="filterStatus"
        :options="statusOptions"
        clearable
        placeholder="筛选状态"
        style="width: 140px;"
        @update:value="load"
      />
      <n-button type="primary" @click="openCreate">新增饰品</n-button>
    </n-space>

    <n-spin :show="loading">
      <n-data-table :columns="columns" :data="rows" :bordered="false" />
      <n-empty v-if="!loading && rows.length === 0" description="暂无数据" style="margin-top: 24px;" />
    </n-spin>

    <n-modal v-model:show="showModal" preset="card" :title="editingId ? '编辑饰品' : '新增饰品'" style="width: 480px;">
      <n-form ref="formRef" :model="form" label-placement="left" label-width="100">
        <n-form-item label="名称" path="name" :rule="{ required: true, message: '请输入名称' }">
          <n-input v-model:value="form.name" />
        </n-form-item>
        <n-form-item label="类目"><n-input v-model:value="form.category" /></n-form-item>
        <n-form-item label="颜色"><n-input v-model:value="form.color" /></n-form-item>
        <n-form-item label="零售价">
          <n-input-number v-model:value="form.retail_price" :min="0" :precision="2" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="批发价">
          <n-input-number v-model:value="form.wholesale_price" :min="0" :precision="2" style="width: 100%;" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
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
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NSwitch, NEmpty, NPopconfirm,
} from 'naive-ui'
import { listJewelries, createJewelry, updateJewelry, updateJewelryStatus, deleteJewelry } from '@/api/jewelries'
import { getStock } from '@/api/inventory'

const router = useRouter()
const message = useMessage()
const loading = ref(true)
const rows = ref([])
const filterStatus = ref(null)
const statusOptions = [
  { label: '启用', value: 'active' },
  { label: '停用', value: 'inactive' },
]

const showModal = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({ name: '', category: '', color: '', retail_price: null, wholesale_price: null })

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    const { data: jewelries } = await listJewelries(params)
    const stocks = await Promise.all(
      jewelries.map((j) => getStock('jewelry', j.id).then((r) => r.data.current).catch(() => 0))
    )
    rows.value = jewelries.map((j, i) => ({ ...j, stock: stocks[i] }))
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingId.value = null
  Object.assign(form, { name: '', category: '', color: '', retail_price: null, wholesale_price: null })
  showModal.value = true
}

const openEdit = (row) => {
  editingId.value = row.id
  Object.assign(form, {
    name: row.name, category: row.category || '', color: row.color || '',
    retail_price: row.retail_price ?? null, wholesale_price: row.wholesale_price ?? null,
  })
  showModal.value = true
}

const save = async () => {
  await formRef.value?.validate()
  saving.value = true
  try {
    if (editingId.value) {
      await updateJewelry(editingId.value, form)
    } else {
      await createJewelry(form)
    }
    message.success('保存成功')
    showModal.value = false
    load()
  } finally {
    saving.value = false
  }
}

const toggleStatus = async (row) => {
  const newStatus = row.status === 'active' ? 'inactive' : 'active'
  try {
    await updateJewelryStatus(row.id, newStatus)
    row.status = newStatus
  } catch (_) {
    // error shown by interceptor; reload to sync visual state
    await load()
  }
}

const doDelete = async (id) => {
  await deleteJewelry(id)
  message.success('已删除')
  load()
}

const columns = [
  { title: '编号', key: 'id', width: 100 },
  { title: '名称', key: 'name' },
  { title: '类目', key: 'category' },
  { title: '颜色', key: 'color' },
  { title: '零售价', key: 'retail_price', render: (r) => r.retail_price?.toFixed(2) ?? '-' },
  { title: '批发价', key: 'wholesale_price', render: (r) => r.wholesale_price?.toFixed(2) ?? '-' },
  { title: '当前库存', key: 'stock' },
  {
    title: '状态',
    key: 'status',
    render: (row) =>
      h(NSwitch, {
        value: row.status === 'active',
        onUpdateValue: () => toggleStatus(row),
      }),
  },
  {
    title: '操作',
    key: 'actions',
    render: (row) =>
      h(NSpace, null, () => [
        h(NButton, { size: 'small', onClick: () => openEdit(row) }, () => '编辑'),
        h(NButton, { size: 'small', onClick: () => router.push(`/jewelries/${row.id}`) }, () => '详情'),
        h(NPopconfirm, { onPositiveClick: () => doDelete(row.id) }, {
          trigger: () => h(NButton, { size: 'small', type: 'error' }, () => '删除'),
          default: () => `确认删除 ${row.name}？`,
        }),
      ]),
  },
]

onMounted(load)
</script>
