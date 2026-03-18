<template>
  <div style="max-width: 900px;">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建手工单</n-h2>
    </n-space>

    <n-form label-placement="left" label-width="110" style="margin-bottom: 16px;">
      <n-form-item label="手工商家名称">
        <n-input v-model:value="supplierName" style="width: 300px;" />
      </n-form-item>
      <n-form-item label="备注">
        <n-input v-model:value="note" type="textarea" :rows="2" style="width: 300px;" />
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
        <n-card title="预期收回饰品">
          <div v-for="(item, idx) in jewelries" :key="idx" style="margin-bottom: 10px;">
            <n-space align="center">
              <n-select
                v-model:value="item.jewelry_id"
                :options="jewelryOptions"
                :render-label="renderOptionWithImage"
                filterable
                placeholder="选择饰品"
                style="width: 190px;"
                @update:value="(val) => onJewelrySelect(item, val)"
              />
              <n-input-number v-model:value="item.qty" :min="1" :precision="0" :step="1" placeholder="预期数量" style="width: 100px;" />
              <n-select
                v-model:value="item.unit"
                :options="jewelryUnitOptions"
                style="width: 80px;"
              />
              <n-button type="error" size="small" @click="jewelries.splice(idx, 1)">删</n-button>
            </n-space>
          </div>
          <n-button dashed style="width: 100%;" @click="jewelries.push({ jewelry_id: null, qty: 1, unit: '个', note: '' })">
            + 添加饰品行
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
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NH2, NGrid, NGi } from 'naive-ui'
import { listParts } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { createHandcraft } from '@/api/handcraft'
import { renderOptionWithImage } from '@/utils/ui'

const router = useRouter()
const message = useMessage()
const supplierName = ref('')
const note = ref('')
const parts = reactive([{ part_id: null, qty: 1, unit: '个', bom_qty: null, note: '' }])
const jewelries = reactive([{ jewelry_id: null, qty: 1, unit: '个', note: '' }])
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

const submit = async () => {
  if (!supplierName.value) { message.warning('请输入手工商家名称'); return }
  if (parts.length === 0) { message.warning('请至少添加一条配件'); return }
  if (jewelries.length === 0) { message.warning('请至少添加一条成品'); return }
  if (parts.some((p) => !p.part_id)) { message.warning('请选择配件'); return }
  if (jewelries.some((j) => !j.jewelry_id)) { message.warning('请选择饰品'); return }
  submitting.value = true
  try {
    const { data } = await createHandcraft({
      supplier_name: supplierName.value,
      parts,
      jewelries,
      note: note.value,
    })
    message.success('创建成功')
    router.push(`/handcraft/${data.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    const [pRes, jRes] = await Promise.all([listParts(), listJewelries({ status: 'active' })])
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
  } catch (_) {
    // error already shown by axios interceptor
  }
})
</script>
