<template>
  <div :style="{ maxWidth: isMobile ? '100%' : '900px' }">
    <n-space align="center" style="margin-bottom: 16px;">
      <n-button text @click="router.back()">← 返回</n-button>
      <n-h2 style="margin: 0;">新建手工单</n-h2>
    </n-space>

    <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="110" style="margin-bottom: 16px;">
      <n-form-item label="手工商家名称">
        <n-select
          v-model:value="supplierName"
          :options="supplierOptions"
          filterable
          tag
          placeholder="选择或输入手工商家名称"
          :style="{ width: isMobile ? '100%' : '300px' }"
        />
      </n-form-item>
      <n-form-item label="备注">
        <n-input v-model:value="note" type="textarea" :rows="2" :style="{ width: isMobile ? '100%' : '300px' }" />
      </n-form-item>
      <n-form-item label="创建时间">
        <n-date-picker
          v-model:value="createdAtTs"
          type="date"
          clearable
          placeholder="不填则使用当前时间，填写后不触发同日合并"
          :style="{ width: isMobile ? '100%' : '360px' }"
        />
      </n-form-item>
    </n-form>

    <n-grid :cols="isMobile ? 1 : 2" :x-gap="16" style="margin-bottom: 16px;">
      <!-- 左: 预期产出 -->
      <n-gi>
        <n-card title="预期产出">
          <div v-for="(group, gIdx) in groups" :key="gIdx" style="margin-bottom: 10px;">
            <n-space align="center">
              <img
                v-if="getOutputImage(group)"
                :src="getOutputImage(group)"
                class="thumb"
                @click="previewImage(getOutputImage(group))"
              />
              <div v-else class="thumb-placeholder">无图</div>
              <n-select
                v-model:value="group.output_type"
                :options="outputTypeOptions"
                style="width: 75px;"
                @update:value="() => onOutputTypeChange(group)"
              />
              <n-select
                v-if="group.output_type === 'jewelry'"
                v-model:value="group.jewelry_id"
                :options="jewelryOptions"
                :render-label="renderOptionWithImage"
                filterable
                clearable
                placeholder="选择饰品"
                style="width: 170px;"
                @update:value="(val) => onOutputSelect(group, val)"
              />
              <n-select
                v-else
                v-model:value="group.part_id"
                :options="compositePartOptions"
                :render-label="renderOptionWithImage"
                filterable
                clearable
                placeholder="选择组合配件"
                style="width: 170px;"
                @update:value="(val) => onOutputSelect(group, val)"
              />
              <n-input-number
                v-model:value="group.qty"
                :min="1" :precision="0" :step="1"
                placeholder="预期数量"
                style="width: 90px;"
                @update:value="(val) => onOutputQtyChange(group, val)"
              />
              <n-select
                v-model:value="group.unit"
                :options="group.output_type === 'jewelry' ? jewelryUnitOptions : partUnitOptions"
                style="width: 70px;"
              />
              <n-button type="error" size="small" @click="groups.splice(gIdx, 1)">删</n-button>
            </n-space>
          </div>
          <n-button dashed style="width: 100%;" @click="addGroup()">
            + 添加产出行
          </n-button>
        </n-card>
      </n-gi>

      <!-- 右: 发出配件 (分组) -->
      <n-gi>
        <div style="font-weight: 600; font-size: 14px; margin-bottom: 10px;">
          发出配件 <span style="font-size: 12px; color: #999;">(根据BOM自动生成，可手动修改)</span>
        </div>

        <div v-if="groups.length === 0" style="color: #999; font-size: 13px; padding: 20px 0; text-align: center;">
          请先在左侧添加产出行
        </div>

        <div v-for="(group, gIdx) in groups" :key="gIdx" class="group-card">
          <div class="group-header">
            <img
              v-if="getOutputImage(group)"
              :src="getOutputImage(group)"
              class="header-thumb"
              @click="previewImage(getOutputImage(group))"
            />
            <div v-else class="header-thumb-placeholder">无图</div>
            <n-tag :type="group.output_type === 'jewelry' ? 'info' : 'success'" size="small">
              {{ group.output_type === 'jewelry' ? '饰品' : '组合配件' }}
            </n-tag>
            <strong>{{ getOutputLabel(group) }}</strong>
            <span style="color: #999;">× {{ group.qty }}</span>
          </div>
          <div class="group-body">
            <div v-for="(item, idx) in group.parts" :key="idx" style="margin-bottom: 8px;">
              <n-space align="center">
                <img
                  v-if="getPartImage(item.part_id)"
                  :src="getPartImage(item.part_id)"
                  class="thumb"
                  @click="previewImage(getPartImage(item.part_id))"
                />
                <div v-else class="thumb-placeholder">无图</div>
                <n-select
                  v-model:value="item.part_id"
                  :options="partOptions"
                  :render-label="renderOptionWithImage"
                  filterable
                  clearable
                  placeholder="选择配件"
                  style="width: 150px;"
                  @update:value="(val) => onPartSelect(item, val)"
                />
                <n-input-number v-model:value="item.qty" :min="0.001" :step="1" placeholder="实际发出" style="width: 80px;" @update:value="() => { item._qty_per_unit = null }" />
                <n-select v-model:value="item.unit" :options="partUnitOptions" style="width: 70px;" />
                <n-input-number v-model:value="item.bom_qty" :min="0" :step="1" placeholder="BOM" style="width: 80px;" @update:value="() => { item._qty_per_unit = null }" />
                <n-button type="error" size="small" @click="group.parts.splice(idx, 1)">删</n-button>
              </n-space>
            </div>
            <n-button dashed size="small" style="width: 100%;" @click="group.parts.push({ part_id: null, qty: 1, unit: '个', bom_qty: null, _qty_per_unit: null, note: '' })">
              + 添加配件行
            </n-button>
          </div>
        </div>
      </n-gi>
    </n-grid>

    <n-space justify="end">
      <n-button type="primary" :loading="submitting" @click="submit">提交</n-button>
    </n-space>

    <!-- Image preview -->
    <div v-if="previewSrc" class="overlay" @click="previewSrc = null">
      <img :src="previewSrc" style="max-width: 80vw; max-height: 80vh; border-radius: 8px; box-shadow: 0 4px 24px rgba(0,0,0,.3);" />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NH2, NGrid, NGi, NDatePicker, NTag } from 'naive-ui'
import { listParts, getPartBom } from '@/api/parts'
import { listJewelries } from '@/api/jewelries'
import { getBom } from '@/api/bom'
import { createHandcraft } from '@/api/handcraft'
import { listSuppliers, createSupplier } from '@/api/suppliers'
import { renderOptionWithImage } from '@/utils/ui'
import { tsToDateStr } from '@/utils/date'
import { useIsMobile } from '@/composables/useIsMobile'

const router = useRouter()
const message = useMessage()
const { isMobile } = useIsMobile()
const supplierName = ref(null)
const supplierOptions = ref([])
const note = ref('')
const createdAtTs = ref(null)
const previewSrc = ref(null)

const groups = reactive([])

const outputTypeOptions = [
  { label: '饰品', value: 'jewelry' },
  { label: '配件', value: 'part' },
]
const submitting = ref(false)
const partOptions = ref([])
const compositePartOptions = ref([])
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

const previewImage = (src) => { previewSrc.value = src }

const getOutputImage = (group) => {
  if (group.output_type === 'jewelry') {
    const found = jewelryOptions.value.find((j) => j.value === group.jewelry_id)
    return found?.image || null
  }
  const found = partOptions.value.find((p) => p.value === group.part_id)
  return found?.image || null
}

const getOutputLabel = (group) => {
  if (group.output_type === 'jewelry') {
    const found = jewelryOptions.value.find((j) => j.value === group.jewelry_id)
    return found ? found.label : '未选择'
  }
  const found = partOptions.value.find((p) => p.value === group.part_id)
  return found ? found.label : '未选择'
}

const getPartImage = (partId) => {
  if (!partId) return null
  const found = partOptions.value.find((p) => p.value === partId)
  return found?.image || null
}

const onPartSelect = (item, val) => {
  const found = partOptions.value.find((p) => p.value === val)
  item.unit = found?.unit || '个'
  item._qty_per_unit = null
}

const addGroup = () => {
  groups.push({
    output_type: 'jewelry',
    jewelry_id: null,
    part_id: null,
    qty: 1,
    unit: '个',
    note: '',
    parts: [],
  })
}

const onOutputTypeChange = (group) => {
  group.jewelry_id = null
  group.part_id = null
  group.parts = []
  group.unit = '个'
}

const onOutputSelect = async (group, val) => {
  group.parts = []
  if (!val) return

  if (group.output_type === 'jewelry') {
    group.jewelry_id = val
    const found = jewelryOptions.value.find((j) => j.value === val)
    group.unit = found?.unit || '个'
    await fetchJewelryBom(group)
  } else {
    group.part_id = val
    const found = partOptions.value.find((p) => p.value === val)
    group.unit = found?.unit || '个'
    await fetchPartBom(group)
  }
}

const fetchJewelryBom = async (group) => {
  const snapshotId = group.jewelry_id
  try {
    const { data } = await getBom(snapshotId)
    if (group.jewelry_id !== snapshotId || group.output_type !== 'jewelry') return
    group.parts = data.map((row) => {
      const partOpt = partOptions.value.find((p) => p.value === row.part_id)
      const total = row.qty_per_unit * group.qty
      return {
        part_id: row.part_id,
        qty: total,
        unit: partOpt?.unit || '个',
        bom_qty: total,
        _qty_per_unit: row.qty_per_unit,
        note: '',
      }
    })
  } catch (_) {
    if (group.jewelry_id === snapshotId) group.parts = []
  }
}

const fetchPartBom = async (group) => {
  const snapshotId = group.part_id
  try {
    const { data } = await getPartBom(snapshotId)
    if (group.part_id !== snapshotId || group.output_type !== 'part') return
    group.parts = data.map((row) => {
      const partOpt = partOptions.value.find((p) => p.value === row.child_part_id)
      const total = row.qty_per_unit * group.qty
      return {
        part_id: row.child_part_id,
        qty: total,
        unit: partOpt?.unit || '个',
        bom_qty: total,
        _qty_per_unit: row.qty_per_unit,
        note: '',
      }
    })
  } catch (_) {
    if (group.part_id === snapshotId) group.parts = []
  }
}

const onOutputQtyChange = (group, newQty) => {
  if (!newQty || newQty < 1) return
  for (const item of group.parts) {
    if (item._qty_per_unit != null) {
      const total = item._qty_per_unit * newQty
      item.qty = total
      item.bom_qty = total
    }
  }
}

const normalizedParts = () => {
  const allParts = []
  for (const group of groups) {
    for (const item of group.parts) {
      if (item.part_id) {
        allParts.push({
          part_id: item.part_id,
          qty: item.qty,
          unit: item.unit,
          bom_qty: item.bom_qty,
          note: item.note,
        })
      }
    }
  }
  return allParts
}

const normalizedJewelries = () => groups
  .filter((g) => g.jewelry_id || g.part_id)
  .map((g) => {
    if (g.output_type === 'part') {
      return { part_id: g.part_id, qty: g.qty, unit: g.unit, note: g.note }
    }
    return { jewelry_id: g.jewelry_id, qty: g.qty, unit: g.unit, note: g.note }
  })

const submit = async () => {
  const validParts = normalizedParts()
  const validJewelries = normalizedJewelries()
  if (!supplierName.value?.trim()) { message.warning('请输入手工商家名称'); return }
  if (validParts.length === 0) { message.warning('请至少添加一条配件'); return }
  submitting.value = true
  try {
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
      is_composite: p.is_composite,
    }))
    compositePartOptions.value = partOptions.value.filter((p) => p.is_composite)
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

  // Start with one empty group
  addGroup()
})
</script>

<style scoped>
.thumb {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  object-fit: cover;
  cursor: pointer;
  border: 1px solid #e0e0e0;
  flex-shrink: 0;
  transition: box-shadow .15s;
}
.thumb:hover { box-shadow: 0 0 0 2px #18a058; }

.thumb-placeholder {
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
  background: #f5f5f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: #ccc;
  flex-shrink: 0;
}

.header-thumb {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  object-fit: cover;
  cursor: pointer;
  border: 1px solid #e0e0e0;
  flex-shrink: 0;
}
.header-thumb:hover { box-shadow: 0 0 0 2px #18a058; }

.header-thumb-placeholder {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  border: 1px solid #e0e0e0;
  background: #f5f5f5;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: #ccc;
  flex-shrink: 0;
}

.group-card {
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  margin-bottom: 12px;
  overflow: hidden;
}

.group-header {
  background: #fafafa;
  padding: 10px 14px;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.group-body {
  padding: 14px;
}

.overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, .6);
  z-index: 1000;
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
}
</style>
