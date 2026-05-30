<template>
  <n-select
    :value="value"
    :options="options"
    filterable
    tag
    clearable
    :placeholder="placeholder"
    :loading="loading"
    :size="size"
    :disabled="disabled"
    @update:value="onUpdate"
    @search="onSearch"
  />
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { NSelect } from 'naive-ui'
import { getCustomerNames } from '@/api/customers'

const props = defineProps({
  value: { type: String, default: null },
  placeholder: { type: String, default: '客户名' },
  size: { type: String, default: 'small' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:value'])

const options = ref([])
const loading = ref(false)

async function loadNames(q) {
  loading.value = true
  try {
    const { data } = await getCustomerNames(q)
    // Naive expects {label, value} options. Customer names are strings; both
    // fields share the same value so user-typed (tag) values still match.
    options.value = (data || []).map((n) => ({ label: n, value: n }))
    // If we have a current value not in the list, surface it as an option so
    // the select renders it instead of blanking.
    if (props.value && !options.value.find((o) => o.value === props.value)) {
      options.value.unshift({ label: props.value, value: props.value })
    }
  } catch (_) {
    options.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => loadNames())

let searchTimer = null
function onSearch(q) {
  // Debounce 200ms so we don't hammer the API while the user is typing.
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadNames(q), 200)
}

function onUpdate(v) {
  emit('update:value', v)
}
</script>
