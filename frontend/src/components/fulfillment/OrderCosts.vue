<template>
  <OrderSection title="费用与成本">
    <template #header-extra><n-button text type="primary" size="small" @click="showDetails = true">查看明细</n-button></template>
    <div class="ow-panel ow-cost-panel">
      <div class="ow-cost-row"><span>商品金额</span><strong>¥{{ fmtMoney(Number(order.total_amount || 0)) }}</strong></div>
      <div class="ow-cost-row"><span>包装费 <n-button v-if="editable" text type="primary" size="tiny" @click="showDetails = true">编辑</n-button></span><strong>¥{{ fmtMoney(Number(order.packaging_cost || 0)) }}</strong></div>
      <div class="ow-cost-row"><span>实际成本</span><span class="wf-muted">待核算</span></div>
      <div class="ow-cost-note"><span class="ow-cost-badge">{{ snapshot?.has_incomplete_cost ? '成本不完整' : '成本待核算' }}</span>加工与实耗未完整核算，暂不展示实际利润。<p v-if="error" role="alert">{{ error }} <n-button text size="tiny" @click="load">重试</n-button></p></div>
    </div>
  </OrderSection>
  <n-modal v-model:show="showDetails" preset="card" title="费用与成本明细" class="order-workspace" :mask-closable="!saving" :closable="!saving" :close-on-esc="!saving" style="width:min(960px,calc(100vw - 24px))">
    <n-space align="center"><span>包装费</span><n-input-number v-model:value="packaging" :min="0" :precision="2" :disabled="!editable || saving" style="width:160px" /><n-button v-if="editable" :loading="saving" @click="save">保存包装费</n-button></n-space>
    <n-alert type="info" :bordered="false" class="wf-notice" style="margin-top:16px">BOM 理论成本与实际发料、加工结算不同。下方保留已有成本快照供追溯，不代表本单实际成本已全部结清。</n-alert>
    <n-alert v-if="error" type="warning">{{ error }} <n-button text @click="load">重试</n-button></n-alert>
    <template v-else-if="snapshot">
      <n-alert v-if="snapshot.has_incomplete_cost" type="warning" class="wf-notice">成本不完整，不展示利润。</n-alert>
      <n-descriptions :column="isMobile ? 1 : 3" bordered>
        <n-descriptions-item label="快照成本（参考）">{{ fmtMoney(snapshot.total_cost) }}</n-descriptions-item>
        <n-descriptions-item label="快照售价">{{ snapshot.total_amount != null ? fmtMoney(snapshot.total_amount) : '—' }}</n-descriptions-item>
        <n-descriptions-item label="成本结算">待核算实际发料与加工费用</n-descriptions-item>
      </n-descriptions>
      <div class="wf-table-wrap"><n-data-table :columns="columns" :data="snapshot.items || []" :bordered="false" :row-key="r => r.id" /></div>
    </template>
    <n-empty v-else description="暂无成本快照，实际成本待核算" class="wf-empty" />
  </n-modal>
</template>
<script setup>
import { h, ref, watch } from 'vue'
import { NAlert, NButton, NDataTable, NDescriptions, NDescriptionsItem, NEmpty, NInputNumber, NModal, NSpace, useMessage } from 'naive-ui'
import OrderSection from '@/components/fulfillment/OrderSection.vue'
import { getCostSnapshot, updatePackagingCost } from '@/api/orders'
import { useIsMobile } from '@/composables/useIsMobile'
import { fmtMoney } from '@/utils/ui'
const props = defineProps({ order: { type: Object, required: true }, editable: Boolean })
const emit = defineEmits(['saved', 'busy']), message = useMessage(), { isMobile } = useIsMobile()
const packaging = ref(0), snapshot = ref(null), saving = ref(false), error = ref(''), showDetails = ref(false)
const bomColumns = [{ title: '配件', key: 'part_id' }, { title: 'BOM 单件用量', key: 'qty_per_unit' }, { title: '单位成本（参考）', key: 'unit_cost' }, { title: '小计（参考）', key: 'subtotal' }]
const columns = [
  { type: 'expand', expandable: row => !!row.bom_details?.length, renderExpand: row => h(NDataTable, { columns: bomColumns, data: row.bom_details, bordered: false }) },
  { title: '商品', key: 'jewelry_name', render: row => row.jewelry_name || row.part_name || '—' },
  { title: '数量', key: 'quantity' }, { title: '单价', key: 'unit_price' }, { title: '手工费（参考）', key: 'handcraft_cost' }, { title: '总成本（参考）', key: 'jewelry_total_cost' },
]
let request = 0
async function load() {
  const id = ++request; error.value = ''; snapshot.value = null
  try { const response = await getCostSnapshot(props.order.id); if (id === request) snapshot.value = response.data }
  catch (e) { if (id === request && e.response?.status !== 404) error.value = '成本快照加载失败，不能当作无成本' }
}
watch(() => props.order, value => { packaging.value = Number(value.packaging_cost || 0); load() }, { immediate: true })
async function save() {
  if (saving.value || !props.editable) return
  if (packaging.value == null || !Number.isFinite(packaging.value)) return message.warning('请填写有效包装费')
  saving.value = true; emit('busy', true)
  try { await updatePackagingCost(props.order.id, { packaging_cost: packaging.value }); emit('saved'); message.success('包装费已保存') }
  catch (_) { /* API interceptor displays failure. */ }
  finally { saving.value = false; emit('busy', false) }
}
</script>
