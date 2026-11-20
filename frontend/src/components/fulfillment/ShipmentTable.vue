<template>
  <n-empty v-if="!shipments.length" description="暂无出货记录；生产回收不计为客户出货" class="wf-empty" />
  <div v-else-if="compact" class="ow-shipment-list">
    <article v-for="shipment in shipments" :key="shipment.id" class="ow-shipment-row">
      <span class="ow-shipment-icon" aria-hidden="true">↗</span>
      <div class="ow-shipment-body"><div class="wf-actions"><router-link :to="`/shipments/${shipment.id}`">{{ shipment.id }}</router-link><span class="badge" :class="`badge-${{ confirmed: 'green', draft: 'amber', void: 'gray' }[shipment.status] || 'gray'}`">{{ { confirmed: '已确认出货', draft: '待确认草稿', void: '已作废' }[shipment.status] || shipment.status }}</span></div><p v-for="entry in shipment.lines" :key="entry.order_item_id">{{ entry.product_name }}<span v-if="entry.customer_code"> · {{ entry.customer_code }}</span> · {{ entry.quantity }} {{ entry.unit }}</p><small class="wf-subtext">{{ shipment.tracking || '未填写物流' }}</small></div>
      <time>{{ shipment.created_at?.slice(0, 10) }}</time>
    </article>
  </div>
  <n-data-table v-else :columns="columns" :data="shipments" :bordered="false" :scroll-x="720" />
</template>
<script setup>
import { h } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { NButton, NDataTable, NEmpty } from 'naive-ui'
defineProps({ shipments: { type: Array, default: () => [] }, compact: Boolean })
const router = useRouter()
const columns = [
  { title: '出货单', key: 'id', render: row => h(RouterLink, { to: `/shipments/${row.id}` }, { default: () => row.id }) },
  { title: '客户订单', key: 'order_id', render: row => h(RouterLink, { to: `/orders/${row.order_id}` }, { default: () => row.order_id }) },
  { title: '客户', key: 'customer_name' },
  { title: '状态', key: 'status', render: row => h('span', { class: `badge ${{ confirmed: 'badge-green', draft: 'badge-amber', void: 'badge-gray' }[row.status]}` }, { draft: '草稿', confirmed: '已出货', void: '已作废' }[row.status]) },
  { title: '明细', key: 'lines', render: row => `${row.lines.length} 项` },
  { title: '创建时间', key: 'created_at', render: row => new Date(row.created_at).toLocaleString('zh-CN') },
  { title: '操作', key: 'actions', render: row => h(NButton, { text: true, type: 'primary', onClick: () => router.push(`/shipments/${row.id}`) }, { default: () => '查看详情' }) },
]
</script>
