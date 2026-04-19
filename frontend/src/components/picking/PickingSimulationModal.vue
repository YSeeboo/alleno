<script setup>
import { ref, computed, watch } from 'vue'
import {
  NModal, NCard, NButton, NCheckbox, NSwitch, NTag, NSpace, NPopconfirm,
  NSpin, useMessage,
} from 'naive-ui'
import {
  getPicking, markPicked, unmarkPicked, resetPicking, downloadPickingListPdf,
} from '@/api/orders'
import { useIsMobile } from '@/composables/useIsMobile'

const { isMobile } = useIsMobile()

const props = defineProps({
  show: { type: Boolean, required: true },
  orderId: { type: String, required: true },
})
const emit = defineEmits(['update:show'])

const message = useMessage()
const loading = ref(false)
const data = ref(null)
const onlyUnpicked = ref(false)
const exporting = ref(false)

const displayRows = computed(() => {
  if (!data.value) return []
  if (!onlyUnpicked.value) return data.value.rows
  return data.value.rows
    .map((r) => ({
      ...r,
      variants: r.variants.filter((v) => !v.picked),
    }))
    .filter((r) => r.variants.length > 0)
})

async function load() {
  loading.value = true
  try {
    const resp = await getPicking(props.orderId)
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

async function toggleVariant(row, variant) {
  const prev = variant.picked
  variant.picked = !prev
  data.value.progress.picked += variant.picked ? 1 : -1
  try {
    const fn = variant.picked ? markPicked : unmarkPicked
    await fn(props.orderId, row.part_id, variant.qty_per_unit)
  } catch (err) {
    // rollback
    variant.picked = prev
    data.value.progress.picked += prev ? 1 : -1
    message.error(err.response?.data?.detail || '操作失败')
  }
}

async function doReset() {
  try {
    await resetPicking(props.orderId)
    await load()
    message.success('已重置所有勾选')
  } catch (err) {
    message.error(err.response?.data?.detail || '重置失败')
  }
}

async function doExport() {
  exporting.value = true
  try {
    const resp = await downloadPickingListPdf(props.orderId, false)
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `配货清单_${props.orderId}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    // err.response.data is a Blob when responseType=blob — read it.
    let detail = '导出失败'
    if (err.response?.data instanceof Blob) {
      try {
        const text = await err.response.data.text()
        const parsed = JSON.parse(text)
        detail = parsed.detail || detail
      } catch {
        // fallthrough
      }
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
</script>

<template>
  <n-modal :show="show" @update:show="(v) => emit('update:show', v)"
           preset="card" :style="{ width: isMobile ? '95vw' : '960px', maxWidth: '95vw' }"
           :title="`配货模拟 · 订单 ${orderId}`">
    <n-spin :show="loading">
      <div v-if="data">
        <div class="header-row">
          <div>
            客户：<b>{{ data.customer_name }}</b>
            <span class="progress">
              进度：{{ data.progress.picked }} / {{ data.progress.total }} 已完成
            </span>
          </div>
          <n-space>
            <span>
              只看未完成
              <n-switch v-model:value="onlyUnpicked" size="small" />
            </span>
            <n-button type="primary" :loading="exporting" @click="doExport">
              导出 PDF
            </n-button>
            <n-popconfirm @positive-click="doReset">
              <template #trigger>
                <n-button>重置勾选</n-button>
              </template>
              确认清空本订单的所有勾选记录？
            </n-popconfirm>
          </n-space>
        </div>

        <div class="table-scroll">
        <table class="picking-table">
          <thead>
            <tr>
              <th>配件编号</th>
              <th>配件</th>
              <th>单份</th>
              <th>份数</th>
              <th>需要总数量</th>
              <th>当前库存</th>
              <th>完成</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="row in displayRows" :key="row.part_id">
              <tr v-for="(v, vi) in row.variants"
                  :key="`${row.part_id}-${v.qty_per_unit}`"
                  :class="{ 'row-picked': v.picked, 'variant-inner': vi > 0 }">
                <td v-if="vi === 0" :rowspan="row.variants.length" class="merged">
                  {{ row.part_id }}
                </td>
                <td v-if="vi === 0" :rowspan="row.variants.length" class="merged">
                  <div class="part-cell">
                    <img v-if="row.part_image" :src="row.part_image" class="part-img" />
                    <div v-else class="part-img placeholder" />
                    <div class="part-name">
                      {{ row.part_name }}
                      <n-tag v-if="row.is_composite_child" size="small"
                             type="info" :bordered="false">
                        组合
                      </n-tag>
                    </div>
                  </div>
                </td>
                <td class="num">{{ fmtQty(v.qty_per_unit) }}</td>
                <td class="num">{{ v.units_count }}</td>
                <td class="num total">{{ fmtQty(v.subtotal) }}</td>
                <td v-if="vi === 0" :rowspan="row.variants.length" class="merged num">
                  {{ fmtQty(row.current_stock) }}
                </td>
                <td class="num">
                  <n-checkbox :checked="v.picked"
                              @update:checked="toggleVariant(row, v)" />
                </td>
              </tr>
            </template>
            <tr v-if="displayRows.length === 0">
              <td colspan="7" class="empty">没有数据</td>
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
.picking-table .merged {
  background: #fafbfc;
}
.picking-table .num {
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.picking-table .total {
  font-weight: 600;
}
.picking-table .variant-inner td:not(.merged) {
  border-top: 1px dashed #e5e5e5;
}
.picking-table .row-picked td:not(.merged) {
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
.empty {
  text-align: center;
  color: #999;
  padding: 24px !important;
}
</style>
