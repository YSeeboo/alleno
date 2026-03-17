<template>
  <n-modal v-model:show="visible" :mask-closable="false">
    <n-card
      title="录入收回"
      style="width: 520px; max-width: 95vw;"
      :bordered="false"
      role="dialog"
    >
      <template #header-extra>
        <n-button text @click="handleClose">
          <template #icon><n-icon :component="CloseOutline" /></template>
        </n-button>
      </template>

      <n-form label-placement="left" label-width="64" :model="form">
        <!-- 厂家 -->
        <n-form-item label="厂家">
          <n-select
            v-model:value="form.vendor_name"
            filterable
            remote
            :options="vendorOptions"
            :loading="vendorLoading"
            placeholder="搜索厂家名..."
            tag
            clearable
            @search="handleVendorSearch"
          />
        </n-form-item>

        <!-- 类型 -->
        <n-form-item label="类型">
          <n-radio-group v-model:value="form.order_type" @update:value="handleTypeChange">
            <n-radio-button value="plating">电镀收回</n-radio-button>
            <n-radio-button value="handcraft">手工收回</n-radio-button>
          </n-radio-group>
        </n-form-item>

        <!-- 订单 -->
        <n-form-item label="订单">
          <n-select
            v-model:value="form.order_id"
            :options="orderOptions"
            :loading="orderLoading"
            :disabled="!form.vendor_name"
            placeholder="选择订单号..."
            clearable
          />
        </n-form-item>

        <!-- 收回明细 -->
        <n-form-item label="明细">
          <div style="width: 100%;">
            <div
              v-for="(row, index) in detailRows"
              :key="index"
              class="detail-row"
            >
              <n-select
                v-model:value="row.selectorValue"
                filterable
                remote
                :options="row.options"
                :loading="row.searching"
                placeholder="搜索编号..."
                style="flex: 1; min-width: 0;"
                @search="(q) => handleItemSearch(q, index)"
              />
              <n-input-number
                v-model:value="row.qty"
                :min="0.01"
                :precision="2"
                placeholder="数量"
                style="width: 110px; flex-shrink: 0;"
              />
              <n-button
                quaternary
                circle
                :disabled="detailRows.length === 1"
                @click="removeRow(index)"
              >
                <template #icon><n-icon :component="CloseOutline" /></template>
              </n-button>
            </div>

            <n-button dashed style="width: 100%; margin-top: 8px;" @click="addRow">
              + 添加
            </n-button>
          </div>
        </n-form-item>
      </n-form>

      <template #footer>
        <n-space justify="end">
          <n-button @click="handleClose">取消</n-button>
          <n-button type="primary" :loading="submitting" @click="handleSubmit">确定</n-button>
        </n-space>
      </template>
    </n-card>
  </n-modal>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import {
  NModal, NCard, NButton, NIcon, NForm, NFormItem,
  NSelect, NRadioGroup, NRadioButton, NInputNumber,
  NSpace, useMessage,
} from 'naive-ui'
import { CloseOutline } from '@vicons/ionicons5'
import { submitReturn, searchVendors, searchParts, searchJewelries, getVendorOrders } from '@/api/kanban'

const props = defineProps({ show: Boolean })
const emit = defineEmits(['update:show', 'success'])

const visible = computed({
  get: () => props.show,
  set: (val) => emit('update:show', val),
})

const message = useMessage()
const form = reactive({ vendor_name: null, order_type: 'plating', order_id: null })
const submitting = ref(false)

// 厂家搜索
const vendorOptions = ref([])
const vendorLoading = ref(false)
let _vendorSearchVersion = 0

const handleVendorSearch = async (q) => {
  _vendorSearchVersion++
  const myVersion = _vendorSearchVersion
  vendorLoading.value = true
  try {
    const { data } = await searchVendors({ q, order_type: form.order_type })
    if (myVersion !== _vendorSearchVersion) return
    const list = Array.isArray(data) ? data : (data.items || [])
    vendorOptions.value = list.map((v) => {
      const name = typeof v === 'string' ? v : (v.vendor_name || v.name || v)
      return { label: name, value: name }
    })
  } finally {
    if (myVersion === _vendorSearchVersion) vendorLoading.value = false
  }
}

// 订单列表
const orderOptions = ref([])
const orderLoading = ref(false)

const loadOrders = async () => {
  if (!form.vendor_name) { orderOptions.value = []; form.order_id = null; return }
  orderLoading.value = true
  try {
    const { data } = await getVendorOrders({ vendor_name: form.vendor_name, order_type: form.order_type })
    orderOptions.value = (Array.isArray(data) ? data : []).map((o) => ({
      label: `${o.order_id}`,
      value: o.order_id,
    }))
    form.order_id = null
  } finally {
    orderLoading.value = false
  }
}

watch(() => [form.vendor_name, form.order_type], loadOrders)

// 明细行
const createRow = () => ({ selectorValue: null, qty: null, options: [], searching: false })
const detailRows = ref([createRow()])

const addRow = () => detailRows.value.push(createRow())
const removeRow = (index) => detailRows.value.splice(index, 1)

const handleTypeChange = () => {
  _vendorSearchVersion++
  detailRows.value = [createRow()]
  vendorOptions.value = []
  orderOptions.value = []
  form.vendor_name = null
  form.order_id = null
}

// 编号搜索（per-row，版本号挂在 row 上防止乱序）
const handleItemSearch = async (q, index) => {
  const row = detailRows.value[index]
  row._searchVersion = (row._searchVersion || 0) + 1
  const myVersion = row._searchVersion
  row.searching = true
  try {
    let newOptions
    if (form.order_type === 'plating') {
      const { data } = await searchParts({ name: q })
      const list = Array.isArray(data) ? data : (data.items || [])
      newOptions = list.map((p) => ({ label: `${p.id} ${p.name}`, value: p.id }))
    } else {
      const [partsRes, jewelriesRes] = await Promise.all([
        searchParts({ name: q }),
        searchJewelries({ name: q }),
      ])
      const parts = Array.isArray(partsRes.data) ? partsRes.data : (partsRes.data.items || [])
      const jewelries = Array.isArray(jewelriesRes.data) ? jewelriesRes.data : (jewelriesRes.data.items || [])
      newOptions = [
        {
          type: 'group',
          label: '配件',
          key: 'parts',
          children: parts.map((p) => ({ label: `${p.id} ${p.name}`, value: `part:${p.id}` })),
        },
        {
          type: 'group',
          label: '饰品',
          key: 'jewelries',
          children: jewelries.map((j) => ({ label: `${j.id} ${j.name}`, value: `jewelry:${j.id}` })),
        },
      ]
    }
    if (myVersion !== row._searchVersion) return
    row.options = newOptions
  } finally {
    if (myVersion === row._searchVersion) row.searching = false
  }
}

// 提交
const handleSubmit = async () => {
  if (!form.vendor_name) { message.warning('请选择厂家'); return }
  if (!form.order_id) { message.warning('请选择订单'); return }
  const items = detailRows.value
    .filter((r) => r.selectorValue && r.qty)
    .map((r) => {
      if (form.order_type === 'plating') {
        return { item_id: r.selectorValue, item_type: 'part', qty: r.qty }
      }
      const [type, id] = r.selectorValue.split(':')
      return { item_id: id, item_type: type, qty: r.qty }
    })

  submitting.value = true
  let data
  try {
    ;({ data } = await submitReturn({
      vendor_name: form.vendor_name,
      order_type: form.order_type,
      order_id: form.order_id,
      items,
    }))
  } finally {
    submitting.value = false
  }

  emit('success')
  handleClose()

  const warns = data?.warnings || []
  warns.forEach((w) => message.warning(w, { duration: 6000, keepAliveOnHover: true }))
}

const handleClose = () => {
  emit('update:show', false)
}

// 重置 modal 状态
watch(
  () => props.show,
  (val) => {
    if (!val) {
      _vendorSearchVersion++
      detailRows.value = [createRow()]
      form.vendor_name = null
      form.order_type = 'plating'
      vendorOptions.value = []
    }
  },
)
</script>

<style scoped>
.detail-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
