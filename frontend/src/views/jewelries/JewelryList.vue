<template>
  <div class="jewelries-page">
    <!-- Page Header -->
    <div class="page-top">
      <div class="page-crumbs">商品 / 饰品管理</div>
      <div class="title-row">
        <h1 class="page-title">饰品管理<span class="title-count">共 {{ rows.length }} 件饰品 · {{ groupCount }} 个款式组</span></h1>
        <div class="top-actions">
          <n-button v-if="canUseTemplates" class="btn-outline" @click="openTemplateSelect">从模板创建</n-button>
          <n-button class="btn-ink" @click="openCreate">新增饰品</n-button>
        </div>
      </div>
    </div>

    <!-- Stat Strip -->
    <div class="stat-strip">
      <div class="stat-card"><div class="stat-label">饰品总数</div><div class="stat-value mono">{{ rows.length }}</div></div>
      <div class="stat-card"><div class="stat-label">低库存预警</div><div class="stat-value mono" :class="{ 'stat-danger': lowStockCount > 0 }">{{ lowStockCount }}</div></div>
      <div class="stat-card"><div class="stat-label">已停用</div><div class="stat-value mono">{{ inactiveCount }}</div></div>
    </div>

    <!-- Filter Row -->
    <div class="filter-row">
      <div class="chip-group">
        <button v-for="chip in categoryChips" :key="chip.value ?? '__all__'" class="chip"
          :class="{ 'chip-active': filterCategory === chip.value }" @click="selectCategory(chip.value)">{{ chip.label }}</button>
      </div>
      <div class="search-wrap">
        <n-input v-model:value="searchName" placeholder="搜索饰品名称" clearable :style="{ width: isMobile ? '100%' : '240px' }" @update:value="debouncedLoad" />
      </div>
      <n-select
        v-model:value="filterStatus"
        :options="statusOptions"
        clearable
        placeholder="筛选状态"
        :style="{ width: isMobile ? '100%' : '130px' }"
        @update:value="load"
      />
    </div>

    <!-- Table -->
    <n-spin :show="loading">
      <div class="table-wrap" v-if="tableData.length > 0 || loading">
        <n-data-table :columns="columns" :data="tableData" :bordered="false" :row-key="(r) => r.id" />
      </div>
      <n-empty v-else-if="!loading" description="暂无数据" style="margin: 40px 0;" />
    </n-spin>

    <!-- Create / Edit Modal -->
    <n-modal v-model:show="showModal" preset="card" :title="modalTitle" :style="{ width: isMobile ? '95vw' : '480px' }">
      <form @submit.prevent="save">
      <n-alert
        v-if="copySourceId"
        type="warning"
        style="margin-bottom: 12px;"
      >
        从 <b>{{ copySourceId }} {{ copySourceName }}</b> 复制（含 BOM 配件清单）。类目沿用源饰品。
      </n-alert>
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
        <n-form-item
          label="类目"
          path="category"
          :rule="(editingId || copySourceId) ? undefined : { required: true, message: '请选择类目', trigger: 'change' }"
        >
          <n-select v-model:value="form.category" :options="categoryOptions" clearable placeholder="请选择类目" :disabled="!!editingId || !!copySourceId" />
          <span v-if="editingId" style="color: #999; font-size: 12px; margin-left: 8px;">类目不可修改</span>
          <span v-else-if="copySourceId" style="color: #999; font-size: 12px; margin-left: 8px;">复制时不可修改</span>
        </n-form-item>
        <n-form-item label="颜色"><n-input v-model:value="form.color" /></n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="form.unit" :options="unitOptions" placeholder="请选择单位" />
        </n-form-item>
        <n-form-item label="零售价">
          <n-input-number v-model:value="form.retail_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="批发价">
          <n-input-number v-model:value="form.wholesale_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width: 100%;" />
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

    <!-- Add Sibling Modal -->
    <n-modal v-model:show="showSiblingModal" preset="card" :style="{ width: isMobile ? '95vw' : '480px' }">
      <template #header>添加同款 · 将生成 {{ siblingBase?.style_group || siblingBase?.id }}-新后缀</template>
      <n-form label-placement="left" label-width="100">
        <n-alert type="warning" style="margin-bottom:12px;">归属款式组 <b>{{ siblingBase?.id }} {{ siblingBase?.name }}</b>，已预填并带入基准 BOM。类目沿用基准不可改。</n-alert>
        <n-form-item label="名称"><n-input v-model:value="siblingForm.name" /></n-form-item>
        <n-form-item label="图片">
          <n-space vertical style="width:100%;">
            <n-space align="center" style="width:100%;">
              <n-input v-model:value="siblingForm.image" placeholder="上传后自动填充，也可手动输入 URL" />
              <n-button @click="openImageModal(null)">上传图片</n-button>
            </n-space>
            <n-image v-if="siblingForm.image" :src="siblingForm.image" :width="72" :height="72" object-fit="cover" style="border-radius:12px;" />
          </n-space>
        </n-form-item>
        <n-form-item label="颜色"><n-input v-model:value="siblingForm.color" /></n-form-item>
        <n-form-item label="单位"><n-select v-model:value="siblingForm.unit" :options="unitOptions" /></n-form-item>
        <n-form-item label="零售价"><n-input-number v-model:value="siblingForm.retail_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width:100%;" /></n-form-item>
        <n-form-item label="批发价"><n-input-number v-model:value="siblingForm.wholesale_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" style="width:100%;" /></n-form-item>
      </n-form>
      <template #footer><n-space justify="end"><n-button @click="showSiblingModal = false">取消</n-button><n-button type="primary" :loading="siblingSaving" @click="saveSibling">创建同款</n-button></n-space></template>
    </n-modal>

    <ImageUploadModal
      v-model:show="showImageModal"
      kind="jewelry"
      :entity-id="currentUploadItemId"
      @uploaded="onImageUploaded"
    />

    <!-- Template selection modal for "从模板创建" -->
    <n-modal v-model:show="showTemplateSelectModal" preset="card" title="从模板创建饰品" :style="{ width: isMobile ? '95vw' : '520px' }">
      <n-spin :show="loadingTemplateList">
        <n-empty v-if="!loadingTemplateList && templateList.length === 0" description="暂无模板" />
        <div v-for="tpl in templateList" :key="tpl.id" style="display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f0f0f0;">
          <div>
            <div style="font-weight: 600;">{{ tpl.name }}</div>
            <div style="color: #999; font-size: 12px;">{{ tpl.item_count || 0 }} 个配件</div>
          </div>
          <n-button size="small" type="primary" @click="selectTemplate(tpl)">选择</n-button>
        </div>
      </n-spin>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NEmpty, NImage, NDropdown, NAlert, NTooltip,
} from 'naive-ui'
import { listJewelries, createJewelry, updateJewelry, updateJewelryStatus, deleteJewelry, copyJewelry, addJewelrySibling } from '@/api/jewelries'
import { batchGetStock } from '@/api/inventory'
import { listTemplates, applyTemplate } from '@/api/jewelryTemplates'
import { renderNamedImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import { useAuthStore } from '@/stores/auth'
import ImageUploadModal from '../../components/ImageUploadModal.vue'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const authStore = useAuthStore()
const { isMobile } = useIsMobile()
const canUseTemplates = computed(() => authStore.hasPermission('parts'))
const modalTitle = computed(() => {
  if (editingId.value) return '编辑饰品'
  if (copySourceId.value) return '复制饰品'
  return '新增饰品'
})
const loading = ref(true)
const rows = ref([])
const filterStatus = ref(null)
const searchName = ref('')
const filterCategory = ref(undefined) // undefined=全部, '__none__'=未分类

const statusOptions = [
  { label: '启用', value: 'active' },
  { label: '停用', value: 'inactive' },
]

const categoryOptions = [
  { label: '套装', value: '套装' },
  { label: '单件', value: '单件' },
  { label: '单对', value: '单对' },
]

const categoryChips = [
  { label: '全部', value: undefined },
  { label: '套装', value: '套装' },
  { label: '单件', value: '单件' },
  { label: '单对', value: '单对' },
  { label: '未分类', value: '__none__' },
]

const unitOptions = [
  { label: '个', value: '个' },
  { label: '套', value: '套' },
  { label: '对', value: '对' },
]

const VALID_CATEGORIES = categoryOptions.map((o) => o.value)

const LOW_STOCK = 10
const lowStockCount = computed(() => rows.value.filter((r) => (r.stock ?? 0) < LOW_STOCK).length)
const inactiveCount = computed(() => rows.value.filter((r) => r.status === 'inactive').length)

function selectCategory(v) { filterCategory.value = v; load() }

// 分组树：按 style_group 聚桶；表头=id===group 的那条，缺则取组内最小 id；
// style_group 为空的为独立单条。返回排好序的「显示行」：每个表头行带 _children 数组。
const displayRows = computed(() => {
  const groups = new Map()
  const singles = []
  for (const r of rows.value) {
    if (r.style_group) {
      if (!groups.has(r.style_group)) groups.set(r.style_group, [])
      groups.get(r.style_group).push(r)
    } else {
      singles.push(r)
    }
  }
  const out = []
  for (const [gid, members] of groups) {
    members.sort((a, b) => a.id.localeCompare(b.id))
    const header = members.find((m) => m.id === gid) || members[0]
    const children = members.filter((m) => m.id !== header.id)
    out.push({ ...header, _isHeader: true, _group: gid, _children: children })
  }
  for (const s of singles) out.push({ ...s, _isHeader: false, _group: null, _children: [] })
  out.sort((a, b) => a.id.localeCompare(b.id))
  return out
})
const groupCount = computed(() => displayRows.value.filter((r) => r._children.length > 0).length)

const expanded = ref(new Set())
function toggleGroup(gid) {
  const s = new Set(expanded.value)
  s.has(gid) ? s.delete(gid) : s.add(gid)
  expanded.value = s
}

const tableData = computed(() => {
  const out = []
  for (const r of displayRows.value) {
    out.push(r)
    if (r._isHeader && expanded.value.has(r._group)) {
      for (const c of r._children) out.push({ ...c, _isChild: true })
    }
  }
  return out
})

// Inline editing for price cells
const inlineEditing = ref({}) // key: `${row.id}_${field}`
const inlineSaving = ref({})
const inlineKey = (rowId, field) => `${rowId}_${field}`

const startInline = (row, field) => {
  inlineEditing.value[inlineKey(row.id, field)] = row[field] ?? null
}

const cancelInline = (rowId, field) => {
  delete inlineEditing.value[inlineKey(rowId, field)]
}

const saveInline = async (row, field, value) => {
  const key = inlineKey(row.id, field)
  if (inlineSaving.value[key]) return
  const oldValue = row[field] ?? null
  if (value === oldValue) { cancelInline(row.id, field); return }
  inlineSaving.value[key] = true
  try {
    await updateJewelry(row.id, { [field]: value })
    row[field] = value
    message.success('已保存')
  } catch (e) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    delete inlineSaving.value[key]
    cancelInline(row.id, field)
  }
}

const renderInlinePrice = (row, field) => {
  const key = inlineKey(row.id, field)
  const isEditing = key in inlineEditing.value
  if (isEditing) {
    return h(NInputNumber, {
      value: inlineEditing.value[key],
      min: 0,
      precision: 7,
      format: fmtPrice,
      parse: parseNum,
      size: 'small',
      style: 'width: 120px;',
      autofocus: true,
      'onUpdate:value': (v) => { inlineEditing.value[key] = v },
      onBlur: () => { if (key in inlineEditing.value) saveInline(row, field, inlineEditing.value[key]) },
      onKeydown: (e) => {
        if (e.key === 'Enter') saveInline(row, field, inlineEditing.value[key])
        if (e.key === 'Escape') { e.preventDefault(); cancelInline(row.id, field) }
      },
    })
  }
  return h('span', {
    class: 'editable-cell',
    onClick: () => startInline(row, field),
  }, row[field] != null ? fmtMoney(row[field]) : '-')
}

const showModal = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formRef = ref(null)
const form = reactive({ name: '', image: '', category: null, color: '', unit: null, retail_price: null, wholesale_price: null })

// Add-sibling modal state
const showSiblingModal = ref(false)
const siblingSaving = ref(false)
const siblingBase = ref(null)
const siblingForm = reactive({ name: '', image: '', color: '', unit: null, retail_price: null, wholesale_price: null })

// Image upload modal state
const showImageModal = ref(false)
const currentUploadItemId = ref(null)

// Template selection state
const showTemplateSelectModal = ref(false)
const loadingTemplateList = ref(false)
const templateList = ref([])
const selectedTemplate = ref(null)
const copySourceId = ref(null)
const copySourceName = ref('')

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
    if (searchName.value) params.name = searchName.value
    if (filterStatus.value) params.status = filterStatus.value
    if (filterCategory.value && filterCategory.value !== '__none__') params.category = filterCategory.value
    const { data: jewelries } = await listJewelries(params)
    const stockMap = jewelries.length
      ? (await batchGetStock('jewelry', jewelries.map((j) => j.id))).data : {}
    let mapped = jewelries.map((j) => ({ ...j, stock: stockMap[j.id] ?? 0 }))
    if (filterCategory.value === '__none__') mapped = mapped.filter((j) => !j.category)
    rows.value = mapped
  } finally { loading.value = false }
}

let _searchTimer = null
const debouncedLoad = () => {
  clearTimeout(_searchTimer)
  _searchTimer = setTimeout(load, 300)
}

const openTemplateSelect = async () => {
  showTemplateSelectModal.value = true
  loadingTemplateList.value = true
  try {
    const { data } = await listTemplates()
    templateList.value = data
  } finally {
    loadingTemplateList.value = false
  }
}

const selectTemplate = (tpl) => {
  selectedTemplate.value = tpl
  copySourceId.value = null
  showTemplateSelectModal.value = false
  editingId.value = null
  Object.assign(form, { name: '', image: tpl.image || '', category: null, color: '', unit: null, retail_price: null, wholesale_price: null })
  showModal.value = true
}

const openCreate = () => {
  editingId.value = null
  selectedTemplate.value = null
  copySourceId.value = null
  Object.assign(form, { name: '', image: '', category: null, color: '', unit: null, retail_price: null, wholesale_price: null })
  showModal.value = true
}

const openEdit = (row) => {
  copySourceId.value = null
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

const openCopy = (row) => {
  editingId.value = null
  selectedTemplate.value = null
  copySourceId.value = row.id
  copySourceName.value = row.name
  const cat = row.category && VALID_CATEGORIES.includes(row.category) ? row.category : null
  Object.assign(form, {
    name: `${row.name}-副本`,
    image: row.image || '',
    category: cat,
    color: row.color || '',
    unit: row.unit || null,
    retail_price: row.retail_price ?? null,
    wholesale_price: row.wholesale_price ?? null,
  })
  showModal.value = true
}

function openAddSibling(row) {
  siblingBase.value = row
  Object.assign(siblingForm, {
    name: row.name, image: row.image || '', color: row.color || '',
    unit: row.unit || null, retail_price: row.retail_price ?? null, wholesale_price: row.wholesale_price ?? null,
  })
  showSiblingModal.value = true
}

async function saveSibling() {
  siblingSaving.value = true
  try {
    const { data } = await addJewelrySibling(siblingBase.value.id, { ...siblingForm })
    message.success('已添加同款')
    showSiblingModal.value = false
    const gid = data.style_group
    if (gid) expanded.value = new Set([...expanded.value, gid])
    await load()
  } catch (e) {
    message.error(e.response?.data?.detail || '添加失败')
  } finally { siblingSaving.value = false }
}

const openImageModal = (id) => {
  currentUploadItemId.value = id
  showImageModal.value = true
}

const onImageUploaded = (url) => {
  if (showSiblingModal.value) {
    siblingForm.image = url
  } else {
    form.image = url
  }
  load()
}

const save = async () => {
  await formRef.value?.validate()
  saving.value = true
  try {
    if (editingId.value) {
      const { category, ...updateData } = form
      await updateJewelry(editingId.value, updateData)
      message.success('保存成功')
      showModal.value = false
      await load()
    } else if (copySourceId.value) {
      const { category, ...copyData } = form
      const { data: newJewelry } = await copyJewelry(copySourceId.value, copyData)
      message.success('复制成功')
      copySourceId.value = null
      copySourceName.value = ''
      showModal.value = false
      router.push(`/jewelries/${newJewelry.id}`)
    } else {
      const { data: newJewelry } = await createJewelry(form)
      if (selectedTemplate.value) {
        try {
          await applyTemplate(selectedTemplate.value.id, newJewelry.id)
          message.success('饰品已创建并导入模板 BOM')
        } catch (_) {
          message.success('饰品已创建，但模板导入失败')
        }
        selectedTemplate.value = null
        showModal.value = false
        router.push(`/jewelries/${newJewelry.id}`)
      } else {
        message.success('保存成功')
        showModal.value = false
        await load()
      }
    }
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
    await load()
  }
}

const doDelete = async (id) => {
  await deleteJewelry(id)
  message.success('已删除')
  await load()
}

const confirmDelete = (row) => {
  dialog.warning({
    title: '确认删除',
    content: `确认删除 ${row.name}？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: () => doDelete(row.id),
  })
}

const columns = [
  {
    title: '编号',
    key: 'id',
    width: 170,
    render: (row) => {
      const caret = row._isHeader && row._children.length
        ? h('span', { class: 'jw-caret', style: expanded.value.has(row._group) ? 'transform:rotate(90deg)' : '',
            onClick: (e) => { e.stopPropagation(); toggleGroup(row._group) } }, '▸')
        : h('span', { class: 'jw-caret jw-caret-spacer' }, '▸')
      return h('span', { class: 'cell-id' }, [caret, ' ', row.id])
    },
  },
  {
    title: '饰品',
    key: 'name',
    minWidth: 200,
    render: (row) => {
      const nodes = [renderNamedImage(row.name, row.image, row.name)]
      if (row._isHeader && row._children.length)
        nodes.push(h('span', { class: 'jw-count-pill' }, `同款×${row._children.length}`))
      return h('div', { class: row._isChild ? 'jw-name jw-indent' : 'jw-name' }, nodes)
    },
  },
  { title: '类目', key: 'category' },
  { title: '颜色', key: 'color' },
  { title: '单位', key: 'unit', width: 60 },
  { title: '零售价', key: 'retail_price', render: (r) => renderInlinePrice(r, 'retail_price') },
  { title: '批发价', key: 'wholesale_price', render: (r) => renderInlinePrice(r, 'wholesale_price') },
  {
    title: '总成本',
    key: 'total_cost',
    width: 120,
    render: (r) => {
      if (r.total_cost == null) return '-'
      const main = h('span', {}, fmtMoney(r.total_cost))
      const warn = r.has_incomplete_cost
        ? h('span', { style: 'color:#f0a020; margin-left:4px; cursor:help;' }, '⚠️')
        : null
      const breakdown = `物料 ${fmtMoney(r.material_cost ?? 0)} ＋ 手工费 ${fmtMoney(r.handcraft_cost ?? 0)}`
        + (r.has_incomplete_cost ? '（成本不完整）' : '')
      return h(NTooltip, { trigger: 'hover' }, {
        trigger: () => h('span', { style: 'cursor:help;' }, [main, warn]),
        default: () => breakdown,
      })
    },
  },
  {
    title: '当前库存',
    key: 'stock',
    render: (r) => {
      const stock = r.stock ?? 0
      if (stock < LOW_STOCK) {
        return h('span', { class: 'stock-low mono' }, [
          String(stock),
          h('span', { class: 'pill-low' }, '低'),
        ])
      }
      return h('span', { class: 'stock-ok mono' }, String(stock))
    },
  },
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
    width: 120,
    render: (row) => {
      if (row._isChild) {
        // Child rows: detail, edit, more (no add-sibling)
        return h(NSpace, { size: 6 }, () => [
          h('button', { class: 'icon-btn', title: '详情', onClick: () => router.push(`/jewelries/${row.id}`) }, '→'),
          h('button', { class: 'icon-btn', title: '编辑', onClick: () => openEdit(row) }, '✎'),
          h(NDropdown, {
            options: [
              { label: '复制', key: 'copy' },
              { label: '删除', key: 'delete' },
            ],
            onSelect: (key) => {
              if (key === 'copy') openCopy(row)
              if (key === 'delete') confirmDelete(row)
            },
          }, {
            default: () => h('button', { class: 'icon-btn', title: '更多' }, '⋮'),
          }),
        ])
      }
      // Header rows and single rows: detail, add-sibling, more
      return h(NSpace, { size: 6 }, () => [
        h('button', { class: 'icon-btn', title: '详情', onClick: () => router.push(`/jewelries/${row.id}`) }, '→'),
        h('button', { class: 'icon-btn', title: '添加同款', onClick: () => openAddSibling(row) }, '＋'),
        h(NDropdown, {
          options: [
            { label: '编辑', key: 'edit' },
            { label: '复制', key: 'copy' },
            { label: '删除', key: 'delete' },
          ],
          onSelect: (key) => {
            if (key === 'edit') openEdit(row)
            if (key === 'copy') openCopy(row)
            if (key === 'delete') confirmDelete(row)
          },
        }, {
          default: () => h('button', { class: 'icon-btn', title: '更多' }, '⋮'),
        }),
      ])
    },
  },
]

onMounted(load)
</script>

<style scoped>
/* ── Page shell ── */
.jewelries-page {
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
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.mono {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
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

/* ── Style group styles ── */
.jw-caret {
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
  flex-shrink: 0;
}

.jw-caret:hover {
  background: #ECEDEF;
}

.jw-caret-spacer {
  visibility: hidden;
  cursor: default;
}

.jw-count-pill {
  font-size: 10.5px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 5px;
  background: #EEF1F4;
  color: #475569;
  margin-left: 8px;
  white-space: nowrap;
}

.jw-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.jw-indent {
  padding-left: 26px;
}
</style>
