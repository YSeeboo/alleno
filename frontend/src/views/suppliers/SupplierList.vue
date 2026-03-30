<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">管理 / 商家管理</div>
      <h2 class="page-title">商家管理</h2>
      <div class="page-divider"></div>
    </div>

    <n-tabs v-model:value="activeTab" type="line" @update:value="onTabChange">
      <n-tab-pane v-for="tab in tabs" :key="tab.value" :name="tab.value">
        <template #tab>
          {{ tab.label }}
          <span v-if="tabCounts[tab.value]" class="tab-count">{{ tabCounts[tab.value] }}</span>
        </template>
      </n-tab-pane>
    </n-tabs>

    <div class="filter-bar">
      <n-input
        v-model:value="searchQuery"
        placeholder="搜索商家名称"
        clearable
        style="width: 240px;"
      />
      <div class="filter-bar-end">
        <n-button type="primary" @click="openCreate">新增</n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table
        v-if="filteredList.length > 0"
        :columns="columns"
        :data="filteredList"
        :bordered="false"
      />
      <n-empty v-else-if="!loading" description="暂无商家" style="margin-top: 24px;" />
    </n-spin>

    <n-modal v-model:show="showModal" preset="card" :title="editingSupplier ? '编辑商家' : '新增商家'" style="width: 400px;">
      <form @submit.prevent="handleSave">
      <n-form label-placement="top">
        <n-form-item label="商家名称">
          <n-input v-model:value="modalName" placeholder="请输入商家名称" />
        </n-form-item>
      </n-form>
      </form>
      <template #action>
        <n-space justify="end">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="handleSave">确定</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, h } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import {
  NTabs, NTabPane, NInput, NButton, NSpin, NDataTable,
  NEmpty, NModal, NForm, NFormItem, NSpace,
} from 'naive-ui'
import { listSuppliers, createSupplier, updateSupplier, deleteSupplier } from '@/api/suppliers'

const message = useMessage()
const dialog = useDialog()

const tabs = [
  { label: '电镀厂', value: 'plating' },
  { label: '手工商家', value: 'handcraft' },
  { label: '配件商家', value: 'parts' },
  { label: '客户', value: 'customer' },
]

const activeTab = ref('plating')
const loading = ref(false)
const allSuppliers = ref([])
const searchQuery = ref('')
const showModal = ref(false)
const modalName = ref('')
const editingSupplier = ref(null)
const saving = ref(false)

const tabCounts = computed(() => {
  const counts = {}
  for (const tab of tabs) {
    counts[tab.value] = allSuppliers.value.filter((s) => s.type === tab.value).length
  }
  return counts
})

const currentList = computed(() =>
  allSuppliers.value.filter((s) => s.type === activeTab.value)
)

const filteredList = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return currentList.value
  return currentList.value.filter((s) => s.name.toLowerCase().includes(q))
})

const fmt = (dt) => new Date(dt).toLocaleString('zh-CN')

const columns = [
  { title: '序号', key: 'index', width: 60, render: (_, idx) => idx + 1 },
  { title: '商家名称', key: 'name' },
  { title: '创建时间', key: 'created_at', width: 180, render: (row) => fmt(row.created_at) },
  {
    title: '操作', key: 'actions', width: 140,
    render: (row) => h(NSpace, { size: 'small' }, () => [
      h(NButton, { size: 'small', text: true, type: 'primary', onClick: () => openEdit(row) }, () => '编辑'),
      h(NButton, { size: 'small', text: true, type: 'error', onClick: () => confirmDelete(row) }, () => '删除'),
    ]),
  },
]

const loadData = async () => {
  loading.value = true
  try {
    const { data } = await listSuppliers()
    allSuppliers.value = data
  } catch (_) {
    // error already shown by axios interceptor
  } finally {
    loading.value = false
  }
}

const onTabChange = () => {
  searchQuery.value = ''
}

const openCreate = () => {
  editingSupplier.value = null
  modalName.value = ''
  showModal.value = true
}

const openEdit = (row) => {
  editingSupplier.value = row
  modalName.value = row.name
  showModal.value = true
}

const handleSave = async () => {
  const name = modalName.value.trim()
  if (!name) { message.warning('请输入商家名称'); return }
  saving.value = true
  try {
    if (editingSupplier.value) {
      await updateSupplier(editingSupplier.value.id, { name })
      message.success('修改成功')
    } else {
      await createSupplier({ name, type: activeTab.value })
      message.success('新增成功')
    }
    showModal.value = false
    await loadData()
  } finally {
    saving.value = false
  }
}

const confirmDelete = (row) => {
  dialog.warning({
    title: '确认删除',
    content: `确定删除商家「${row.name}」吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await deleteSupplier(row.id)
      message.success('已删除')
      await loadData()
    },
  })
}

onMounted(loadData)
</script>

<style scoped>
.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 16px 0;
}
.filter-bar-end {
  display: flex;
  gap: 8px;
}
.tab-count {
  display: inline-block;
  margin-left: 6px;
  font-size: 12px;
  color: #999;
}
</style>
