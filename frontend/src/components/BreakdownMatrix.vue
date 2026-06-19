<template>
  <div v-if="cols.length > 0" class="bm-root">
    <div class="bm-head-wrap">
      <span class="bm-head-left">
        <span class="bm-title">客户分拣</span>
        <span :class="['status-tag', allFull ? 'full' : 'under']">{{ statusTagText }}</span>
      </span>
      <div class="bm-actions">
        <template v-if="mode === 'view'">
          <n-button size="small" :disabled="!canEdit" @click="enterEdit">编辑</n-button>
        </template>
        <template v-else>
          <n-button size="small" :disabled="saving" @click="cancelEdit">取消</n-button>
          <n-button size="small" type="primary" :loading="saving" @click="save">保存</n-button>
        </template>
      </div>
    </div>
    <div class="bm-body">
      <div class="mx-scroll">
        <table class="mx">
        <thead>
          <tr>
            <th class="mx__col-cust">客户</th>
            <th v-for="c in cols" :key="c.key" :class="['mx__col-jw', colAssigned[c.key] === c.total_qty ? 'full' : 'under']">
              <div class="oh">
                <span class="oh-top">
                  <span class="nm">{{ c.jewelry_name }}</span>
                  <span class="id">{{ c.jewelry_id }}</span>
                </span>
                <span class="alloc">
                  <span class="n">{{ colAssigned[c.key] }}/{{ c.total_qty }}</span>
                  <span class="track">
                    <span class="fill" :style="{ width: c.total_qty > 0 ? Math.min(100, Math.round(colAssigned[c.key] / c.total_qty * 100)) + '%' : '0%' }"></span>
                  </span>
                </span>
              </div>
            </th>
            <th class="mx__col-sum">合计</th>
          </tr>
        </thead>
        <tbody v-if="mode === 'view'">
          <tr v-for="r in rows" :key="r.customer_name">
            <td class="mx__cust">
              <div class="cust-nm">{{ r.customer_name }}</div>
              <template v-if="r.is_locked_customer">
                <span class="src order">订单{{ lockedSourceLine(r) ? ' ' + lockedSourceLine(r) : '' }} ↗</span>
              </template>
              <template v-else>
                <span class="src manual">手填</span>
              </template>
            </td>
            <td v-for="c in cols" :key="c.key" :class="cellClass(r.cells[c.key], r.customer_name, c.key)">
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
                <div class="cust-nm">{{ r.customer_name }}</div>
                <span class="src order">订单{{ lockedSourceLine(r) ? ' ' + lockedSourceLine(r) : '' }} ↗</span>
              </template>
              <template v-else>
                <div class="manual-edit">
                  <div class="manual-edit__name">
                    <CustomerNameSelect
                      v-if="canEditCustomerName"
                      v-model:value="r.customer_name"
                      :disabled="!canEditCustomerName"
                    />
                    <span v-else class="cust-nm">{{ r.customer_name }}</span>
                  </div>
                  <n-button
                    v-if="canDeleteRow(r)"
                    text
                    type="error"
                    size="tiny"
                    @click="removeDraftRow(ri)"
                  >×</n-button>
                </div>
                <span class="src manual">手填</span>
              </template>
            </td>
            <td v-for="c in cols" :key="c.key" :class="cellClass(r.cells[c.key], r.customer_name, c.key)">
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
                <span class="add-bar__sep">|</span>
                <n-popover
                  v-model:show="bulkShow"
                  :show-arrow="true"
                  placement="top"
                  trigger="manual"
                  :disabled="!canBulkAssign"
                >
                  <template #trigger>
                    <n-button
                      size="tiny"
                      :disabled="!canBulkAssign"
                      class="bulk-btn"
                      @click="bulkShow = !bulkShow"
                    >
                      ⚡ 一键剩余分给…
                    </n-button>
                  </template>
                  <BulkAssignPopover
                    :preview-items="bulkPreviewItems"
                    :has-locked="bulkHasLocked"
                    :has-partial-manual="bulkHasPartialManual"
                    @confirm="onBulkConfirm"
                    @cancel="bulkShow = false"
                  />
                </n-popover>
                <span v-if="!canBulkAssign" class="add-bar__hint">
                  {{ props.hcStatus !== 'pending' ? '仅 pending 状态可用' : '已无剩余可分' }}
                </span>
              </div>
            </td>
          </tr>
        </tbody>
        <tfoot>
          <tr class="totrow">
            <td class="mx__foot-label">已分 / 总数</td>
            <td v-for="c in cols" :key="c.key" :class="footCellClass(c)">
              <span :class="colAssigned[c.key] === c.total_qty ? 'tot-ok' : 'tot-bad'">{{ colAssigned[c.key] }} / {{ c.total_qty }}</span>
              <div v-if="colAssigned[c.key] === c.total_qty" class="tot-sub">已分满</div>
              <div v-else class="tot-sub">缺 {{ c.total_qty - colAssigned[c.key] }}</div>
            </td>
            <td class="mx__foot-total">{{ totalAssigned }} / {{ totalAll }}</td>
          </tr>
        </tfoot>
        </table>
      </div>
      <!-- Sticky-bottom save bar appears only in edit mode on narrow screens -->
      <div v-if="mode === 'edit'" class="mx-sticky-foot">
        <n-button size="small" :disabled="saving" @click="cancelEdit">取消</n-button>
        <n-button size="small" type="primary" :loading="saving" @click="save">保存</n-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, h, defineComponent } from 'vue'
import { NButton, NPopover, useMessage } from 'naive-ui'
import CustomerNameSelect from './CustomerNameSelect.vue'
import BulkAssignPopover from './BulkAssignPopover.vue'
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

const bulkShow = ref(false)
const flashedColKeys = ref(new Set())  // for CSS pulse on newly-filled columns

const bulkPreviewItems = computed(() => {
  if (!draft.value) return []
  // For each column, sum the placeholder qty for that column
  const placeholderByCol = new Map()
  for (const pe of draft.value.placeholderEntries) {
    if ((pe.customer_name || '').trim()) continue  // already claimed by previous bulk click
    const k = pe._col_key
    placeholderByCol.set(k, (placeholderByCol.get(k) || 0) + Number(pe.qty))
  }
  return cols.value
    .filter((c) => placeholderByCol.get(c.key) > 0)
    .map((c) => ({
      jewelry_id: c.jewelry_id,
      jewelry_name: c.jewelry_name,
      delta: placeholderByCol.get(c.key),
    }))
})

const bulkHasLocked = computed(() => rows.value.some((r) => r.is_locked_customer))
const bulkHasPartialManual = computed(() => rows.value.some((r) => !r.is_locked_customer))

const canBulkAssign = computed(
  () => props.hcStatus === 'pending' && bulkPreviewItems.value.length > 0,
)

function onBulkConfirm(customerName) {
  const name = (customerName || '').trim()
  if (!name) return

  // 1. Find or create the destination customer row in draft.
  let row = draft.value.rows.find((r) => r.customer_name === name)
  if (!row) {
    const cells = {}
    for (const c of cols.value) {
      cells[c.key] = { lockedQty: 0, lockedSources: [], manualQty: 0, manualEntryIds: [] }
    }
    row = {
      customer_name: name,
      is_locked_customer: false,
      cells,
      row_sum: 0,
      _new: true,  // brand-new in draft; computeDiff treats it as new-row branch
      _dirty: true,
    }
    draft.value.rows.push(row)
  }

  // 2. Move all unclaimed placeholder entries INTO the row's cells.
  //    Their hc_jewelry_item_id is preserved in cell.manualEntryIds — the diff
  //    will detect these as "newIds" (in draft cell but not in original cell)
  //    and emit a single PATCH(id, customer_name=name) per id.
  const stillPending = []
  for (const pe of draft.value.placeholderEntries) {
    if ((pe.customer_name || '').trim()) {
      // already claimed in a previous bulk-click — keep in array but skip
      stillPending.push(pe)
      continue
    }
    const cell = row.cells[pe._col_key]
    if (!cell) {
      stillPending.push(pe)
      continue
    }
    cell.manualEntryIds.push(pe.hc_jewelry_item_id)
    cell.manualQty += Number(pe.qty)
    flashedColKeys.value.add(`${name}:${pe._col_key}`)
    // Mark the placeholder as claimed and remove it from the "pending" array
    // so subsequent bulk-clicks don't try to re-claim it. We tag it with the
    // claimer's name purely for symmetry with the bulkPreviewItems filter.
    pe.customer_name = name
  }
  // Rebuild placeholderEntries to only contain still-pending ones
  draft.value.placeholderEntries = stillPending

  bulkShow.value = false

  // 3. Schedule flash fade-out
  setTimeout(() => {
    flashedColKeys.value = new Set()
  }, 3000)
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

// Overall allocation status
const allFull = computed(() =>
  cols.value.length > 0 && cols.value.every((c) => colAssigned.value[c.key] === c.total_qty),
)

// Total shortfall across all columns
const totalShortfall = computed(() =>
  cols.value.reduce((s, c) => s + Math.max(0, c.total_qty - (colAssigned.value[c.key] || 0)), 0),
)

const statusTagText = computed(() => {
  if (cols.value.length === 0) return ''
  if (allFull.value) return '已分满'
  return `未分满 · 缺 ${totalShortfall.value}`
})

function cellClass(cell, rowName, colKey) {
  const out = []
  if (!cell || (cell.lockedQty === 0 && cell.manualQty === 0)) out.push('empty')
  if (cell?.lockedQty > 0 && cell.manualQty === 0) out.push('locked')
  if (cell?.lockedQty > 0 && cell?.manualQty > 0) out.push('mixed')
  if (rowName && colKey && flashedColKeys.value.has(`${rowName}:${colKey}`)) out.push('flash')
  return ['mx__qty', ...out]
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
/* ── Design tokens ── */
:root {
  --ink: #1A1D21;
  --accent: #1E7A5A;
  --accent-soft: #E6F2EC;
  --danger: #E5484D;
  --amber: #B7791F;
  --line: #ECEDEF;
  --line-2: #F4F5F6;
  --muted: #8B9096;
  --muted-2: #AEB3B8;
  --sub: #F6F7F8;
}

/* ── Header — eyebrow section, matches sibling .hc-sec-h ── */
.bm-root { width: 100%; }
.bm-head-wrap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0 0 8px;
  border-bottom: 1px solid #ECEDEF;
  margin-bottom: 12px;
}
.bm-head-left { display: flex; align-items: center; gap: 8px; }
.bm-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  color: #8B9096;
}
.status-tag {
  font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 11px;
}
.status-tag.full { background: #E6F2EC; color: #1E7A5A; }
.status-tag.under { background: #FBF0DC; color: #B7791F; }
.bm-actions { display: flex; gap: 6px; }

/* ── Table shell — hairline grid ── */
.mx-scroll { overflow-x: auto; }
.mx {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.mx th,
.mx td {
  border-bottom: 1px solid #F4F5F6;
  border-right: 1px solid #F4F5F6;
  padding: 9px 12px;
  background: #fff;
  text-align: center;
  vertical-align: middle;
}
.mx thead th {
  position: sticky;
  top: 0;
  z-index: 3;
  background: #fff;
  border-bottom: 1px solid #ECEDEF;
  vertical-align: bottom;
}

/* ── Sticky customer column ── */
.mx__col-cust,
.mx__cust,
.mx__foot-label {
  position: sticky;
  left: 0;
  z-index: 2;
  background: #fff;
  text-align: left;
  min-width: 110px;
  box-shadow: 1px 0 0 #ECEDEF;
}
.mx thead .mx__col-cust { z-index: 4; }
.mx__col-cust { font-weight: 600; font-size: 13px; }

/* ── Sum column ── */
.mx__col-sum { text-align: right; min-width: 64px; background: #F6F7F8; }

/* 客户 / 合计 表头标签：水平 + 垂直居中（覆盖 sticky 左对齐、sum 右对齐与 thead 的 bottom 对齐） */
.mx thead .mx__col-cust,
.mx thead .mx__col-sum {
  text-align: center;
  vertical-align: middle;
}

/* ── Output column header: allocation progress ── */
.mx__col-jw { min-width: 120px; }
.oh { display: flex; flex-direction: column; gap: 3px; align-items: flex-start; }
.oh-top { display: flex; align-items: baseline; gap: 5px; flex-wrap: wrap; }
.oh .nm { font-weight: 600; font-size: 12.5px; text-align: left; line-height: 1.3; }
.oh .id { font-size: 10.5px; color: #AEB3B8; font-weight: 400; text-align: left; }
.oh .alloc { display: flex; align-items: center; gap: 6px; }
.oh .alloc .n { font-size: 11px; font-variant-numeric: tabular-nums; }
.oh .alloc .track { width: 46px; height: 4px; border-radius: 2px; background: #EDEFF1; overflow: hidden; flex-shrink: 0; }
.oh .alloc .fill { display: block; height: 100%; }
/* full = emerald, under = amber — driven by parent th class */
.mx__col-jw.full .fill { background: #1E7A5A; }
.mx__col-jw.full .n { color: #1E7A5A; font-weight: 600; }
.mx__col-jw.under .fill { background: #B7791F; }
.mx__col-jw.under .n { color: #B7791F; font-weight: 600; }

/* ── Customer cell ── */
.mx__cust { padding: 8px 12px; }
.cust-nm { font-weight: 600; font-size: 13px; color: #1A1D21; }
.src {
  font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 5px;
  display: inline-block; margin-top: 3px;
}
.src.order { background: #EEF1F4; color: #475569; }
.src.manual { background: #FBF0DC; color: #B7791F; }

/* ── Qty cells ── */
.mx__qty {
  font-variant-numeric: tabular-nums;
  color: #1A1D21;
  min-width: 86px;
  height: 38px;
}
.mx__qty.empty { color: #AEB3B8; }
.mx__qty.locked { background: #fff8e6; color: #8a6500; }
.mx__qty.mixed { background: linear-gradient(to right, #fff8e6 50%, #ffffff 50%); }
.mx__qty.flash { background: #fffae8; transition: background 1.5s ease-out; }
.mx__qty.flash::after { content: "✨"; display: inline-block; margin-left: 4px; font-size: 10px; vertical-align: 2px; }
.mx__qty.flash .cell-input { border-color: #f0c000; box-shadow: 0 0 0 2px rgba(240,192,0,.16); }

/* qty-* classes used in h() render functions must NOT be scoped-only;
   they are applied to spans inside h() which don't receive data-v attrs.
   We define them here but they will NOT be scoped — intentionally global
   via :global() so the render-function spans are styled. */
:global(.qty-empty) { color: #AEB3B8; }
:global(.qty-locked) { color: #8a6500; }
:global(.qty-manual) { font-weight: 600; color: #1A1D21; }
:global(.qty-mixed .l) { color: #8a6500; }
:global(.qty-mixed .plus) { color: #8B9096; }
:global(.qty-mixed .m) { font-weight: 600; color: #1A1D21; }

/* ── Row sum ── */
.mx__row-sum {
  text-align: right;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  background: #F6F7F8;
  color: #1A1D21;
}

/* ── Empty rows ── */
.mx__empty td {
  height: 60px; color: #AEB3B8; font-size: 12px;
  background: repeating-linear-gradient(45deg, #F6F7F8 0 6px, #ECEDEF 6px 12px);
}

/* ── Foot totals row ── */
.totrow td {
  background: #F6F7F8;
  border-top: 1px solid #ECEDEF;
  font-weight: 600;
}
.mx__foot-label {
  font-size: 12px;
  color: #8B9096;
  text-transform: uppercase;
  letter-spacing: .4px;
  background: #F6F7F8;
}
.mx__foot-cell { text-align: center; font-variant-numeric: tabular-nums; }
.mx__foot-cell.ok .tot-ok { color: #1E7A5A; }
.mx__foot-cell.warn .tot-bad { color: #B7791F; }
.tot-sub { font-size: 10.5px; color: #AEB3B8; margin-top: 2px; }
.mx__foot-total {
  text-align: right;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  background: #F6F7F8;
}

/* ── Edit mode: add-row bar ── */
.mx__add-bar-row td { padding: 6px 10px; background: #F6F7F8; text-align: left; }
.add-bar { display: flex; gap: 10px; align-items: center; }
.add-bar__link { color: #1E7A5A; cursor: pointer; padding: 4px 8px; border-radius: 3px; font-size: 12px; }
.add-bar__link:hover { background: #E6F2EC; }
.add-bar__sep { color: #AEB3B8; }
.add-bar__hint { color: #8B9096; font-size: 11px; margin-left: 4px; }
.bulk-btn { color: #1E7A5A; }

/* ── Edit mode: manual row editor ── */
.manual-edit { display: flex; gap: 6px; align-items: center; }
.manual-edit__name { flex: 1; }
.cell-input {
  width: 56px; padding: 3px 6px;
  border: 1px solid #ECEDEF;
  border-radius: 3px;
  font-variant-numeric: tabular-nums;
  font-size: 12px; text-align: center;
  background: #fff;
}
.cell-input:focus { outline: none; border-color: #1E7A5A; box-shadow: 0 0 0 2px rgba(30,122,90,.12); }
.cell-input.zero { color: #AEB3B8; }
.cell-input:disabled { background: #F6F7F8; color: #8B9096; }
:global(.qty-locked-edit) { display: inline-flex; align-items: center; gap: 4px; }
:global(.qty-locked-edit .l) { color: #8a6500; }
:global(.qty-locked-edit .plus) { color: #8B9096; }

/* ── Sticky-bottom save bar (mobile only) ── */
.mx-sticky-foot { display: none; }
@media (max-width: 768px) {
  .mx-sticky-foot {
    display: flex; gap: 6px; justify-content: flex-end;
    position: sticky; bottom: 0; padding: 8px 12px;
    background: #fff; border-top: 1px solid #ECEDEF;
    box-shadow: 0 -2px 4px rgba(0,0,0,.04);
    z-index: 3;
  }
}
</style>
