<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">商品 / 饰品模板</div>
      <h2 class="page-title">饰品模板</h2>
      <div class="page-divider"></div>
    </div>

    <div class="filter-bar">
      <div class="filter-bar-end">
        <n-button type="primary" @click="router.push('/jewelry-templates/create')">新建模板</n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" />
      <n-empty v-else-if="!loading" description="暂无模板" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NButton, NSpace, NDataTable, NSpin, NEmpty, NPopconfirm } from 'naive-ui'
import { listTemplates, getTemplate, createTemplate, deleteTemplate } from '@/api/jewelryTemplates'
import { renderNamedImage } from '@/utils/ui'
const router = useRouter()
const message = useMessage()
const loading = ref(true)
const rows = ref([])

const load = async () => {
  loading.value = true
  try {
    const { data } = await listTemplates()
    rows.value = data
  } finally {
    loading.value = false
  }
}

const doDelete = async (row) => {
  await deleteTemplate(row.id)
  message.success('已删除')
  await load()
}

const doCopy = async (row) => {
  const { data: src } = await getTemplate(row.id)
  const { data: created } = await createTemplate({
    name: `${src.name} (副本)`,
    image: src.image || null,
    note: src.note || null,
    items: (src.items || []).map((i) => ({ part_id: i.part_id, qty_per_unit: i.qty_per_unit })),
  })
  message.success('已复制')
  router.push(`/jewelry-templates/${created.id}`)
}

const columns = [
  { title: '编号', key: 'id', width: 80 },
  {
    title: '模板名称',
    key: 'name',
    minWidth: 120,
    render: (row) => renderNamedImage(row.name, row.image, row.name),
  },
  { title: '配件数量', key: 'item_count', width: 100 },
  {
    title: '创建时间',
    key: 'created_at',
    width: 180,
    render: (r) => r.created_at ? new Date(r.created_at).toLocaleString('zh-CN') : '-',
  },
  {
    title: '操作',
    key: 'actions',
    width: 200,
    render: (row) =>
      h(NSpace, { size: 8 }, () => [
        h(NButton, { size: 'small', onClick: () => router.push(`/jewelry-templates/${row.id}`) }, () => '详情'),
        h(NButton, { size: 'small', onClick: () => doCopy(row) }, () => '复制'),
        h(NPopconfirm, { onPositiveClick: () => doDelete(row) }, {
          trigger: () => h(NButton, { size: 'small', type: 'error' }, () => '删除'),
          default: () => `确认删除模板「${row.name}」？`,
        }),
      ]),
  },
]

onMounted(load)
</script>
