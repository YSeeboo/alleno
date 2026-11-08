<template>
  <n-alert v-if="order?.archived_at" type="warning" title="历史归档 · 不代表全部收回" style="margin-bottom: 16px;">
    <div>本单已退出日常待处理列表。原始数量、库存及付款信息保持不变；不支持继续发出、收回或修改数量。</div>
    <div>归档时间：{{ order.archived_at.replace('T', ' ') }}；操作人：{{ order.archived_by || '—' }}</div>
    <div>原因：{{ order.archive_reason || '—' }}</div>
  </n-alert>
</template>

<script setup>
import { NAlert } from 'naive-ui'

defineProps({ order: Object })
</script>
