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
          <n-select v-model:value="item.part_id" :options="partOptions" filterable placeholder="选择配件" style="width: 220px;" />
          <n-input-number v-model:value="item.qty" :min="0.01" placeholder="发出数量" style="width: 110px;" />
          <n-input v-model:value="item.plating_method" placeholder="电镀方式" style="width: 120px;" />
          <n-input v-model:value="item.note" placeholder="备注" style="width: 140px;" />
          <n-button type="error" size="small" @click="items.splice(idx, 1)">删除</n-button>
        </n-space>
      </div>
      <n-button dashed style="width: 100%;" @click="items.push({ part_id: null, qty: 1, plating_method: '', note: '' })">
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

const router = useRouter()
const message = useMessage()
const supplierName = ref('')
const note = ref('')
const items = reactive([{ part_id: null, qty: 1, plating_method: '', note: '' }])
const submitting = ref(false)
const partOptions = ref([])

const submit = async () => {
  if (!supplierName.value) { message.warning('请输入电镀厂名称'); return }
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
  const { data } = await listParts()
  partOptions.value = data.map((p) => ({ label: `${p.id} ${p.name}`, value: p.id }))
})
</script>
