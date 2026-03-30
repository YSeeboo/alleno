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
        <n-space>
          <n-button @click="openImportModal">导入配件</n-button>
          <n-button type="primary" @click="openCreate">新增配件</n-button>
        </n-space>
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" />
      <n-empty v-else-if="!loading" description="暂无数据" style="margin-top: 24px;" />
    </n-spin>

    <!-- Create / Edit Modal -->
    <n-modal v-model:show="showModal" preset="card" :title="editingId ? '编辑配件' : '新增配件'" style="width: 480px;">
      <form @submit.prevent="save">
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
        <n-form-item
          label="类目"
          path="category"
          :rule="editingId ? undefined : { required: true, message: '请选择类目', trigger: 'change' }"
        >
          <n-select v-model:value="form.category" :options="categoryOptions" clearable placeholder="请选择类目" :disabled="!!editingId" />
          <span v-if="!!editingId" style="color: #999; font-size: 12px; margin-left: 8px;">类目不可修改</span>
        </n-form-item>
        <n-form-item label="颜色">
          <n-input v-model:value="form.color" :disabled="editingIsVariant" />
          <span v-if="editingIsVariant" style="color: #999; font-size: 12px; margin-left: 8px;">变体不可修改</span>
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="form.unit" :options="unitOptions" placeholder="请选择单位" />
        </n-form-item>
        <n-form-item label="单件成本">
          <n-input-number v-model:value="form.unit_cost" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="关联原色配件">
          <n-select
            v-model:value="form.parent_part_id"
            :options="parentPartOptions"
            filterable
            clearable
            placeholder="选填，选择原色配件"
            :disabled="editingIsVariant"
          />
          <span v-if="editingIsVariant" style="color: #999; font-size: 12px; margin-left: 8px;">变体不可修改</span>
        </n-form-item>
        <n-form-item v-if="editingId" label="创建变体">
          <n-space>
            <n-button
              v-for="vc in variantColorOptions"
              :key="vc.code"
              size="small"
              :disabled="vc.exists || creatingVariant || loadingVariants"
              :type="vc.exists ? 'default' : 'primary'"
              secondary
              @click="doCreateVariant(vc.code)"
            >
              {{ vc.label }}{{ vc.exists ? ' ✓' : '' }}
            </n-button>
          </n-space>
        </n-form-item>
      </n-form>
      </form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Quick Stock-In Modal -->
    <n-modal v-model:show="showStockModal" preset="card" title="快速入库" style="width: 360px;">
      <form @submit.prevent="doStock">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="数量">
          <n-input-number v-model:value="stockQty" :min="0.01" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="stockNote" />
        </n-form-item>
      </n-form>
      </form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showStockModal = false">取消</n-button>
          <n-button type="primary" :loading="stocking" @click="doStock">入库</n-button>
        </n-space>
      </template>
    </n-modal>

    <n-modal v-model:show="showImportModal" preset="card" title="导入配件" style="width: 560px;">
      <n-space vertical :size="16" style="width: 100%;">
        <div style="padding: 14px 16px; border-radius: 14px; background: #fff9ec; color: #6f5214; line-height: 1.75;">
          仅支持 `.xlsx` 文件。系统按首个工作表导入，表头建议使用：
          名称、类目、颜色、单位、采购成本、默认电镀工艺、入库数量。
          配件编号会由系统自动生成；如果系统里已存在同名同类目的配件，会自动更新该配件并追加入库数量。
        </div>
        <n-space align="center" justify="space-between">
          <div style="color: #6b7280;">
            {{ importFile ? `已选择：${importFile.name}` : '尚未选择文件' }}
          </div>
          <n-space>
            <n-button class="template-download-btn" @click="downloadTemplate">下载模板</n-button>
            <n-button @click="triggerImportFileSelect">选择 Excel</n-button>
          </n-space>
        </n-space>
        <div v-if="importError" style="padding: 12px 14px; border-radius: 12px; background: #fff1f2; color: #b42318; white-space: pre-wrap;">
          {{ importError }}
        </div>
      </n-space>
      <template #footer>
        <n-space justify="end">
          <n-button :disabled="importing" @click="closeImportModal">取消</n-button>
          <n-button type="primary" :loading="importing" @click="doImport">开始导入</n-button>
        </n-space>
      </template>
    </n-modal>

    <ImageUploadModal
      v-model:show="showImageModal"
      kind="part"
      :entity-id="currentUploadItemId"
      @uploaded="onImageUploaded"
    />

    <input
      ref="importFileInputRef"
      type="file"
      accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      style="display: none;"
      @change="handleImportFileChange"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NEmpty, NDropdown, NImage,
} from 'naive-ui'
import { listParts, createPart, updatePart, deletePart, importPartsExcel, downloadPartsImportTemplate, getPartVariants, createPartVariant } from '@/api/parts'
import { getStock, addStock } from '@/api/inventory'
import { renderNamedImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import ImageUploadModal from '../../components/ImageUploadModal.vue'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()

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

const existingVariantColors = ref([])
const creatingVariant = ref(false)
const loadingVariants = ref(false)

const COLOR_CODE_REVERSE = { '金色': 'G', '白K': 'S', '玫瑰金': 'RG' }
const VARIANT_COLORS = [
  { code: 'G', label: '金色 G' },
  { code: 'S', label: '白K S' },
  { code: 'RG', label: '玫瑰金 RG' },
]

const variantColorOptions = computed(() =>
  VARIANT_COLORS.map((vc) => ({
    ...vc,
    exists: existingVariantColors.value.includes(vc.code),
  }))
)

const doCreateVariant = async (colorCode) => {
  creatingVariant.value = true
  try {
    await createPartVariant(editingId.value, { color_code: colorCode })
    message.success(`变体 ${colorCode} 创建成功`)
    // Refresh existing variants
    const { data: variants } = await getPartVariants(editingId.value)
    existingVariantColors.value = variants
      .map((v) => COLOR_CODE_REVERSE[v.color])
      .filter(Boolean)
    await load()
  } catch (error) {
    message.error(error.response?.data?.detail || '创建变体失败')
  } finally {
    creatingVariant.value = false
  }
}

// Modal state
const showModal = ref(false)
const editingId = ref(null)
const editingIsVariant = ref(false)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({ name: '', image: '', category: null, color: '', unit: '个', unit_cost: null, plating_process: '', parent_part_id: null })

// Image upload modal state
const showImageModal = ref(false)
const currentUploadItemId = ref(null)

// Stock modal state
const showStockModal = ref(false)
const stockingId = ref(null)
const stockQty = ref(1)
const stockNote = ref('')
const stocking = ref(false)

// Import modal state
const showImportModal = ref(false)
const importFileInputRef = ref(null)
const importFile = ref(null)
const importing = ref(false)
const importError = ref('')

const load = async () => {
  loading.value = true
  try {
    const [filteredRes, allRes] = await Promise.all([
      listParts((() => {
        const params = {}
        if (searchName.value) params.name = searchName.value
        if (searchCategory.value) params.category = searchCategory.value
        return params
      })()),
      listParts(),
    ])
    allPartsForSelect.value = allRes.data
    const parts = filteredRes.data
    const stocks = await Promise.all(
      parts.map((p) => getStock('part', p.id).then((r) => r.data.current).catch(() => 0))
    )
    rows.value = parts.map((p, i) => ({ ...p, stock: stocks[i] }))
  } finally {
    loading.value = false
  }
}

const VALID_CATEGORIES = categoryOptions.map((o) => o.value)

const allPartsForSelect = ref([])

const parentPartOptions = computed(() => {
  const currentId = editingId.value
  if (!currentId) {
    return allPartsForSelect.value.map((p) => ({ label: `${p.id} ${p.name}`, value: p.id }))
  }
  // Collect all descendants to prevent circular references
  const excluded = new Set([currentId])
  let frontier = [currentId]
  while (frontier.length > 0) {
    const children = allPartsForSelect.value
      .filter((p) => p.parent_part_id && frontier.includes(p.parent_part_id) && !excluded.has(p.id))
      .map((p) => p.id)
    children.forEach((id) => excluded.add(id))
    frontier = children
  }
  return allPartsForSelect.value
    .filter((p) => !excluded.has(p.id))
    .map((p) => ({ label: `${p.id} ${p.name}`, value: p.id }))
})

const openCreate = () => {
  editingId.value = null
  editingIsVariant.value = false
  existingVariantColors.value = []
  Object.assign(form, { name: '', image: '', category: null, color: '', unit: '个', unit_cost: null, plating_process: '', parent_part_id: null })
  showModal.value = true
}

const openImportModal = () => {
  importError.value = ''
  showImportModal.value = true
}

const closeImportModal = () => {
  showImportModal.value = false
  importError.value = ''
  importFile.value = null
  if (importFileInputRef.value) importFileInputRef.value.value = ''
}

const openEdit = async (row) => {
  const rowId = row.id
  editingId.value = rowId
  editingIsVariant.value = !!row.parent_part_id
  existingVariantColors.value = []
  const cat = row.category && VALID_CATEGORIES.includes(row.category) ? row.category : null
  Object.assign(form, {
    name: row.name,
    image: row.image || '',
    category: cat,
    color: row.color || '',
    unit: row.unit || '个',
    unit_cost: row.unit_cost ?? null,
    plating_process: row.plating_process || '',
    parent_part_id: row.parent_part_id || null,
  })
  showModal.value = true
  // Load existing variants (non-blocking, buttons disabled until done)
  // For variants, query via root parent; for root parts, query directly
  const variantQueryId = row.parent_part_id || rowId
  loadingVariants.value = true
  try {
    const { data: variants } = await getPartVariants(variantQueryId)
    if (editingId.value !== rowId) return
    existingVariantColors.value = variants
      .map((v) => COLOR_CODE_REVERSE[v.color])
      .filter(Boolean)
  } catch {
    // ignore — buttons will show all options as fallback
  } finally {
    if (editingId.value === rowId) loadingVariants.value = false
  }
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
      // Variant parts: backend rejects color/parent_part_id changes
      if (editingIsVariant.value) {
        delete updateData.color
        delete updateData.parent_part_id
      }
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

const triggerImportFileSelect = () => {
  importFileInputRef.value?.click()
}

const downloadTemplate = async () => {
  try {
    const { data } = await downloadPartsImportTemplate()
    const url = window.URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = 'parts-import-template.xlsx'
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch {
    message.error('模板下载失败')
  }
}

const handleImportFileChange = (event) => {
  const [file] = event.target.files || []
  event.target.value = ''
  importError.value = ''
  importFile.value = file || null
}

const doImport = async () => {
  if (!importFile.value) {
    message.warning('请先选择 Excel 文件')
    return
  }
  importing.value = true
  importError.value = ''
  try {
    const { data } = await importPartsExcel(importFile.value)
    message.success(`导入成功：新增 ${data.created_count} 条，更新 ${data.updated_count} 条，入库 ${data.stock_entry_count} 条`)
    closeImportModal()
    await load()
  } catch (error) {
    importError.value = error.response?.data?.detail || error.message || '导入失败'
  } finally {
    importing.value = false
  }
}

const confirmDelete = (row) => {
  dialog.warning({
    title: '确认删除',
    content: `确认删除 ${row.name}？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePart(row.id)
        message.success('已删除')
        await load()
      } catch (error) {
        message.error(error.response?.data?.detail || '删除失败')
      }
    },
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
  { title: '单件成本', key: 'unit_cost', width: 100, render: (r) => r.unit_cost != null ? fmtMoney(r.unit_cost) : '-' },
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

<style scoped>
.template-download-btn {
  background: #f6efe2;
  border-color: #d6b98d;
  color: #7a5321;
}

.template-download-btn:hover {
  background: #efe1c7;
  border-color: #c89b5a;
  color: #603d15;
}
</style>
