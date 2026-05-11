<template>
  <n-modal
    :show="show"
    preset="card"
    title="加入到手工单"
    :style="{ width: isMobile ? '95vw' : '460px' }"
    :mask-closable="false"
    @update:show="$emit('update:show', $event)"
  >
    <n-radio-group v-model:value="target" name="attach-target">
      <n-space vertical size="medium">
        <div :class="['target-card', target === 'existing' ? 'selected' : '']" @click="target = 'existing'">
          <n-radio value="existing">
            <strong>加入已有 pending 单</strong>
          </n-radio>
          <div v-if="target === 'existing'" style="margin: 8px 0 0 24px; display: flex; flex-direction: column; gap: 8px;">
            <n-select
              v-model:value="existingSupplier"
              :options="supplierOptions"
              filterable
              placeholder="选择手工商家"
              style="width: 100%;"
              @update:value="onSupplierChange"
            />
            <n-select
              v-model:value="existingOrderId"
              :options="orderOptions"
              :disabled="!existingSupplier || orderOptions.length === 0"
              filterable
              :placeholder="existingSupplier ? (orderOptions.length === 0 ? '该商家无 pending 单' : '选择手工单') : '请先选商家'"
              style="width: 100%;"
            />
          </div>
        </div>

        <div :class="['target-card', target === 'new' ? 'selected' : '']" @click="target = 'new'">
          <n-radio value="new">
            <strong>新建一张</strong>
          </n-radio>
          <div v-if="target === 'new'" style="margin: 8px 0 0 24px; display: flex; flex-direction: column; gap: 8px;">
            <n-select
              v-model:value="newSupplierName"
              :options="supplierOptions"
              filterable
              tag
              placeholder="选择或新建手工商家"
              style="width: 100%;"
            />
            <n-input v-model:value="newNote" placeholder="备注（可选）" />
          </div>
        </div>
      </n-space>
    </n-radio-group>

    <div class="preview-bar">
      📦 将带入 <strong>{{ effectiveParts.length }}</strong> 项 part ·
      共 <strong>{{ totalQty }}</strong> 件
      <span v-if="zeroQtyCount > 0" style="color: #b45309; margin-left: 8px;">
        （{{ zeroQtyCount }} 项数量为 0，已跳过）
      </span>
    </div>

    <template #footer>
      <n-space justify="end">
        <n-button :disabled="submitting" @click="$emit('update:show', false)">取消</n-button>
        <n-button
          type="primary"
          :loading="submitting"
          :disabled="!canSubmit"
          @click="confirm"
        >确认并跳转</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NModal, NRadio, NRadioGroup, NSelect, NInput, NButton, NSpace } from 'naive-ui'
import { listSuppliers, createSupplier } from '@/api/suppliers'
import { listHandcraft, createHandcraft } from '@/api/handcraft'
import { attachPartsToOrder } from '@/api/handcraftActions'
import { useIsMobile } from '@/composables/useIsMobile'

const props = defineProps({
  show: Boolean,
  // Batch parts: [{ part_id, name, image, unit, imported_qty }]
  batchParts: { type: Array, default: () => [] },
  // Which radio target should be selected when the modal opens.
  // Set by the caller's openAttach(key). Allowed: 'new' | 'existing'.
  initialTarget: { type: String, default: 'new' },
})
const emit = defineEmits(['update:show'])

const router = useRouter()
const message = useMessage()
const { isMobile } = useIsMobile()

const target = ref('new') // default per spec — high-frequency path
const supplierOptions = ref([])

// existing-order state
const existingSupplier = ref(null)
const existingOrderId = ref(null)
const orderOptions = ref([])

// new-order state
const newSupplierName = ref(null)
const newNote = ref('')

const submitting = ref(false)

// --- Effective parts (filter qty <= 0) ---
const effectiveParts = computed(() =>
  props.batchParts.filter((p) => Number(p.imported_qty) > 0),
)
const zeroQtyCount = computed(() => props.batchParts.length - effectiveParts.value.length)
const totalQty = computed(() =>
  effectiveParts.value.reduce((s, p) => s + Number(p.imported_qty), 0),
)

const canSubmit = computed(() => {
  if (effectiveParts.value.length === 0) return false
  if (target.value === 'existing') return !!existingOrderId.value
  if (target.value === 'new') return !!newSupplierName.value?.trim()
  return false
})

// --- Load suppliers when modal becomes visible ---
watch(
  () => props.show,
  async (v) => {
    if (!v) return
    // Reset transient state — keep the form consistent across reopens.
    target.value = props.initialTarget
    existingSupplier.value = null
    existingOrderId.value = null
    orderOptions.value = []
    newSupplierName.value = null
    newNote.value = ''
    try {
      const { data } = await listSuppliers({ type: 'handcraft' })
      supplierOptions.value = data.map((s) => ({ label: s.name, value: s.name }))
    } catch (_) { /* axios interceptor handled */ }
  },
)

const onSupplierChange = async (name) => {
  existingOrderId.value = null
  if (!name) {
    orderOptions.value = []
    return
  }
  try {
    const { data } = await listHandcraft({ supplier_name: name, status: 'pending' })
    orderOptions.value = (data.items || data || []).map((o) => ({
      label: `${o.id} · ${o.created_at?.slice(0, 10) || ''}`,
      value: o.id,
    }))
  } catch (_) {
    orderOptions.value = []
  }
}

// --- Confirm ---
const confirm = async () => {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    const partsPayload = effectiveParts.value.map((p) => ({
      part_id: p.part_id,
      qty: Number(p.imported_qty),
      unit: p.unit || '个',
    }))

    let targetOrderId = null

    if (target.value === 'new') {
      const supplier = newSupplierName.value.trim()
      // Ensure supplier exists (mirrors HandcraftCreate logic).
      const isNewSupplier = !supplierOptions.value.some((o) => o.value === supplier)
      if (isNewSupplier) {
        try {
          await createSupplier({ name: supplier, type: 'handcraft' })
        } catch (e) {
          if (e.response?.status !== 400) throw e
        }
      }
      const { data } = await createHandcraft({
        supplier_name: supplier,
        parts: partsPayload,
        jewelries: [],
        note: newNote.value || '',
      })
      targetOrderId = data.id
      message.success(`已创建手工单 ${data.id}（${partsPayload.length} 项已带入）`)
    } else {
      // existing
      targetOrderId = existingOrderId.value
      try {
        const { okNew, okUpd, failures } = await attachPartsToOrder(targetOrderId, partsPayload)
        failures.forEach((f) => {
          message.error(`${f.part_id} 加入失败：${f.detail}`)
        })
        const okCount = okNew + okUpd
        if (okCount > 0) {
          message.success(`已加入 ${okCount} 项${failures.length > 0 ? `（${failures.length} 项失败）` : ''}`)
        } else {
          // Nothing succeeded; don't navigate.
          return
        }
      } catch (err) {
        if (err?.code === 'NOT_PENDING') {
          message.error(err.message)
          return
        }
        throw err
      }
    }

    emit('update:show', false)
    if (targetOrderId) router.push(`/handcraft/${targetOrderId}`)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.target-card {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all .15s;
}
.target-card.selected {
  border-color: #18a058;
  background: #f0fdf4;
}
.preview-bar {
  margin-top: 14px;
  padding: 10px 12px;
  background: #f0f6ff;
  border: 1px solid #d6e4ff;
  border-radius: 4px;
  font-size: 12px;
  color: #1d4ed8;
}
.preview-bar strong { font-variant-numeric: tabular-nums; }
</style>
