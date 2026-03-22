<template>
  <div style="max-width: 800px;">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建购入单</n-h2>
    </n-space>

    <n-form label-placement="left" label-width="100" style="margin-bottom: 16px;">
      <n-form-item label="商家名称">
        <n-select
          v-model:value="vendorName"
          :options="vendorOptions"
          filterable
          tag
          placeholder="选择或输入商家名称"
          style="width: 300px;"
        />
      </n-form-item>
      <n-form-item label="备注">
        <n-input v-model:value="note" type="textarea" :rows="2" style="width: 300px;" />
      </n-form-item>
    </n-form>

    <n-card title="购入明细" style="margin-bottom: 16px;">
      <div v-for="(item, idx) in items" :key="idx" style="margin-bottom: 10px;">
        <n-space align="center">
          <n-select
            v-model:value="item.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="选择配件"
            style="width: 220px;"
            @update:value="(val) => onPartSelect(item, val)"
          />
          <n-input-number v-model:value="item.qty" :min="1" :precision="0" :step="1" placeholder="数量" style="width: 100px;" />
          <n-select
            v-model:value="item.unit"
            :options="unitOptions"
            style="width: 90px;"
          />
          <n-input-number v-model:value="item.price" :min="0" :precision="3" :step="0.1" placeholder="单价" style="width: 110px;" />
          <span style="min-width: 80px; color: #666;">{{ formatAmount(item.qty, item.price) }}</span>
          <n-button type="error" size="small" @click="items.splice(idx, 1)">删除</n-button>
        </n-space>
      </div>
      <n-button dashed style="width: 100%;" @click="addRow">
        + 添加明细行
      </n-button>
    </n-card>

    <div style="margin-bottom: 16px; font-size: 15px; font-weight: 600;">
      总金额：¥ {{ totalAmount }}
    </div>

    <n-form label-placement="left" label-width="100" style="margin-bottom: 16px;">
      <n-form-item label="付款状态">
        <n-radio-group v-model:value="status">
          <n-radio value="未付款">未付款</n-radio>
          <n-radio value="已付款">已付款</n-radio>
        </n-radio-group>
      </n-form-item>
    </n-form>

    <n-space justify="end">
      <n-button type="primary" :loading="submitting" @click="submit">提交</n-button>
    </n-space>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NH2, NRadioGroup, NRadio } from 'naive-ui'
import { listParts } from '@/api/parts'
import { createPurchaseOrder, getPurchaseOrderVendors } from '@/api/purchaseOrders'
import { renderOptionWithImage } from '@/utils/ui'

const router = useRouter()
const message = useMessage()
const vendorName = ref(null)
const note = ref('')
const status = ref('未付款')
const items = reactive([{ part_id: null, qty: 1, unit: '个', price: 0, note: '' }])
const submitting = ref(false)
const partOptions = ref([])
const vendorOptions = ref([])

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const formatAmount = (qty, price) => {
  if (!qty || price == null) return '¥ 0.000'
  return `¥ ${(qty * price).toFixed(3)}`
}

const totalAmount = computed(() => {
  return items.reduce((sum, item) => sum + (item.qty || 0) * (item.price || 0), 0).toFixed(3)
})

const addRow = () => {
  items.push({ part_id: null, qty: 1, unit: '个', price: 0, note: '' })
}

const onPartSelect = (item, val) => {
  const found = partOptions.value.find((p) => p.value === val)
  if (found && found.unit) {
    item.unit = found.unit
  } else {
    item.unit = '个'
  }
}

const submit = async () => {
  if (!vendorName.value?.trim()) { message.warning('请输入商家名称'); return }
  if (items.length === 0) { message.warning('请至少添加一条明细'); return }
  if (items.some((i) => !i.part_id)) { message.warning('请选择配件'); return }
  submitting.value = true
  try {
    const { data } = await createPurchaseOrder({
      vendor_name: vendorName.value.trim(),
      items,
      status: status.value,
      note: note.value,
    })
    message.success('创建成功')
    router.push(`/purchase-orders/${data.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const partsPromise = listParts().then(({ data }) => {
    partOptions.value = data.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
      unit: p.unit,
    }))
  }).catch(() => {})
  const vendorsPromise = getPurchaseOrderVendors().then(({ data }) => {
    vendorOptions.value = data.map((v) => ({ label: v, value: v }))
  }).catch(() => {})
  await Promise.all([partsPromise, vendorsPromise])
})
</script>
