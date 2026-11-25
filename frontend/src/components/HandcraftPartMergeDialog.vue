<template>
  <n-modal
    :show="true"
    preset="card"
    :title="bulk ? '合并相同配件' : '合并此配件'"
    class="part-merge-modal"
    :style="{ width: 'min(680px, calc(100vw - 24px))' }"
    :closable="!saving"
    :close-on-esc="!saving"
    :mask-closable="false"
    @update:show="(show) => { if (!show) close() }"
  >
    <p class="merge-intro">手工单 {{ orderId }} · 请核对发出数量，确认后才会更新明细。</p>
    <div class="merge-preview">
      <section v-for="group in groups" :key="group.retain_item_id" class="merge-group">
        <header class="merge-group-heading">
          <n-checkbox
            v-if="bulk"
            :checked="selected.includes(group.retain_item_id)"
            :disabled="saving || stale"
            @update:checked="checked => toggle(group.retain_item_id, checked)"
          >{{ group.part_name }} · {{ group.part_id }}</n-checkbox>
          <strong v-else>{{ group.part_name }} · {{ group.part_id }}</strong>
          <n-tag size="small" type="success">{{ group.rows.length }} 行 → 1 行</n-tag>
        </header>
        <div class="merge-comparison">
          <div class="merge-before">
            <h4>合并前</h4>
            <ul>
              <li v-for="row in group.rows" :key="row.id">
                <div><span>明细 #{{ row.id }}</span><strong>{{ quantity(row.qty) }} {{ group.unit }}</strong></div>
                <small v-if="row.note" class="merge-note">备注：{{ row.note }}</small>
              </li>
            </ul>
          </div>
          <div class="merge-after">
            <h4>合并后</h4>
            <strong class="merge-qty">{{ quantity(group.merged_qty) }} {{ group.unit }}</strong>
            <div>保留明细 #{{ group.retain_item_id }}</div>
            <div v-if="group.merged_bom_qty != null">BOM 理论用量：{{ quantity(group.merged_bom_qty) }} {{ group.unit }}</div>
            <small v-if="group.merged_note" class="merge-note">备注：{{ group.merged_note }}</small>
          </div>
        </div>
      </section>
    </div>
    <p class="merge-intro">每组保留第一行，其余重复行移除。单位不换算，不改变单据状态或库存。</p>
    <n-alert v-if="error" type="error" role="alert">{{ error }}</n-alert>
    <template #footer>
      <div class="merge-footer">
        <span role="status">{{ chosen.length ? `已选 ${chosen.length} 组 · ${originalCount} 行 → ${chosen.length} 行` : '请选择要合并的配件' }}</span>
        <n-space>
          <n-button :disabled="saving" @click="close">{{ stale ? '关闭' : '取消' }}</n-button>
          <n-button type="primary" :loading="saving" :disabled="!chosen.length || stale || saving" @click="apply">确认合并</n-button>
        </n-space>
      </div>
    </template>
  </n-modal>
</template>

<script setup>
import { computed, ref } from 'vue'
import { NAlert, NButton, NCheckbox, NModal, NSpace, NTag } from 'naive-ui'
import { applyHandcraftPartMerge } from '@/api/handcraft'

const props = defineProps({
  orderId: { type: String, required: true },
  groups: { type: Array, required: true },
  bulk: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved'])
const selected = ref(props.groups.map(group => group.retain_item_id))
const chosen = computed(() => props.groups.filter(group => selected.value.includes(group.retain_item_id)))
const originalCount = computed(() => chosen.value.reduce((count, group) => count + group.rows.length, 0))
const saving = ref(false)
const stale = ref(false)
const error = ref('')
const formatQuantity = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 4 })
const quantity = value => formatQuantity.format(Number(value))

function toggle(id, checked) {
  selected.value = checked ? [...selected.value, id] : selected.value.filter(value => value !== id)
}

function close() {
  if (!saving.value) emit('close', stale.value)
}

async function apply() {
  if (!chosen.value.length || saving.value || stale.value) return
  saving.value = true
  error.value = ''
  try {
    const { data } = await applyHandcraftPartMerge(props.orderId, chosen.value.map(group => ({
      retain_item_id: group.retain_item_id,
      revision: group.revision,
    })))
    emit('saved', data)
  } catch (err) {
    stale.value = err.response?.status === 409 || !err.response
    const detail = err.response?.data?.detail
    error.value = typeof detail === 'string' ? detail : '未能确认合并结果，请关闭后重新查看明细。'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.merge-intro { margin: 0 0 10px; color: #666; font-size: 13px; }
.merge-preview { display: grid; gap: 10px; max-height: 46dvh; overflow-y: auto; margin-bottom: 10px; }
.merge-group { min-width: 0; border: 1px solid #e4ebe7; border-radius: 8px; }
.merge-group-heading, .merge-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.merge-group-heading { padding: 8px 10px; border-bottom: 1px solid #e4ebe7; overflow-wrap: anywhere; }
.merge-comparison { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding: 8px; }
.merge-before, .merge-after { padding: 8px; border-radius: 5px; overflow-wrap: anywhere; background: #f7f9f8; }
.merge-after { background: #edf6f0; }
.merge-comparison h4 { margin: 0 0 4px; color: #52635a; font-size: 13px; }
.merge-before ul { margin: 0; padding: 0; list-style: none; }
.merge-before li { padding: 2px 0; }
.merge-before li div { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0 6px; }
.merge-qty { display: block; color: #166049; font-size: 20px; }
.merge-note { display: block; white-space: pre-wrap; color: #52635a; }
.merge-footer > span { font-weight: 600; font-size: 13px; }
@media (max-width: 520px) {
  .merge-preview { max-height: 40dvh; }
  .merge-footer { justify-content: flex-end; }
  .merge-footer > span { margin-right: auto; }
}
</style>
