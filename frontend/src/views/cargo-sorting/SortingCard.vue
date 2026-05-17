<template>
  <div class="card">
    <div class="head">
      <div class="receipt-code">{{ order.receipt_code || '—' }}</div>
      <span class="badge" :class="badgeClass">{{ badgeText }}</span>
    </div>
    <div class="meta">{{ order.supplier_name }} · {{ order.breakdown.length }} 个饰品</div>

    <div
      v-for="g in order.breakdown"
      :key="g.jewelry_id"
      class="jewelry-row"
    >
      <div class="thumb-wrap">
        <n-image
          :src="g.jewelry_image || ''"
          :preview-src="g.jewelry_image || ''"
          :show-toolbar-tooltip="false"
          object-fit="cover"
          class="thumb"
          :fallback-src="placeholder"
        />
      </div>
      <div class="info">
        <div class="name">{{ g.jewelry_name }}</div>
        <div class="id">{{ g.jewelry_id }}</div>
        <div class="customers">
          <div v-for="(e, idx) in g.entries" :key="idx" class="customer-line">
            {{ e.customer_name }} ×{{ formatQty(e.qty) }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { NImage } from 'naive-ui'

const props = defineProps({
  order: { type: Object, required: true },
})

const placeholder =
  'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72"><rect width="72" height="72" fill="%23f3f4f6"/><text x="50%" y="55%" text-anchor="middle" font-size="11" fill="%239ca3af">无图</text></svg>'

const STATUS_TEXT = {
  pending: '待发出',
  processing: '已发出',
  completed: '已完成',
}

const badgeText = computed(() => STATUS_TEXT[props.order.status] || props.order.status)
const badgeClass = computed(() =>
  props.order.status === 'completed' ? 'badge-green' : 'badge-gray'
)

const formatQty = (q) => (Number.isInteger(q) ? q : q.toFixed(2).replace(/\.?0+$/, ''))
</script>

<style scoped>
.card {
  background: white;
  border-radius: 14px;
  padding: 14px;
  margin-top: 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
}
.receipt-code {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
  letter-spacing: .5px;
}
.badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 4px;
}
.badge-green { background: #d1fae5; color: #065f46; }
.badge-gray { background: #f3f4f6; color: #6b7280; }
.meta { font-size: 12px; color: #6b7280; }
.jewelry-row {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e5e7eb;
}
.thumb-wrap {
  flex-shrink: 0;
  width: 72px;
  height: 72px;
  cursor: pointer;
}
.thumb {
  width: 72px !important;
  height: 72px !important;
  border-radius: 8px;
}
.info { flex: 1; min-width: 0; }
.name { font-size: 14px; font-weight: 600; color: #111827; }
.id { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.customers { margin-top: 6px; }
.customer-line {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.7;
}
</style>
