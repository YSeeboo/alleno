<template>
  <div class="parts-page">
    <!-- Page Header -->
    <div class="page-top">
      <div class="page-crumbs">商品 / 配件管理</div>
      <div class="title-row">
        <h1 class="page-title">
          配件管理<span class="title-count">共 {{ rows.length }} 个配件 · {{ displayRows.length }} 个根件</span>
        </h1>
        <div class="top-actions">
          <n-button class="btn-outline" @click="openImportModal">导入配件</n-button>
          <n-button class="btn-ink" @click="openCreate">新增配件</n-button>
        </div>
      </div>
    </div>

    <!-- Stat Strip -->
    <div class="stat-strip">
      <div class="stat-card">
        <div class="stat-label">配件总数</div>
        <div class="stat-value mono">{{ rows.length }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">组合件</div>
        <div class="stat-value mono">{{ compositeCount }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">低库存预警</div>
        <div class="stat-value mono" :class="{ 'stat-danger': lowStockCount > 0 }">{{ lowStockCount }}</div>
      </div>
    </div>

    <!-- Filter Row -->
    <div class="filter-row">
      <div class="chip-group">
        <button
          v-for="chip in categoryChips"
          :key="chip.value ?? '__all__'"
          class="chip"
          :class="{ 'chip-active': searchCategory === chip.value }"
          @click="selectCategory(chip.value)"
        >
          {{ chip.label }}
        </button>
      </div>
      <div class="search-wrap">
        <n-input
          v-model:value="searchName"
          placeholder="搜索配件名称 / 编号"
          clearable
          :style="{ width: isMobile ? '100%' : '240px' }"
          @update:value="debouncedLoad"
        />
      </div>
    </div>

    <!-- Table -->
    <n-spin :show="loading">
      <div class="table-wrap" v-if="tableData.length > 0 || loading">
        <n-data-table :columns="columns" :data="tableData" :bordered="false" :row-key="(r) => r.id" />
      </div>
      <n-empty v-else-if="!loading" description="暂无数据" style="margin: 40px 0;" />
    </n-spin>

    <!-- Create / Edit Modal -->
    <n-modal v-model:show="showModal" preset="card" :title="editingId ? '编辑配件' : '新增配件'" :style="{ width: isMobile ? '95vw' : '540px' }">
      <form @submit.prevent="save">
      <n-form ref="formRef" :model="form" label-placement="top">

        <!-- 基本信息 -->
        <div class="modal-sec-h">基本信息</div>
        <div class="modal-grid2">
          <!-- 名称 — full width -->
          <div class="modal-full">
            <n-form-item label="名称" path="name" :rule="{ required: true, message: '请输入名称' }">
              <n-input v-model:value="form.name" />
            </n-form-item>
          </div>

          <!-- 类目 pill selector — full width -->
          <div class="modal-full">
            <n-form-item
              label="类目"
              path="category"
              :rule="editingId ? undefined : { required: true, message: '请选择类目', trigger: 'change' }"
            >
              <div class="modal-pills" :class="{ 'modal-pills-disabled': !!editingId }">
                <button
                  v-for="opt in categoryOptions"
                  :key="opt.value"
                  type="button"
                  class="modal-pill"
                  :class="{ 'modal-pill-on': form.category === opt.value }"
                  :disabled="!!editingId"
                  @click="!editingId && (form.category = opt.value)"
                >{{ opt.label }}</button>
              </div>
              <span v-if="!!editingId" class="modal-note">类目不可修改</span>
            </n-form-item>
          </div>

          <!-- 颜色 | 单位 — half width each -->
          <n-form-item label="颜色">
            <n-input v-model:value="form.color" :disabled="editingIsVariant" />
            <span v-if="editingIsVariant" class="modal-note">变体不可修改</span>
          </n-form-item>
          <n-form-item label="单位">
            <n-select v-model:value="form.unit" :options="unitOptions" placeholder="请选择单位" />
          </n-form-item>

          <!-- 规格 | 单件成本 — half width each -->
          <n-form-item label="规格">
            <n-input v-model:value="form.spec" placeholder="如 45cm" />
          </n-form-item>
          <n-form-item label="单件成本">
            <n-input-number v-model:value="form.unit_cost" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width: 100%;" />
          </n-form-item>
        </div>

        <!-- 图片 -->
        <div class="modal-sec-h">图片</div>
        <n-form-item label="">
          <div class="modal-img-row">
            <n-image
              v-if="form.image"
              :src="form.image"
              alt="配件图片"
              :width="48"
              :height="48"
              object-fit="cover"
              class="modal-img-preview"
            />
            <div v-else class="modal-img-placeholder"></div>
            <n-input v-model:value="form.image" placeholder="上传后自动填充，也可手动粘贴 URL" style="flex: 1;" />
            <n-button @click="openImageModal(editingId)" class="modal-upload-btn">上传图片</n-button>
          </div>
        </n-form-item>

        <!-- 关联 -->
        <div class="modal-sec-h">关联</div>
        <n-form-item label="关联原色配件">
          <n-select
            v-model:value="form.parent_part_id"
            :options="parentPartOptions"
            filterable
            clearable
            placeholder="选填，选择原色配件（变体归并用）"
            :disabled="editingIsVariant"
          />
          <span v-if="editingIsVariant" class="modal-note">变体不可修改</span>
        </n-form-item>

        <!-- 手工加量规则 collapse -->
        <n-collapse class="modal-collapse">
          <n-collapse-item name="buffer-rules">
            <template #header>
              <span class="modal-collapse-title">手工加量规则</span>
              <span class="modal-collapse-preview">{{ effectiveRulePreview }}</span>
            </template>
            <template #header-extra>
              <n-tag :type="bufferIsCustom ? 'warning' : 'success'" size="small" round>
                {{ bufferIsCustom ? '自定义' : '默认 · 按类目' }}
              </n-tag>
            </template>
            <n-form-item label="配件大小">
              <n-select
                v-model:value="form.size_tier"
                :options="sizeTierOptions"
                placeholder="未选择则按类目自动"
                clearable
                style="width: 160px;"
              />
              <span class="modal-note">决定加量规则的默认值</span>
            </n-form-item>
            <n-form-item label="自定义比例">
              <n-input-number
                v-model:value="form.buffer_ratio_override"
                :min="0" :max="0.9999" :step="0.005" :precision="4"
                placeholder="留空使用默认"
                clearable
                style="width: 100%;"
              />
              <span class="modal-note">小数，如 0.025 = 2.5%</span>
            </n-form-item>
            <n-form-item label="自定义最低">
              <n-input-number
                v-model:value="form.buffer_floor_override"
                :min="0" :precision="0"
                placeholder="留空使用默认"
                clearable
                style="width: 100%;"
              />
              <span class="modal-note">最少要发的件数</span>
            </n-form-item>
          </n-collapse-item>
        </n-collapse>

        <!-- 变体（编辑时显示，组合件不显示） -->
        <template v-if="editingId && !editingIsComposite">
          <div class="modal-sec-h" style="margin-top: 18px;">变体</div>
          <n-form-item label="创建颜色变体">
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
          <n-form-item label="创建规格变体">
            <n-space align="center">
              <n-select
                v-model:value="specVariantColor"
                :options="specVariantColorOptions"
                clearable
                placeholder="颜色（可选）"
                style="width: 120px;"
              />
              <n-input v-model:value="specVariantInput" placeholder="规格，如 45cm" style="width: 140px;" />
              <n-button
                size="small"
                type="primary"
                secondary
                :disabled="!specVariantInput || creatingVariant || loadingVariants"
                @click="doCreateSpecVariant"
              >
                创建
              </n-button>
            </n-space>
          </n-form-item>
        </template>

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
    <n-modal v-model:show="showStockModal" preset="card" title="快速入库" :style="{ width: isMobile ? '95vw' : '360px' }">
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

    <n-modal v-model:show="showImportModal" preset="card" title="导入配件" :style="{ width: isMobile ? '95vw' : '560px' }">
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

    <BatchImageUpload
      v-model:show="showBatchImageUpload"
      :parts="batchImageParts"
      :batch-id="batchImageBatchId"
      triggered-by="import"
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
import { ref, reactive, computed, onMounted, watch, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NEmpty, NDropdown, NImage,
  NCollapse, NCollapseItem, NTag,
} from 'naive-ui'
import { listParts, createPart, updatePart, deletePart, importPartsExcel, downloadPartsImportTemplate, getPartVariants, createPartVariant } from '@/api/parts'
import { batchGetStock, addStock } from '@/api/inventory'
import { renderNamedImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import ImageUploadModal from '../../components/ImageUploadModal.vue'
import BatchImageUpload from '@/components/BatchImageUpload.vue'
import { pushBatch } from '@/utils/recentImports'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const { isMobile } = useIsMobile()
const authStore = useAuthStore()

const loading = ref(true)
const rows = ref([])
const searchName = ref('')
const searchCategory = ref(null)

const categoryOptions = [
  { label: '吊坠', value: '吊坠' },
  { label: '链条', value: '链条' },
  { label: '小配件', value: '小配件' },
]

const categoryChips = [
  { label: '全部', value: null },
  { label: '吊坠', value: '吊坠' },
  { label: '链条', value: '链条' },
  { label: '小配件', value: '小配件' },
]

const selectCategory = (value) => {
  searchCategory.value = value
  load()
}

// Stat strip — computed from loaded row data only
const compositeCount = computed(() => rows.value.filter((r) => r.is_composite).length)
const lowStockCount = computed(() => rows.value.filter((r) => r.stock < 10).length)

// Grouping tree: root parts (parent_part_id == null) with their variant children
const expanded = ref(new Set())
function toggleGroup(rootId) {
  const s = new Set(expanded.value)
  s.has(rootId) ? s.delete(rootId) : s.add(rootId)
  expanded.value = s
}
const displayRows = computed(() => {
  const variantsByRoot = new Map()
  const roots = []
  for (const r of rows.value) {
    if (r.parent_part_id) {
      if (!variantsByRoot.has(r.parent_part_id)) variantsByRoot.set(r.parent_part_id, [])
      variantsByRoot.get(r.parent_part_id).push(r)
    } else roots.push(r)
  }
  return roots.map((root) => {
    const children = (variantsByRoot.get(root.id) || []).slice().sort((a, b) => a.id.localeCompare(b.id))
    return { ...root, _children: children }
  })
})
const tableData = computed(() => {
  const out = []
  for (const r of displayRows.value) {
    out.push(r)
    if (expanded.value.has(r.id)) for (const c of r._children) out.push({ ...c, _isChild: true })
  }
  return out
})

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
const specVariantInput = ref('')
const specVariantColor = ref(null)

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
    const { data: variants } = await getPartVariants(editingId.value)
    existingVariantColors.value = variants
      .filter((v) => !v.spec)
      .map((v) => COLOR_CODE_REVERSE[v.color])
      .filter(Boolean)
    await load()
  } catch (error) {
    message.error(error.response?.data?.detail || '创建变体失败')
  } finally {
    creatingVariant.value = false
  }
}

const specVariantColorOptions = VARIANT_COLORS.map((vc) => ({ label: vc.label, value: vc.code }))

const doCreateSpecVariant = async () => {
  if (!specVariantInput.value) return
  creatingVariant.value = true
  const body = { spec: specVariantInput.value }
  if (specVariantColor.value) body.color_code = specVariantColor.value
  try {
    await createPartVariant(editingId.value, body)
    message.success(`规格变体 ${specVariantInput.value} 创建成功`)
    specVariantInput.value = ''
    specVariantColor.value = null
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
const editingIsComposite = ref(false)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({ name: '', image: '', category: null, color: '', spec: '', unit: '个', unit_cost: null, plating_process: '', parent_part_id: null, size_tier: null, buffer_ratio_override: null, buffer_floor_override: null })

const sizeTierOptions = [
  { label: '小件', value: 'small' },
  { label: '中件', value: 'medium' },
]

// Mirror backend services/handcraft.py::HANDCRAFT_BUFFER_RULES.
const TIER_DEFAULTS = {
  small:  { ratio: 0.02, floor: 50 },
  medium: { ratio: 0.01, floor: 15 },
}

const effectiveTier = computed(() => {
  if (form.size_tier) return form.size_tier
  // Mirror backend default: 小配件 → small, 吊坠/链条 → medium
  if (form.category === '小配件') return 'small'
  if (form.category === '吊坠' || form.category === '链条') return 'medium'
  return null
})

const bufferIsCustom = computed(() =>
  form.buffer_ratio_override != null || form.buffer_floor_override != null
)

const effectiveRulePreview = computed(() => {
  const tier = effectiveTier.value
  if (!tier) return '（请先选类目）'
  const def = TIER_DEFAULTS[tier]
  const ratio = form.buffer_ratio_override != null ? form.buffer_ratio_override : def.ratio
  const floor = form.buffer_floor_override != null ? form.buffer_floor_override : def.floor
  const ratioPct = (ratio * 100).toFixed(2).replace(/\.?0+$/, '')
  const tierLabel = tier === 'small' ? '小件' : '中件'
  return `${tierLabel}：max(${floor}, 数量 × ${ratioPct}%)`
})

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
const showBatchImageUpload = ref(false)
const batchImageParts = ref([])
const batchImageBatchId = ref(null)
watch(showBatchImageUpload, (val) => {
  if (!val) load()
})

const loadAllPartsForSelect = async () => {
  const { data } = await listParts()
  allPartsForSelect.value = data
}

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (searchName.value) params.name = searchName.value
    if (searchCategory.value) params.category = searchCategory.value
    const { data: parts } = await listParts(params)
    if (parts.length > 0) {
      const { data: stockMap } = await batchGetStock('part', parts.map((p) => p.id))
      rows.value = parts.map((p) => ({ ...p, stock: stockMap[p.id] ?? 0 }))
    } else {
      rows.value = []
    }
  } finally {
    loading.value = false
  }
}

let _searchTimer = null
const debouncedLoad = () => {
  clearTimeout(_searchTimer)
  _searchTimer = setTimeout(load, 300)
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
  editingIsComposite.value = false
  existingVariantColors.value = []
  specVariantInput.value = ''
  specVariantColor.value = null
  Object.assign(form, { name: '', image: '', category: null, color: '', spec: '', unit: '个', unit_cost: null, plating_process: '', parent_part_id: null, size_tier: null, buffer_ratio_override: null, buffer_floor_override: null })
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
  editingIsComposite.value = !!row.is_composite
  existingVariantColors.value = []
  specVariantInput.value = ''
  specVariantColor.value = null
  const cat = row.category && VALID_CATEGORIES.includes(row.category) ? row.category : null
  Object.assign(form, {
    name: row.name,
    image: row.image || '',
    category: cat,
    color: row.color || '',
    spec: row.spec || '',
    unit: row.unit || '个',
    unit_cost: row.unit_cost ?? null,
    plating_process: row.plating_process || '',
    parent_part_id: row.parent_part_id || null,
    size_tier: row.size_tier || null,
    buffer_ratio_override: row.buffer_ratio_override ?? null,
    buffer_floor_override: row.buffer_floor_override ?? null,
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
      .filter((v) => !v.spec)
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
    loadAllPartsForSelect()
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

    // Persist the import as a "batch" — feeds both the post-import
    // image-upload step and the downstream handcraft attach flows
    // (HandcraftDetail "最近导入" tab + BatchImageUpload submodal).
    const allImported = (data.results || []).map((r) => ({
      part_id: r.part_id,
      name: r.name,
      image: r.image,
      unit: r.unit || '个',
      imported_qty: r.stock_added,
    }))
    const batch = allImported.length > 0
      ? pushBatch(allImported, { operator: authStore.user?.username || '' })
      : null

    const partsWithoutImage = (data.results || []).filter((r) => !r.image)
    if (partsWithoutImage.length > 0) {
      const doUpload = await new Promise((resolve) => {
        dialog.info({
          title: '上传图片',
          content: `有 ${partsWithoutImage.length} 个配件没有图片，是否现在上传？`,
          positiveText: '是',
          negativeText: '否',
          onPositiveClick: () => resolve(true),
          onNegativeClick: () => resolve(false),
          onClose: () => resolve(false),
        })
      })
      if (doUpload) {
        batchImageParts.value = partsWithoutImage
        batchImageBatchId.value = batch?.batch_id ?? null
        showBatchImageUpload.value = true
      }
    }
    closeImportModal()
    loadAllPartsForSelect()
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
        loadAllPartsForSelect()
        await load()
      } catch (error) {
        message.error(error.response?.data?.detail || '删除失败')
      }
    },
  })
}

// Color dot map for known color names
const COLOR_DOT_MAP = {
  '金色': '#d9b24a',
  '白K': '#a9b0b8',
  '玫瑰金': '#cf8f7d',
  '古银': '#8a9a8e',
  '银色': '#a9b0b8',
}

const columns = [
  {
    title: '编号',
    key: 'id',
    width: 150,
    render: (row) => {
      const hasKids = !row._isChild && row._children && row._children.length
      const caret = hasKids
        ? h('span', { class: 'pt-caret', style: expanded.value.has(row.id) ? 'transform:rotate(90deg)' : '',
            onClick: (e) => { e.stopPropagation(); toggleGroup(row.id) } }, '▸')
        : h('span', { class: 'pt-caret pt-caret-spacer' }, '▸')
      return h('span', { class: 'cell-id mono' }, [caret, ' ', row.id])
    },
  },
  {
    title: '配件',
    key: 'name',
    minWidth: 200,
    render: (row) => {
      const children = [
        renderNamedImage(row.name, row.image, row.name, 36),
      ]
      if (row.is_composite) {
        children.push(h('span', { class: 'tag-combo' }, '组合'))
      }
      if (!row._isChild && row._children && row._children.length) {
        children.push(h('span', { class: 'count-pill' }, `变体×${row._children.length}`))
      }
      return h('div', { class: row._isChild ? 'cell-name-wrap pt-indent' : 'cell-name-wrap' }, children)
    },
  },
  { title: '类目', key: 'category' },
  {
    title: '颜色',
    key: 'color',
    render: (row) => {
      if (!row.color) return '-'
      const dotColor = COLOR_DOT_MAP[row.color] || '#c0c6cd'
      return h('span', { class: 'cell-color' }, [
        h('span', {
          class: 'color-dot',
          style: { background: dotColor },
        }),
        row.color,
      ])
    },
  },
  { title: '规格', key: 'spec' },
  { title: '单位', key: 'unit', width: 60 },
  {
    title: '单件成本',
    key: 'unit_cost',
    width: 110,
    titleAlign: 'right',
    align: 'right',
    render: (r) => r.unit_cost != null
      ? h('span', { class: 'mono' }, [
          h('small', { class: 'currency-sym' }, '¥'),
          ' ',
          fmtMoney(r.unit_cost),
        ])
      : h('span', { style: { color: '#8B9096' } }, '-'),
  },
  {
    title: '当前库存',
    key: 'stock',
    width: 100,
    titleAlign: 'right',
    align: 'right',
    render: (r) => {
      if (r.stock < 10) {
        return h('span', { class: 'stock-low mono' }, [
          String(r.stock),
          h('span', { class: 'pill-low' }, '低'),
        ])
      }
      return h('span', { class: 'stock-ok mono' }, String(r.stock))
    },
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

onMounted(() => {
  loadAllPartsForSelect()
  load()
})
</script>

<style scoped>
/* ── Page shell ── */
.parts-page {
  padding: 0;
}

/* ── Header ── */
.page-top {
  padding: 24px 28px 0;
}

.page-crumbs {
  font-size: 12px;
  color: #8B9096;
  margin-bottom: 10px;
  letter-spacing: 0.1px;
}

.title-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.4px;
  margin: 0;
  color: #1A1D21;
  line-height: 1.2;
}

.title-count {
  font-size: 14px;
  font-weight: 500;
  color: #8B9096;
  margin-left: 10px;
}

.top-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}

/* Override Naive UI button styles for the ink/outline variants */
.btn-outline {
  height: 36px !important;
  border-radius: 9px !important;
  border: 1px solid #ECEDEF !important;
  background: #fff !important;
  color: #1A1D21 !important;
  font-size: 13.5px !important;
  font-weight: 500 !important;
}

.btn-ink {
  height: 36px !important;
  border-radius: 9px !important;
  background: #1A1D21 !important;
  border-color: #1A1D21 !important;
  color: #fff !important;
  font-size: 13.5px !important;
  font-weight: 500 !important;
}

/* ── Stat strip ── */
.stat-strip {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  border: 1px solid #ECEDEF;
  border-radius: 10px;
  margin: 20px 28px 0;
  background: #fff;
  overflow: hidden;
}

.stat-card {
  padding: 14px 20px;
  border-right: 1px solid #ECEDEF;
}

.stat-card:last-child {
  border-right: 0;
}

.stat-label {
  font-size: 10.5px;
  letter-spacing: 0.7px;
  text-transform: uppercase;
  color: #8B9096;
  font-weight: 600;
}

.stat-value {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.5px;
  margin-top: 5px;
  line-height: 1;
  color: #1A1D21;
}

.stat-danger {
  color: #E5484D;
}

/* ── Filter row ── */
.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 28px 14px;
  flex-wrap: wrap;
}

.chip-group {
  display: flex;
  gap: 7px;
  flex-wrap: wrap;
}

.chip {
  height: 32px;
  border-radius: 16px;
  border: 1px solid #ECEDEF;
  background: #fff;
  padding: 0 14px;
  font-size: 13px;
  color: #4b5158;
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
  white-space: nowrap;
}

.chip:hover {
  border-color: #c8cdd4;
}

.chip-active {
  background: #1A1D21;
  border-color: #1A1D21;
  color: #fff;
  font-weight: 500;
}

.search-wrap {
  margin-left: auto;
}

/* ── Table wrap ── */
.table-wrap {
  margin: 0 28px 28px;
  border: 1px solid #ECEDEF;
  border-radius: 10px;
  overflow: hidden;
}

/* ── Table cell styles ── */
.cell-id {
  font-size: 12.5px;
  color: #6b7280;
  font-variant-numeric: tabular-nums;
}

.cell-name-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag-combo {
  font-size: 10.5px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 5px;
  background: #E6F2EC;
  color: #1E7A5A;
  letter-spacing: 0.2px;
  white-space: nowrap;
}

.cell-color {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.color-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.08);
}

.mono {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}

.currency-sym {
  color: #8B9096;
  font-size: 11px;
}

.stock-ok {
  font-weight: 600;
  color: #1A1D21;
}

.stock-low {
  font-weight: 700;
  color: #E5484D;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.pill-low {
  font-size: 10px;
  background: #fdecec;
  color: #E5484D;
  border-radius: 5px;
  padding: 1px 6px;
  font-weight: 600;
}

/* ── Template download button ── */
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

/* ── Create/Edit modal layout ── */

/* Eyebrow section headers */
.modal-sec-h {
  font-size: 11px;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: #8B9096;
  font-weight: 600;
  margin: 0 0 10px;
}

/* 2-column grid for short fields */
.modal-grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 14px;
}

.modal-full {
  grid-column: 1 / -1;
}

/* Category pill selector */
.modal-pills {
  display: flex;
  gap: 8px;
  width: 100%;
}

.modal-pill {
  height: 36px;
  flex: 1;
  border: 1px solid #DFE2E6;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #4b5158;
  cursor: pointer;
  background: #fff;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}

.modal-pill:hover:not(:disabled) {
  border-color: #c8cdd4;
}

.modal-pill.modal-pill-on {
  background: #1A1D21;
  border-color: #1A1D21;
  color: #fff;
  font-weight: 500;
}

.modal-pills-disabled .modal-pill {
  cursor: default;
  opacity: 0.65;
}

/* Inline note/hint text */
.modal-note {
  color: #8B9096;
  font-size: 12px;
  margin-left: 8px;
  white-space: nowrap;
}

/* Image inline row */
.modal-img-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.modal-img-preview {
  width: 48px;
  height: 48px;
  border-radius: 9px;
  flex-shrink: 0;
  overflow: hidden;
  border: 1px solid #ECEDEF;
  display: block;
}

.modal-img-placeholder {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  border-radius: 9px;
  background: linear-gradient(135deg, #f2cdbf, #cf8f7d);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.05);
}

.modal-upload-btn {
  white-space: nowrap;
  flex-shrink: 0;
}

/* Collapse for buffer rules */
.modal-collapse {
  margin: 4px 0 14px;
  border: 1px solid #ECEDEF;
  border-radius: 11px;
  overflow: hidden;
}

.modal-collapse-title {
  font-size: 13.5px;
  font-weight: 600;
  margin-right: 12px;
}

.modal-collapse-preview {
  font-size: 12px;
  color: #8B9096;
  font-variant-numeric: tabular-nums;
}

/* ── Variant grouping tree ── */
.pt-caret {
  display: inline-flex;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  cursor: pointer;
  color: #6b7280;
  font-size: 10px;
  align-items: center;
  justify-content: center;
  transition: transform .12s;
}
.pt-caret-spacer {
  visibility: hidden;
  cursor: default;
}
.count-pill {
  font-size: 10.5px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 5px;
  background: #EEF1F4;
  color: #475569;
  margin-left: 6px;
}
.pt-indent {
  padding-left: 26px;
}
</style>
