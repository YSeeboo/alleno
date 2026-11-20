<template>
  <div class="fulfillment-page">
    <div class="page-header"><div class="page-breadcrumb">生产 / <router-link to="/shipments">出货管理</router-link> / 出货详情</div><h2 class="page-title">{{ data?.id || '出货详情' }}</h2><div class="page-divider"></div></div>
    <div class="filter-bar"><n-button text @click="router.push('/shipments')">← 返回出货列表</n-button><span class="wf-muted">{{ data?.customer_name }} · {{ data ? statusLabel[data.status] : '加载中' }}</span><div class="filter-bar-end"><n-button v-if="data?.status === 'draft'" type="error" :disabled="saving" @click="voidDraft">作废草稿</n-button></div></div>
    <n-alert v-if="error" type="error" class="wf-notice">{{ error }}</n-alert>
    <n-spin :show="loading"><template v-if="data">
      <n-alert :type="data.status === 'confirmed' ? 'success' : data.status === 'draft' ? 'warning' : 'info'" class="wf-notice"><strong>{{ data.status === 'confirmed' ? '出货已确认，库存已扣减' : data.status === 'draft' ? '草稿已保存，尚未占库或扣库' : '草稿已作废，无库存变动' }}</strong><br>{{ data.status === 'confirmed' ? '重复确认不会重复扣库；实际退货需要独立凭据，不能只改订单状态回库。' : '最终确认重新校验订单剩余待发与公共库存；草稿不保证届时仍有货。' }}</n-alert>
      <n-card title="实际出货明细" class="wf-section">
        <p class="wf-section-description"><router-link :to="`/orders/${data.order_id}`">{{ data.order_id }}</router-link> · {{ data.customer_name }} · 不要求加工来源关联</p>
        <div class="wf-table-wrap"><n-table :bordered="false" class="wf-table"><thead><tr><th>产品 / 客户货号</th><th>本次实发</th><th>库存凭据</th></tr></thead><tbody><tr v-for="line in data.lines" :key="line.order_item_id"><td><ProductCell :line="line" /></td><td><strong>{{ line.quantity }} {{ line.unit }}</strong></td><td>{{ line.inventory_log_id ? `库存流水 #${line.inventory_log_id}` : '未扣库' }}</td></tr></tbody></n-table></div>
        <n-descriptions :column="1" bordered label-placement="left" style="margin-top:16px">
          <n-descriptions-item label="创建时间">{{ new Date(data.created_at).toLocaleString('zh-CN') }}</n-descriptions-item>
          <n-descriptions-item v-if="data.confirmed_at" label="确认时间">{{ new Date(data.confirmed_at).toLocaleString('zh-CN') }}</n-descriptions-item>
          <n-descriptions-item label="物流">{{ data.tracking || '未填写' }}</n-descriptions-item>
          <n-descriptions-item label="备注">{{ data.note || '无' }}</n-descriptions-item>
        </n-descriptions>
      </n-card>
      <n-card v-if="data.status === 'draft'" title="重新核对并确认" class="wf-section">
        <template #header-extra><n-button text type="primary" :disabled="saving" @click="refresh">刷新库存与待发数量</n-button></template>
        <p class="wf-section-description">优先消耗当前明细预留；不挪用同款其他行或其他客户的预留。</p>
        <n-alert v-for="warning in warnings" :key="warning" type="warning" class="wf-notice">{{ warning }}</n-alert>
        <n-alert v-if="!warnings.length && summary" type="success" :bordered="false" class="wf-notice">当前库存与待发数量校验通过，确认时仍会再次校验。</n-alert>
        <p>实际有货但未入账？<router-link to="/inventory" target="_blank" rel="noopener">登记真实入库 →</router-link> 后刷新，不按缺口自动补库。</p>
        <n-checkbox v-model:checked="checked" :disabled="saving" style="margin-top:16px">我已核对实际货物与数量，确认后将扣减库存。</n-checkbox>
        <div class="wf-dialog-footer"><n-button type="primary" :loading="saving" :disabled="!checked || !summary || warnings.length > 0" @click="confirm">确认实际出货</n-button></div>
      </n-card>
    </template></n-spin>
  </div>
</template>
<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { NAlert, NButton, NCard, NCheckbox, NDescriptions, NDescriptionsItem, NSpin, NTable, useDialog, useMessage } from 'naive-ui'
import { getShipment, getFulfillment, confirmShipment, voidShipment } from '@/api/fulfillment'
import { stockWarnings } from '@/utils/fulfillment'
import ProductCell from '@/components/fulfillment/ProductCell.vue'
const route = useRoute(), dialog = useDialog(), message = useMessage()
const router = useRouter()
const data = ref(null), summary = ref(null), loading = ref(false), saving = ref(false), checked = ref(false), error = ref('')
const statusLabel = { draft: '草稿未扣库', confirmed: '已确认实物出货', void: '已作废' }
const warnings = computed(() => {
  if (!summary.value || !data.value) return ['库存与订单数据尚未加载']
  if (!summary.value.editable) return ['订单当前只读，不能确认此草稿']
  return stockWarnings(summary.value.lines, data.value.lines)
})
let requestId = 0
async function load() {
  const request = ++requestId
  checked.value = false; summary.value = null; loading.value = true; error.value = ''
  try { const response = await getShipment(route.params.id); if (request !== requestId) return; data.value = response.data; if (data.value.status === 'draft') { const state = await getFulfillment(data.value.order_id); if (request === requestId) summary.value = state.data } }
  catch (e) { if (request === requestId) error.value = e.response?.data?.detail || '加载失败' }
  finally { if (request === requestId) loading.value = false }
}
async function refresh() { try { await load() } catch (_) { /* Displayed in load. */ } }
async function confirm() { if (!checked.value || saving.value) return; saving.value = true; try { await confirmShipment(data.value.id); message.success('实际出货已确认'); await load() } catch (e) { error.value = e.response?.data?.detail || '确认失败'; checked.value = false } finally { saving.value = false } }
function voidDraft() { dialog.warning({ title: '作废出货草稿', content: '此操作不改变库存，不影响已确认的其他出货。', positiveText: '作废草稿', negativeText: '返回', onPositiveClick: async () => { saving.value = true; try { await voidShipment(data.value.id); await load() } finally { saving.value = false } } }) }
onBeforeRouteLeave(() => !saving.value)
watch(() => route.params.id, () => { data.value = null; summary.value = null; load() }, { immediate: true })
</script>
