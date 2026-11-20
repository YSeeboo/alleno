<template>
  <div class="fulfillment-page">
    <div class="page-header"><div class="page-breadcrumb">生产 / 出货管理</div><h2 class="page-title">出货管理</h2><div class="page-divider"></div></div>
    <div class="filter-bar">
      <n-select v-model:value="status" :options="statusOptions" clearable placeholder="筛选状态" style="width:140px" aria-label="出货状态" />
      <n-input v-model:value="search" clearable placeholder="搜索出货单、客户或订单" style="width:260px" :input-props="{ 'aria-label': '搜索出货记录' }" />
      <div class="filter-bar-end wf-actions"><n-button :loading="loading" @click="load">刷新</n-button><n-button type="primary" @click="router.push('/shipments/create')">新建出货单</n-button></div>
    </div>
    <n-alert type="info" :bordered="false" class="wf-notice">公共现货可直接出货，其他订单和其他明细的预留不可挪用。草稿不占库、不扣库，确认后才记入实际出货；旧订单状态不自动生成出货记录。</n-alert>
    <n-alert v-if="error" type="error" class="wf-notice">{{ error }}</n-alert>
    <n-spin :show="loading"><ShipmentTable :shipments="filtered" /></n-spin>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NInput, NSelect, NSpin } from 'naive-ui'
import { listShipments } from '@/api/fulfillment'
import ShipmentTable from '@/components/fulfillment/ShipmentTable.vue'
const records = ref([]), loading = ref(false), error = ref(''), search = ref(''), status = ref(null)
const router = useRouter()
const statusOptions = [{ label: '草稿', value: 'draft' }, { label: '已出货', value: 'confirmed' }, { label: '已作废', value: 'void' }]
const filtered = computed(() => records.value.filter(s => (!status.value || s.status === status.value) && `${s.id} ${s.order_id} ${s.customer_name}`.toLowerCase().includes(search.value.trim().toLowerCase())))
async function load() { loading.value = true; error.value = ''; try { records.value = (await listShipments()).data } catch (e) { error.value = e.response?.data?.detail || '加载失败' } finally { loading.value = false } }
onMounted(load)
</script>
