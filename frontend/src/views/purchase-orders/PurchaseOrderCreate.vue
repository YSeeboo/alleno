<template>
  <div :style="{ maxWidth: isMobile ? '100%' : '960px' }">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建购入单</n-h2>
    </n-space>

    <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="100" style="margin-bottom: 16px;">
      <n-form-item label="商家名称">
        <n-select
          v-model:value="vendorName"
          :options="vendorOptions"
          filterable
          tag
          placeholder="选择或输入商家名称"
          :style="{ width: isMobile ? '100%' : '300px' }"
        />
      </n-form-item>
      <n-form-item label="备注">
        <n-input v-model:value="note" type="textarea" :rows="2" :style="{ width: isMobile ? '100%' : '300px' }" />
      </n-form-item>
      <n-form-item label="创建时间">
        <n-date-picker
          v-model:value="createdAtTs"
          type="date"
          clearable
          placeholder="不填则使用当前时间"
          :style="{ width: isMobile ? '100%' : '300px' }"
        />
      </n-form-item>
    </n-form>

    <n-card title="购入明细" style="margin-bottom: 16px;">
      <n-space v-if="!isMobile" align="center" class="items-header">
        <div style="width: 220px;">配件</div>
        <div style="width: 100px;">数量</div>
        <div style="width: 90px;">单位</div>
        <div style="width: 130px;">单价</div>
        <div style="width: 100px;">金额</div>
        <div style="width: 56px; text-align: center;">操作</div>
      </n-space>
      <div v-for="(item, idx) in items" :key="idx" style="margin-bottom: 10px;">
        <n-space align="center">
          <n-select
            v-model:value="item.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            clearable
            placeholder="选择配件"
            :style="{ width: isMobile ? '100%' : '220px' }"
            @update:value="(val) => onPartSelect(item, val)"
          />
          <n-input-number v-model:value="item.qty" :min="1" :precision="0" :step="1" placeholder="数量" style="width: 100px;" />
          <n-select
            v-model:value="item.unit"
            :options="unitOptions"
            style="width: 90px;"
          />
          <n-input-number v-model:value="item.price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" :step="0.1" placeholder="单价" style="width: 130px;" />
          <span style="display: inline-block; width: 100px; color: #666;">{{ formatAmount(item.qty, item.price) }}</span>
          <div style="width: 56px; text-align: center;">
            <n-button type="error" size="small" @click="items.splice(idx, 1)">删除</n-button>
          </div>
        </n-space>
      </div>
      <n-button dashed style="width: 100%;" @click="addRow">
        + 添加明细行
      </n-button>
    </n-card>

    <div style="margin-bottom: 16px; font-size: 15px; font-weight: 600;">
      总金额：¥ {{ totalAmount }}
    </div>

    <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="100" style="margin-bottom: 16px;">
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
    <!-- Cost Diff Modal -->
    <n-modal v-model:show="costDiffVisible" :mask-closable="false" preset="card" title="成本变动确认" :style="{ width: isMobile ? '95vw' : '600px' }">
      <div style="margin-bottom: 12px; color: #333;">
        当前成本与配件已有成本金额不相同，是否更新配件成本？
      </div>
      <div style="margin-bottom: 12px; color: #999; font-size: 12px;">来源：{{ costDiffSourceId }}</div>
      <n-data-table
        :columns="[
          { title: '配件编号', key: 'part_id', width: 160 },
          { title: '配件名称', key: 'part_name', minWidth: 120 },
          { title: '原单价', key: 'current_value', width: 110, render: (r) => r.current_value != null ? `¥ ${fmtMoney(r.current_value)}` : '-' },
          { title: '更新单价', key: 'new_value', width: 110, render: (r) => h('span', { style: 'color: #d03050; font-weight: 600;' }, `¥ ${fmtMoney(r.new_value)}`) },
        ]"
        :data="costDiffs"
        :bordered="false"
        size="small"
      />
      <template #footer>
        <n-space justify="end">
          <n-button @click="skipCostUpdate" :disabled="costDiffUpdating">跳过</n-button>
          <n-button type="primary" :loading="costDiffUpdating" @click="confirmCostUpdate">确认更新</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NH2, NRadioGroup, NRadio, NModal, NDataTable, NDatePicker } from 'naive-ui'
import { listParts, batchUpdatePartCosts } from '@/api/parts'
import { createPurchaseOrder } from '@/api/purchaseOrders'
import { listSuppliers, createSupplier } from '@/api/suppliers'
import { renderOptionWithImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import { tsToDateStr } from '@/utils/date'
import { useIsMobile } from '@/composables/useIsMobile'

const router = useRouter()
const message = useMessage()
const { isMobile } = useIsMobile()
const vendorName = ref(null)
const note = ref('')
const status = ref('未付款')
const createdAtTs = ref(null)
const items = reactive([{ part_id: null, qty: 1, unit: '个', price: 0, note: '' }])
const submitting = ref(false)
const partOptions = ref([])
const vendorOptions = ref([])

// Cost diff modal
const costDiffVisible = ref(false)
const costDiffs = ref([])
const costDiffSourceId = ref('')
const costDiffUpdating = ref(false)

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const formatAmount = (qty, price) => {
  if (!qty || price == null) return '¥ 0.00'
  return `¥ ${fmtMoney(qty * price)}`
}

const totalAmount = computed(() => {
  return fmtMoney(items.reduce((sum, item) => sum + (item.qty || 0) * (item.price || 0), 0))
})

const addRow = () => {
  items.push({ part_id: null, qty: 1, unit: '个', price: 0, note: '' })
}

const onPartSelect = (item, val) => {
  if (!val) { item.price = 0; item.unit = '个'; return }
  const found = partOptions.value.find((p) => p.value === val)
  item.unit = found?.unit || '个'
  item.price = found?.purchase_cost ?? 0
}

const handleCostDiffs = (data) => {
  if (data.cost_diffs && data.cost_diffs.length > 0) {
    costDiffs.value = data.cost_diffs
    costDiffSourceId.value = data.id
    costDiffVisible.value = true
  } else {
    router.push(`/purchase-orders/${data.id}`)
  }
}

const confirmCostUpdate = async () => {
  costDiffUpdating.value = true
  try {
    await batchUpdatePartCosts({
      updates: costDiffs.value.map((d) => ({
        part_id: d.part_id,
        field: d.field,
        value: d.new_value,
        source_id: costDiffSourceId.value,
      })),
    })
    message.success('配件成本已更新')
    costDiffVisible.value = false
    router.push(`/purchase-orders/${costDiffSourceId.value}`)
  } catch (_) {
    message.error('成本更新失败，请重试')
  } finally {
    costDiffUpdating.value = false
  }
}

const skipCostUpdate = () => {
  costDiffVisible.value = false
  router.push(`/purchase-orders/${costDiffSourceId.value}`)
}

const submit = async () => {
  if (!vendorName.value?.trim()) { message.warning('请输入商家名称'); return }
  if (items.length === 0) { message.warning('请至少添加一条明细'); return }
  if (items.some((i) => !i.part_id)) { message.warning('请选择配件'); return }
  submitting.value = true
  try {
    // Auto-create supplier if new (swallow duplicate 400, rethrow others)
    const isNew = !vendorOptions.value.some((o) => o.value === vendorName.value)
    if (isNew) {
      try { await createSupplier({ name: vendorName.value.trim(), type: 'parts' }) } catch (e) { if (e.response?.status !== 400) throw e }
    }
    const payload = {
      vendor_name: vendorName.value.trim(),
      items,
      status: status.value,
      note: note.value,
    }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createPurchaseOrder(payload)
    message.success('创建成功')
    handleCostDiffs(data)
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
      purchase_cost: p.purchase_cost,
    }))
  }).catch(() => {})
  const vendorsPromise = listSuppliers({ type: 'parts' }).then(({ data }) => {
    vendorOptions.value = data.map((s) => ({ label: s.name, value: s.name }))
  }).catch(() => {})
  await Promise.all([partsPromise, vendorsPromise])
})
</script>

<style scoped>
.items-header {
  padding-bottom: 6px;
  margin-bottom: 10px;
  border-bottom: 1px solid #efeff5;
  font-size: 13px;
  color: #888;
}
</style>
