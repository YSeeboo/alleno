<template>
  <div>
    <n-h2>库存流水查询</n-h2>
    <n-space style="margin-bottom: 16px;">
      <n-select
        v-model:value="itemType"
        :options="[{ label: '配件', value: 'part' }, { label: '饰品', value: 'jewelry' }]"
        placeholder="选择品类"
        style="width: 120px;"
      />
      <n-input v-model:value="itemId" placeholder="输入编号（如 PJ-0001）" style="width: 200px;" clearable />
      <n-button type="primary" :loading="loading" @click="query">查询</n-button>
    </n-space>

    <n-spin :show="loading">
      <n-data-table v-if="logs.length > 0" :columns="columns" :data="logs" :bordered="false" />
      <n-empty v-else-if="!loading && queried" description="暂无流水记录" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>

<script setup>
import { ref, h } from 'vue'
import { useMessage } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NDataTable, NSpin, NH2, NEmpty } from 'naive-ui'
import { getStockLog } from '@/api/inventory'
import { getPart } from '@/api/parts'
import { getJewelry } from '@/api/jewelries'
import { renderNamedImage } from '@/utils/ui'

const message = useMessage()
const itemType = ref('part')
const itemId = ref('')
const logs = ref([])
const loading = ref(false)
const queried = ref(false)

const query = async () => {
  if (!itemType.value || !itemId.value) { message.warning('请选择品类并输入编号'); return }
  loading.value = true
  queried.value = true
  try {
    const [logRes, itemRes] = await Promise.all([
      getStockLog(itemType.value, itemId.value),
      itemType.value === 'part' ? getPart(itemId.value) : getJewelry(itemId.value),
    ])
    const entity = itemRes.data
    const kindLabel = itemType.value === 'part' ? '配件' : '饰品'
    logs.value = logRes.data.map((log) => ({
      ...log,
      item_name: entity.name,
      item_image: entity.image,
      item_label: `${kindLabel} ${entity.name}`,
    }))
  } finally {
    loading.value = false
  }
}

const columns = [
  { title: '时间', key: 'created_at', render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
  { title: '品类', key: 'item_type', render: (r) => r.item_type === 'part' ? '配件' : '饰品' },
  { title: '编号', key: 'item_id' },
  {
    title: '图片',
    key: 'item_label',
    minWidth: 180,
    render: (row) => renderNamedImage(row.item_name, row.item_image, row.item_label),
  },
  {
    title: '变动数量',
    key: 'change_qty',
    render: (r) =>
      h('span', { style: { color: r.change_qty > 0 ? '#18a058' : '#d03050', fontWeight: 600 } },
        (r.change_qty > 0 ? '+' : '') + r.change_qty
      ),
  },
  { title: '原因', key: 'reason' },
  { title: '备注', key: 'note', render: (r) => r.note || '-' },
]
</script>
