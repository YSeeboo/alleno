<template>
  <div class="plating-summary">
    <div class="page-head">
      <h2 class="page-title">电镀汇总</h2>
    </div>

    <div class="toolbar">
      <n-button-group>
        <n-button :type="tab === 'out' ? 'primary' : 'default'" @click="setTab('out')">已发出</n-button>
        <n-button :type="tab === 'in' ? 'primary' : 'default'" @click="setTab('in')">已收回</n-button>
      </n-button-group>

      <div class="filters">
        <n-date-picker v-model:value="dateRangeRaw" type="daterange" clearable style="width: 240px" placeholder="日期范围" />
        <n-select v-model:value="supplier" :options="supplierOptions" placeholder="商家" clearable style="width: 160px" />
        <n-input v-model:value="qInput" placeholder="搜索 ID 或配件名" clearable style="width: 220px" />
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table
        :columns="columns"
        :data="rows"
        :row-class-name="rowClassName"
        :scroll-x="1400"
        size="small"
      />
    </n-spin>

    <div class="pager-wrap">
      <n-pagination v-model:page="page" :page-count="pageCount" :page-size="pageSize" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NButtonGroup, NDataTable, NDatePicker, NInput, NPagination, NSelect, NSpin,
} from 'naive-ui'
import { listDispatchedSummary, listReceivedSummary } from '@/api/platingSummary'
import { getPlatingSuppliers } from '@/api/plating'

const route = useRoute()
const router = useRouter()

const tab = ref('out')
const supplier = ref(null)
const dateRangeRaw = ref(null)
const qInput = ref('')
const page = ref(1)
const pageSize = 30

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const supplierOptions = ref([])

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const columns = computed(() => [])
const rowClassName = () => ''

function setTab(t) { tab.value = t; page.value = 1 }

async function loadSuppliers() {
  const list = await getPlatingSuppliers()
  supplierOptions.value = list.map((s) => ({ label: s, value: s }))
}

async function load() { /* implemented in Task 11 */ }

onMounted(() => { loadSuppliers() })
watch([tab, supplier, dateRangeRaw, page], load)
</script>

<style scoped>
.plating-summary { padding: 4px 0; }
.page-head { margin-bottom: 12px; }
.page-title { font-size: 20px; font-weight: 700; margin: 0; }
.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; gap: 12px; flex-wrap: wrap;
}
.filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pager-wrap { display: flex; justify-content: flex-end; margin-top: 12px; }
</style>
