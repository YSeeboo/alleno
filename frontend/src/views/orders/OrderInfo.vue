<template>
  <div class="fulfillment-page order-workspace">
    <OrderWorkspaceHeader :order-id="orderId" :customer-name="order?.customer_name" :status="data?.status" :created-at="order?.created_at" active="information">
      <n-button :loading="loading" :disabled="busy" @click="load">刷新</n-button>
    </OrderWorkspaceHeader>
    <n-alert v-if="error" type="error" class="wf-notice">{{ error }} <n-button text type="primary" @click="load">重新加载</n-button></n-alert>
    <n-spin :show="loading">
      <OrderInformation v-if="order && data && !error" :order="order" :editable="canEdit" @saved="load" @busy="busy = $event">
        {{ data.managed ? `已全部发货 ${data.completed_items} / ${data.total_items} 项` : '历史实发未核实，不补造出货' }} · {{ data.status }}
      </OrderInformation>
    </n-spin>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { NAlert, NButton, NSpin } from 'naive-ui'
import OrderWorkspaceHeader from '@/components/fulfillment/OrderWorkspaceHeader.vue'
import OrderInformation from '@/components/fulfillment/OrderInformation.vue'
import { getOrder } from '@/api/orders'
import { getFulfillment } from '@/api/fulfillment'

const route = useRoute()
const orderId = computed(() => String(route.params.id))
const order = ref(null), data = ref(null), loading = ref(false), error = ref(''), busy = ref(false)
const canEdit = computed(() => !loading.value && !error.value && ['待生产', '生产中'].includes(data.value?.status))
onBeforeRouteLeave(() => !busy.value)
onBeforeRouteUpdate(() => !busy.value)
let requestId = 0
async function load() {
  const request = ++requestId
  loading.value = true; error.value = ''
  try {
    const [info, summary] = await Promise.all([getOrder(orderId.value), getFulfillment(orderId.value)])
    if (request !== requestId) return
    order.value = info.data; data.value = summary.data
  } catch (e) { if (request === requestId) error.value = e.response?.data?.detail || '加载失败' }
  finally { if (request === requestId) loading.value = false }
}
watch(orderId, () => { order.value = null; data.value = null; load() }, { immediate: true })
</script>
