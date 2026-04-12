<template>
  <div style="max-width: 900px;">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建手工单</n-h2>
    </n-space>

    <n-form label-placement="left" label-width="110" style="margin-bottom: 16px;">
      <n-form-item label="手工商家名称">
        <n-select
          v-model:value="supplierName"
          :options="supplierOptions"
          filterable
          tag
          placeholder="选择或输入手工商家名称"
          style="width: 300px;"
        />
      </n-form-item>
      <n-form-item label="备注">
        <n-input v-model:value="note" type="textarea" :rows="2" style="width: 300px;" />
      </n-form-item>
      <n-form-item label="创建时间">
        <n-date-picker
          v-model:value="createdAtTs"
          type="date"
          clearable
          placeholder="不填则使用当前时间，填写后不触发同日合并"
          style="width: 360px;"
        />
      </n-form-item>
    </n-form>

    <n-grid :cols="2" :x-gap="16" style="margin-bottom: 16px;">
      <n-gi>
        <n-card title="发出配件">
          <div v-for="(item, idx) in parts" :key="idx" style="margin-bottom: 10px;">
            <n-space align="center">
              <n-select
                v-model:value="item.part_id"
                :options="partOptions"
                :render-label="renderOptionWithImage"
                filterable
                clearable
                placeholder="选择配件"
                style="width: 190px;"
                @update:value="(val) => onPartSelect(item, val)"
              />
              <n-input-number v-model:value="item.qty" :min="1" :precision="0" :step="1" placeholder="实际发出" style="width: 100px;" />
              <n-select
                v-model:value="item.unit"
                :options="partUnitOptions"
                style="width: 80px;"
              />
              <n-input-number v-model:value="item.bom_qty" :min="0" :precision="0" :step="1" placeholder="BOM理论(选填)" style="width: 120px;" />
              <n-button type="error" size="small" @click="parts.splice(idx, 1)">删</n-button>
            </n-space>
          </div>
          <n-button dashed style="width: 100%;" @click="parts.push({ part_id: null, qty: 1, unit: '个', bom_qty: null, note: '' })">
            + 添加配件行
          </n-button>
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="预期产出">
          <div v-for="(item, idx) in jewelries" :key="idx" style="margin-bottom: 10px;">
            <n-space align="center">
              <n-select
                v-model:value="item.output_type"
                :options="outputTypeOptions"
                style="width: 80px;"
                @update:value="() => { item.jewelry_id = null; item.part_id = null }"
              />
              <n-select
                v-if="item.output_type === 'jewelry'"
                v-model:value="item.jewelry_id"
                :options="jewelryOptions"
                :render-label="renderOptionWithImage"
                filterable
                clearable
                placeholder="选择饰品"
                style="width: 190px;"
                @update:value="(val) => onJewelrySelect(item, val)"
              />
              <n-select
                v-else
                v-model:value="item.part_id"
                :options="partOptions"
                :render-label="renderOptionWithImage"
                filterable
                clearable
                placeholder="选择配件"
                style="width: 190px;"
                @update:value="(val) => onOutputPartSelect(item, val)"
              />
              <n-input-number v-model:value="item.qty" :min="1" :precision="0" :step="1" placeholder="预期数量" style="width: 100px;" />
              <n-select
                v-model:value="item.unit"
                :options="item.output_type === 'jewelry' ? jewelryUnitOptions : partUnitOptions"
                style="width: 80px;"
              />
              <n-button type="error" size="small" @click="jewelries.splice(idx, 1)">删</n-button>
            </n-space>
          </div>
          <n-button dashed style="width: 100%;" @click="jewelries.push({ output_type: 'jewelry', jewelry_id: null, part_id: null, qty: 1, unit: '个', note: '' })">
            + 添加产出行
          </n-button>
        </n-card>
      </n-gi>
    </n-grid>

    <n-space justify="end">
      <n-button type="primary" :loading="submitting" @click="submit">提交</n-button>
    </n-space>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NH2, NGrid, NGi, NDatePicker } from 'naive-ui'
import { listParts } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { createHandcraft } from '@/api/handcraft'
import { listSuppliers, createSupplier } from '@/api/suppliers'
import { renderOptionWithImage } from '@/utils/ui'
import { tsToDateStr } from '@/utils/date'

const router = useRouter()
const message = useMessage()
const supplierName = ref(null)
const supplierOptions = ref([])
const note = ref('')
const createdAtTs = ref(null)
const parts = reactive([{ part_id: null, qty: 1, unit: '个', bom_qty: null, note: '' }])
const jewelries = reactive([{ output_type: 'jewelry', jewelry_id: null, part_id: null, qty: 1, unit: '个', note: '' }])

const outputTypeOptions = [
  { label: '饰品', value: 'jewelry' },
  { label: '配件', value: 'part' },
]
const submitting = ref(false)
const partOptions = ref([])
const jewelryOptions = ref([])

const partUnitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const jewelryUnitOptions = [
  { label: '个', value: '个' },
  { label: '套', value: '套' },
  { label: '对', value: '对' },
]

const onPartSelect = (item, val) => {
  const found = partOptions.value.find((p) => p.value === val)
  if (found && found.unit) {
    item.unit = found.unit
  } else {
    item.unit = '个'
  }
}

const onJewelrySelect = (item, val) => {
  const found = jewelryOptions.value.find((j) => j.value === val)
  if (found && found.unit) {
    item.unit = found.unit
  } else {
    item.unit = '个'
  }
}

const onOutputPartSelect = (item, val) => {
  const found = partOptions.value.find((p) => p.value === val)
  if (found && found.unit) {
    item.unit = found.unit
  } else {
    item.unit = '个'
  }
}

const normalizedParts = () => parts.filter((item) => item.part_id)
const normalizedJewelries = () => jewelries
  .filter((item) => item.jewelry_id || item.part_id)
  .map((item) => {
    if (item.output_type === 'part') {
      return { part_id: item.part_id, qty: item.qty, unit: item.unit, note: item.note }
    }
    return { jewelry_id: item.jewelry_id, qty: item.qty, unit: item.unit, note: item.note }
  })

const submit = async () => {
  const validParts = normalizedParts()
  const validJewelries = normalizedJewelries()
  if (!supplierName.value?.trim()) { message.warning('请输入手工商家名称'); return }
  if (validParts.length === 0) { message.warning('请至少添加一条配件'); return }
  submitting.value = true
  try {
    // Auto-create supplier if new (swallow duplicate 400, rethrow others)
    const isNew = !supplierOptions.value.some((o) => o.value === supplierName.value)
    if (isNew) {
      try { await createSupplier({ name: supplierName.value, type: 'handcraft' }) } catch (e) { if (e.response?.status !== 400) throw e }
    }
    const payload = {
      supplier_name: supplierName.value,
      parts: validParts,
      jewelries: validJewelries,
      note: note.value,
    }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createHandcraft(payload)
    message.success('创建成功')
    router.push(`/handcraft/${data.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    const [pRes, jRes, sRes] = await Promise.all([
      listParts(), listJewelries({ status: 'active' }), listSuppliers({ type: 'handcraft' }),
    ])
    partOptions.value = pRes.data.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
      unit: p.unit,
    }))
    jewelryOptions.value = jRes.data.map((j) => ({
      label: `${j.id} ${j.name}`,
      value: j.id,
      code: j.id,
      name: j.name,
      image: j.image,
      unit: j.unit,
    }))
    supplierOptions.value = sRes.data.map((s) => ({ label: s.name, value: s.name }))
  } catch (_) {
    // error already shown by axios interceptor
  }
})
</script>
