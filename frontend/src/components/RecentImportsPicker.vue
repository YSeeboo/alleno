<template>
  <div>
    <div v-if="batches.length === 0" class="empty">
      <p style="font-size: 14px; color: #6b7280;">没有最近导入的批次</p>
      <p style="font-size: 12px; color: #9ca3af; margin-top: 4px;">
        到「商品 / 配件管理」页面用 Excel 导入一批后，这里就能批量挂入。
      </p>
    </div>

    <div v-else>
      <!-- Batch selector -->
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
        <label style="font-size: 13px; color: #4b5563; min-width: 38px;">批次</label>
        <n-select
          v-model:value="selectedBatchId"
          :options="batchOptions"
          style="flex: 1;"
        />
      </div>

      <!-- Helper hint -->
      <div class="hint">
        📦 数量沿用导入时的"入库数量" · 修改高亮 · 已存在的明细将累加
      </div>

      <!-- Select-all + count -->
      <div class="select-all-bar">
        <n-checkbox
          :checked="allEligibleSelected"
          :indeterminate="someEligibleSelected && !allEligibleSelected"
          @update:checked="toggleSelectAll"
        >
          全选
        </n-checkbox>
        <span class="count">已选 {{ checkedCount }} / {{ rows.length }}</span>
      </div>

      <!-- Rows -->
      <div class="part-list">
        <div v-for="row in rows" :key="row.part_id" class="part-item">
          <n-checkbox v-model:checked="row._checked" />
          <img v-if="row.image" :src="row.image" class="thumb" />
          <div v-else class="thumb-empty">无图</div>
          <div class="meta">
            <div class="part-id">{{ row.part_id }}</div>
            <div class="part-name" :title="row.name">{{ row.name }}</div>
          </div>
          <div class="qty-cell">
            <n-input-number
              v-model:value="row.qty"
              :min="0"
              :precision="0"
              :step="1"
              size="small"
              :show-button="false"
              :class="{ modified: row.qty !== row.imported_qty }"
              style="width: 72px;"
            />
            <span class="unit">{{ row.unit || '个' }}</span>
          </div>
          <span v-if="row._existingItemId != null" class="badge-existing">已在本单</span>
        </div>
      </div>

      <div class="legend">
        <span><span class="dot dot-modified"></span>已修改</span>
        <span><span class="dot dot-existing"></span>已在本单（累加）</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { NSelect, NCheckbox, NInputNumber } from 'naive-ui'
import { getActiveBatches, getBatchById } from '@/utils/recentImports'

const props = defineProps({
  // Existing items in the current handcraft order — used to mark "已在本单"
  // and to calculate the post-attach qty for accumulation.
  // Shape: [{ id, part_id, qty, ... }]
  existingItems: { type: Array, default: () => [] },
})

const emit = defineEmits(['change'])

// --- Batches ---
const batches = ref(getActiveBatches())
const selectedBatchId = ref(batches.value[0]?.batch_id ?? null)

const batchOptions = computed(() =>
  batches.value.map((b) => {
    const date = new Date(b.imported_at)
    const pad = (n) => String(n).padStart(2, '0')
    const label =
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
      `${pad(date.getHours())}:${pad(date.getMinutes())} · ${b.parts.length} 件` +
      (b.operator ? ` · ${b.operator}` : '')
    return { label, value: b.batch_id }
  }),
)

// --- Rows (one per part in the selected batch) ---
const rows = ref([])

const refreshRows = () => {
  if (!selectedBatchId.value) {
    rows.value = []
    return
  }
  const batch = getBatchById(selectedBatchId.value)
  if (!batch) {
    rows.value = []
    return
  }
  rows.value = batch.parts.map((p) => {
    const existing = props.existingItems.find((it) => it.part_id === p.part_id)
    return {
      part_id: p.part_id,
      name: p.name,
      image: p.image,
      unit: p.unit || '个',
      imported_qty: p.imported_qty,
      qty: p.imported_qty,
      _existingItemId: existing ? existing.id : null,
      _existingQty: existing ? existing.qty : null,
      _checked: !existing, // default: tick only if not already in the order
    }
  })
}

watch(selectedBatchId, refreshRows, { immediate: true })

// existingItems can change while the modal is open (sibling actions, polling,
// loadData after a partial save). Patch markers in place so the user's edited
// qty and checkbox state survive.
watch(() => props.existingItems, (newItems) => {
  for (const row of rows.value) {
    const existing = newItems.find((it) => it.part_id === row.part_id)
    row._existingItemId = existing ? existing.id : null
    row._existingQty = existing ? existing.qty : null
  }
}, { deep: true })

// --- Selection helpers ---
const eligibleRows = computed(() => rows.value.filter((r) => r._existingItemId == null))
const checkedCount = computed(() => rows.value.filter((r) => r._checked).length)
const allEligibleSelected = computed(() =>
  eligibleRows.value.length > 0 &&
  eligibleRows.value.every((r) => r._checked),
)
const someEligibleSelected = computed(() =>
  eligibleRows.value.some((r) => r._checked),
)

const toggleSelectAll = (checked) => {
  for (const r of eligibleRows.value) r._checked = checked
  bubble()
}

// Watch row changes (qty, _checked) — emit summary up so the modal footer can
// show "新增 X · 累加 Y · 共 Z 件" and enable/disable the submit button.
watch(rows, bubble, { deep: true })

function bubble() {
  const checked = rows.value.filter((r) => r._checked)
  const newOnes = checked.filter((r) => r._existingItemId == null)
  const updateOnes = checked.filter((r) => r._existingItemId != null)
  const totalQty = checked.reduce((s, r) => s + (Number(r.qty) || 0), 0)
  const hasZeroQty = checked.some((r) => !r.qty || r.qty <= 0)
  emit('change', {
    rows: checked.map((r) => ({
      part_id: r.part_id,
      qty: Number(r.qty),
      unit: r.unit,
      _existingItemId: r._existingItemId,
      _existingQty: r._existingQty,
    })),
    newCount: newOnes.length,
    updateCount: updateOnes.length,
    totalQty,
    hasZeroQty,
  })
}
</script>

<style scoped>
.empty {
  padding: 36px 0;
  text-align: center;
}
.hint {
  background: #f7f9fa;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 10px;
}
.select-all-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 0; border-bottom: 1px solid #efeff5;
  margin-bottom: 4px;
}
.count { font-size: 12px; color: #888; }

.part-list {
  max-height: 360px;
  overflow-y: auto;
}
.part-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 4px; border-bottom: 1px solid #f5f5f5;
}
.part-item:hover { background: #fafafa; }
.thumb, .thumb-empty {
  width: 36px; height: 36px; border-radius: 4px; flex-shrink: 0;
  object-fit: cover;
}
.thumb-empty {
  border: 1px dashed #d9d9d9; background: #f5f5f5; color: #ccc;
  font-size: 10px; display: inline-flex; align-items: center; justify-content: center;
}
.meta { flex: 1; min-width: 0; }
.part-id { font-size: 12px; color: #888; font-family: ui-monospace, monospace; }
.part-name {
  font-size: 13.5px; color: #1f2937; margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.qty-cell {
  display: flex; align-items: center; gap: 4px; flex-shrink: 0;
}
.unit { font-size: 12px; color: #6b7280; min-width: 18px; }
.badge-existing {
  background: #fef3c7; color: #92400e;
  font-size: 10.5px; padding: 2px 6px; border-radius: 8px;
  flex-shrink: 0; white-space: nowrap;
}
:deep(.modified .n-input__input-el) {
  background: #fffbeb;
}
:deep(.modified .n-input) {
  border-color: #f0a020;
}

.legend {
  margin-top: 8px; font-size: 11px; color: #888;
  display: flex; gap: 14px; align-items: center;
}
.dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 2px; margin-right: 4px; vertical-align: middle;
}
.dot-modified { background: #fffbeb; border: 1px solid #f0a020; }
.dot-existing { background: #fef3c7; border: 1px solid #fcd34d; }
</style>
