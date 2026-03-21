<template>
  <div class="kanban-page">
    <!-- 顶部工具栏 -->
    <div class="kanban-toolbar">
      <h2 class="page-title">进度看板</h2>
      <div class="toolbar-right">
        <n-select v-model:value="filterType" :options="filterOptions" style="width: 120px;" @update:value="reloadAll" />
      </div>
    </div>
    <div class="page-divider" style="margin-bottom: 24px;"></div>

    <!-- 三行看板 -->
    <div v-for="row in kanbanRows" :key="row.status" class="kanban-section">
      <div class="section-title" :style="{ '--lane-color': row.color }">
        <span class="section-label">{{ row.label }}</span>
        <span class="section-count">{{ row.cards.length }}</span>
      </div>

      <div v-if="row.cards.length > 0" class="cards-grid">
        <div
          v-for="card in row.cards"
          :key="`${card.vendor_name}-${card.order_type}`"
          class="vendor-card"
          @click="openDetail(card)"
        >
          <div class="card-header">
            <span class="supplier-name">{{ card.vendor_name }}</span>
            <span :class="`badge ${card.order_type === 'plating' ? 'badge-indigo' : 'badge-amber'}`">
              {{ card.order_type === 'plating' ? '电镀' : '手工' }}
            </span>
          </div>
          <div v-if="row.status !== 'pending_dispatch'" class="card-meta">
            {{ getCardMetaLabel(row.status, card.order_type) }}：{{ card.part_count ?? '-' }} 种
          </div>
        </div>
      </div>

      <n-empty
        v-else-if="!row.loading"
        description="暂无数据哦"
        style="margin: 16px 0 24px;"
      />

      <div v-if="row.loading" class="row-loading">
        <n-spin size="small" />
      </div>

      <!-- 哨兵：触底加载 -->
      <div :ref="(el) => setSentinel(el, row)" class="sentinel" />
    </div>

    <!-- 厂家详情弹窗 -->
    <VendorDetailModal
      v-model:show="detailVisible"
      :vendor="selectedVendor"
      @refresh="reloadAll"
    />

  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { NSelect, NSpin, NEmpty } from 'naive-ui'
import VendorDetailModal from './VendorDetailModal.vue'
import { getKanban } from '@/api/kanban'

const PAGE_SIZE = 20

const filterType = ref('all')
let _filterVersion = 0

const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '电镀', value: 'plating' },
  { label: '手工', value: 'handcraft' },
]

const kanbanRows = reactive([
  { status: 'pending_dispatch', label: '待发出', color: '#F59E0B', cards: [], page: 1, hasMore: true, loading: false },
  { status: 'pending_return',   label: '待收回', color: '#6366F1', cards: [], page: 1, hasMore: true, loading: false },
  { status: 'returned',         label: '已收回', color: '#10B981', cards: [], page: 1, hasMore: true, loading: false },
])

const getCardMetaLabel = (rowStatus, orderType) => {
  if (rowStatus === 'pending_return') {
    return orderType === 'plating' ? '未收回配件种类' : '未收回种类'
  }
  if (rowStatus === 'returned') {
    return orderType === 'plating' ? '已完成配件种类' : '已完成种类'
  }
  return orderType === 'plating' ? '配件种类' : '种类'
}

const loadMore = async (row, version = _filterVersion) => {
  if (row.loading || !row.hasMore) return
  row.loading = true
  try {
    const { data } = await getKanban({
      type: filterType.value,
      page: row.page,
      page_size: PAGE_SIZE,
    })
    if (version !== _filterVersion) return
    const rowData = data[row.status] || {}
    const items = rowData.vendors || []
    row.cards.push(...items)
    row.hasMore = row.cards.length < (rowData.total || 0)
    row.page++
  } finally {
    if (version === _filterVersion) row.loading = false
  }
}

const reloadAll = () => {
  _filterVersion++
  const myVersion = _filterVersion
  for (const row of kanbanRows) {
    row.cards = []
    row.page = 1
    row.hasMore = true
    row.loading = false
    loadMore(row, myVersion)
  }
}

// Intersection Observer 无限滚动
const observers = new Map()

const setSentinel = (el, row) => {
  const existing = observers.get(row.status)
  if (existing) existing.disconnect()
  if (!el) return

  const observer = new IntersectionObserver(
    ([entry]) => { if (entry.isIntersecting) loadMore(row) },
    { rootMargin: '80px' },
  )
  observer.observe(el)
  observers.set(row.status, observer)
}

onMounted(reloadAll)
onUnmounted(() => observers.forEach((obs) => obs.disconnect()))

// 厂家详情弹窗
const detailVisible = ref(false)
const selectedVendor = ref(null)

const openDetail = (card) => {
  selectedVendor.value = card
  detailVisible.value = true
}

</script>

<style scoped>
.kanban-page {
  max-width: 1100px;
}

.kanban-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.kanban-toolbar .page-title {
  margin: 0;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.kanban-section {
  margin-bottom: 36px;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-left: 3px solid var(--lane-color);
  margin-bottom: 14px;
}

.section-label {
  font-size: 13px;
  font-weight: 600;
  color: #0F172A;
}

.section-count {
  font-size: 12px;
  color: #94A3B8;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

@media (max-width: 860px) {
  .cards-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 560px) {
  .cards-grid { grid-template-columns: 1fr; }
}

.vendor-card {
  background: #FFFFFF;
  border-radius: 8px;
  border: 1px solid #E2E8F0;
  padding: 14px 16px;
  cursor: pointer;
  min-height: 72px;
  transition: border-color 0.15s, box-shadow 0.15s;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.vendor-card:hover {
  border-color: #6366F1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
  transform: none;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.supplier-name {
  font-size: 14px;
  font-weight: 600;
  color: #1C1B18;
  max-width: 50%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-meta {
  font-size: 12px;
  color: #8A8880;
}

.row-loading {
  display: flex;
  justify-content: center;
  padding: 12px 0;
}

.sentinel {
  height: 1px;
}
</style>
