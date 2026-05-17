<template>
  <div class="page">
    <header class="sticky-head">
      <div class="search-box">
        <n-input
          v-model:value="codeInput"
          placeholder="输入回执编号"
          @keydown.enter="onSearch"
          clearable
        />
        <n-button type="primary" @click="onSearch" :loading="searchLoading">搜索</n-button>
      </div>
      <div class="filter-btn" @click="sheetShow = true">
        <span v-if="!selectedSupplier">按商家筛选 ▾</span>
        <span v-else>
          商家：<strong>{{ selectedSupplier }}</strong>
          <span class="clear" @click.stop="clearSupplier">×</span>
        </span>
      </div>
    </header>

    <main class="results">
      <div v-if="loading && orders.length === 0" class="loading">加载中...</div>

      <template v-else-if="orders.length > 0">
        <SortingCard v-for="o in orders" :key="o.id" :order="o" />
        <div v-if="hasMore" class="load-more">
          <n-button block @click="loadMore" :loading="loadMoreLoading">加载更多</n-button>
        </div>
      </template>

      <div v-else-if="hasInteracted && lastEmptyContext === 'supplier-empty'" class="empty">
        <p>该商家暂无含分拣信息的手工单</p>
      </div>

      <div v-else class="empty initial">
        <p>输入回执编号或选择商家查看分拣信息</p>
      </div>
    </main>

    <SupplierSheet
      v-model:show="sheetShow"
      :selected="selectedSupplier"
      @pick="onSupplierPicked"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { NInput, NButton, useMessage } from 'naive-ui'
import SortingCard from './SortingCard.vue'
import SupplierSheet from './SupplierSheet.vue'
import {
  getCargoSortingByReceiptCode,
  listCargoSortingOrders,
} from '@/api/cargoSorting'

const message = useMessage()

const codeInput = ref('')
const selectedSupplier = ref('')
const sheetShow = ref(false)
const orders = ref([])
const loading = ref(false)
const searchLoading = ref(false)
const loadMoreLoading = ref(false)
const hasMore = ref(false)
const hasInteracted = ref(false)
const lastEmptyContext = ref('initial') // 'initial' | 'supplier-empty'

const onSearch = async () => {
  const code = codeInput.value.trim().toUpperCase()
  if (!code) return
  // 互斥：点击搜索就清商家选择
  selectedSupplier.value = ''
  searchLoading.value = true
  try {
    const { data } = await getCargoSortingByReceiptCode(code)
    if (!data.breakdown || data.breakdown.length === 0) {
      message.warning('此手工单没有分拣信息')
      return
    }
    orders.value = [data]
    hasMore.value = false
    hasInteracted.value = true
    codeInput.value = code  // normalize the displayed code
  } catch (err) {
    if (err.response?.status === 404) {
      message.warning(`无此回执编号：${code}`)
      // 保持上次结果区状态（不动 orders / hasMore）
    } else {
      message.error('搜索失败')
    }
  } finally {
    searchLoading.value = false
  }
}

const fetchSupplierOrders = async (offset = 0) => {
  const { data } = await listCargoSortingOrders(selectedSupplier.value, {
    limit: 15,
    offset,
  })
  return data
}

const onSupplierPicked = async (name) => {
  selectedSupplier.value = name
  codeInput.value = ''  // 互斥
  loading.value = true
  hasInteracted.value = true
  try {
    const data = await fetchSupplierOrders(0)
    orders.value = data.orders
    hasMore.value = data.has_more
    lastEmptyContext.value = orders.value.length === 0 ? 'supplier-empty' : 'initial'
  } catch (err) {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

const loadMore = async () => {
  loadMoreLoading.value = true
  try {
    const data = await fetchSupplierOrders(orders.value.length)
    orders.value = [...orders.value, ...data.orders]
    hasMore.value = data.has_more
  } catch (err) {
    message.error('加载失败')
  } finally {
    loadMoreLoading.value = false
  }
}

const clearSupplier = () => {
  selectedSupplier.value = ''
  orders.value = []
  hasMore.value = false
  hasInteracted.value = false
  lastEmptyContext.value = 'initial'
}
</script>

<style scoped>
.page {
  min-height: 100vh;
  background: #f9fafb;
}
.sticky-head {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #f9fafb;
  padding: 16px 16px 12px;
  border-bottom: 1px solid #f3f4f6;
}
.search-box {
  display: flex;
  gap: 8px;
}
.search-box :deep(.n-button) {
  min-height: 44px;
  min-width: 64px;
}
.search-box :deep(.n-input) {
  min-height: 44px;
}
.filter-btn {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: white;
  padding: 12px 14px;
  border-radius: 12px;
  margin-top: 10px;
  font-size: 14px;
  color: #374151;
  min-height: 44px;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(0,0,0,.04);
}
.clear {
  margin-left: 8px;
  font-size: 16px;
  color: #9ca3af;
  padding: 0 4px;
}
.results {
  padding: 0 16px 24px;
}
.empty, .loading {
  text-align: center;
  color: #9ca3af;
  padding: 60px 0;
  font-size: 13px;
}
.load-more {
  margin-top: 14px;
}
</style>
