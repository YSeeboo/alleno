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
        <tbody v-if="mode === 'view'">
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

        <tbody v-else>
          <tr v-for="(r, ri) in draft.rows" :key="`${r.customer_name}:${ri}`">
            <td class="mx__cust">
              <template v-if="r.is_locked_customer">
                <div class="lock-name">{{ r.customer_name }}</div>
                <div v-if="lockedSourceLine(r)" class="lock-src">↗ {{ lockedSourceLine(r) }}</div>
              </template>
              <template v-else>
                <div class="manual-edit">
                  <div class="manual-edit__name">
                    <CustomerNameSelect
                      v-if="canEditCustomerName"
                      v-model:value="r.customer_name"
                      :disabled="!canEditCustomerName"
                    />
                    <span v-else class="manual-name">{{ r.customer_name }}</span>
                  </div>
                  <n-button
                    v-if="canDeleteRow(r)"
                    text
                    type="error"
                    size="tiny"
                    @click="removeDraftRow(ri)"
                  >×</n-button>
                </div>
              </template>
            </td>
            <td v-for="c in cols" :key="c.key" :class="cellClass(r.cells[c.key])">
              <CellEditable
                v-if="!r.is_locked_customer || r.cells[c.key].manualQty > 0 || canAddNewManual"
                :cell="r.cells[c.key]"
                :qty-editable="canEditQty"
                :on-change="(v) => setCellManual(r, c.key, v)"
              />
              <CellReadonly v-else :cell="r.cells[c.key]" />
            </td>
            <td class="mx__row-sum">{{ draftRowSum(r) }}</td>
          </tr>
          <tr v-if="draft.rows.length === 0" class="mx__empty">
            <td :colspan="cols.length + 2">尚未分配给任何客户</td>
          </tr>
          <tr v-if="canAddNewRow" class="mx__add-bar-row">
            <td :colspan="cols.length + 2">
              <div class="add-bar">
                <span class="add-bar__link" @click="addDraftRow">+ 加一行客户</span>
                <!-- bulk-assign button slot — Task 12 -->
              </div>
            </td>
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
import CustomerNameSelect from './CustomerNameSelect.vue'
import {
  addHandcraftJewelry,
  updateHandcraftJewelry,
  deleteHandcraftJewelry,
} from '@/api/handcraft'

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

const CellEditable = defineComponent({
  name: 'CellEditable',
  props: {
    cell: { type: Object, required: true },
    qtyEditable: { type: Boolean, default: true },  // false when status forbids
    onChange: { type: Function, required: true },   // (newManualQty: number) => void
  },
  setup(props) {
    return () => {
      const c = props.cell
      const showLock = c.lockedQty > 0
      const input = h('input', {
        type: 'number',
        min: 0,
        value: c.manualQty,
        disabled: !props.qtyEditable,
        class: ['cell-input', c.manualQty === 0 ? 'zero' : ''],
        onInput: (e) => {
          const v = Number(e.target.value)
          props.onChange(Number.isFinite(v) && v >= 0 ? v : 0)
        },
      })
      if (showLock && c.manualQty > 0) {
        return h('span', { class: 'qty-mixed' }, [
          h('span', { class: 'l' }, `${c.lockedQty}🔒`),
          h('span', { class: 'plus' }, ' + '),
          input,
        ])
      }
      if (showLock) {
        return h('span', { class: 'qty-locked-edit' }, [
          h('span', { class: 'l' }, `${c.lockedQty}🔒`),
          h('span', { class: 'plus' }, ' + '),
          input,
        ])
      }
      return input
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

// Status gates (sourced from the spec's state matrix)
const canAddNewRow = computed(() => props.hcStatus === 'pending')
const canAddNewManual = computed(() => props.hcStatus === 'pending')  // new manual entry on existing row
const canEditQty = computed(() => props.hcStatus === 'pending')
const canEditCustomerName = computed(() => props.hcStatus !== 'completed')

function canDeleteRow(r) {
  if (r.is_locked_customer) return false
  if (props.hcStatus === 'completed') return false
  // processing: only deletable if all manual entries have received_qty == 0
  // (the spec defers exact check to backend; we let DELETE fail loudly if
  // backend rejects, but block obviously-bad delete attempts here)
  if (props.hcStatus === 'processing') {
    // we don't have received_qty per cell in the matrix; rely on backend
    // (a refresh on save-failure will surface remaining state)
  }
  return true
}

function draftRowSum(r) {
  return Object.values(r.cells).reduce((s, c) => s + c.lockedQty + c.manualQty, 0)
}

function setCellManual(r, colKey, newQty) {
  // Mutate the draft row's cell.manualQty in place; mark internal flag for diff.
  const cell = r.cells[colKey]
  cell.manualQty = Number(newQty) || 0
  r._dirty = true
}

function addDraftRow() {
  // New empty manual row; customer_name empty until user picks
  const cells = {}
  for (const c of cols.value) {
    cells[c.key] = { lockedQty: 0, lockedSources: [], manualQty: 0, manualEntryIds: [] }
  }
  draft.value.rows.push({
    customer_name: '',
    is_locked_customer: false,
    cells,
    row_sum: 0,
    _new: true,
    _dirty: true,
  })
}

function removeDraftRow(idx) {
  draft.value.rows.splice(idx, 1)
}

async function save() {
  if (saving.value) return
  saving.value = true
  let mutated = false

  try {
    // Compose the operation lists by diffing draft vs original.
    const operations = computeDiff()

    // Validate: customer name required on every kept row
    for (const op of [...operations.adds, ...operations.patches]) {
      if (op.customer_name !== undefined && (!op.customer_name || !op.customer_name.trim())) {
        message.error('客户名不能为空')
        saving.value = false
        return
      }
    }

    // 1. DELETE first
    for (const id of operations.deletes) {
      await deleteHandcraftJewelry(props.hcId, id)
      mutated = true
    }
    // 2. PATCH next
    for (const p of operations.patches) {
      const payload = {}
      if (p.qty !== undefined) payload.qty = p.qty
      if (p.customer_name !== undefined) payload.customer_name = p.customer_name
      if (Object.keys(payload).length === 0) continue
      await updateHandcraftJewelry(props.hcId, p.id, payload)
      mutated = true
    }
    // 3. POST last
    for (const a of operations.adds) {
      const payload = {
        qty: a.qty,
        customer_name: a.customer_name,
      }
      if (a.jewelry_id) payload.jewelry_id = a.jewelry_id
      if (a.part_id) payload.part_id = a.part_id
      await addHandcraftJewelry(props.hcId, payload)
      mutated = true
    }

    message.success('已保存')
    mode.value = 'view'
    draft.value = null
  } catch (err) {
    message.error(err?.response?.data?.detail || '保存失败,请刷新核对')
  } finally {
    if (mutated) emit('saved')
    saving.value = false
  }
}

/**
 * Compute the diff between draft state and original state.
 * Returns {deletes: [item_id, ...], patches: [...], adds: [...]}.
 *
 * Model: each cell in draft.rows has `manualEntryIds` (which IDs back this cell)
 * and `manualQty` (the displayed total). Bulk-assign (Task 12) moves placeholder
 * IDs from `draft.placeholderEntries` INTO `cell.manualEntryIds` and bumps
 * `cell.manualQty` by the placeholder qty. computeDiff detects IDs newly present
 * in a draft cell (vs the original) and emits PATCH customer_name for each.
 *
 * Rules:
 * - newIds in cell (present in draft but not original) → PATCH(id, customer_name=row.name)
 *   (covers bulk-assigned placeholder IDs)
 * - removedIds in cell (in original but not in draft) → DELETE
 * - cell.manualQty - origCell.manualQty - sum(qty of newIds) = userDelta
 *     - userDelta > 0 → ADD (qty=userDelta) (only allowed in pending; backend enforces)
 *     - userDelta < 0 → reduce a retained id, then claimed ids until exhausted
 *     - userDelta == 0 → no qty op
 * - row.customer_name changed vs orig → PATCH customer_name on every retained id
 *   (PATCH-customer-name + PATCH-qty can collapse to one op per id)
 * - Brand-new customer row (not in original): unified branch — origCell empty,
 *   newIds = all claimed ids, userDelta handles ADD for typed-in qty
 * - Customer row removed from draft entirely → DELETE all manualEntryIds (locked rows skipped)
 *   EXCEPT ids that moved to a different draft row (rename / regroup)
 */
function computeDiff() {
  const deletes = []
  const patches = []     // [{id, qty?, customer_name?}, ...]
  const adds = []        // [{customer_name, qty, jewelry_id?, part_id?}, ...]
  const idx = draft.value.entriesIndex

  // Index original rows by customer_name for fast lookup
  const originalByName = new Map()
  for (const r of rows.value) originalByName.set(r.customer_name, r)
  const draftNames = new Set(draft.value.rows.map((r) => r.customer_name))

  // Helper: merge PATCH ops for the same id (qty + customer_name in one call)
  const patchById = new Map()
  function patch(id, fields) {
    const existing = patchById.get(id) || { id }
    patchById.set(id, { ...existing, ...fields })
  }

  // Unified per-row diff: orig may be undefined (brand-new row).
  // For brand-new rows, origCell is treated as empty — so all draft ids are
  // newIds and trigger PATCH(customer_name=...). For existing rows, renames
  // and qty edits flow through the same logic.
  for (const r of draft.value.rows) {
    const orig = originalByName.get(r.customer_name)
    const renameChanged = orig && r.customer_name !== orig.customer_name
    for (const c of cols.value) {
      const cell = r.cells[c.key]
      const origCell = (orig?.cells || {})[c.key] || { manualQty: 0, manualEntryIds: [] }
      const origIdSet = new Set(origCell.manualEntryIds || [])
      const draftIdSet = new Set(cell.manualEntryIds || [])

      const newIds = (cell.manualEntryIds || []).filter((id) => !origIdSet.has(id))
      const removedIds = (origCell.manualEntryIds || []).filter((id) => !draftIdSet.has(id))

      // 1. DELETE removed ids
      for (const id of removedIds) deletes.push(id)

      // 2. PATCH customer_name for new ids (bulk-claimed placeholders or
      //    ids moved from a different row). Also PATCH retained ids if
      //    the customer name was renamed in place.
      for (const id of newIds) patch(id, { customer_name: r.customer_name })
      if (renameChanged) {
        for (const id of cell.manualEntryIds || []) {
          if (!newIds.includes(id)) patch(id, { customer_name: r.customer_name })
        }
      }

      // 3. Qty conservation:
      //   origCell.manualQty - removedIdsQty + newIdsQty + userDelta = cell.manualQty
      const newIdsQty = newIds.reduce((s, id) => s + (idx.get(id)?.qty || 0), 0)
      const removedIdsQty = removedIds.reduce((s, id) => s + (idx.get(id)?.qty || 0), 0)
      const userDelta = cell.manualQty - origCell.manualQty + removedIdsQty - newIdsQty

      if (userDelta > 0) {
        adds.push({
          customer_name: r.customer_name,
          qty: userDelta,
          jewelry_id: c.kind === 'jewelry' ? c.jewelry_id : undefined,
          part_id: c.kind === 'part' ? c.jewelry_id : undefined,
        })
      } else if (userDelta < 0) {
        // Need to reduce by abs(userDelta). Prefer reducing a retained id,
        // else a newly-claimed id (each backed by `idx`'s qty). Walk through
        // candidates until the reduction is exhausted.
        const candidates = [
          ...(cell.manualEntryIds || []).filter((id) => origIdSet.has(id)),
          ...newIds,
        ]
        let remaining = -userDelta
        for (const id of candidates) {
          if (remaining <= 0) break
          const baseQty = idx.get(id)?.qty || 0
          if (baseQty === 0) continue
          if (baseQty <= remaining) {
            deletes.push(id)
            remaining -= baseQty
          } else {
            patch(id, { qty: baseQty - remaining })
            remaining = 0
          }
        }
        // remaining > 0 here would mean the user reduced below 0 — guarded
        // by the input's `min=0`, so this should not be reachable.
      }
    }
  }

  // Customer rows that existed but are now gone from draft → DELETE their manual ids.
  // EXCEPT ids that moved to a different draft row (rename / regroup) — those will
  // be PATCHed by the destination row's loop above, so DELETE-ing them here would
  // either run first and break the PATCH, or run after and undo the rename.
  const draftAllIds = new Set()
  for (const r of draft.value.rows) {
    for (const k of Object.keys(r.cells)) {
      for (const id of r.cells[k].manualEntryIds || []) draftAllIds.add(id)
    }
  }
  for (const r of rows.value) {
    if (draftNames.has(r.customer_name)) continue
    if (r.is_locked_customer) continue
    for (const k of Object.keys(r.cells)) {
      for (const id of r.cells[k].manualEntryIds || []) {
        if (!draftAllIds.has(id)) deletes.push(id)
      }
    }
  }

  patches.push(...patchById.values())
  return { deletes, patches, adds }
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

.manual-edit { display: flex; gap: 6px; align-items: center; }
.manual-edit__name { flex: 1; }
.cell-input {
  width: 56px; padding: 3px 6px; border: 1px solid #d0d0d6;
  border-radius: 3px; font-family: "SF Mono", Menlo, monospace;
  font-size: 12px; text-align: center;
}
.cell-input:focus { outline: none; border-color: #2080f0; box-shadow: 0 0 0 2px rgba(32,128,240,.12); }
.cell-input.zero { color: #999; }
.cell-input:disabled { background: #fafafa; color: #777; }
.qty-locked-edit { display: inline-flex; align-items: center; gap: 4px; }
.qty-locked-edit .l { color: #8a6500; }
.qty-mixed .plus, .qty-locked-edit .plus { color: #888; }
.mx__add-bar-row td { padding: 6px 10px; background: #f9f9fc; text-align: left; }
.add-bar { display: flex; gap: 10px; align-items: center; }
.add-bar__link { color: #4338ca; cursor: pointer; padding: 4px 8px; border-radius: 3px; font-size: 12px; }
.add-bar__link:hover { background: #eef0fe; }
</style>
