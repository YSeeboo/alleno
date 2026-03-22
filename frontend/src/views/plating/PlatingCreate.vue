<template>
  <div style="max-width: 800px;">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建电镀单</n-h2>
    </n-space>

    <n-form label-placement="left" label-width="100" style="margin-bottom: 16px;">
      <n-form-item label="电镀厂名称">
        <n-input v-model:value="supplierName" style="width: 300px;" />
      </n-form-item>
      <n-form-item label="备注">
        <n-input v-model:value="note" type="textarea" :rows="2" style="width: 300px;" />
      </n-form-item>
    </n-form>

    <n-card title="电镀明细" style="margin-bottom: 16px;">
      <div v-for="(item, idx) in items" :key="idx" style="margin-bottom: 10px;">
        <n-space align="center">
          <n-select
            v-model:value="item.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="发出配件"
            style="width: 220px;"
            @update:value="(val) => onPartSelect(item, val)"
          />
          <n-select
            v-model:value="item.receive_part_id"
            :options="getReceivePartOptions(item.part_id)"
            :render-label="renderOptionWithImage"
            filterable
            clearable
            placeholder="收回配件（默认同发出）"
            style="width: 220px;"
          />
          <n-input-number v-model:value="item.qty" :min="1" :precision="0" :step="1" placeholder="发出数量" style="width: 110px;" />
          <n-select
            v-model:value="item.unit"
            :options="unitOptions"
            style="width: 90px;"
          />
          <n-select
            v-model:value="item.plating_method"
            :options="platingMethodOptions"
            style="width: 110px;"
          />
          <n-input v-model:value="item.note" placeholder="备注" style="width: 140px;" />
          <n-button type="error" size="small" @click="items.splice(idx, 1)">删除</n-button>
        </n-space>
      </div>
      <n-button dashed style="width: 100%;" @click="items.push({ part_id: null, receive_part_id: null, qty: 1, unit: '个', plating_method: '金', note: '' })">
        + 添加明细行
      </n-button>
    </n-card>

    <n-space justify="end">
      <n-button type="primary" :loading="submitting" @click="submit">提交</n-button>
    </n-space>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NH2 } from 'naive-ui'
import { listParts } from '@/api/parts'
import { createPlating } from '@/api/plating'
import { renderOptionWithImage } from '@/utils/ui'

const router = useRouter()
const message = useMessage()
const supplierName = ref('')
const note = ref('')
const items = reactive([{ part_id: null, receive_part_id: null, qty: 1, unit: '个', plating_method: '金', note: '' }])
const submitting = ref(false)
const partOptions = ref([])
const allParts = ref([])

const COLOR_BADGE_MAP = { '金色': 'G', '白K': 'S', '玫瑰金': 'RG' }

const getReceivePartOptions = (sendPartId) => {
  if (!sendPartId) return partOptions.value
  const sendPart = allParts.value.find((p) => p.id === sendPartId)
  if (!sendPart) return partOptions.value
  const rootId = sendPart.parent_part_id || sendPart.id
  const variantIds = new Set(
    allParts.value
      .filter((p) => p.id === rootId || p.parent_part_id === rootId)
      .map((p) => p.id)
  )
  if (variantIds.size <= 1) return []
  return partOptions.value
    .filter((opt) => variantIds.has(opt.value))
    .map((opt) => {
      const part = allParts.value.find((p) => p.id === opt.value)
      const badge = part?.color ? COLOR_BADGE_MAP[part.color] : null
      if (!badge) return opt
      return { ...opt, label: `${opt.label} [${badge}]` }
    })
}

const platingMethodOptions = [
  { label: '金', value: '金' },
  { label: '白K', value: '白K' },
  { label: '玫瑰金', value: '玫瑰金' },
  { label: '银色', value: '银色' },
]

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const onPartSelect = (item, val) => {
  const found = partOptions.value.find((p) => p.value === val)
  if (found && found.unit) {
    item.unit = found.unit
  } else {
    item.unit = '个'
  }
  item.receive_part_id = null
}

const submit = async () => {
  if (!supplierName.value) { message.warning('请输入电镀厂名称'); return }
  if (items.length === 0) { message.warning('请至少添加一条明细'); return }
  if (items.some((i) => !i.part_id)) { message.warning('请选择配件'); return }
  submitting.value = true
  try {
    const { data } = await createPlating({ supplier_name: supplierName.value, items, note: note.value })
    message.success('创建成功')
    router.push(`/plating/${data.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    const { data } = await listParts()
    allParts.value = data
    partOptions.value = data.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
      unit: p.unit,
    }))
  } catch (_) {
    // error already shown by axios interceptor
  }
})
</script>
