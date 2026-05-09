<script setup>
import { ref, computed, watch } from 'vue'
import {
  NModal, NButton, NCheckbox, NSwitch, NTag, NSpace, NPopconfirm,
  NSpin, NTooltip, NInputNumber, NSelect, useMessage,
} from 'naive-ui'
import {
  getHandcraftPicking,
  markHandcraftPicked,
  unmarkHandcraftPicked,
  resetHandcraftPicking,
  downloadHandcraftPickingPdf,
  upsertHandcraftPickingWeight,
  deleteHandcraftPickingWeight,
  upsertHandcraftPickingActualQty,
  deleteHandcraftPickingActualQty,
} from '@/api/handcraft'
import { useIsMobile } from '@/composables/useIsMobile'

const { isMobile } = useIsMobile()

const props = defineProps({
  show: { type: Boolean, required: true },
  orderId: { type: String, required: true },
  status: { type: String, required: true },  // pending / processing / completed
})
const emit = defineEmits(['update:show'])

const message = useMessage()
const loading = ref(false)
const data = ref(null)
const onlyUnpicked = ref(false)
const exporting = ref(false)

// Prefer the just-loaded status over props.status — covers the case where
// another tab transitioned the order out of pending while this modal was open.
const readonly = computed(
  () => (data.value?.status ?? props.status) !== 'pending',
)

const displayGroups = computed(() => {
  if (!data.value) return []
  // Drop empty groups (composite parts with no BOM) so the user never sees a
  // header row with nothing under it. PDF export already does this.
  const groups = data.value.groups.filter((g) => g.rows.length > 0)
  if (!onlyUnpicked.value) return groups
  return groups
    .map((g) => ({ ...g, rows: g.rows.filter((r) => !r.picked) }))
    .filter((g) => g.rows.length > 0)
})

async function load() {
  loading.value = true
  try {
    const resp = await getHandcraftPicking(props.orderId)
    data.value = resp.data
    // Ensure each row has a stable weight_unit fallback for the unit selector
    for (const g of data.value.groups) {
      for (const r of g.rows) {
        if (!r.weight_unit) r.weight_unit = 'kg'
      }
    }
  } catch (err) {
    message.error(err.response?.data?.detail || '加载配货数据失败')
    emit('update:show', false)
  } finally {
    loading.value = false
  }
}

watch(() => props.show, (v) => {
  if (v) {
    data.value = null
    onlyUnpicked.value = false
    load()
  }
})

async function toggleRow(row) {
  if (readonly.value) return
  const prev = row.picked
  row.picked = !prev
  data.value.progress.picked += row.picked ? 1 : -1
  try {
    const fn = row.picked ? markHandcraftPicked : unmarkHandcraftPicked
    await fn(props.orderId, row.part_item_id, row.atom_part_id)
  } catch (err) {
    row.picked = prev
    data.value.progress.picked += prev ? 1 : -1
    message.error(err.response?.data?.detail || '操作失败')
  }
}

function onWeightFocus(row) {
  // Snapshot the value at focus time so onWeightBlur can decide whether a
  // DELETE is even necessary. Without this, blurring an empty input on a
  // never-set row would fire a no-op DELETE on every focus cycle.
  row._weightAtFocus = row.weight
}

async function onWeightBlur(row) {
  if (readonly.value) return
  const w = row.weight
  const prior = row._weightAtFocus
  row._weightAtFocus = undefined
  try {
    if (w == null || Number(w) <= 0) {
      // Only DELETE when the row actually had a weight before this edit.
      // Empty-blur on a never-set row is a no-op (avoid spurious traffic).
      const hadPrior = prior != null && Number(prior) > 0
      if (!hadPrior) {
        row.weight = null
        return
      }
      await deleteHandcraftPickingWeight(
        props.orderId,
        row.part_item_id,
        row.atom_part_id,
      )
      row.weight = null
    } else {
      const unit = row.weight_unit || 'kg'
      await upsertHandcraftPickingWeight(
        props.orderId,
        row.part_item_id,
        row.atom_part_id,
        Number(w),
        unit,
      )
      row.weight_unit = unit
    }
  } catch (err) {
    message.error(err.response?.data?.detail || '保存重量失败')
  }
}

async function onWeightUnitChange(row, unit) {
  row.weight_unit = unit
  if (readonly.value) return
  if (row.weight != null && Number(row.weight) > 0) {
    try {
      await upsertHandcraftPickingWeight(
        props.orderId,
        row.part_item_id,
        row.atom_part_id,
        Number(row.weight),
        unit,
      )
    } catch (err) {
      message.error(err.response?.data?.detail || '保存重量单位失败')
    }
  }
}

function onActualQtyFocus(row) {
  row._actualAtFocus = row.actual_qty
}

async function onActualQtyBlur(group, row) {
  if (readonly.value) return
  const fresh = row._localActualQty
  const prev = row._actualAtFocus
  const isClear =
    fresh == null ||
    fresh === '' ||
    Number(fresh) <= 0 ||
    Number(fresh) === Number(row.needed_qty)

  try {
    if (isClear) {
      if (prev != null) {
        await deleteHandcraftPickingActualQty(
          props.orderId,
          row.part_item_id,
          row.atom_part_id,
        )
      }
      row.actual_qty = null
    } else {
      const resp = await upsertHandcraftPickingActualQty(
        props.orderId,
        row.part_item_id,
        row.atom_part_id,
        Number(fresh),
      )
      row.actual_qty = resp.data.actual_qty
    }
    // Recompute group total locally to mirror server (server-sent value
    // becomes stale after the per-row mutation)
    group.total_needed_qty = group.rows.reduce(
      (s, x) => s + (x.actual_qty != null ? Number(x.actual_qty) : Number(x.needed_qty)),
      0,
    )
  } catch (err) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    row._localActualQty = undefined
  }
}

async function doReset() {
  try {
    await resetHandcraftPicking(props.orderId)
    await load()
    message.success('已重置所有勾选')
  } catch (err) {
    message.error(err.response?.data?.detail || '重置失败')
  }
}

async function doExport() {
  exporting.value = true
  try {
    const resp = await downloadHandcraftPickingPdf(props.orderId)
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `手工单配货清单_${props.orderId}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    let detail = '导出失败'
    if (err.response?.data instanceof Blob) {
      try {
        const text = await err.response.data.text()
        const parsed = JSON.parse(text)
        detail = parsed.detail || detail
      } catch { /* fallthrough */ }
    } else {
      detail = err.response?.data?.detail || detail
    }
    message.error(detail)
  } finally {
    exporting.value = false
  }
}

function fmtQty(v) {
  if (v == null) return '-'
  const f = Number(v)
  if (Number.isNaN(f)) return String(v)
  const r = parseFloat(f.toPrecision(12))
  if (r === Math.trunc(r)) return String(Math.trunc(r))
  return r.toString()
}

const SUGGESTED_TOOLTIP_RULES = {
  small:  { ratio: 0.02, floor: 50, label: '小件' },
  medium: { ratio: 0.01, floor: 15, label: '中件' },
}

const SIZE_TIER_LABEL = {
  small: '小件',
  medium: '中件',
}

function suggestedTooltip(group) {
  const rule = SUGGESTED_TOOLTIP_RULES[group.size_tier] || SUGGESTED_TOOLTIP_RULES.small
  return `${rule.label}规则: max(${rule.floor}, 理论×${rule.ratio * 100}%) | 建议数量为 ceil(理论) + ceil(buffer)`
}

function groupAllPicked(g) {
  return g.rows.length > 0 && g.rows.every((r) => r.picked)
}

const WEIGHT_UNIT_OPTIONS = [
  { label: 'kg', value: 'kg' },
  { label: 'g',  value: 'g' },
]
</script>

<template>
  <n-modal
    :show="show"
    @update:show="(v) => emit('update:show', v)"
    preset="card"
    :style="{ width: isMobile ? '95vw' : '1040px', maxWidth: '95vw' }"
    :title="`配货模拟 · 手工单 ${orderId}`"
  >
    <n-spin :show="loading">
      <div v-if="data">
        <div class="header-row">
          <div>
            商家：<b>{{ data.supplier_name }}</b>
            <span class="progress">
              进度：{{ data.progress.picked }} / {{ data.progress.total }} 已完成
            </span>
            <n-tag v-if="readonly" size="small" type="warning" style="margin-left: 12px;">
              只读 ({{ data.status === 'processing' ? '处理中' : '已完成' }})
            </n-tag>
          </div>
          <n-space>
            <span>
              只看未完成
              <n-switch v-model:value="onlyUnpicked" size="small" />
            </span>
            <n-button
              v-if="!readonly"
              type="primary"
              :loading="exporting"
              @click="doExport"
            >
              导出 PDF
            </n-button>
            <n-popconfirm v-if="!readonly" @positive-click="doReset">
              <template #trigger>
                <n-button :disabled="readonly">重置勾选</n-button>
              </template>
              确认清空本手工单的所有勾选记录？
            </n-popconfirm>
          </n-space>
        </div>

        <div class="table-scroll">
          <table class="picking-table">
            <thead>
              <tr>
                <th class="col-source">配件 / 来源</th>
                <th class="col-weight">重量</th>
                <th class="col-num">实际</th>
                <th class="col-num">建议</th>
                <th class="col-num">库存</th>
                <th class="col-num">已配</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="g in displayGroups" :key="g.atom_part_id">
                <tr
                  class="group-header"
                  :class="{ 'group-all-picked': groupAllPicked(g) }"
                >
                  <td class="col-source">
                    <div class="group-cell">
                      <img v-if="g.atom_part_image" :src="g.atom_part_image" class="group-img" />
                      <div v-else class="group-img placeholder" />
                      <div class="group-meta">
                        <div class="group-name-line">
                          <span class="group-name">{{ g.atom_part_name }}</span>
                          <n-tag size="tiny" type="default" :bordered="false" style="margin-left: 6px;">
                            {{ SIZE_TIER_LABEL[g.size_tier] || '小件' }}
                          </n-tag>
                        </div>
                        <div class="group-id">{{ g.atom_part_id }}</div>
                      </div>
                    </div>
                  </td>
                  <td class="col-weight"></td>
                  <td class="col-num">合计 {{ fmtQty(g.total_needed_qty) }}</td>
                  <td class="col-num suggested">
                    <n-tooltip trigger="hover">
                      <template #trigger>
                        <span>{{ g.total_suggested_qty }}</span>
                      </template>
                      {{ suggestedTooltip(g) }}
                    </n-tooltip>
                  </td>
                  <td
                    class="col-num"
                    :class="{ 'stock-low': g.current_stock < g.total_suggested_qty }"
                  >
                    {{ fmtQty(g.current_stock) }}
                  </td>
                  <td class="col-num group-progress">
                    {{ g.rows.filter((r) => r.picked).length }}/{{ g.rows.length }} 已配
                  </td>
                </tr>
                <tr
                  v-for="r in g.rows"
                  :key="`${r.part_item_id}-${r.atom_part_id}`"
                  :class="{ 'row-picked': r.picked }"
                >
                  <td class="col-source">
                    <div class="source-cell">
                      <span class="source-qty">
                        qty {{ fmtQty(r.qty) }}
                        <span v-if="r.bom_qty != null" class="source-bom">
                          · bom {{ fmtQty(r.bom_qty) }}
                        </span>
                      </span>
                      <n-tag
                        v-if="r.is_composite_expansion && r.parent_composite_name"
                        size="tiny"
                        type="default"
                        :bordered="false"
                        class="composite-badge"
                      >
                        来自 {{ r.parent_composite_name }} atom
                      </n-tag>
                    </div>
                  </td>
                  <td class="col-weight">
                    <div class="weight-cell" @click.stop>
                      <n-input-number
                        v-model:value="r.weight"
                        :precision="4"
                        :min="0"
                        :show-button="false"
                        :disabled="readonly"
                        size="small"
                        placeholder="-"
                        class="weight-input"
                        @focus="onWeightFocus(r)"
                        @blur="onWeightBlur(r)"
                      />
                      <n-select
                        :value="r.weight_unit || 'kg'"
                        :options="WEIGHT_UNIT_OPTIONS"
                        :disabled="readonly"
                        size="small"
                        class="weight-unit"
                        @update:value="(v) => onWeightUnitChange(r, v)"
                      />
                    </div>
                  </td>
                  <td class="col-num" @click.stop>
                    <n-input-number
                      :value="r.actual_qty ?? r.needed_qty"
                      :precision="4"
                      :show-button="false"
                      :min="0"
                      :disabled="readonly"
                      size="small"
                      class="actual-qty-input"
                      @focus="onActualQtyFocus(r)"
                      @blur="onActualQtyBlur(g, r, $event)"
                      @update:value="(v) => { r._localActualQty = v }"
                    />
                  </td>
                  <td class="col-num suggested">
                    <n-tooltip v-if="r.suggested_qty != null" trigger="hover">
                      <template #trigger>
                        <span>{{ r.suggested_qty }}</span>
                      </template>
                      {{ suggestedTooltip(g) }}
                    </n-tooltip>
                    <span v-else class="dim">-</span>
                  </td>
                  <td class="col-num"></td>
                  <td class="col-num" @click.stop>
                    <n-checkbox
                      :checked="r.picked"
                      :disabled="readonly"
                      @update:checked="toggleRow(r)"
                    />
                  </td>
                </tr>
              </template>
              <tr v-if="displayGroups.length === 0">
                <td colspan="6" class="empty">没有数据</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="footer-note">
          多人同时操作时，最后一次保存会覆盖之前的勾选/重量记录。
        </div>
      </div>
    </n-spin>
  </n-modal>
</template>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.progress {
  margin-left: 20px;
  color: #4361ee;
  font-weight: 500;
}
.table-scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.picking-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 760px;
}
.picking-table th,
.picking-table td {
  border: 1px solid #eee;
  padding: 8px;
  vertical-align: middle;
}
.picking-table thead th {
  background: #fafbfc;
  font-weight: 600;
}
.picking-table .col-num {
  text-align: center;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.picking-table .col-weight {
  width: 200px;
}
.picking-table .col-source {
  min-width: 240px;
}
.picking-table .suggested {
  color: #1890ff;
  font-weight: 600;
}
.picking-table .stock-low {
  color: #d03050;
  font-weight: 600;
}

/* Group header (orange tint) */
.picking-table .group-header td {
  background: #fff4e6;
  font-weight: 500;
  font-size: 13px;
}
.picking-table .group-header.group-all-picked td {
  background: #f0fbf3;
}
.group-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.group-img {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
  background: #fff;
}
.group-img.placeholder {
  background: #f0f0f0;
}
.group-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.group-name-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}
.group-name {
  font-weight: 600;
}
.group-id {
  color: #999;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}
.group-progress {
  color: #555;
  font-size: 12px;
}

/* Source row */
.source-cell {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding-left: 50px;  /* indent under group image */
  color: #555;
}
.source-qty {
  font-variant-numeric: tabular-nums;
}
.source-bom {
  color: #999;
}
.composite-badge {
  background: #f5f5f5;
  color: #888;
}

/* Weight cell */
.weight-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}
.weight-input {
  flex: 1 1 auto;
  min-width: 0;
}
.weight-unit {
  flex: 0 0 64px;
  width: 64px;
}

/* Actual qty input — compact, fits in num column */
.actual-qty-input {
  width: 80px;
}

/* Picked rows: muted text + line-through, but DO NOT strike through inputs/checkbox */
.picking-table .row-picked td {
  color: #999;
}
.picking-table .row-picked .source-cell,
.picking-table .row-picked .col-num {
  text-decoration: line-through;
}
.picking-table .row-picked .weight-cell,
.picking-table .row-picked .weight-cell * {
  text-decoration: none !important;
}
.dim {
  color: #bbb;
}
.empty {
  text-align: center;
  color: #999;
  padding: 24px !important;
}
.footer-note {
  margin-top: 10px;
  font-size: 12px;
  color: #999;
  text-align: right;
}
</style>
