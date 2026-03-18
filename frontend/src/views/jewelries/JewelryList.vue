<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">商品 / 饰品管理</div>
      <h2 class="page-title">饰品管理</h2>
      <div class="page-divider"></div>
    </div>

    <div class="filter-bar">
      <n-select
        v-model:value="filterStatus"
        :options="statusOptions"
        clearable
        placeholder="筛选状态"
        style="width: 140px;"
        @update:value="load"
      />
      <div class="filter-bar-end">
        <n-button type="primary" @click="openCreate">新增饰品</n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" />
      <n-empty v-else-if="!loading" description="暂无数据" style="margin-top: 24px;" />
    </n-spin>

    <n-modal v-model:show="showModal" preset="card" :title="editingId ? '编辑饰品' : '新增饰品'" style="width: 480px;">
      <n-form ref="formRef" :model="form" label-placement="left" label-width="100">
        <n-form-item label="名称" path="name" :rule="{ required: true, message: '请输入名称' }">
          <n-input v-model:value="form.name" />
        </n-form-item>
        <n-form-item label="图片">
          <n-space vertical style="width: 100%;">
            <n-space align="center" style="width: 100%;">
              <n-input v-model:value="form.image" placeholder="上传后自动填充，也可手动输入 URL" />
              <n-button @click="openImageModal(editingId)">上传图片</n-button>
            </n-space>
            <n-image
              v-if="form.image"
              :src="form.image"
              alt="饰品图片"
              :width="72"
              :height="72"
              object-fit="cover"
              style="border-radius: 12px; border: 1px solid #ffd6d6; overflow: hidden; display: block; cursor: zoom-in;"
            />
          </n-space>
        </n-form-item>
        <n-form-item label="类目">
          <n-select v-model:value="form.category" :options="categoryOptions" clearable placeholder="请选择类目" />
        </n-form-item>
        <n-form-item label="颜色"><n-input v-model:value="form.color" /></n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="form.unit" :options="unitOptions" placeholder="请选择单位" />
        </n-form-item>
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

    <ImageUploadModal
      v-model:show="showImageModal"
      kind="jewelry"
      :entity-id="currentUploadItemId"
      @uploaded="onImageUploaded"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NEmpty, NImage, NDropdown,
} from 'naive-ui'
import { listJewelries, createJewelry, updateJewelry, updateJewelryStatus, deleteJewelry } from '@/api/jewelries'
import { getStock } from '@/api/inventory'
import { renderNamedImage } from '@/utils/ui'
import ImageUploadModal from '../../components/ImageUploadModal.vue'

const router = useRouter()
const message = useMessage()
const loading = ref(true)
const rows = ref([])
const filterStatus = ref(null)
const statusOptions = [
  { label: '启用', value: 'active' },
  { label: '停用', value: 'inactive' },
]

const categoryOptions = [
  { label: '套装', value: '套装' },
  { label: '单件', value: '单件' },
  { label: '单对', value: '单对' },
]

const unitOptions = [
  { label: '个', value: '个' },
  { label: '套', value: '套' },
  { label: '对', value: '对' },
]

const VALID_CATEGORIES = categoryOptions.map((o) => o.value)

const showModal = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({ name: '', image: '', category: null, color: '', unit: null, retail_price: null, wholesale_price: null })

// Image upload modal state
const showImageModal = ref(false)
const currentUploadItemId = ref(null)

// Auto-fill unit based on category
watch(
  () => form.category,
  (cat) => {
    if (cat === '套装') form.unit = '套'
    else if (cat === '单件') form.unit = '个'
    else if (cat === '单对') form.unit = '对'
  }
)

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
  Object.assign(form, { name: '', image: '', category: null, color: '', unit: null, retail_price: null, wholesale_price: null })
  showModal.value = true
}

const openEdit = (row) => {
  editingId.value = row.id
  const cat = row.category && VALID_CATEGORIES.includes(row.category) ? row.category : null
  Object.assign(form, {
    name: row.name,
    image: row.image || '',
    category: cat,
    color: row.color || '',
    unit: row.unit || null,
    retail_price: row.retail_price ?? null,
    wholesale_price: row.wholesale_price ?? null,
  })
  showModal.value = true
}

const openImageModal = (id) => {
  currentUploadItemId.value = id
  showImageModal.value = true
}

const onImageUploaded = (url) => {
  form.image = url
  load()
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
    await load()
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
  await load()
}

const confirmDelete = (row) => {
  window.$dialog.warning({
    title: '确认删除',
    content: `确认删除 ${row.name}？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: () => doDelete(row.id),
  })
}

const columns = [
  { title: '编号', key: 'id', width: 100 },
  {
    title: '饰品',
    key: 'name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.name, row.image, row.name),
  },
  { title: '类目', key: 'category' },
  { title: '颜色', key: 'color' },
  { title: '单位', key: 'unit', width: 60 },
  { title: '零售价', key: 'retail_price', render: (r) => r.retail_price?.toFixed(2) ?? '-' },
  { title: '批发价', key: 'wholesale_price', render: (r) => r.wholesale_price?.toFixed(2) ?? '-' },
  { title: '当前库存', key: 'stock' },
  {
    title: '状态',
    key: 'status',
    render: (row) =>
      h('span', {
        class: `badge ${row.status === 'active' ? 'badge-green' : 'badge-gray'}`,
        style: 'cursor: pointer;',
        onClick: () => toggleStatus(row),
      }, row.status === 'active' ? '• 启用' : '• 停用'),
  },
  {
    title: '操作',
    key: 'actions',
    render: (row) =>
      h(NSpace, { size: 6 }, () => [
        h('button', { class: 'icon-btn', title: '详情', onClick: () => router.push(`/jewelries/${row.id}`) }, '→'),
        h('button', { class: 'icon-btn', title: '编辑', onClick: () => openEdit(row) }, '✎'),
        h(NDropdown, {
          options: [{ label: '删除', key: 'delete' }],
          onSelect: (key) => { if (key === 'delete') confirmDelete(row) },
        }, {
          default: () => h('button', { class: 'icon-btn', title: '更多' }, '⋮'),
        }),
      ]),
  },
]

onMounted(load)
</script>
