<template>
  <div style="max-width: 800px;">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建订单</n-h2>
    </n-space>

    <n-form label-placement="left" label-width="90" style="margin-bottom: 16px;">
      <n-form-item label="客户名">
        <n-input v-model:value="customerName" placeholder="请输入客户名称" style="width: 300px;" />
      </n-form-item>
    </n-form>

    <n-card title="订单明细" style="margin-bottom: 16px;">
      <div v-for="(item, idx) in items" :key="idx" style="margin-bottom: 12px;">
        <n-space align="center">
          <n-select
            v-model:value="item.jewelry_id"
            :options="jewelryOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="选择饰品"
            style="width: 220px;"
            @update:value="(v) => onJewelrySelect(idx, v)"
          />
          <n-input-number v-model:value="item.quantity" :min="1" placeholder="数量" style="width: 90px;" />
          <n-input-number
            v-model:value="item.unit_price"
            :min="0"
            :precision="3"
            placeholder="单价"
            style="width: 100px;"
          />
          <n-input v-model:value="item.remarks" placeholder="备注" style="width: 160px;" />
          <n-button type="error" size="small" @click="items.splice(idx, 1)">删除</n-button>
        </n-space>
      </div>
      <n-button dashed style="width: 100%;" @click="addLine">+ 添加明细行</n-button>
    </n-card>

    <n-space justify="space-between" align="center">
      <n-text>合计：<n-text style="font-size: 18px; font-weight: 600; color: #FF0000;">
        ¥{{ total.toFixed(3) }}
      </n-text></n-text>
      <n-button type="primary" :loading="submitting" @click="submit">提交订单</n-button>
    </n-space>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NText, NH2 } from 'naive-ui'
import { listJewelries } from '@/api/jewelries'
import { createOrder } from '@/api/orders'
import { renderOptionWithImage } from '@/utils/ui'

const router = useRouter()
const message = useMessage()

const customerName = ref('')
const items = reactive([])
const submitting = ref(false)
const jewelryMap = ref({})  // id -> jewelry
const jewelryOptions = ref([])

const addLine = () => items.push({ jewelry_id: null, quantity: 1, unit_price: 0, remarks: '' })

const onJewelrySelect = (idx, jewelryId) => {
  const jewelry = jewelryMap.value[jewelryId]
  if (jewelry) items[idx].unit_price = jewelry.wholesale_price ?? 0
}

const total = computed(() => items.reduce((s, i) => s + (i.quantity || 0) * (i.unit_price || 0), 0))

const submit = async () => {
  if (!customerName.value) { message.warning('请输入客户名称'); return }
  if (items.length === 0) { message.warning('请添加订单明细'); return }
  if (items.some((i) => !i.jewelry_id)) { message.warning('请选择饰品'); return }
  submitting.value = true
  try {
    const { data } = await createOrder({ customer_name: customerName.value, items })
    message.success('订单创建成功')
    router.push(`/orders/${data.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const { data } = await listJewelries({ status: 'active' })
  data.forEach((j) => { jewelryMap.value[j.id] = j })
  jewelryOptions.value = data.map((j) => ({
    label: `${j.id} ${j.name}`,
    value: j.id,
    code: j.id,
    name: j.name,
    image: j.image,
  }))
  addLine()
})
</script>
