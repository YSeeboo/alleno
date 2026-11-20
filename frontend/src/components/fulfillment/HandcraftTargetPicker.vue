<template>
  <div class="handcraft-target-picker">
    <label :for="id">制作单处理方式</label>
    <n-select :id="id" :value="modelValue || ''" :options="selectOptions" :disabled="disabled" :loading="loading" aria-label="制作单处理方式" @update:value="$emit('update:modelValue', $event || null)" />
    <small>{{ modelValue ? '只追加本次新增明细，不合并或改写原明细；保存时重新检查商家、状态和归档。' : '不会因为同商家、同一天而自动合单。需要追加时，请明确选择上方具体单号。' }}</small>
    <small v-if="loading">正在查询本商家的可追加单…</small>
    <small v-if="error" role="alert">{{ error }} <n-button text type="primary" :disabled="disabled" @click="load">重试查询</n-button></small>
  </div>
</template>
<script setup>
import { computed, ref, watch, useId } from 'vue'
import { NButton, NSelect } from 'naive-ui'
import { listHandcraft } from '@/api/handcraft'
const props = defineProps({ modelValue: String, supplierName: String, disabled: Boolean })
const emit = defineEmits(['update:modelValue'])
const id = useId(), options = ref([]), loading = ref(false), error = ref('')
const selectOptions = computed(() => [
  { label: '新建独立手工单（默认）', value: '' },
  ...options.value.map(order => ({ label: `追加到 ${order.id} · ${order.created_at?.slice(0,10)}`, value: order.id })),
])
let requestId = 0
async function load() {
  const request = ++requestId
  options.value = []; error.value = ''
  if (!props.supplierName?.trim()) { loading.value = false; return }
  loading.value = true
  try { const { data } = await listHandcraft({ supplier_name: props.supplierName.trim(), status: 'pending', archive: 'active' }); if (request === requestId) options.value = data }
  catch (_) { if (request === requestId) error.value = '可追加单查询失败；仍可新建独立单，但不能选择未知旧单。' }
  finally { if (request === requestId) loading.value = false }
}
watch(() => props.supplierName, () => { emit('update:modelValue', null); load() }, { immediate: true })
</script>
<style scoped>
.handcraft-target-picker { display:flex; flex-direction:column; gap:8px; margin:8px 0 20px; max-width:600px; }
label { color:#333639; font-size:14px; }
small { color:#6B7280; font-size:12px; line-height:1.8; }
</style>
