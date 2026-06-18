<template>
  <!-- Desktop: n-modal card -->
  <n-modal
    v-if="!isMobile"
    :show="show"
    preset="card"
    :title="null"
    :style="{ width: '620px', maxHeight: '90vh' }"
    :mask-closable="false"
    @update:show="emit('update:show', $event)"
  >
    <!-- Header -->
    <template #header>
      <div>
        <div style="font-size: 16px; font-weight: 600; margin-bottom: 3px;">配件回收</div>
        <div style="font-size: 12px; color: #9ca3af; font-weight: 400;">该商家发出的配件余料，勾选并填写回收数量</div>
      </div>
    </template>

    <!-- Filter -->
    <div style="margin-bottom: 12px;">
      <n-input
        v-model:value="filterText"
        placeholder="配件名称 / 编号筛选"
        clearable
        style="width: 100%;"
      >
        <template #prefix>
          <span style="color: #9ca3af;">🔍</span>
        </template>
      </n-input>
    </div>

    <!-- Part rows -->
    <div style="overflow-y: auto; max-height: 380px;">
      <div
        v-for="part in filteredParts"
        :key="part.id"
        style="display: flex; align-items: center; gap: 11px; padding: 10px 0; border-bottom: 1px solid #f0f1f3;"
      >
        <n-checkbox
          :checked="!!localSel[String(part.id)]"
          @update:checked="(v) => togglePart(part, v)"
        />
        <n-image
          :src="part.item_image || ''"
          width="38"
          height="38"
          object-fit="cover"
          style="border-radius: 7px; flex: none; background: linear-gradient(135deg, #f3d9b1, #d9a441); cursor: zoom-in;"
          :fallback-src="''"
          :preview-disabled="!part.item_image"
        />
        <div style="flex: 1; min-width: 0;">
          <div style="font-size: 13.5px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{{ part.item_name }}</div>
          <div style="font-size: 11px; color: #9ca3af;">{{ part.item_id }}<span v-if="part.color"> · {{ part.color }}</span></div>
        </div>
        <span style="font-size: 12px; color: #6b7280; width: 74px; text-align: right; flex: none;">
          剩余 {{ getRemaining(part) }}
        </span>
        <n-input-number
          :value="localSel[String(part.id)] ?? null"
          :min="0.0001"
          :max="getRemaining(part)"
          :precision="4"
          :step="1"
          size="small"
          style="width: 110px; flex: none;"
          :disabled="!localSel[String(part.id)]"
          @update:value="(v) => setQty(part, v)"
        />
      </div>
      <n-empty
        v-if="filteredParts.length === 0"
        description="无配件"
        style="padding: 24px 0;"
      />
    </div>

    <!-- Footer -->
    <template #footer>
      <div style="display: flex; align-items: center; gap: 10px;">
        <span style="font-size: 12px; color: #9ca3af;">已选 {{ selectedCount }} 项</span>
        <div style="flex: 1;" />
        <n-button @click="onCancel">取消</n-button>
        <n-button type="primary" @click="onConfirm">确定（{{ selectedCount }}）</n-button>
      </div>
    </template>
  </n-modal>

  <!-- Mobile: bottom sheet -->
  <teleport v-else to="body">
    <transition name="sheet-fade">
      <div
        v-if="show"
        style="position: fixed; inset: 0; background: rgba(17,17,17,0.4); z-index: 2000; display: flex; align-items: flex-end;"
        @click.self="onCancel"
      >
        <div style="width: 100%; height: 86%; background: #fff; border-radius: 18px 18px 0 0; display: flex; flex-direction: column; overflow: hidden;">
          <!-- grab bar -->
          <div style="width: 38px; height: 4px; background: #dcdfe4; border-radius: 2px; margin: 9px auto 4px;" />
          <!-- header -->
          <div style="padding: 4px 16px 12px; border-bottom: 1px solid #f0f1f3;">
            <div style="font-size: 16px; font-weight: 600; margin-bottom: 3px;">配件回收</div>
            <div style="font-size: 12px; color: #9ca3af;">该商家发出的配件余料，勾选并填写回收数量</div>
            <n-input
              v-model:value="filterText"
              placeholder="配件名称 / 编号筛选"
              clearable
              style="width: 100%; margin-top: 10px;"
            >
              <template #prefix>
                <span style="color: #9ca3af;">🔍</span>
              </template>
            </n-input>
          </div>
          <!-- body -->
          <div style="flex: 1; overflow-y: auto; padding: 0 16px;">
            <div
              v-for="part in filteredParts"
              :key="part.id"
              :style="{
                border: '1px solid ' + (localSel[String(part.id)] ? '#c7cbf5' : '#e5e7eb'),
                background: localSel[String(part.id)] ? '#f3f4fe' : '#fff',
                borderRadius: '9px',
                padding: '11px',
                marginTop: '10px',
              }"
            >
              <div style="display: flex; align-items: center; gap: 10px;">
                <n-checkbox
                  :checked="!!localSel[String(part.id)]"
                  @update:checked="(v) => togglePart(part, v)"
                />
                <n-image
                  :src="part.item_image || ''"
                  width="38"
                  height="38"
                  object-fit="cover"
                  style="border-radius: 7px; flex: none; background: linear-gradient(135deg, #f3d9b1, #d9a441);"
                  :fallback-src="''"
                  :preview-disabled="!part.item_image"
                />
                <div style="flex: 1; min-width: 0;">
                  <div style="font-size: 13.5px; font-weight: 500;">{{ part.item_name }}</div>
                  <div style="font-size: 11px; color: #9ca3af;">{{ part.item_id }}<span v-if="part.color"> · {{ part.color }}</span> · 剩余 {{ getRemaining(part) }}</div>
                </div>
              </div>
              <div v-if="localSel[String(part.id)]" style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #e5e7eb;">
                <div style="font-size: 11px; color: #9ca3af; margin-bottom: 3px;">回收数量</div>
                <n-input-number
                  :value="localSel[String(part.id)] ?? null"
                  :min="0.0001"
                  :max="getRemaining(part)"
                  :precision="4"
                  :step="1"
                  style="width: 100%;"
                  @update:value="(v) => setQty(part, v)"
                />
              </div>
            </div>
            <n-empty
              v-if="filteredParts.length === 0"
              description="无配件"
              style="padding: 24px 0;"
            />
          </div>
          <!-- footer -->
          <div style="padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px)); border-top: 1px solid #f0f1f3; display: flex; gap: 10px;">
            <n-button style="flex: 1; height: 44px; border-radius: 10px;" @click="onCancel">取消</n-button>
            <n-button type="primary" style="flex: 1.4; height: 44px; border-radius: 10px;" @click="onConfirm">确定（{{ selectedCount }}）</n-button>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  NModal, NInput, NInputNumber, NCheckbox, NImage, NButton, NEmpty,
} from 'naive-ui'

const props = defineProps({
  show: { type: Boolean, required: true },
  parts: { type: Array, default: () => [] },
  selections: { type: Object, default: () => ({}) },
  isMobile: { type: Boolean, default: false },
})

const emit = defineEmits(['update:show', 'confirm', 'cancel'])

const filterText = ref('')

// Local selection: {String(partId): qty}
const localSel = ref({})

// Initialize localSel from selections whenever modal opens
watch(() => props.show, (val) => {
  if (val) {
    filterText.value = ''
    // Deep copy from props.selections
    localSel.value = {}
    for (const [k, v] of Object.entries(props.selections)) {
      if (v > 0) localSel.value[String(k)] = v
    }
  }
})

const getRemaining = (part) => part.qty - (part.received_qty || 0)

const filteredParts = computed(() => {
  const q = filterText.value.trim().toLowerCase()
  if (!q) return props.parts
  return props.parts.filter(
    (p) => (p.item_name || '').toLowerCase().includes(q) || (p.item_id || '').toLowerCase().includes(q),
  )
})

const selectedCount = computed(() => Object.values(localSel.value).filter((v) => v != null && v > 0).length)

const togglePart = (part, checked) => {
  const key = String(part.id)
  if (checked) {
    // Default qty = remaining
    const remaining = getRemaining(part)
    localSel.value[key] = remaining > 0 ? remaining : 0.0001
  } else {
    delete localSel.value[key]
  }
}

const setQty = (part, v) => {
  const key = String(part.id)
  if (v != null && v > 0) {
    localSel.value[key] = v
  } else if (localSel.value[key] !== undefined) {
    // Keep checked but qty becomes null — store 0 as sentinel to avoid losing selection
    // Actually: if qty cleared, keep selection but store null to indicate incomplete
    localSel.value[key] = v
  }
}

const onConfirm = () => {
  // Only pass entries with positive qty
  const result = {}
  for (const [k, v] of Object.entries(localSel.value)) {
    if (v != null && v > 0) result[k] = v
  }
  emit('confirm', result)
  emit('update:show', false)
}

const onCancel = () => {
  emit('cancel')
  emit('update:show', false)
}
</script>

<style scoped>
.sheet-fade-enter-active,
.sheet-fade-leave-active {
  transition: opacity 0.2s ease;
}
.sheet-fade-enter-from,
.sheet-fade-leave-to {
  opacity: 0;
}
</style>
