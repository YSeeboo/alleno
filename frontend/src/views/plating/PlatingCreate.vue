<template>
  <div style="max-width: 800px;">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建电镀单</n-h2>
    </n-space>

    <n-form label-placement="left" label-width="100" style="margin-bottom: 16px;">
      <n-form-item label="电镀厂名称">
        <n-select
          v-model:value="supplierName"
          :options="supplierOptions"
          filterable
          tag
          placeholder="选择或输入电镀厂名称"
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
          placeholder="不填则使用当前时间"
          style="width: 300px;"
        />
      </n-form-item>
    </n-form>

    <n-card title="电镀明细" style="margin-bottom: 16px;">
      <div v-for="(item, idx) in items" :key="idx" style="margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid #f0f0f0;">
        <n-space align="center" style="margin-bottom: 8px;">
          <n-select
            v-model:value="item.part_id"
            :options="partOptions"
            :render-label="renderOptionWithImage"
            filterable
            placeholder="发出配件"
            style="width: 220px;"
            @update:value="(val) => onPartSelect(item, val)"
          />
          <n-input-number v-model:value="item.qty" :min="1" :precision="0" :step="1" placeholder="发出数量" style="width: 110px;" />
          <n-select
            v-model:value="item.unit"
            :options="unitOptions"
            style="width: 90px;"
          />
          <n-input v-model:value="item.note" placeholder="备注" style="width: 140px;" />
          <n-button type="error" size="small" @click="items.splice(idx, 1)">删除</n-button>
        </n-space>
        <div v-if="item.part_id" style="margin-left: 4px;">
          <div style="margin-bottom: 6px; font-size: 13px; color: #666;">电镀颜色：</div>
          <n-space size="small" style="margin-bottom: 6px;">
            <span
              v-for="cv in colorVariants"
              :key="cv.code"
              :style="{
                display: 'inline-block',
                fontSize: '11px',
                fontWeight: 'bold',
                color: item._selectedColor === cv.code ? '#fff' : BADGE_COLORS[cv.code],
                background: item._selectedColor === cv.code ? BADGE_COLORS[cv.code] : '#f5f5f5',
                padding: '2px 10px',
                borderRadius: '4px',
                cursor: 'pointer',
                border: `1px solid ${BADGE_COLORS[cv.code]}`,
              }"
              @click="toggleColor(item, cv.code)"
            >{{ cv.code }}</span>
          </n-space>
          <div v-if="item._selectedColor && item._variantInfo" style="font-size: 13px; color: #333;">
            <template v-if="item._variantInfo.part">
              <span>对应配件：{{ item._variantInfo.part.name }} ({{ item._variantInfo.part.id }})</span>
            </template>
            <template v-else-if="item._variantInfo.suggested_name">
              <span style="color: #999;">对应配件：{{ item._variantInfo.suggested_name }}</span>
              <n-button
                size="tiny"
                type="primary"
                style="margin-left: 8px;"
                :loading="item._creatingVariant"
                @click="doCreateVariantForItem(item)"
              >新建</n-button>
            </template>
          </div>
          <div v-if="item._selectedColor && item._variantLoading" style="font-size: 13px; color: #999;">
            查询中...
          </div>
        </div>
      </div>
      <n-button dashed style="width: 100%;" @click="addItem">
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
import { useMessage, useDialog } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NH2, NDatePicker } from 'naive-ui'
import { listParts, findOrCreateVariant, createPartVariant, getColorVariants } from '@/api/parts'
import { createPlating } from '@/api/plating'
import { listSuppliers, createSupplier } from '@/api/suppliers'
import { renderOptionWithImage } from '@/utils/ui'
import { tsToDateStr } from '@/utils/date'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const supplierName = ref(null)
const supplierOptions = ref([])
const note = ref('')
const createdAtTs = ref(null)
const items = reactive([createEmptyItem()])
const submitting = ref(false)
const partOptions = ref([])
const allParts = ref([])
const colorVariants = ref([])

const BADGE_COLORS = { G: '#DAA520', S: '#C0C0C0', RG: '#B76E79' }
const COLOR_CODE_TO_METHOD = { G: '金', S: '白K', RG: '玫瑰金' }

function createEmptyItem() {
  return { part_id: null, receive_part_id: null, qty: 1, unit: '个', plating_method: '金', note: '', _selectedColor: null, _variantInfo: null, _variantLoading: false, _creatingVariant: false, _reqSeq: 0 }
}

const unitOptions = [
  { label: '个', value: '个' },
  { label: '条', value: '条' },
  { label: '米', value: '米' },
  { label: 'g', value: 'g' },
  { label: 'kg', value: 'kg' },
]

const COLOR_LABEL_TO_CODE = { '金色': 'G', '白K': 'S', '玫瑰金': 'RG' }

const getPartColorCode = (part) => {
  if (!part) return null
  // Prefer the color field (authoritative)
  if (part.color && COLOR_LABEL_TO_CODE[part.color]) return COLOR_LABEL_TO_CODE[part.color]
  // Fallback: parse name suffix
  for (const [suffix, code] of Object.entries({ '_金色': 'G', '_白K': 'S', '_玫瑰金': 'RG' })) {
    if (part.name?.endsWith(suffix)) return code
  }
  return null
}

const onPartSelect = (item, val) => {
  const found = partOptions.value.find((p) => p.value === val)
  item.unit = found?.unit || '个'
  item.receive_part_id = null
  item._selectedColor = null
  item._variantInfo = null
  item._variantLoading = false
  ++item._reqSeq
  if (val) {
    const part = allParts.value.find((p) => p.id === val)
    const existingCode = getPartColorCode(part)
    // Default: use existing color if variant, otherwise G
    toggleColor(item, existingCode || 'G')
  }
}

const toggleColor = async (item, code) => {
  if (item._selectedColor === code) {
    // Deselect
    item._selectedColor = null
    item._variantInfo = null
    item.receive_part_id = null
    item.plating_method = '金'
    return
  }
  item._selectedColor = code
  item.plating_method = COLOR_CODE_TO_METHOD[code] || '金'
  item.receive_part_id = null
  item._variantInfo = null
  item._variantLoading = true
  const seq = ++item._reqSeq
  try {
    const { data } = await findOrCreateVariant(item.part_id, { color_code: code })
    if (item._reqSeq !== seq) return // stale
    item._variantInfo = data
    item.receive_part_id = data.part?.id || null
  } catch (e) {
    if (item._reqSeq === seq) {
      message.error(e.response?.data?.detail || '查询变体失败')
    }
  } finally {
    if (item._reqSeq === seq) {
      item._variantLoading = false
    }
  }
}

const doCreateVariantForItem = (item) => {
  const suggestedName = item._variantInfo?.suggested_name
  dialog.info({
    title: '确认新建',
    content: `当前没有 ${suggestedName}，确定新建吗？`,
    positiveText: '确认',
    negativeText: '取消',
    onPositiveClick: async () => {
      item._creatingVariant = true
      try {
        const { data: newPart } = await createPartVariant(item.part_id, { color_code: item._selectedColor })
        item.receive_part_id = newPart.id
        item._variantInfo = { part: newPart, created: true }
        // Refresh parts list
        const { data: parts } = await listParts()
        allParts.value = parts
        partOptions.value = parts.map((p) => ({
          label: `${p.id} ${p.name}`,
          value: p.id,
          code: p.id,
          name: p.name,
          image: p.image,
          unit: p.unit,
        }))
        message.success('变体创建成功')
      } catch (e) {
        message.error(e.response?.data?.detail || '创建变体失败')
      } finally {
        item._creatingVariant = false
      }
    },
  })
}

const addItem = () => {
  items.push(createEmptyItem())
}

const submit = async () => {
  if (!supplierName.value?.trim()) { message.warning('请输入电镀厂名称'); return }
  if (items.length === 0) { message.warning('请至少添加一条明细'); return }
  if (items.some((i) => !i.part_id)) { message.warning('请选择配件'); return }
  submitting.value = true
  try {
    // Auto-create supplier if new (swallow duplicate 400, rethrow others)
    const isNew = !supplierOptions.value.some((o) => o.value === supplierName.value)
    if (isNew) {
      try { await createSupplier({ name: supplierName.value, type: 'plating' }) } catch (e) { if (e.response?.status !== 400) throw e }
    }
    // Strip internal fields before submit
    const cleanItems = items.map(({ _selectedColor, _variantInfo, _variantLoading, _creatingVariant, ...rest }) => rest)
    const payload = { supplier_name: supplierName.value, items: cleanItems, note: note.value }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createPlating(payload)
    message.success('创建成功')
    router.push(`/plating/${data.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    const [partsRes, colorsRes, suppliersRes] = await Promise.all([
      listParts(), getColorVariants(), listSuppliers({ type: 'plating' }),
    ])
    allParts.value = partsRes.data
    partOptions.value = partsRes.data.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
      unit: p.unit,
    }))
    colorVariants.value = colorsRes.data
    supplierOptions.value = suppliersRes.data.map((s) => ({ label: s.name, value: s.name }))
  } catch (_) {
    // error already shown by axios interceptor
  }
})
</script>
