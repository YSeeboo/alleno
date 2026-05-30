<template>
  <n-card v-if="cols.length > 0" :content-style="collapsed ? 'padding: 0' : undefined">
    <template #header>
      <div class="bm-head-wrap">
        <div class="bm-head" @click="collapsed = !collapsed">
          <span class="chev">{{ collapsed ? '▸' : '▾' }}</span>
          <span class="title">客户分拣</span>
          <span class="status-tag">{{ statusTagText }}</span>
        </div>
        <div v-if="!collapsed" class="bm-actions">
          <template v-if="mode === 'view'">
            <n-button size="small" :disabled="!canEdit" @click.stop="enterEdit">编辑</n-button>
          </template>
          <template v-else>
            <n-button size="small" :disabled="saving" @click.stop="cancelEdit">取消</n-button>
            <n-button size="small" type="primary" :loading="saving" @click.stop="save">保存</n-button>
          </template>
        </div>
      </div>
    </template>
    <div v-show="!collapsed">
      <table class="mx">
        <thead>
          <tr>
            <th class="mx__col-cust">客户</th>
            <th v-for="c in cols" :key="c.key" class="mx__col-jw">
              <span class="jid">{{ c.jewelry_id }}</span>
              <span class="jname">{{ c.jewelry_name }}</span>
              <span class="jtot">{{ c.total_qty }} 套</span>
            </th>
            <th class="mx__col-sum">合计</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.customer_name">
            <td class="mx__cust">
              <template v-if="r.is_locked_customer">
                <div class="lock-name">{{ r.customer_name }}</div>
                <div v-if="lockedSourceLine(r)" class="lock-src">↗ {{ lockedSourceLine(r) }}</div>
              </template>
              <template v-else>
                <span class="manual-name">{{ r.customer_name }}</span>
              </template>
            </td>
            <td v-for="c in cols" :key="c.key" :class="cellClass(r.cells[c.key])">
              <CellReadonly :cell="r.cells[c.key]" />
            </td>
            <td class="mx__row-sum">{{ r.row_sum }}</td>
          </tr>
          <tr v-if="rows.length === 0" class="mx__empty">
            <td :colspan="cols.length + 2">尚未分配给任何客户</td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td class="mx__foot-label">已分 / 总数</td>
            <td v-for="c in cols" :key="c.key" :class="footCellClass(c)">
              {{ colAssigned[c.key] }} / {{ c.total_qty }}
              <span v-if="colAssigned[c.key] === c.total_qty">✓</span>
              <span v-else>⚠</span>
            </td>
            <td class="mx__foot-total">{{ totalAssigned }} / {{ totalAll }}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  </n-card>
</template>

<script setup>
import { ref, computed, h, defineComponent } from 'vue'
import { NCard, NButton, useMessage } from 'naive-ui'

const CellReadonly = defineComponent({
  name: 'CellReadonly',
  props: { cell: { type: Object, required: true } },
  setup(props) {
    return () => {
      const c = props.cell
      if (!c || (c.lockedQty === 0 && c.manualQty === 0)) {
        return h('span', { class: 'qty-empty' }, '—')
      }
      if (c.lockedQty > 0 && c.manualQty === 0) {
        return h('span', { class: 'qty-locked' }, [
          String(c.lockedQty),
          h('span', { class: 'lock-icon' }, ' 🔒'),
        ])
      }
      if (c.lockedQty === 0 && c.manualQty > 0) {
        return h('span', { class: 'qty-manual' }, String(c.manualQty))
      }
      // Mixed
      return h('span', { class: 'qty-mixed' }, [
        h('span', { class: 'l' }, `${c.lockedQty}🔒`),
        h('span', { class: 'plus' }, ' + '),
        h('span', { class: 'm' }, String(c.manualQty)),
      ])
    }
  },
})

const props = defineProps({
  hcId: { type: String, required: true },
  hcStatus: { type: String, required: true },
  groups: { type: Array, required: true },  // backend breakdown response
})
const emit = defineEmits(['saved'])

const collapsed = ref(false)

// 'view' = read-only, 'edit' = editing local snapshot
const mode = ref('view')
const saving = ref(false)
const message = useMessage()

// Snapshot rows + placeholder entries when entering edit mode, so we can
// compute a diff at save time. `entriesIndex` lets the diff look up the
// per-id (qty, original customer_name) so it can detect "this id moved
// from a placeholder into a customer row" and emit a single PATCH rather
// than (ADD + PATCH) double-writes.
const draft = ref(null)  // { rows: [...], placeholderEntries: [...], entriesIndex: Map<id, {qty, customer_name, is_locked}> }

function enterEdit() {
  // Deep-clone for safe local mutation. JSON round-trip is fine here:
  // no Date / Map / function values in this state.
  const index = new Map()
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      index.set(e.hc_jewelry_item_id, {
        qty: Number(e.qty),
        customer_name: e.customer_name || null,
        is_locked: !!e.is_locked,
      })
    }
  }
  draft.value = {
    rows: JSON.parse(JSON.stringify(rows.value)),
    placeholderEntries: JSON.parse(JSON.stringify(placeholderEntries.value)),
    entriesIndex: index,  // NOT serialized — Maps survive direct assignment fine
  }
  mode.value = 'edit'
}

function cancelEdit() {
  draft.value = null
  mode.value = 'view'
}

async function save() {
  message.warning('保存逻辑将在后续任务实现')
  cancelEdit()
}

const canEdit = computed(() => props.hcStatus !== 'completed')

// --- Transpose backend groups → rows (customer-major) + cols (jewelry-major) ---

// cols: one entry per jewelry/part group in backend order
const cols = computed(() =>
  (props.groups || []).map((g) => ({
    key: `${g.kind}:${g.jewelry_id}`,
    kind: g.kind,
    jewelry_id: g.jewelry_id,
    jewelry_name: g.jewelry_name,
    total_qty: Number(g.total_qty),
  })),
)

// rows: derived from entries with non-empty customer_name.
// Locked customers first (in their first-seen order), then manual customers
// (also first-seen). Each row aggregates entries by (customer, jewelry).
const rows = computed(() => {
  const order = []     // [customer_name, ...] in display order
  const seen = new Set()
  const isLockedCust = new Map()  // customer_name → boolean (any entry locked?)

  // First pass — locked customers
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      const name = e.customer_name
      if (!name || !e.is_locked) continue
      if (!seen.has(name)) {
        seen.add(name)
        order.push(name)
        isLockedCust.set(name, true)
      }
    }
  }
  // Second pass — manual customers
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      const name = e.customer_name
      if (!name || e.is_locked) continue
      if (!seen.has(name)) {
        seen.add(name)
        order.push(name)
        if (!isLockedCust.has(name)) isLockedCust.set(name, false)
      }
    }
  }

  // Build per-cell aggregates
  return order.map((name) => {
    const cellsByCol = {}
    for (const g of props.groups || []) {
      const colKey = `${g.kind}:${g.jewelry_id}`
      const matchingEntries = (g.entries || []).filter((e) => e.customer_name === name)
      const lockedEntries = matchingEntries.filter((e) => e.is_locked)
      const manualEntries = matchingEntries.filter((e) => !e.is_locked)
      cellsByCol[colKey] = {
        lockedQty: lockedEntries.reduce((s, e) => s + Number(e.qty), 0),
        lockedSources: lockedEntries.map((e) => e.source_order_id).filter(Boolean),
        manualQty: manualEntries.reduce((s, e) => s + Number(e.qty), 0),
        manualEntryIds: manualEntries.map((e) => e.hc_jewelry_item_id),
      }
    }
    const rowSum = Object.values(cellsByCol).reduce(
      (s, c) => s + c.lockedQty + c.manualQty, 0,
    )
    return {
      customer_name: name,
      is_locked_customer: isLockedCust.get(name) || false,
      cells: cellsByCol,
      row_sum: rowSum,
    }
  })
})

// Placeholder entries: customer_name is null/empty, is_locked false
const placeholderEntries = computed(() => {
  const out = []
  for (const g of props.groups || []) {
    for (const e of g.entries || []) {
      const name = (e.customer_name || '').trim()
      if (!name && !e.is_locked) {
        out.push({ ...e, _col_key: `${g.kind}:${g.jewelry_id}` })
      }
    }
  }
  return out
})

const placeholderQtySum = computed(() =>
  placeholderEntries.value.reduce((s, e) => s + Number(e.qty), 0),
)

// Per-column "assigned" total = sum of all rows' (locked + manual) for that col.
// "Remaining" per col = total_qty - assigned.
const colAssigned = computed(() => {
  const m = {}
  for (const c of cols.value) m[c.key] = 0
  for (const r of rows.value) {
    for (const k of Object.keys(r.cells)) {
      m[k] = (m[k] || 0) + r.cells[k].lockedQty + r.cells[k].manualQty
    }
  }
  return m
})

const totalAssigned = computed(() =>
  Object.values(colAssigned.value).reduce((s, n) => s + n, 0),
)
const totalAll = computed(() =>
  cols.value.reduce((s, c) => s + c.total_qty, 0),
)

const statusTagText = computed(() => {
  if (rows.value.length === 0) {
    return `未分拣 · ${totalAssigned.value}/${totalAll.value}`
  }
  if (props.hcStatus === 'pending') return `pending · 可编辑`
  if (props.hcStatus === 'processing') return `processing · 仅可改客户名 / 删未发出行`
  if (props.hcStatus === 'completed') return `completed · 只读`
  return props.hcStatus
})

function cellClass(cell) {
  if (!cell) return ['mx__qty', 'empty']
  if (cell.lockedQty === 0 && cell.manualQty === 0) return ['mx__qty', 'empty']
  if (cell.lockedQty > 0 && cell.manualQty === 0) return ['mx__qty', 'locked']
  if (cell.lockedQty === 0 && cell.manualQty > 0) return ['mx__qty']
  return ['mx__qty', 'mixed']
}

function footCellClass(col) {
  return [
    'mx__foot-cell',
    colAssigned.value[col.key] === col.total_qty ? 'ok' : 'warn',
  ]
}

function lockedSourceLine(row) {
  // Collect first unique source_order_id across this row's cells
  const sources = new Set()
  for (const k of Object.keys(row.cells)) {
    for (const s of row.cells[k].lockedSources || []) sources.add(s)
  }
  return sources.size ? Array.from(sources).join(', ') : ''
}
</script>

<style scoped>
.bm-head { display: flex; align-items: center; gap: 10px; cursor: pointer; font-size: 14px; }
.chev { color: #888; }
.title { font-weight: 600; }
.status-tag {
  font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 400;
  background: #fff5e0; color: #b76100;
}

.mx { width: 100%; border-collapse: collapse; font-size: 12px; }
.mx th, .mx td { border: 1px solid #e8e8ec; padding: 7px 9px; text-align: center; vertical-align: middle; }
.mx thead th { background: #fafafc; font-weight: 600; padding: 6px 8px; }
.mx__col-cust { text-align: left; min-width: 140px; }
.mx__col-jw .jid { display: block; font-family: "SF Mono", Menlo, monospace; font-size: 10px; color: #999; font-weight: 400; line-height: 1.2; }
.mx__col-jw .jname { display: block; font-size: 12px; margin-top: 2px; }
.mx__col-jw .jtot { display: block; font-size: 10px; font-weight: 400; color: #888; font-family: "SF Mono", Menlo, monospace; margin-top: 2px; }
.mx__col-sum { width: 70px; color: #666; }

.mx__cust { text-align: left; background: #fafafc; padding: 6px 9px; }
.lock-name { color: rgba(0,0,0,.7); padding-left: 18px; position: relative; font-size: 12px; }
.lock-name::before { content: "🔒"; position: absolute; left: 0; }
.lock-src { color: #b76100; font-size: 10px; margin-left: 18px; font-family: "SF Mono", Menlo, monospace; margin-top: 2px; }
.manual-name { color: #333; }

.mx__qty { font-family: "SF Mono", Menlo, monospace; color: #333; min-width: 86px; height: 38px; }
.mx__qty.empty { color: #ccc; }
.mx__qty.locked { background: #fff8e6; color: #8a6500; }
.mx__qty.mixed { background: linear-gradient(to right, #fff8e6 50%, #ffffff 50%); }
.qty-empty { color: #ccc; }
.qty-locked { color: #8a6500; }
.qty-mixed .l { color: #8a6500; }
.qty-mixed .plus { color: #888; }

.mx__row-sum { font-family: "SF Mono", Menlo, monospace; background: #fafafc; color: #555; }

.mx__empty td {
  height: 60px; color: #aaa; font-size: 12px;
  background: repeating-linear-gradient(45deg, #fafafc 0 6px, #f4f4f8 6px 12px);
}

.mx tfoot td { background: #eef0fe; font-family: "SF Mono", Menlo, monospace; font-size: 11px; color: #4338ca; padding: 7px 10px; }
.mx__foot-label { font-family: -apple-system, sans-serif; text-align: left; font-weight: 600; }
.mx__foot-cell.ok { color: #18a058; }
.mx__foot-cell.warn { color: #d03050; }
.mx__foot-total { color: #4338ca; }

.bm-head-wrap { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.bm-actions { display: flex; gap: 6px; }
</style>
