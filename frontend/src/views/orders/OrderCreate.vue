<template>
  <div :style="{ maxWidth: isMobile ? '100%' : '900px' }">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建订单</n-h2>
    </n-space>

    <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90" style="margin-bottom: 16px;">
      <n-form-item label="客户名">
        <n-input v-model:value="customerName" placeholder="请输入客户名称" :style="{ width: isMobile ? '100%' : '300px' }" />
      </n-form-item>
      <n-form-item label="创建时间">
        <n-date-picker
          v-model:value="createdAtTs"
          type="date"
          clearable
          placeholder="不填则使用当前时间"
          :style="{ width: isMobile ? '100%' : '300px' }"
        />
      </n-form-item>
    </n-form>

    <!-- Jewelry section -->
    <n-card style="margin-bottom: 16px;">
      <template #header>
        <n-space justify="space-between" align="center" style="width: 100%;">
          <span>💎 饰品明细 <n-text depth="3" style="font-size: 13px;">({{ jewelryItems.length }} 项)</n-text></span>
          <n-space align="center">
            <n-text depth="3" style="font-size: 13px;">小计 ¥{{ fmtMoney(jewelrySubtotal) }}</n-text>
            <n-button type="primary" size="small" @click="addJewelryLine">+ 添加饰品</n-button>
          </n-space>
        </n-space>
      </template>
      <div v-for="(item, idx) in jewelryItems" :key="`j-${idx}`" style="margin-bottom: 12px;">
        <n-space align="center">
          <n-select
            v-model:value="item.jewelry_id"
            :options="jewelryOptions"
            :render-label="renderOptionWithImage"
            filterable clearable
            placeholder="选择饰品"
            :style="{ width: isMobile ? '100%' : '220px' }"
            @update:value="(v) => onJewelrySelect(idx, v)"
          />
          <n-input-number v-model:value="item.quantity" :min="1" placeholder="数量" style="width: 90px;" />
          <n-input-number v-model:value="item.unit_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" placeholder="单价" style="width: 120px;" />
          <n-input v-model:value="item.remarks" placeholder="备注" style="width: 160px;" />
          <n-button type="error" size="small" @click="jewelryItems.splice(idx, 1)">删除</n-button>
        </n-space>
      </div>
      <n-text v-if="jewelryItems.length === 0" depth="3">点击右上角 "+ 添加饰品" 开始</n-text>
    </n-card>

    <!-- Parts section -->
    <n-card style="margin-bottom: 16px;">
      <template #header>
        <n-space justify="space-between" align="center" style="width: 100%;">
          <span>🔧 配件明细 <n-text depth="3" style="font-size: 13px;">({{ partItems.length }} 项)</n-text></span>
          <n-space align="center">
            <n-text depth="3" style="font-size: 13px;">小计 ¥{{ fmtMoney(partSubtotal) }}</n-text>
            <n-button type="primary" size="small" @click="addPartLine">+ 添加配件</n-button>
          </n-space>
        </n-space>
      </template>
      <div v-for="(item, idx) in partItems" :key="`p-${idx}`" style="margin-bottom: 12px;">
        <n-space align="center">
          <n-select
            v-model:value="item.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable clearable
            placeholder="选择配件"
            :style="{ width: isMobile ? '100%' : '220px' }"
            @update:value="(v) => onPartSelect(idx, v)"
          />
          <n-input-number v-model:value="item.quantity" :min="1" placeholder="数量" style="width: 90px;" />
          <n-input-number v-model:value="item.unit_price" :min="0" :precision="7" :format="fmtPrice" :parse="parseNum" placeholder="单价" style="width: 120px;" />
          <n-input v-model:value="item.remarks" placeholder="备注" style="width: 160px;" />
          <n-button type="error" size="small" @click="partItems.splice(idx, 1)">删除</n-button>
        </n-space>
      </div>
      <n-text v-if="partItems.length === 0" depth="3">点击右上角 "+ 添加配件" 开始</n-text>
    </n-card>

    <n-space justify="space-between" align="center">
      <n-text>合计：<n-text style="font-size: 18px; font-weight: 600; color: #FF0000;">
        ¥{{ fmtMoney(total) }}
      </n-text></n-text>
      <n-button type="primary" :loading="submitting" @click="submit">提交订单</n-button>
    </n-space>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NText, NH2, NDatePicker } from 'naive-ui'
import { listJewelries } from '@/api/jewelries'
import { listParts } from '@/api/parts'
import { createOrder } from '@/api/orders'
import { renderOptionWithImage, fmtMoney, fmtPrice, parseNum } from '@/utils/ui'
import { tsToDateStr } from '@/utils/date'
import { useIsMobile } from '@/composables/useIsMobile'

const router = useRouter()
const message = useMessage()
const { isMobile } = useIsMobile()

const customerName = ref('')
const createdAtTs = ref(null)
const jewelryItems = reactive([])
const partItems = reactive([])
const submitting = ref(false)

const jewelryMap = ref({})
const jewelryOptions = ref([])
const partMap = ref({})
const partOptions = ref([])

const addJewelryLine = () =>
  jewelryItems.push({ jewelry_id: null, quantity: 1, unit_price: 0, remarks: '' })

const addPartLine = () =>
  partItems.push({ part_id: null, quantity: 1, unit_price: 0, remarks: '' })

const onJewelrySelect = (idx, jewelryId) => {
  if (!jewelryId) { jewelryItems[idx].unit_price = 0; return }
  jewelryItems[idx].unit_price = jewelryMap.value[jewelryId]?.wholesale_price ?? 0
}

const onPartSelect = (idx, partId) => {
  if (!partId) { partItems[idx].unit_price = 0; return }
  partItems[idx].unit_price = partMap.value[partId]?.wholesale_price ?? 0
}

const jewelrySubtotal = computed(() =>
  jewelryItems.reduce((s, i) => s + (i.quantity || 0) * (i.unit_price || 0), 0)
)
const partSubtotal = computed(() =>
  partItems.reduce((s, i) => s + (i.quantity || 0) * (i.unit_price || 0), 0)
)
const total = computed(() => jewelrySubtotal.value + partSubtotal.value)

const submit = async () => {
  if (!customerName.value) { message.warning('请输入客户名称'); return }
  if (jewelryItems.length === 0 && partItems.length === 0) {
    message.warning('请添加订单明细'); return
  }
  if (jewelryItems.some((i) => !i.jewelry_id)) { message.warning('请选择饰品'); return }
  if (partItems.some((i) => !i.part_id)) { message.warning('请选择配件'); return }

  const items = [
    ...jewelryItems.map(i => ({ jewelry_id: i.jewelry_id, quantity: i.quantity, unit_price: i.unit_price, remarks: i.remarks })),
    ...partItems.map(i => ({ part_id: i.part_id, quantity: i.quantity, unit_price: i.unit_price, remarks: i.remarks })),
  ]
  submitting.value = true
  try {
    const payload = { customer_name: customerName.value, items }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createOrder(payload)
    message.success('订单创建成功')
    router.push(`/orders/${data.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const [{ data: jData }, { data: pData }] = await Promise.all([
    listJewelries({ status: 'active' }),
    listParts({}),
  ])
  jData.forEach((j) => { jewelryMap.value[j.id] = j })
  jewelryOptions.value = jData.map((j) => ({
    label: `${j.id} ${j.name}`, value: j.id, code: j.id, name: j.name, image: j.image,
  }))
  pData.forEach((p) => { partMap.value[p.id] = p })
  partOptions.value = pData.map((p) => ({
    label: `${p.id} ${p.name}`, value: p.id, code: p.id, name: p.name, image: p.image,
  }))
})
</script>
