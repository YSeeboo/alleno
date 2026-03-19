<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">手工单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-card v-if="order" title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="手工单号">{{ order.id }}</n-descriptions-item>
          <n-descriptions-item label="手工商家">{{ order.supplier_name }}</n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-popselect
              :value="order?.status"
              :options="statusOptions"
              trigger="click"
              :disabled="statusOptions.length === 0"
              @update:value="doChangeStatus"
            >
              <n-tag
                :type="statusType[order.status]"
                :style="statusOptions.length > 0 ? 'cursor: pointer;' : ''"
              >
                {{ statusLabel[order.status] }}{{ statusOptions.length > 0 ? ' ▾' : '' }}
              </n-tag>
            </n-popselect>
          </n-descriptions-item>
          <n-descriptions-item label="创建时间">{{ fmt(order.created_at) }}</n-descriptions-item>
          <n-descriptions-item label="完成时间">{{ order.completed_at ? fmt(order.completed_at) : '-' }}</n-descriptions-item>
          <n-descriptions-item label="备注">{{ order.note || '-' }}</n-descriptions-item>
        </n-descriptions>
        <n-space style="margin-top: 12px;">
          <n-button v-if="order.status === 'pending'" type="primary" :loading="sending" @click="doSend">
            确认发出
          </n-button>
        </n-space>
      </n-card>

      <n-grid :cols="2" :x-gap="16">
        <n-gi>
          <n-card title="配件明细">
            <n-data-table v-if="partItems.length > 0" :columns="partColumns" :data="partItems" :bordered="false" size="small" />
            <n-empty v-else description="暂无配件明细" style="margin-top: 16px;" />
            <div v-if="order?.status === 'pending'" style="margin-top: 12px;">
              <n-button dashed style="width: 100%;" @click="openAddPartModal">+ 添加配件行</n-button>
            </div>
          </n-card>
        </n-gi>
        <n-gi>
          <n-card title="成品明细">
            <n-data-table v-if="jewelryItems.length > 0" :columns="jewelryColumns" :data="jewelryItems" :bordered="false" size="small" />
            <n-empty v-else description="暂无成品明细" style="margin-top: 16px;" />
            <div v-if="order?.status === 'pending'" style="margin-top: 12px;">
              <n-button dashed style="width: 100%;" @click="openAddJewelryModal">+ 添加饰品行</n-button>
            </div>
          </n-card>
        </n-gi>
      </n-grid>
    </n-spin>

    <!-- Add Part Modal -->
    <n-modal v-model:show="addPartModalVisible" preset="card" title="添加配件明细" style="width: 500px;">
      <n-form label-placement="left" label-width="100">
        <n-form-item label="配件">
          <n-select
            v-model:value="addPartForm.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="选择配件"
            @update:value="onAddPartSelect"
          />
        </n-form-item>
        <n-form-item label="实际发出">
          <n-input-number v-model:value="addPartForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="addPartForm.unit" :options="partUnitOptions" />
        </n-form-item>
        <n-form-item label="BOM理论(选填)">
          <n-input-number v-model:value="addPartForm.bom_qty" :min="0" :precision="2" :step="1" style="width: 100%;" placeholder="可选" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="addPartForm.note" placeholder="备注（可选）" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="addPartModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="addPartSubmitting" @click="doAddPart">确认添加</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Edit Part Modal -->
    <n-modal v-model:show="editPartModalVisible" preset="card" title="修改配件明细" style="width: 500px;">
      <n-form label-placement="left" label-width="100">
        <n-form-item label="实际发出">
          <n-input-number v-model:value="editPartForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="editPartForm.unit" :options="partUnitOptions" />
        </n-form-item>
        <n-form-item label="BOM理论(选填)">
          <n-input-number v-model:value="editPartForm.bom_qty" :min="0" :precision="2" :step="1" style="width: 100%;" placeholder="可选" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="editPartModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="editPartSubmitting" @click="doEditPart">保存修改</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Add Jewelry Modal -->
    <n-modal v-model:show="addJewelryModalVisible" preset="card" title="添加饰品明细" style="width: 500px;">
      <n-form label-placement="left" label-width="100">
        <n-form-item label="饰品">
          <n-select
            v-model:value="addJewelryForm.jewelry_id"
            :options="jewelryOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="选择饰品"
            @update:value="onAddJewelrySelect"
          />
        </n-form-item>
        <n-form-item label="预期数量">
          <n-input-number v-model:value="addJewelryForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="addJewelryForm.unit" :options="jewelryUnitOptions" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="addJewelryForm.note" placeholder="备注（可选）" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="addJewelryModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="addJewelrySubmitting" @click="doAddJewelry">确认添加</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Edit Jewelry Modal -->
    <n-modal v-model:show="editJewelryModalVisible" preset="card" title="修改饰品明细" style="width: 500px;">
      <n-form label-placement="left" label-width="100">
        <n-form-item label="预期数量">
          <n-input-number v-model:value="editJewelryForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="editJewelryForm.unit" :options="jewelryUnitOptions" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="editJewelryModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="editJewelrySubmitting" @click="doEditJewelry">保存修改</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, h, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NGrid, NGi, NEmpty, NModal, NForm, NFormItem,
  NSelect, NInputNumber, NInput, NPopselect, NTooltip, NIcon,
} from 'naive-ui'
import { CreateOutline } from '@vicons/ionicons5'
import {
  getHandcraft, getHandcraftParts, getHandcraftJewelries, sendHandcraft,
  addHandcraftPart, updateHandcraftPart, deleteHandcraftPart,
  addHandcraftJewelry, updateHandcraftJewelry, deleteHandcraftJewelry,
} from '@/api/handcraft'
import { changeOrderStatus } from '@/api/kanban'
import { listParts } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { renderNamedImage, renderOptionWithImage } from '@/utils/ui'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const loading = ref(true)
const sending = ref(false)
const order = ref(null)
const partItems = ref([])
const jewelryItems = ref([])
const partMap = ref({})
const jewelryMap = ref({})
const partOptions = ref([])
const jewelryOptions = ref([])

const statusType = { pending: 'default', processing: 'info', completed: 'success' }
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }
const statusOptions = computed(() => {
  if (!order.value) return []
  const s = order.value.status
  if (s === 'pending') return [{ label: '进行中', value: 'processing' }]
  if (s === 'processing') return [
    { label: '待发出', value: 'pending' },
    { label: '已完成', value: 'completed' },
  ]
  if (s === 'completed') return [{ label: '进行中', value: 'processing' }]
  return []
})
const fmt = (dt) => new Date(dt).toLocaleString('zh-CN')

const partUnitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const jewelryUnitOptions = [
  { label: '个', value: '个' },
  { label: '套', value: '套' },
  { label: '对', value: '对' },
]

// Add Part Modal
const addPartModalVisible = ref(false)
const addPartSubmitting = ref(false)
const addPartForm = ref({ part_id: null, qty: 1, unit: '个', bom_qty: null, note: '' })

// Edit Part Modal
const editPartModalVisible = ref(false)
const editPartSubmitting = ref(false)
const editPartForm = ref({ id: null, qty: 1, unit: '个', bom_qty: null })

// Add Jewelry Modal
const addJewelryModalVisible = ref(false)
const addJewelrySubmitting = ref(false)
const addJewelryForm = ref({ jewelry_id: null, qty: 1, unit: '个', note: '' })

// Edit Jewelry Modal
const editJewelryModalVisible = ref(false)
const editJewelrySubmitting = ref(false)
const editJewelryForm = ref({ id: null, qty: 1, unit: '个' })
const editingNoteKey = ref(null)
const editingNoteValue = ref('')
const savingNoteKey = ref(null)
const noteInputRef = ref(null)

const loadData = async () => {
  const id = route.params.id
  const [oRes, pRes, jRes] = await Promise.all([
    getHandcraft(id), getHandcraftParts(id), getHandcraftJewelries(id),
  ])
  order.value = oRes.data
  partItems.value = pRes.data.map((p) => ({
    ...p,
    part_name: partMap.value[p.part_id]?.name || p.part_id,
    part_image: partMap.value[p.part_id]?.image || '',
  }))
  jewelryItems.value = jRes.data.map((j) => ({
    ...j,
    jewelry_name: jewelryMap.value[j.jewelry_id]?.name || j.jewelry_id,
    jewelry_image: jewelryMap.value[j.jewelry_id]?.image || '',
  }))
  if (!isPending()) {
    stopEditNote()
  }
}

const doSend = async () => {
  sending.value = true
  try {
    await sendHandcraft(route.params.id)
    message.success('已确认发出')
    await loadData()
  } finally {
    sending.value = false
  }
}

const doChangeStatus = (newStatus) => {
  const currentLabel = statusLabel[order.value?.status] || order.value?.status
  const newLabel = statusLabel[newStatus] || newStatus
  dialog.warning({
    title: '确认状态变更',
    content: `请确认将「${order.value?.supplier_name}」的订单「${order.value?.id}」状态从「${currentLabel}」转为「${newLabel}」`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      const loadingMsg = message.loading('正在更新状态...', { duration: 0 })
      try {
        await changeOrderStatus({ order_id: order.value.id, order_type: 'handcraft', new_status: newStatus })
        loadingMsg.destroy()
        message.success(`状态已更新为${newLabel}`)
        await loadData()
      } catch (_) {
        loadingMsg.destroy()
        // errors shown by axios interceptor
        await loadData()
      }
    },
  })
}

// --- Part CRUD ---

const openAddPartModal = () => {
  addPartForm.value = { part_id: null, qty: 1, unit: '个', bom_qty: null, note: '' }
  addPartModalVisible.value = true
}

const onAddPartSelect = (val) => {
  const found = partOptions.value.find((p) => p.value === val)
  if (found && found.unit) {
    addPartForm.value.unit = found.unit
  } else {
    addPartForm.value.unit = '个'
  }
}

const doAddPart = async () => {
  if (!addPartForm.value.part_id) { message.warning('请选择配件'); return }
  if (!addPartForm.value.qty || addPartForm.value.qty < 1) { message.warning('数量不能小于 1'); return }
  addPartSubmitting.value = true
  try {
    await addHandcraftPart(route.params.id, addPartForm.value)
    message.success('配件明细已添加')
    addPartModalVisible.value = false
    await loadData()
  } finally {
    addPartSubmitting.value = false
  }
}

const openEditPartModal = (row) => {
  editPartForm.value = {
    id: row.id,
    qty: row.qty,
    unit: row.unit || '个',
    bom_qty: row.bom_qty ?? null,
  }
  editPartModalVisible.value = true
}

const doEditPart = async () => {
  editPartSubmitting.value = true
  try {
    const { id, ...body } = editPartForm.value
    await updateHandcraftPart(route.params.id, id, body)
    message.success('修改已保存')
    editPartModalVisible.value = false
    await loadData()
  } finally {
    editPartSubmitting.value = false
  }
}

const doDeletePart = (row) => {
  dialog.warning({
    title: '确认删除',
    content: `确认删除配件 ${row.part_name || row.part_id} 的明细行？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteHandcraftPart(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (_) {
        // error shown by axios interceptor
      }
    },
  })
}

// --- Jewelry CRUD ---

const openAddJewelryModal = () => {
  addJewelryForm.value = { jewelry_id: null, qty: 1, unit: '个', note: '' }
  addJewelryModalVisible.value = true
}

const onAddJewelrySelect = (val) => {
  const found = jewelryOptions.value.find((j) => j.value === val)
  if (found && found.unit) {
    addJewelryForm.value.unit = found.unit
  } else {
    addJewelryForm.value.unit = '个'
  }
}

const doAddJewelry = async () => {
  if (!addJewelryForm.value.jewelry_id) { message.warning('请选择饰品'); return }
  if (!addJewelryForm.value.qty || addJewelryForm.value.qty < 1) { message.warning('数量不能小于 1'); return }
  addJewelrySubmitting.value = true
  try {
    await addHandcraftJewelry(route.params.id, addJewelryForm.value)
    message.success('饰品明细已添加')
    addJewelryModalVisible.value = false
    await loadData()
  } finally {
    addJewelrySubmitting.value = false
  }
}

const openEditJewelryModal = (row) => {
  editJewelryForm.value = {
    id: row.id,
    qty: row.qty,
    unit: row.unit || '个',
  }
  editJewelryModalVisible.value = true
}

const doEditJewelry = async () => {
  editJewelrySubmitting.value = true
  try {
    const { id, ...body } = editJewelryForm.value
    await updateHandcraftJewelry(route.params.id, id, body)
    message.success('修改已保存')
    editJewelryModalVisible.value = false
    await loadData()
  } finally {
    editJewelrySubmitting.value = false
  }
}

const doDeleteJewelry = (row) => {
  dialog.warning({
    title: '确认删除',
    content: `确认删除饰品 ${row.jewelry_name || row.jewelry_id} 的明细行？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteHandcraftJewelry(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (_) {
        // error shown by axios interceptor
      }
    },
  })
}

const isPending = () => order.value?.status === 'pending'
const noteKeyOf = (kind, id) => `${kind}:${id}`
const normalizeNote = (value) => (value || '').trim()

const focusEditingNoteInput = () => {
  nextTick(() => {
    noteInputRef.value?.focus?.()
  })
}

const startEditNote = (kind, row) => {
  if (!isPending()) return
  editingNoteKey.value = noteKeyOf(kind, row.id)
  editingNoteValue.value = row.note || ''
  focusEditingNoteInput()
}

const stopEditNote = (noteKey = null) => {
  if (noteKey !== null && editingNoteKey.value !== noteKey) return
  editingNoteKey.value = null
  editingNoteValue.value = ''
}

const saveNote = async (kind, row) => {
  const noteKey = noteKeyOf(kind, row.id)
  if (editingNoteKey.value !== noteKey || savingNoteKey.value === noteKey) return

  const nextNote = normalizeNote(editingNoteValue.value)
  const currentNote = normalizeNote(row.note)
  if (nextNote === currentNote) {
    stopEditNote(noteKey)
    return
  }

  savingNoteKey.value = noteKey
  try {
    const request = kind === 'part'
      ? updateHandcraftPart(route.params.id, row.id, { note: nextNote })
      : updateHandcraftJewelry(route.params.id, row.id, { note: nextNote })
    const { data } = await request
    row.note = data.note || ''
    message.success(nextNote ? '备注已保存' : '备注已清空')
    stopEditNote(noteKey)
  } finally {
    if (savingNoteKey.value === noteKey) {
      savingNoteKey.value = null
    }
  }
}

const onNoteInputKeydown = (event, kind, row) => {
  if (event.key !== 'Enter') return
  if (event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  void saveNote(kind, row)
}

const renderNoteCell = (kind, row) => {
  const noteKey = noteKeyOf(kind, row.id)
  const isEditing = editingNoteKey.value === noteKey
  const isSaving = savingNoteKey.value === noteKey
  const noteText = row.note || ''

  if (isEditing) {
    return h(NInput, {
      ref: noteInputRef,
      value: editingNoteValue.value,
      size: 'small',
      placeholder: '输入备注后按回车或点击空白处保存',
      disabled: isSaving,
      autofocus: true,
      'onUpdate:value': (value) => { editingNoteValue.value = value },
      onBlur: () => { void saveNote(kind, row) },
      onKeydown: (event) => onNoteInputKeydown(event, kind, row),
    })
  }

  if (!noteText) {
    if (!isPending()) {
      return h('span', { style: 'color: #999;' }, '-')
    }
    return h(
      NButton,
      {
        text: true,
        type: 'primary',
        size: 'small',
        onClick: () => startEditNote(kind, row),
      },
      {
        icon: () => h(NIcon, null, { default: () => h(CreateOutline) }),
        default: () => '添加备注',
      },
    )
  }

  return h(
    'span',
    {
      title: noteText,
      style: [
        'display: inline-block',
        'max-width: 180px',
        'overflow: hidden',
        'text-overflow: ellipsis',
        'white-space: nowrap',
        'vertical-align: bottom',
        isPending() ? 'cursor: pointer; color: #2080f0;' : '',
      ].join('; '),
      onClick: isPending() ? () => startEditNote(kind, row) : undefined,
    },
    noteText,
  )
}

const partColumns = [
  { title: '配件编号', key: 'part_id', width: 110 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 160,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
  },
  { title: '实际发出', key: 'qty' },
  { title: '单位', key: 'unit', render: (r) => r.unit || '-' },
  { title: 'BOM理论', key: 'bom_qty', render: (r) => r.bom_qty ?? '-' },
  {
    title: '差异',
    key: 'diff',
    render: (r) => {
      if (r.bom_qty == null) return '-'
      const diff = r.qty - r.bom_qty
      return h('span', { style: { color: diff > 0 ? '#d03050' : diff < 0 ? '#18a058' : undefined } },
        (diff > 0 ? '+' : '') + diff
      )
    },
  },
  {
    title: '备注',
    key: 'note',
    minWidth: 200,
    render: (row) => renderNoteCell('part', row),
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    render: (row) => {
      const pending = isPending()
      const editBtn = h(
        NTooltip,
        { disabled: pending, trigger: 'hover' },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: 'small',
                disabled: !pending,
                style: 'margin-right: 6px;',
                onClick: pending ? () => openEditPartModal(row) : undefined,
              },
              { default: () => '修改' },
            ),
          default: () => '当前单子进行中/已完成，不允许修改/删除',
        },
      )
      const deleteBtn = h(
        NTooltip,
        { disabled: pending, trigger: 'hover' },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: 'small',
                type: 'error',
                disabled: !pending,
                onClick: pending ? () => doDeletePart(row) : undefined,
              },
              { default: () => '删除' },
            ),
          default: () => '当前单子进行中/已完成，不允许修改/删除',
        },
      )
      return h(NSpace, { size: 'small' }, { default: () => [editBtn, deleteBtn] })
    },
  },
]

const jewelryColumns = [
  { title: '饰品编号', key: 'jewelry_id', width: 110 },
  {
    title: '饰品',
    key: 'jewelry_name',
    minWidth: 160,
    render: (row) => renderNamedImage(row.jewelry_name, row.jewelry_image, row.jewelry_name),
  },
  { title: '预期数量', key: 'qty' },
  { title: '单位', key: 'unit', render: (r) => r.unit || '-' },
  { title: '状态', key: 'status' },
  {
    title: '备注',
    key: 'note',
    minWidth: 200,
    render: (row) => renderNoteCell('jewelry', row),
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    render: (row) => {
      const pending = isPending()
      const editBtn = h(
        NTooltip,
        { disabled: pending, trigger: 'hover' },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: 'small',
                disabled: !pending,
                style: 'margin-right: 6px;',
                onClick: pending ? () => openEditJewelryModal(row) : undefined,
              },
              { default: () => '修改' },
            ),
          default: () => '当前单子进行中/已完成，不允许修改/删除',
        },
      )
      const deleteBtn = h(
        NTooltip,
        { disabled: pending, trigger: 'hover' },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: 'small',
                type: 'error',
                disabled: !pending,
                onClick: pending ? () => doDeleteJewelry(row) : undefined,
              },
              { default: () => '删除' },
            ),
          default: () => '当前单子进行中/已完成，不允许修改/删除',
        },
      )
      return h(NSpace, { size: 'small' }, { default: () => [editBtn, deleteBtn] })
    },
  },
]

onMounted(async () => {
  try {
    const [pRes, jRes] = await Promise.all([listParts(), listJewelries()])
    pRes.data.forEach((p) => { partMap.value[p.id] = p })
    jRes.data.forEach((j) => { jewelryMap.value[j.id] = j })
    partOptions.value = pRes.data.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
      unit: p.unit,
    }))
    jewelryOptions.value = jRes.data.map((j) => ({
      label: `${j.id} ${j.name}`,
      value: j.id,
      code: j.id,
      name: j.name,
      image: j.image,
      unit: j.unit,
    }))
    await loadData()
  } finally {
    loading.value = false
  }
})
</script>
