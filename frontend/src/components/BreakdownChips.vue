<template>
  <div class="breakdown-chips">
    <span
      v-for="e in entries"
      :key="e.hc_jewelry_item_id"
      class="chip"
      :class="{ 'chip--manual': e.source === 'manual' }"
      :title="chipTitle(e)"
    >
      <span class="chip__name">{{ e.customer_name || '—' }}</span>
      <span class="chip__qty">{{ formatQty(e.qty) }}</span>
      <span class="chip__source">
        <template v-if="e.source === 'order'">↗ {{ e.source_order_id }}</template>
        <template v-else>手填</template>
      </span>
    </span>
    <span v-if="!entries.length" class="empty">— 未分拣</span>
  </div>
</template>

<script setup>
defineProps({
  entries: { type: Array, required: true },
})

function formatQty(n) {
  const num = Number(n)
  return Number.isInteger(num) ? String(num) : num.toFixed(2)
}

function chipTitle(e) {
  return e.source === 'order'
    ? `来自订单 ${e.source_order_id}，需到订单详情修改`
    : 'HC 详情手填，可在此处编辑'
}
</script>

<style scoped>
.breakdown-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.chip {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 2px 9px;
  background: #f5f5f8;
  border: 1px solid #e0e0e6;
  border-radius: 3px;
  font-size: 13px;
  line-height: 20px;
}
.chip--manual {
  background: #eef0fe;
  border-color: #e0e3fc;
}
.chip__name {
  color: rgba(0, 0, 0, 0.88);
}
.chip__qty {
  font-family: "SF Mono", Menlo, monospace;
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
}
.chip__source {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.3);
  margin-left: 2px;
  padding-left: 6px;
  border-left: 1px solid #e0e0e6;
}
.chip--manual .chip__source {
  color: #4338ca;
  border-left-color: #e0e3fc;
}
.empty {
  color: rgba(0, 0, 0, 0.45);
  font-size: 13px;
}
</style>
