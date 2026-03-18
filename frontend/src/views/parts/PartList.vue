<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">商品 / 配件管理</div>
      <h2 class="page-title">配件管理</h2>
      <div class="page-divider"></div>
    </div>

    <div class="filter-bar">
      <n-input v-model:value="searchName" placeholder="搜索配件名称" clearable style="width: 200px;" @update:value="load" />
      <n-select
        v-model:value="searchCategory"
        :options="categoryOptions"
        clearable
        placeholder="筛选类目"
        style="width: 160px;"
        @update:value="load"
      />
      <div class="filter-bar-end">
        <n-button type="primary" @click="openCreate">新增配件</n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" />
      <n-empty v-else-if="!loading" description="暂无数据" style="margin-top: 24px;" />
    </n-spin>

    <!-- Create / Edit Modal -->
    <n-modal v-model:show="showModal" preset="card" :title="editingId ? '编辑配件' : '新增配件'" style="width: 480px;">
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
              alt="配件图片"
              :width="72"
              :height="72"
              object-fit="cover"
              style="border-radius: 12px; border: 1px solid #ffd6d6; overflow: hidden; display: block; cursor: zoom-in;"
            />
          </n-space>
        </n-form-item>
        <n-form-item label="类目">
          <n-select v-model:value="form.category" :options="categoryOptions" clearable placeholder="请选择类目" :disabled="!!editingId" />
          <span v-if="!!editingId" style="color: #999; font-size: 12px; margin-left: 8px;">类目不可修改</span>
        </n-form-item>
        <n-form-item label="颜色"><n-input v-model:value="form.color" /></n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="form.unit" :options="unitOptions" placeholder="请选择单位" />
        </n-form-item>
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

    <ImageUploadModal
      v-model:show="showImageModal"
      kind="part"
      :entity-id="currentUploadItemId"
      @uploaded="onImageUploaded"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NEmpty, NDropdown, NImage,
} from 'naive-ui'
import { listParts, createPart, updatePart, deletePart } from '@/api/parts'
import { getStock, addStock } from '@/api/inventory'
import { renderNamedImage } from '@/utils/ui'
import ImageUploadModal from '../../components/ImageUploadModal.vue'

const router = useRouter()
const message = useMessage()

const loading = ref(true)
const rows = ref([])
const searchName = ref('')
const searchCategory = ref(null)

const categoryOptions = [
  { label: '吊坠', value: '吊坠' },
  { label: '链条', value: '链条' },
  { label: '小配件', value: '小配件' },
]

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

// Modal state
const showModal = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({ name: '', image: '', category: null, color: '', unit: '个', unit_cost: null, plating_process: '' })

// Image upload modal state
const showImageModal = ref(false)
const currentUploadItemId = ref(null)

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

const VALID_CATEGORIES = categoryOptions.map((o) => o.value)

const openCreate = () => {
  editingId.value = null
  Object.assign(form, { name: '', image: '', category: null, color: '', unit: '个', unit_cost: null, plating_process: '' })
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
    unit: row.unit || '个',
    unit_cost: row.unit_cost ?? null,
    plating_process: row.plating_process || '',
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
      const { category, ...updateData } = form
      await updatePart(editingId.value, updateData)
    } else {
      await createPart(form)
    }
    message.success('保存成功')
    showModal.value = false
    await load()
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
    await load()
  } finally {
    stocking.value = false
  }
}

const doDelete = async (id) => {
  await deletePart(id)
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
    title: '配件',
    key: 'name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.name, row.image, row.name),
  },
  { title: '类目', key: 'category' },
  { title: '颜色', key: 'color' },
  { title: '单位', key: 'unit', width: 60 },
  { title: '单件成本', key: 'unit_cost', width: 90, render: (r) => r.unit_cost?.toFixed(2) ?? '-' },
  {
    title: '当前库存',
    key: 'stock',
    width: 90,
    render: (r) => r.stock < 10
      ? h('span', { class: 'badge badge-red' }, ['• ', r.stock])
      : r.stock,
  },
  { title: '默认电镀', key: 'plating_process' },
  {
    title: '操作',
    key: 'actions',
    width: 160,
    render: (row) =>
      h(NSpace, { size: 6 }, () => [
        h('button', {
          class: 'icon-btn',
          title: '详情',
          onClick: () => router.push(`/parts/${row.id}`),
        }, '→'),
        h('button', {
          class: 'icon-btn',
          title: '编辑',
          onClick: () => openEdit(row),
        }, '✎'),
        h(NDropdown, {
          options: [
            { label: '入库', key: 'stock' },
            { label: '删除', key: 'delete' },
          ],
          onSelect: (key) => {
            if (key === 'stock') openStock(row)
            if (key === 'delete') confirmDelete(row)
          },
        }, {
          default: () => h('button', { class: 'icon-btn', title: '更多' }, '⋮'),
        }),
      ]),
  },
]

onMounted(load)
</script>
