<template>
  <div class="page-breadcrumb ow-breadcrumb"><router-link to="/orders">生产 / 订单管理</router-link><span>/</span>{{ orderId }}</div>
  <header class="ow-head">
    <div class="ow-heading">
      <div class="ow-title-line"><h2 class="page-title">订单 {{ orderId }}</h2><span v-if="status" class="ow-status" :class="{ 'is-green': status === '已完成', 'is-muted': status === '已取消' }">{{ status }}</span></div>
      <div class="ow-subtitle"><strong>{{ customerName || '—' }}</strong><template v-if="createdAt"><span>·</span><span>创建于 {{ createdAt.slice(0, 10) }}</span></template></div>
    </div>
    <div class="wf-actions ow-head-actions">
      <n-button text size="small" @click="router.push(summaryReturn || '/orders')">← {{ summaryReturn ? '返回手工汇总' : '返回列表' }}</n-button>
      <slot />
    </div>
  </header>
  <n-tabs :value="active" type="line" class="wf-workspace-tabs" aria-label="本订单工作区" @update:value="openTab">
    <n-tab name="fulfillment">商品详情</n-tab>
    <n-tab name="production">生产安排</n-tab>
    <n-tab name="information">订单信息</n-tab>
  </n-tabs>
</template>
<script setup>
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'
import { getHandcraftSummaryReturn } from '@/utils/handcraftNavigation'
import { NButton, NTab, NTabs } from 'naive-ui'
const props = defineProps({ orderId: String, customerName: String, active: String, status: String, createdAt: String })
const router = useRouter()
const route = useRoute()
const summaryReturn = computed(() => getHandcraftSummaryReturn(route.query))
function openTab(tab) {
  const suffix = { fulfillment: '', production: '/production', information: '/information' }[tab]
  router.push({ path: `/orders/${props.orderId}${suffix}`, query: route.query })
}
</script>
<style src="../../styles/order-workspace.css"></style>
