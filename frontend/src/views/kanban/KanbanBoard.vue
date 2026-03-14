<template>
  <div class="kanban-page">
    <!-- 顶部工具栏 -->
    <div class="page-header">
      <h2 class="page-title">进度看板</h2>
      <div class="toolbar-right">
        <n-radio-group v-model:value="filterType" @update:value="reloadAll" style="display: flex;">
          <n-radio-button value="all">全部</n-radio-button>
          <n-radio-button value="plating">电镀</n-radio-button>
          <n-radio-button value="handcraft">手工</n-radio-button>
        </n-radio-group>
        <n-button type="primary" @click="receiptVisible = true">收回</n-button>
      </div>
    </div>

    <!-- 三行看板 -->
    <div v-for="row in kanbanRows" :key="row.status" class="kanban-section">
      <div class="section-title">{{ row.label }}</div>

      <div v-if="row.cards.length > 0" class="cards-grid">
        <div
          v-for="card in row.cards"
          :key="`${card.vendor_name}-${card.order_type}`"
          class="vendor-card"
          @click="openDetail(card)"
        >
          <div class="card-header">
            <span class="supplier-name">{{ card.vendor_name }}</span>
            <n-tag
              size="small"
              :type="card.order_type === 'plating' ? 'info' : 'warning'"
            >
              {{ card.order_type === 'plating' ? '电镀' : '手工' }}
            </n-tag>
          </div>
          <div v-if="row.status !== 'pending_dispatch'" class="card-meta">
            {{ card.order_type === 'plating' ? '配件种类' : '待收回种类' }}：{{ card.part_count ?? '-' }} 种
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
    />

    <!-- 收回弹窗 -->
    <ReceiptModal
      v-model:show="receiptVisible"
      @success="reloadAll"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { NButton, NTag, NSpin, NEmpty, NRadioGroup, NRadioButton } from 'naive-ui'
import VendorDetailModal from './VendorDetailModal.vue'
import ReceiptModal from './ReceiptModal.vue'
import { getKanban } from '@/api/kanban'

const PAGE_SIZE = 20

const filterType = ref('all')
let _filterVersion = 0

const kanbanRows = reactive([
  { status: 'pending_dispatch', label: '待发出', cards: [], page: 1, hasMore: true, loading: false },
  { status: 'pending_return',   label: '待收回', cards: [], page: 1, hasMore: true, loading: false },
  { status: 'returned',         label: '已收回', cards: [], page: 1, hasMore: true, loading: false },
])

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

// 收回弹窗
const receiptVisible = ref(false)
</script>

<style scoped>
.kanban-page {
  max-width: 1100px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 28px;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #1C1B18;
  letter-spacing: -0.01em;
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
  font-size: 13px;
  font-weight: 600;
  color: #6B6560;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid #EEECE6;
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
  border-radius: 12px;
  border: 1px solid #EEECE6;
  padding: 16px 18px;
  cursor: pointer;
  min-height: 88px;
  box-shadow: 0 1px 4px rgba(15, 14, 13, 0.04);
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.vendor-card:hover {
  transform: translateY(-3px);
  box-shadow:
    0 0 0 2px #D62828,
    0 8px 24px rgba(214, 40, 40, 0.2);
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
