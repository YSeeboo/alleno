<template>
  <n-card v-if="cols.length > 0" :content-style="collapsed ? 'padding: 0' : undefined">
    <template #header>
      <div class="bm-head" @click="collapsed = !collapsed">
        <span class="chev">{{ collapsed ? '▸' : '▾' }}</span>
        <span class="title">客户分拣</span>
        <span class="status-tag">{{ statusTagText }}</span>
      </div>
    </template>
    <div v-show="!collapsed">
      <!-- Render skeleton — real table comes in next task -->
      <pre class="debug" style="font-size: 11px; background: #f5f5f8; padding: 8px;">
cols: {{ cols.length }}
rows: {{ rows.length }}
placeholder qty: {{ placeholderQtySum }}
</pre>
    </div>
  </n-card>
</template>

<script setup>
import { ref, computed } from 'vue'
import { NCard } from 'naive-ui'

const props = defineProps({
  hcId: { type: String, required: true },
  hcStatus: { type: String, required: true },
  groups: { type: Array, required: true },  // backend breakdown response
})
const emit = defineEmits(['saved'])

const collapsed = ref(false)

// --- Transpose backend groups → rows (customer-major) + cols (jewelry-major) ---

// cols: one entry per jewelry/part group in backend order
const cols = computed(() =>
  (props.groups || []).map((g) => ({
    key: `${g.kind}:${g.jewelry_id}`,
    kind: g.kind,
    jewelry_id: g.jewelry_id,
    jewelry_name: g.jewelry_name,
    total_qty: Number(g.total_qty),
  })),
)

// rows: derived from entries with non-empty customer_name.
// Locked customers first (in their first-seen order), then manual customers
// (also first-seen). Each row aggregates entries by (customer, jewelry).
const rows = computed(() => {
  const order = []     // [customer_name, ...] in display order
  const seen = new Set()
  const isLockedCust = new Map()  // customer_name → boolean (any entry locked?)

  // First pass — locked customers
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      const name = e.customer_name
      if (!name || !e.is_locked) continue
      if (!seen.has(name)) {
        seen.add(name)
        order.push(name)
        isLockedCust.set(name, true)
      }
    }
  }
  // Second pass — manual customers
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      const name = e.customer_name
      if (!name || e.is_locked) continue
      if (!seen.has(name)) {
        seen.add(name)
        order.push(name)
        if (!isLockedCust.has(name)) isLockedCust.set(name, false)
      }
    }
  }

  // Build per-cell aggregates
  return order.map((name) => {
    const cellsByCol = {}
    for (const g of props.groups || []) {
      const colKey = `${g.kind}:${g.jewelry_id}`
      const matchingEntries = (g.entries || []).filter((e) => e.customer_name === name)
      const lockedEntries = matchingEntries.filter((e) => e.is_locked)
      const manualEntries = matchingEntries.filter((e) => !e.is_locked)
      cellsByCol[colKey] = {
        lockedQty: lockedEntries.reduce((s, e) => s + Number(e.qty), 0),
        lockedSources: lockedEntries.map((e) => e.source_order_id).filter(Boolean),
        manualQty: manualEntries.reduce((s, e) => s + Number(e.qty), 0),
        manualEntryIds: manualEntries.map((e) => e.hc_jewelry_item_id),
      }
    }
    const rowSum = Object.values(cellsByCol).reduce(
      (s, c) => s + c.lockedQty + c.manualQty, 0,
    )
    return {
      customer_name: name,
      is_locked_customer: isLockedCust.get(name) || false,
      cells: cellsByCol,
      row_sum: rowSum,
    }
  })
})

// Placeholder entries: customer_name is null/empty, is_locked false
const placeholderEntries = computed(() => {
  const out = []
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      const name = (e.customer_name || '').trim()
      if (!name && !e.is_locked) {
        out.push({ ...e, _col_key: `${g.kind}:${g.jewelry_id}` })
      }
    }
  }
  return out
})

const placeholderQtySum = computed(() =>
  placeholderEntries.value.reduce((s, e) => s + Number(e.qty), 0),
)

// Per-column "assigned" total = sum of all rows' (locked + manual) for that col.
// "Remaining" per col = total_qty - assigned.
const colAssigned = computed(() => {
  const m = {}
  for (const c of cols.value) m[c.key] = 0
  for (const r of rows.value) {
    for (const k of Object.keys(r.cells)) {
      m[k] = (m[k] || 0) + r.cells[k].lockedQty + r.cells[k].manualQty
    }
  }
  return m
})

const totalAssigned = computed(() =>
  Object.values(colAssigned.value).reduce((s, n) => s + n, 0),
)
const totalAll = computed(() =>
  cols.value.reduce((s, c) => s + c.total_qty, 0),
)

const statusTagText = computed(() => {
  if (rows.value.length === 0) {
    return `未分拣 · ${totalAssigned.value}/${totalAll.value}`
  }
  if (props.hcStatus === 'pending') return `pending · 可编辑`
  if (props.hcStatus === 'processing') return `processing · 仅可改客户名 / 删未发出行`
  if (props.hcStatus === 'completed') return `completed · 只读`
  return props.hcStatus
})
</script>

<style scoped>
.bm-head { display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; }
.chev { color: #888; }
.title { font-weight: 600; }
.status-tag { font-size: 11px; color: #b76100; background: #fff5e0; padding: 2px 8px; border-radius: 10px; font-weight: 400; }
.debug { white-space: pre-wrap; }
</style>
