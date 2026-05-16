<template>
  <n-modal :show="show" preset="card" :title="title" :style="{ width: '680px' }"
           :closable="!saving"
           :mask-closable="!saving"
           :close-on-esc="!saving"
           @update:show="onShowUpdate">
    <p class="hint">
      订单来源行只读，需要修改请回到对应订单。手填行可在此处编辑/删除（数量与新增仅在
      <strong>未发出</strong> 状态可用）。
    </p>
    <n-data-table :columns="columns" :data="rows" :bordered="false" size="small" />
    <n-button v-if="canAddManual" dashed block style="margin-top: 12px;"
              @click="addManualRow">
      + 添加手填客户
    </n-button>
    <div class="footer">
      <span class="sum" :class="sumClass">
        合计 <strong>{{ sumQty }}</strong> / {{ group.total_qty }}
      </span>
      <n-button :disabled="saving" @click="$emit('update:show', false)">关闭</n-button>
      <n-button type="primary" :loading="saving" @click="save">保存</n-button>
    </div>
  </n-modal>
</template>

<script setup>
import { ref, computed, watch, h } from 'vue'
import {
  NModal, NInput, NInputNumber, NButton, NTag, NDataTable, useMessage,
} from 'naive-ui'
import {
  addHandcraftJewelry, updateHandcraftJewelry, deleteHandcraftJewelry,
} from '@/api/handcraft'

const props = defineProps({
  show: Boolean,
  hcId: { type: String, required: true },
  hcStatus: { type: String, required: true },
  group: { type: Object, required: true },
})
const emit = defineEmits(['update:show', 'saved'])
const message = useMessage()

const rows = ref([])
const saving = ref(false)

watch(() => props.show, (v) => {
  if (v && props.group) {
    rows.value = props.group.entries.map((e) => ({
      ...e,
      _dirty: false,
      _new: false,
    }))
  }
})

// Block all close paths while a save is in flight. Naive-UI's close props
// already disable the X / mask / esc, but update:show also fires from those
// paths in some flows, so we double-gate here for safety.
function onShowUpdate(v) {
  if (!v && saving.value) return
  emit('update:show', v)
}

const canAddManual = computed(() => props.hcStatus === 'pending')
const canEditQty = computed(() => props.hcStatus === 'pending')

const sumQty = computed(() =>
  rows.value.reduce((acc, r) => acc + Number(r.qty || 0), 0),
)
const sumClass = computed(() =>
  sumQty.value === props.group.total_qty ? 'sum--ok' : 'sum--err',
)

const title = computed(
  () => `客户分拣 · ${props.group.jewelry_name || props.group.jewelry_id}`,
)

const columns = [
  {
    title: '客户',
    key: 'customer_name',
    render(row) {
      if (row.is_locked) {
        return h(
          'span',
          { style: 'color: rgba(0,0,0,.65)' },
          row.customer_name || '—',
        )
      }
      return h(NInput, {
        value: row.customer_name || '',
        'onUpdate:value': (v) => {
          row.customer_name = v
          row._dirty = true
        },
        size: 'small',
        placeholder: '客户名',
      })
    },
  },
  {
    title: '数量',
    key: 'qty',
    width: 110,
    render(row) {
      const editable = !row.is_locked && (row._new || canEditQty.value)
      if (!editable) {
        return h(
          'span',
          { style: 'font-family: monospace; color: rgba(0,0,0,.65)' },
          row.qty,
        )
      }
      return h(NInputNumber, {
        value: Number(row.qty),
        min: 1,
        showButton: false,
        size: 'small',
        'onUpdate:value': (v) => {
          row.qty = v || 0
          row._dirty = true
        },
      })
    },
  },
  {
    title: '来源',
    key: 'source',
    width: 180,
    render(row) {
      if (row.source === 'order') {
        return h(
          NTag,
          { size: 'small' },
          { default: () => `🔒 ${row.source_order_id}` },
        )
      }
      return h(
        NTag,
        { size: 'small', type: 'info' },
        { default: () => (row._new ? '手填 · 新增' : '手填') },
      )
    },
  },
  {
    title: '',
    key: 'action',
    width: 60,
    render(row) {
      // Locked (order-linked) rows can't be removed here — go to the
      // source order. Manual rows are removable in pending OR processing;
      // the backend enforces the same rule.
      if (row.is_locked) return null
      return h(
        NButton,
        {
          size: 'small',
          text: true,
          type: 'error',
          onClick: () => {
            rows.value = rows.value.filter((r) => r !== row)
          },
        },
        { default: () => '×' },
      )
    },
  },
]

function addManualRow() {
  rows.value.push({
    hc_jewelry_item_id: null,
    qty: 1,
    customer_name: '',
    source: 'manual',
    source_order_id: null,
    is_locked: false,
    _new: true,
    _dirty: true,
  })
}

async function save() {
  // Pre-flight validation — surface row-specific problems before any HTTP
  // call so we don't end up half-committed.
  for (let i = 0; i < rows.value.length; i++) {
    const r = rows.value[i]
    if (r.is_locked) continue
    const trimmed = (r.customer_name || '').trim()
    if (!trimmed) {
      message.error(`第 ${i + 1} 行客户名不能为空`)
      return
    }
    if (!(Number(r.qty) > 0)) {
      message.error(`第 ${i + 1} 行数量必须大于 0`)
      return
    }
  }

  saving.value = true
  // Save is not transactional across the multiple HTTP calls below. If any
  // call fails mid-flight, some changes may have already been persisted.
  // We always emit('saved') in the finally so the parent re-fetches a fresh
  // breakdown, preventing the modal from showing stale "before-save" state.
  let dirtied = false
  try {
    // 1) Delete originals that are no longer in `rows`
    const survivingIds = new Set(
      rows.value.filter((r) => !r._new).map((r) => r.hc_jewelry_item_id),
    )
    for (const orig of props.group.entries) {
      if (orig.is_locked) continue
      if (!survivingIds.has(orig.hc_jewelry_item_id)) {
        await deleteHandcraftJewelry(props.hcId, orig.hc_jewelry_item_id)
        dirtied = true
      }
    }

    // 2) Add or update remaining rows
    for (const r of rows.value) {
      if (r.is_locked) continue
      if (r._new) {
        const payload = {
          qty: r.qty,
          customer_name: r.customer_name.trim(),
        }
        if (props.group.kind === 'jewelry') {
          payload.jewelry_id = props.group.jewelry_id
        } else {
          payload.part_id = props.group.jewelry_id
        }
        await addHandcraftJewelry(props.hcId, payload)
        dirtied = true
      } else if (r._dirty) {
        const payload = { customer_name: r.customer_name.trim() }
        if (canEditQty.value) payload.qty = r.qty
        await updateHandcraftJewelry(props.hcId, r.hc_jewelry_item_id, payload)
        dirtied = true
      }
    }

    message.success('已保存')
    emit('update:show', false)
  } catch (err) {
    message.error(err?.response?.data?.detail || '保存失败，请刷新核对')
  } finally {
    // Always re-emit saved if we touched anything, so the parent reloads
    // breakdown groups and reflects whatever did succeed.
    if (dirtied) emit('saved')
    saving.value = false
  }
}
</script>

<style scoped>
.hint {
  color: rgba(0, 0, 0, 0.45);
  font-size: 12px;
  margin-bottom: 12px;
}
.footer {
  margin-top: 16px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.sum {
  margin-right: auto;
  color: rgba(0, 0, 0, 0.65);
  font-size: 13px;
}
.sum strong {
  font-family: "SF Mono", Menlo, monospace;
}
.sum--ok strong {
  color: #18a058;
}
.sum--err strong {
  color: #d03050;
}
</style>
