<template>
  <div>
    <h2 style="margin-top: 0;">待补货清单</h2>

    <n-tabs v-model:value="activeTab" type="line" animated>
      <n-tab-pane name="pending" :tab="`待补货 (${summaryRows.length})`">
        <div class="filter-bar">
          <n-input v-model:value="searchQuery" placeholder="搜索配件 ID / 名称" clearable class="filter-search" />
          <n-checkbox v-if="!isMobile" v-model:checked="onlyZeroStock">仅看库存为 0</n-checkbox>
          <n-select
            v-model:value="supplierFilter"
            :options="supplierOptions"
            placeholder="按商家筛选"
            clearable
            filterable
            class="filter-supplier"
          />
          <span class="filter-stats">
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
                  <n-image
                    v-if="row.part_image"
                    :src="row.part_image"
                    :width="48"
                    :height="48"
                    object-fit="cover"
                    class="part-img"
                    style="cursor:zoom-in;"
                    @click.stop
                  />
                  <div v-else class="part-img placeholder" />
                  <div class="part-meta">
                    <div class="part-name"><span class="part-id">{{ row.part_id }} · </span>{{ row.part_name }}</div>
                  </div>
                  <div class="metric supplier-col">
                    <div class="metric-label">商家</div>
                    <div class="supplier-chips">
                      <template v-if="partSuppliers(row).length === 0">
                        <span class="supplier-empty">—</span>
                      </template>
                      <template v-else>
                        <n-tag
                          v-for="name in partSuppliers(row).slice(0, 2)"
                          :key="name"
                          size="small"
                          :bordered="false"
                          :title="name"
                          class="supplier-chip"
                        >
                          {{ name }}
                        </n-tag>
                        <n-popover v-if="partSuppliers(row).length > 2" trigger="hover" placement="bottom">
                          <template #trigger>
                            <n-tag size="small" type="info" :bordered="false" class="supplier-chip-more">
                              +{{ partSuppliers(row).length - 2 }}
                            </n-tag>
                          </template>
                          <div class="supplier-popover">
                            <div v-for="name in partSuppliers(row).slice(2)" :key="name">{{ name }}</div>
                          </div>
                        </n-popover>
                      </template>
                    </div>
                  </div>
                  <div class="metric-group">
                    <div class="metric">
                      <div class="metric-label">需求量</div>
                      <div class="metric-value">{{ formatQty(row.total_qty) }}</div>
                    </div>
                    <div class="metric" :class="{ 'stock-low': isStockLow(row) }">
                      <div class="metric-label">当前库存</div>
                      <div class="metric-value">{{ row.current_stock }}</div>
                    </div>
                    <div class="metric metric-source">
                      <div class="metric-label">来源</div>
                      <div class="metric-value">{{ row.source_count }} 单</div>
                    </div>
                  </div>
                </div>
              </template>
              <template v-if="!isMobile" #header-extra>
                <n-button size="small" type="success" @click.stop="markPartDone(row)">
                  全部点击完成
                </n-button>
              </template>
              <div>
                <div
                  v-for="src in row.sources"
                  :key="src.request_id"
                  class="source-row"
                >
                  <a
                    class="hc-link"
                    :class="{ 'hc-link-disabled': !canViewHandcraft }"
                    :title="canViewHandcraft ? '' : '无手工单查看权限'"
                    @click="goToHandcraft(src.handcraft_order_id)"
                  >
                    {{ src.handcraft_order_id }}
                  </a>
                  <div class="source-info">
                    <span class="supplier">{{ src.supplier_name }}</span>
                    <span class="qty">需求 {{ formatQty(src.qty) }}</span>
                    <span class="ts">{{ formatDate(src.created_at) }} 标记</span>
                  </div>
                  <n-button size="small" type="success" class="src-action" @click="markOneDone(src)">点击完成</n-button>
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
  NTabs, NTabPane, NInput, NCheckbox, NSelect, NImage, NSpin, NEmpty,
  NCollapse, NCollapseItem, NButton, NDataTable, NTag, NPopover,
  useDialog, useMessage,
} from 'naive-ui'
import { useIsMobile } from '@/composables/useIsMobile'
import { useAuthStore } from '@/stores/auth'
import {
  listRestockSummary,
  listRestockHistory,
  markRestockDone,
  markPartRestockDone,
} from '@/api/restock'

const router = useRouter()
const dialog = useDialog()
const message = useMessage()
const { isMobile } = useIsMobile()
const authStore = useAuthStore()
const canViewHandcraft = computed(() => authStore.hasPermission('handcraft'))

const activeTab = ref('pending')
const summaryRows = ref([])
const summaryLoading = ref(false)
const searchQuery = ref('')
const onlyZeroStock = ref(false)
const supplierFilter = ref(null)

function partSuppliers(row) {
  // Unique, non-empty supplier names across the part's pending sources.
  const seen = new Set()
  const out = []
  for (const s of row.sources || []) {
    const name = (s.supplier_name || '').trim()
    if (name && !seen.has(name)) {
      seen.add(name)
      out.push(name)
    }
  }
  return out
}

const supplierOptions = computed(() => {
  // Suppliers derived from currently-pending rows — keeps the filter scoped
  // to suppliers that actually have something to restock.
  const seen = new Set()
  for (const r of summaryRows.value) {
    for (const name of partSuppliers(r)) seen.add(name)
  }
  return [...seen].sort().map((name) => ({ label: name, value: name }))
})

const filteredRows = computed(() => {
  let rows = summaryRows.value
  if (onlyZeroStock.value) {
    rows = rows.filter((r) => r.current_stock <= 0)
  }
  if (supplierFilter.value) {
    rows = rows.filter((r) => partSuppliers(r).includes(supplierFilter.value))
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
  if (!canViewHandcraft.value) {
    message.warning('无手工单查看权限')
    return
  }
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
    title: '确认全部完成',
    content: `把「${row.part_id} · ${row.part_name}」的所有 ${row.source_count} 条补货记录标记为完成？`,
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
  padding-right: 32px;
}
.part-img {
  width: 48px;
  height: 48px;
  border-radius: 4px;
  background: #eee;
  object-fit: cover;
  flex-shrink: 0;
  overflow: hidden;
}
.part-img.placeholder { background: #fafafa; }
.metric.supplier-col {
  min-width: 140px;
  max-width: 220px;
  text-align: left;
}
.supplier-chips {
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  align-items: center;
  margin-top: 2px;
  overflow: hidden;
}
.supplier-chip {
  max-width: 90px;
  flex-shrink: 1;
}
.supplier-chip :deep(.n-tag__content) {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.supplier-chip-more { flex-shrink: 0; }
.supplier-empty { color: #999; font-size: 14px; }
.supplier-popover { font-size: 13px; line-height: 1.7; }
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
/* Wrappers are layout-flat on desktop (children flow into the parent grid/flex)
   and become real flex containers on mobile to share a single grid cell. */
.metric-group { display: contents; }
.source-info { display: contents; }

.source-row {
  display: grid;
  grid-template-columns: 120px 1fr 110px 140px auto;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-top: 1px solid #f5f5f5;
  font-size: 13px;
}
.hc-link { color: #4361ee; cursor: pointer; }
.hc-link.hc-link-disabled { color: #999; cursor: help; text-decoration: line-through; text-decoration-thickness: 1px; }
.supplier { color: #666; }
.qty { color: #555; }
.ts { color: #888; font-size: 12px; }

.filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 8px 0 12px;
  flex-wrap: wrap;
}
.filter-search { width: 280px; }
.filter-supplier { width: 200px; }
.filter-stats {
  margin-left: auto;
  color: #888;
  font-size: 13px;
}

@media (max-width: 768px) {
  /* Drop ID prefix + 来源 metric on mobile — name and demand/stock are
     the only fields that earn their pixel cost on a phone. */
  .part-id,
  .metric-source { display: none; }

  .filter-bar { gap: 8px; }
  .filter-search,
  .filter-supplier { width: 100%; }
  .filter-stats { margin-left: 0; flex-basis: 100%; }

  .row-header {
    display: grid;
    grid-template-columns: 56px 1fr;
    column-gap: 12px;
    row-gap: 4px;
    padding-right: 4px;
    align-items: start;
  }
  .part-img {
    width: 56px;
    height: 56px;
    grid-row: 1 / span 3;
    align-self: start;
  }
  .part-meta {
    grid-column: 2;
    grid-row: 1;
    min-width: 0;
    align-self: center;
  }
  .part-name { font-size: 14px; line-height: 1.3; }

  .metric.supplier-col {
    grid-column: 2;
    grid-row: 2;
    min-width: 0;
    max-width: 100%;
    display: flex;
    align-items: baseline;
    gap: 6px;
  }
  .metric.supplier-col .metric-label { font-size: 12px; }
  .supplier-chips { margin-top: 0; }

  .metric-group {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 12px;
    grid-column: 2;
    grid-row: 3;
    align-items: baseline;
  }
  .metric-group .metric {
    min-width: 0;
    text-align: left;
  }
  .metric-group .metric-label {
    display: inline;
    font-size: 12px;
    margin-right: 4px;
  }
  .metric-group .metric-value {
    display: inline;
    font-size: 13px;
    font-weight: 600;
  }

  .source-row {
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-areas:
      "hc btn"
      "info info";
    gap: 4px 8px;
    padding: 10px 8px;
  }
  .hc-link {
    grid-area: hc;
    font-weight: 500;
    align-self: center;
  }
  .src-action {
    grid-area: btn;
    justify-self: end;
  }
  .source-info {
    grid-area: info;
    display: flex;
    flex-wrap: wrap;
    gap: 2px 10px;
    align-items: baseline;
    font-size: 12px;
  }
  .source-info .supplier,
  .source-info .qty,
  .source-info .ts { font-size: 12px; }
}
</style>
