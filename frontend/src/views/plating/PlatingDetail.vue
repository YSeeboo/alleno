<template>
  <div>
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">电镀单详情</n-h2>
    </n-space>

    <n-spin :show="loading">
      <n-card v-if="order" title="基本信息" style="margin-bottom: 16px;">
        <n-descriptions :column="3" bordered>
          <n-descriptions-item label="电镀单号">{{ order.id }}</n-descriptions-item>
          <n-descriptions-item label="电镀厂">{{ order.supplier_name }}</n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-popselect
              v-model:value="order.status"
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

      <n-card title="电镀明细">
        <n-data-table v-if="items.length > 0" :columns="itemColumns" :data="items" :bordered="false" />
        <n-empty v-else description="暂无明细" style="margin-top: 16px;" />
        <div v-if="order?.status === 'pending'" style="margin-top: 12px;">
          <n-button dashed style="width: 100%;" @click="openAddModal">+ 添加明细行</n-button>
        </div>
      </n-card>
    </n-spin>

    <!-- Add Item Modal -->
    <n-modal v-model:show="addModalVisible" preset="card" title="添加电镀明细" style="width: 500px;">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="配件">
          <n-select
            v-model:value="addForm.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="选择配件"
            @update:value="onAddPartSelect"
          />
        </n-form-item>
        <n-form-item label="数量">
          <n-input-number v-model:value="addForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="addForm.unit" :options="unitOptions" />
        </n-form-item>
        <n-form-item label="电镀方式">
          <n-select v-model:value="addForm.plating_method" :options="platingMethodOptions" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="addForm.note" placeholder="备注（可选）" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="addModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="addSubmitting" @click="doAddItem">确认添加</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Edit Item Modal -->
    <n-modal v-model:show="editModalVisible" preset="card" title="修改明细" style="width: 500px;">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="数量">
          <n-input-number v-model:value="editForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="单位">
          <n-select v-model:value="editForm.unit" :options="unitOptions" />
        </n-form-item>
        <n-form-item label="电镀方式">
          <n-select v-model:value="editForm.plating_method" :options="platingMethodOptions" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="editForm.note" placeholder="备注（可选）" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="editModalVisible = false">取消</n-button>
          <n-button type="primary" :loading="editSubmitting" @click="doEditItem">保存修改</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import {
  NCard, NDescriptions, NDescriptionsItem, NSpin, NDataTable,
  NSpace, NButton, NH2, NTag, NEmpty, NModal, NForm, NFormItem,
  NSelect, NInputNumber, NInput, NPopselect, NTooltip,
} from 'naive-ui'
import {
  getPlating, getPlatingItems, sendPlating,
  addPlatingItem, updatePlatingItem, deletePlatingItem, updatePlatingStatus,
} from '@/api/plating'
import { listParts } from '@/api/parts'
import { renderNamedImage, renderOptionWithImage } from '@/utils/ui'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const loading = ref(true)
const sending = ref(false)
const order = ref(null)
const items = ref([])
const partMap = ref({})
const partOptions = ref([])

const statusType = { pending: 'default', processing: 'info', completed: 'success' }
const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }
// Only processing -> completed is a valid PATCH /status transition.
// pending -> processing must go through POST /send (deducts inventory).
// All status transitions go through dedicated endpoints (POST /send, POST /receive)
const statusOptions = computed(() => [])
const fmt = (dt) => new Date(dt).toLocaleString('zh-CN')

const platingMethodOptions = [
  { label: '金', value: '金' },
  { label: '白K', value: '白K' },
  { label: '玫瑰金', value: '玫瑰金' },
  { label: '银色', value: '银色' },
]

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

// Add Item Modal
const addModalVisible = ref(false)
const addSubmitting = ref(false)
const addForm = ref({ part_id: null, qty: 1, unit: '个', plating_method: '金', note: '' })

// Edit Item Modal
const editModalVisible = ref(false)
const editSubmitting = ref(false)
const editForm = ref({ id: null, qty: 1, unit: '个', plating_method: '金', note: '' })

const loadData = async () => {
  const id = route.params.id
  const [oRes, iRes] = await Promise.all([getPlating(id), getPlatingItems(id)])
  order.value = oRes.data
  items.value = iRes.data.map((i) => ({
    ...i,
    part_name: partMap.value[i.part_id]?.name || i.part_id,
    part_image: partMap.value[i.part_id]?.image || '',
  }))
}

const doSend = async () => {
  sending.value = true
  try {
    await sendPlating(route.params.id)
    message.success('已确认发出')
    await loadData()
  } finally {
    sending.value = false
  }
}

const doChangeStatus = async (newStatus) => {
  try {
    await updatePlatingStatus(route.params.id, newStatus)
    message.success('状态已更新')
    await loadData()
  } catch (_) {
    // error shown by axios interceptor; reload to restore displayed value
    await loadData()
  }
}

const openAddModal = () => {
  addForm.value = { part_id: null, qty: 1, unit: '个', plating_method: '金', note: '' }
  addModalVisible.value = true
}

const onAddPartSelect = (val) => {
  const found = partOptions.value.find((p) => p.value === val)
  if (found && found.unit) {
    addForm.value.unit = found.unit
  } else {
    addForm.value.unit = '个'
  }
}

const doAddItem = async () => {
  if (!addForm.value.part_id) { message.warning('请选择配件'); return }
  if (!addForm.value.qty || addForm.value.qty < 1) { message.warning('数量不能小于 1'); return }
  addSubmitting.value = true
  try {
    await addPlatingItem(route.params.id, addForm.value)
    message.success('明细已添加')
    addModalVisible.value = false
    await loadData()
  } finally {
    addSubmitting.value = false
  }
}

const openEditModal = (row) => {
  editForm.value = {
    id: row.id,
    qty: row.qty,
    unit: row.unit || '个',
    plating_method: row.plating_method || '金',
    note: row.note || '',
  }
  editModalVisible.value = true
}

const doEditItem = async () => {
  editSubmitting.value = true
  try {
    const { id, ...body } = editForm.value
    await updatePlatingItem(route.params.id, id, body)
    message.success('修改已保存')
    editModalVisible.value = false
    await loadData()
  } finally {
    editSubmitting.value = false
  }
}

const doDeleteItem = (row) => {
  dialog.warning({
    title: '确认删除',
    content: `确认删除配件 ${row.part_name || row.part_id} 的明细行？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deletePlatingItem(route.params.id, row.id)
        message.success('已删除')
        await loadData()
      } catch (_) {
        // error shown by axios interceptor
      }
    },
  })
}

const isPending = () => order.value?.status === 'pending'

const itemColumns = [
  { title: '配件编号', key: 'part_id', width: 110 },
  {
    title: '配件',
    key: 'part_name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.part_name, row.part_image, row.part_name),
  },
  { title: '发出数量', key: 'qty' },
  { title: '单位', key: 'unit', render: (r) => r.unit || '-' },
  { title: '电镀方式', key: 'plating_method', render: (r) => r.plating_method || '-' },
  {
    title: '状态',
    key: 'item_status',
    render: (r) => h('span', r.status),
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
                onClick: pending ? () => openEditModal(row) : undefined,
              },
              { default: () => '修改' },
            ),
          default: () => '当前单子进行中/已完成，不允许修改',
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
                onClick: pending ? () => doDeleteItem(row) : undefined,
              },
              { default: () => '删除' },
            ),
          default: () => '当前单子进行中/已完成，不允许删除',
        },
      )
      return h(NSpace, { size: 'small' }, { default: () => [editBtn, deleteBtn] })
    },
  },
]

onMounted(async () => {
  try {
    const { data: parts } = await listParts()
    parts.forEach((p) => { partMap.value[p.id] = p })
    partOptions.value = parts.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
      unit: p.unit,
    }))
    await loadData()
  } finally {
    loading.value = false
  }
})
</script>
