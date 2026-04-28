<script setup>
import { ref, computed, watch } from 'vue'
import {
  NModal, NButton, NCheckbox, NSwitch, NTag, NSpace, NPopconfirm,
  NSpin, NTooltip, useMessage,
} from 'naive-ui'
import {
  getHandcraftPicking,
  markHandcraftPicked,
  unmarkHandcraftPicked,
  resetHandcraftPicking,
  downloadHandcraftPickingPdf,
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

async function toggleRow(group, row) {
  if (readonly.value) return
  const prev = row.picked
  row.picked = !prev
  data.value.progress.picked += row.picked ? 1 : -1
  try {
    const fn = row.picked ? markHandcraftPicked : unmarkHandcraftPicked
    await fn(props.orderId, group.part_item_id, row.part_id)
  } catch (err) {
    row.picked = prev
    data.value.progress.picked += prev ? 1 : -1
    message.error(err.response?.data?.detail || '操作失败')
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

function suggestedTooltip(row, group) {
  if (row.suggested_qty == null) return ''
  const rule = SUGGESTED_TOOLTIP_RULES[row.size_tier] || SUGGESTED_TOOLTIP_RULES.small
  return `${rule.label}规则: max(${rule.floor}, 理论×${rule.ratio * 100}%) | 建议数量为 ceil(理论) + ceil(buffer)`
}
</script>

<template>
  <n-modal
    :show="show"
    @update:show="(v) => emit('update:show', v)"
    preset="card"
    :style="{ width: isMobile ? '95vw' : '960px', maxWidth: '95vw' }"
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
                <n-button>重置勾选</n-button>
              </template>
              确认清空本手工单的所有勾选记录？
            </n-popconfirm>
          </n-space>
        </div>

        <div class="table-scroll">
          <table class="picking-table">
            <thead>
              <tr>
                <th>配件编号</th>
                <th>配件</th>
                <th>需要</th>
                <th>建议</th>
                <th>库存</th>
                <th>完成</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="g in displayGroups" :key="g.part_item_id">
                <tr class="group-header">
                  <td colspan="6">
                    <span class="group-id">{{ g.parent_part_id }}</span>
                    <span class="group-name">{{ g.parent_part_name }}</span>
                    <n-tag v-if="g.parent_is_composite" size="tiny" type="info" :bordered="false" style="margin-left: 6px;">
                      组合
                    </n-tag>
                    <span class="group-qty">× {{ fmtQty(g.parent_qty) }}</span>
                    <span v-if="g.parent_bom_qty != null" class="group-bom">
                      理论 {{ fmtQty(g.parent_bom_qty) }}
                    </span>
                  </td>
                </tr>
                <tr
                  v-for="r in g.rows"
                  :key="`${g.part_item_id}-${r.part_id}`"
                  :class="{ 'row-picked': r.picked }"
                >
                  <td>{{ r.part_id }}</td>
                  <td>
                    <div class="part-cell">
                      <img v-if="r.part_image" :src="r.part_image" class="part-img" />
                      <div v-else class="part-img placeholder" />
                      <div class="part-name">{{ r.part_name }}</div>
                    </div>
                  </td>
                  <td class="num">{{ fmtQty(r.needed_qty) }}</td>
                  <td class="num suggested">
                    <n-tooltip v-if="r.suggested_qty != null" trigger="hover">
                      <template #trigger>
                        <span>{{ r.suggested_qty }}</span>
                      </template>
                      {{ suggestedTooltip(r, g) }}
                    </n-tooltip>
                    <span v-else class="dim">-</span>
                  </td>
                  <td
                    class="num"
                    :class="{ 'stock-low': r.current_stock < r.needed_qty }"
                  >
                    {{ fmtQty(r.current_stock) }}
                  </td>
                  <td class="num">
                    <n-checkbox
                      :checked="r.picked"
                      :disabled="readonly"
                      @update:checked="toggleRow(g, r)"
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
  min-width: 580px;
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
.picking-table .num {
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.picking-table .suggested {
  color: #1890ff;
  font-weight: 600;
}
.picking-table .stock-low {
  color: #d03050;
  font-weight: 600;
}
.picking-table .group-header td {
  background: #eef3fb;
  font-weight: 500;
  font-size: 13px;
}
.picking-table .group-header .group-id {
  color: #888;
  margin-right: 6px;
  font-variant-numeric: tabular-nums;
}
.picking-table .group-header .group-qty {
  margin-left: 8px;
  color: #4361ee;
}
.picking-table .group-header .group-bom {
  margin-left: 8px;
  color: #999;
  font-size: 12px;
}
.picking-table .row-picked td {
  opacity: 0.5;
  text-decoration: line-through;
}
.part-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.part-img {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 4px;
  flex-shrink: 0;
}
.part-img.placeholder {
  background: #f0f0f0;
}
.part-name {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.dim {
  color: #bbb;
}
.empty {
  text-align: center;
  color: #999;
  padding: 24px !important;
}
</style>
