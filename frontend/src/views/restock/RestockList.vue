<template>
  <div>
    <h2 style="margin-top: 0;">待补货清单</h2>

    <n-tabs v-model:value="activeTab" type="line" animated>
      <n-tab-pane name="pending" :tab="`待补货 (${summaryRows.length})`">
        <div style="display:flex;gap:12px;align-items:center;margin:8px 0 12px;">
          <n-input v-model:value="searchQuery" placeholder="搜索配件 ID / 名称" clearable style="width:280px;" />
          <n-checkbox v-model:checked="onlyZeroStock">仅看库存为 0</n-checkbox>
          <span style="margin-left:auto;color:#888;font-size:13px;">
            共 {{ filteredRows.length }} 个配件 · {{ totalSourceCount }} 条来源
          </span>
        </div>

        <n-spin :show="summaryLoading">
          <n-empty v-if="!summaryLoading && filteredRows.length === 0" description="暂无待补货" />
          <n-collapse v-else accordion arrow-placement="left" :default-expanded-names="[]">
            <n-collapse-item
              v-for="row in filteredRows"
              :key="row.part_id"
              :name="row.part_id"
            >
              <template #header>
                <div class="row-header">
                  <img v-if="row.part_image" :src="row.part_image" class="part-img" />
                  <div v-else class="part-img placeholder" />
                  <div class="part-meta">
                    <div class="part-name">{{ row.part_id }} · {{ row.part_name }}</div>
                  </div>
                  <div class="metric">
                    <div class="metric-label">需求量</div>
                    <div class="metric-value">{{ formatQty(row.total_qty) }}</div>
                  </div>
                  <div class="metric" :class="{ 'stock-low': isStockLow(row) }">
                    <div class="metric-label">当前库存</div>
                    <div class="metric-value">{{ row.current_stock }}</div>
                  </div>
                  <div class="metric">
                    <div class="metric-label">来源</div>
                    <div class="metric-value">{{ row.source_count }} 单</div>
                  </div>
                </div>
              </template>
              <template #header-extra>
                <n-button size="small" type="success" @click.stop="markPartDone(row)">
                  全部已补货
                </n-button>
              </template>
              <div>
                <div
                  v-for="src in row.sources"
                  :key="src.request_id"
                  class="source-row"
                >
                  <a class="hc-link" @click="goToHandcraft(src.handcraft_order_id)">
                    {{ src.handcraft_order_id }}
                  </a>
                  <span class="supplier">{{ src.supplier_name }}</span>
                  <span class="qty">需求 {{ formatQty(src.qty) }}</span>
                  <span class="ts">{{ formatDate(src.created_at) }} 标记</span>
                  <n-button size="tiny" @click="markOneDone(src)">已补货</n-button>
                </div>
              </div>
            </n-collapse-item>
          </n-collapse>
        </n-spin>
      </n-tab-pane>

      <n-tab-pane name="history" tab="历史">
        <n-data-table
          :columns="historyColumns"
          :data="historyRows"
          :loading="historyLoading"
          :bordered="false"
          size="small"
          :pagination="{ pageSize: 50 }"
        />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NTabs, NTabPane, NInput, NCheckbox, NSpin, NEmpty,
  NCollapse, NCollapseItem, NButton, NDataTable, useDialog, useMessage,
} from 'naive-ui'
import {
  listRestockSummary,
  listRestockHistory,
  markRestockDone,
  markPartRestockDone,
} from '@/api/restock'

const router = useRouter()
const dialog = useDialog()
const message = useMessage()

const activeTab = ref('pending')
const summaryRows = ref([])
const summaryLoading = ref(false)
const searchQuery = ref('')
const onlyZeroStock = ref(false)

const filteredRows = computed(() => {
  let rows = summaryRows.value
  if (onlyZeroStock.value) {
    rows = rows.filter((r) => r.current_stock <= 0)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    rows = rows.filter((r) =>
      r.part_id.toLowerCase().includes(q) || r.part_name.toLowerCase().includes(q)
    )
  }
  return rows
})

const totalSourceCount = computed(() =>
  filteredRows.value.reduce((acc, r) => acc + r.source_count, 0),
)

const historyRows = ref([])
const historyLoading = ref(false)

const historyColumns = [
  { title: '配件', key: 'part_id', render: (row) => `${row.part_id} · ${row.part_name}` },
  { title: '手工单', key: 'handcraft_order_id', render: (row) => row.handcraft_order_id || '—' },
  { title: '手工商家', key: 'supplier_name', render: (row) => row.supplier_name || '—' },
  { title: '数量', key: 'qty', render: (row) => formatQty(row.qty) },
  { title: '来源', key: 'source', render: (row) => row.source === 'picking' ? '配货模拟' : '手动添加' },
  { title: '备注', key: 'note', render: (row) => row.note || '—' },
  { title: '标记时间', key: 'created_at', render: (row) => formatDate(row.created_at) },
  { title: '完成时间', key: 'completed_at', render: (row) => formatDate(row.completed_at) },
]

async function loadSummary() {
  summaryLoading.value = true
  try {
    const { data } = await listRestockSummary()
    summaryRows.value = data
  } finally {
    summaryLoading.value = false
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const { data } = await listRestockHistory({ limit: 200 })
    historyRows.value = data
  } finally {
    historyLoading.value = false
  }
}

function formatDate(ts) {
  return new Date(ts).toLocaleDateString()
}

function formatQty(v) {
  if (v == null) return '—'
  const f = Number(v)
  if (Number.isNaN(f)) return String(v)
  const r = parseFloat(f.toPrecision(12))
  return r === Math.trunc(r) ? String(Math.trunc(r)) : r.toString()
}

function isStockLow(row) {
  // Prefer comparing against the actual demand when known; fall back to
  // source count as a heuristic (one source ≈ one unit of demand).
  const threshold = row.total_qty != null ? row.total_qty : row.source_count
  return row.current_stock < threshold
}

function goToHandcraft(hcId) {
  router.push(`/handcraft/${hcId}`)
}

async function markOneDone(src) {
  try {
    await markRestockDone(src.request_id)
    await loadSummary()
  } catch (err) {
    message.error(err?.response?.data?.detail || '操作失败')
  }
}

function markPartDone(row) {
  dialog.warning({
    title: '确认全部已补货',
    content: `把「${row.part_id} · ${row.part_name}」的所有 ${row.source_count} 条记录都标为已补货？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await markPartRestockDone(row.part_id)
        await loadSummary()
      } catch (err) {
        message.error(err?.response?.data?.detail || '操作失败')
      }
    },
  })
}

watch(activeTab, (val) => {
  if (val === 'history') loadHistory()
})

onMounted(loadSummary)
</script>

<style scoped>
.row-header {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
  padding-right: 12px;
}
.part-img {
  width: 48px;
  height: 48px;
  border-radius: 4px;
  background: #eee;
  object-fit: cover;
  flex-shrink: 0;
}
.part-img.placeholder { background: #fafafa; }
.part-meta {
  flex: 1;
  min-width: 140px;
  overflow: hidden;
}
.part-name {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.metric {
  text-align: right;
  min-width: 80px;
  flex-shrink: 0;
}
.metric-label {
  font-size: 11px;
  color: #888;
  line-height: 1.2;
}
.metric-value {
  font-size: 16px;
  font-weight: 500;
  line-height: 1.4;
}
.metric.stock-low .metric-value { color: #d32f2f; }
.source-row {
  display: grid;
  grid-template-columns: 120px 1fr 110px 140px 80px;
  align-items: center;
  padding: 8px 12px;
  border-top: 1px solid #f5f5f5;
  font-size: 13px;
}
.hc-link { color: #4361ee; cursor: pointer; }
.supplier { color: #666; }
.qty { color: #555; }
.ts { color: #888; font-size: 12px; }
</style>
