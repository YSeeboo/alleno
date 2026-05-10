# Handcraft Batch Bridge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bridge the gap between Excel-imported parts and handcraft order detail by adding two batch entry points — a "最近导入" tab in `HandcraftDetail`'s add-part modal (entry A), and an "加入手工单" split button in `BatchImageUpload` (entry B).

**Architecture:** Front-end-only. Recently-imported part batches are stored in `localStorage` (max 5 batches / 7 days, FIFO). Two consumer UIs (entry A: pick/edit per row; entry B: one-click direct attach) read this storage and call existing handcraft APIs (`addHandcraftPart` / `updateHandcraftPart` / `createHandcraft`). No backend changes.

**Tech Stack:** Vue 3.5, Naive UI 2.44, Pinia (auth store), Vite 7, vanilla `node:assert` for unit tests (matches existing `frontend/tests/*.test.mjs` pattern).

**Branch note:** Spec was committed on `feat/jewelry-copy`. Confirm with the user whether to continue on that branch, switch back to `main`, or create a fresh `feat/handcraft-batch-bridge` branch before starting.

**Spec reference:** `docs/superpowers/specs/2026-05-10-handcraft-batch-bridge-design.md`

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/utils/recentImports.js` | Create | Pure functions: read/write/expire/delete batches in localStorage |
| `frontend/tests/recentImports.test.mjs` | Create | Unit tests for the util (node:assert pattern, no test runner) |
| `frontend/src/components/RecentImportsPicker.vue` | Create | Picker UI for entry A — multi-select rows with editable qty |
| `frontend/src/components/AttachToHandcraftModal.vue` | Create | Submodal for entry B — choose existing/new handcraft, confirm-and-jump |
| `frontend/src/views/parts/PartList.vue` | Modify | After `doImport`: push new batch to localStorage; pass `batchId` and `triggeredBy="import"` to `BatchImageUpload` |
| `frontend/src/components/BatchImageUpload.vue` | Modify | New props `batchId`, `triggeredBy`; image upload/remove writes back to batch; split button → opens `AttachToHandcraftModal` |
| `frontend/src/views/handcraft/HandcraftDetail.vue` | Modify | Wrap existing add-part form in tabs; add "最近导入" tab using `RecentImportsPicker`; add `attachBatch()` handler |

---

## Task 1: `recentImports.js` util — write tests first

**Files:**
- Create: `frontend/src/utils/recentImports.js`
- Create: `frontend/tests/recentImports.test.mjs`

The util manages batches in `localStorage` under key `allen_shop.recent_part_imports`. Pure functions for testability. Follows the node-assert pattern from `frontend/tests/partsSummarySort.test.mjs`.

**API surface:**
- `pushBatch(parts, opts) → batch` — pushes a new batch, returns the created batch object. `opts.now` allows test override of timestamp; `opts.operator` is shown in UI.
- `getActiveBatches(opts) → Batch[]` — returns batches sorted newest-first, after pruning expired (>7d) and excess (>5).
- `getBatchById(batchId) → Batch | null`
- `updateBatchPartImage(batchId, partId, imageUrl)` — used by `BatchImageUpload` to write back URLs.
- All read paths defensively handle a missing/corrupt key (catch `JSON.parse` errors → return `[]`).

**Constants:**
- `STORAGE_KEY = 'allen_shop.recent_part_imports'`
- `MAX_BATCHES = 5`
- `MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000` (7 days)

- [ ] **Step 1: Write the failing tests**

Create `frontend/tests/recentImports.test.mjs`:

```js
// Pure-function unit tests for src/utils/recentImports.js.
// Self-contained: run with `node frontend/tests/recentImports.test.mjs`.
// Follows the same pattern as partsSummarySort.test.mjs.

import assert from 'node:assert/strict'

// Polyfill localStorage for node (the util uses globalThis.localStorage).
const store = new Map()
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
}

const {
  STORAGE_KEY,
  MAX_BATCHES,
  MAX_AGE_MS,
  pushBatch,
  getActiveBatches,
  getBatchById,
  updateBatchPartImage,
} = await import('../src/utils/recentImports.js')

const tests = []
const test = (name, fn) => tests.push({ name, fn })
const reset = () => { localStorage.clear() }

const samplePart = (id, qty = 1) => ({
  part_id: id, name: `name-${id}`, image: null, unit: '个', imported_qty: qty,
})

// ---- pushBatch ----
test('pushBatch: returns a batch with batch_id, imported_at, parts', () => {
  reset()
  const batch = pushBatch([samplePart('PJ-DZ-00001')], { now: 1715332920000, operator: 'ycb' })
  assert.equal(typeof batch.batch_id, 'string')
  assert.match(batch.batch_id, /^imp-/)
  assert.equal(batch.imported_at, 1715332920000)
  assert.equal(batch.operator, 'ycb')
  assert.equal(batch.parts.length, 1)
  assert.equal(batch.parts[0].part_id, 'PJ-DZ-00001')
})

test('pushBatch: persists to localStorage and shows up in getActiveBatches', () => {
  reset()
  pushBatch([samplePart('PJ-DZ-00001')], { now: 1715332920000, operator: 'ycb' })
  const list = getActiveBatches({ now: 1715332920000 })
  assert.equal(list.length, 1)
  assert.equal(list[0].parts[0].part_id, 'PJ-DZ-00001')
})

test('pushBatch: newest first', () => {
  reset()
  pushBatch([samplePart('A')], { now: 1000, operator: 'x' })
  pushBatch([samplePart('B')], { now: 2000, operator: 'x' })
  const list = getActiveBatches({ now: 2000 })
  assert.equal(list[0].parts[0].part_id, 'B')
  assert.equal(list[1].parts[0].part_id, 'A')
})

// ---- getActiveBatches ----
test('getActiveBatches: empty when nothing stored', () => {
  reset()
  assert.deepEqual(getActiveBatches({ now: Date.now() }), [])
})

test('getActiveBatches: filters out batches older than MAX_AGE_MS', () => {
  reset()
  const now = 10_000_000
  pushBatch([samplePart('OLD')], { now: now - MAX_AGE_MS - 1, operator: 'x' })
  pushBatch([samplePart('NEW')], { now: now - 1000, operator: 'x' })
  const list = getActiveBatches({ now })
  assert.equal(list.length, 1)
  assert.equal(list[0].parts[0].part_id, 'NEW')
})

test('getActiveBatches: keeps at most MAX_BATCHES (FIFO)', () => {
  reset()
  // Push MAX_BATCHES + 3 batches with increasing timestamps: P0 (oldest) ... P7 (newest).
  for (let i = 0; i < MAX_BATCHES + 3; i++) {
    pushBatch([samplePart(`P${i}`)], { now: 1000 + i, operator: 'x' })
  }
  const list = getActiveBatches({ now: 9999 })
  assert.equal(list.length, MAX_BATCHES)
  // Newest first → list[0] = P(MAX+2) = P7
  assert.equal(list[0].parts[0].part_id, `P${MAX_BATCHES + 2}`)
  // Oldest kept = P3 (P0/P1/P2 dropped by FIFO), at the tail
  assert.equal(list[list.length - 1].parts[0].part_id, 'P3')
})

test('getActiveBatches: tolerates corrupt storage', () => {
  reset()
  localStorage.setItem(STORAGE_KEY, 'not-json{')
  assert.deepEqual(getActiveBatches({ now: Date.now() }), [])
})

// ---- getBatchById ----
test('getBatchById: returns the batch when present', () => {
  reset()
  const batch = pushBatch([samplePart('A')], { now: 5000, operator: 'x' })
  const found = getBatchById(batch.batch_id)
  assert.equal(found.parts[0].part_id, 'A')
})

test('getBatchById: returns null when absent', () => {
  reset()
  assert.equal(getBatchById('nope'), null)
})

// ---- updateBatchPartImage ----
test('updateBatchPartImage: writes the image URL into the matching part', () => {
  reset()
  const batch = pushBatch(
    [samplePart('A'), samplePart('B')],
    { now: 5000, operator: 'x' },
  )
  updateBatchPartImage(batch.batch_id, 'B', 'https://cdn/img.png')
  const after = getBatchById(batch.batch_id)
  assert.equal(after.parts[0].image, null)
  assert.equal(after.parts[1].image, 'https://cdn/img.png')
})

test('updateBatchPartImage: clears image when given null', () => {
  reset()
  const batch = pushBatch([samplePart('A')], { now: 5000, operator: 'x' })
  updateBatchPartImage(batch.batch_id, 'A', 'https://cdn/img.png')
  updateBatchPartImage(batch.batch_id, 'A', null)
  assert.equal(getBatchById(batch.batch_id).parts[0].image, null)
})

test('updateBatchPartImage: silently ignores unknown batch / part', () => {
  reset()
  // Should not throw.
  updateBatchPartImage('nope', 'X', 'https://cdn/img.png')
  const batch = pushBatch([samplePart('A')], { now: 5000, operator: 'x' })
  updateBatchPartImage(batch.batch_id, 'NOPE', 'https://cdn/img.png')
  assert.equal(getBatchById(batch.batch_id).parts[0].image, null)
})

// ---- runner ----
let failed = 0
for (const t of tests) {
  try {
    t.fn()
    console.log(`ok  ${t.name}`)
  } catch (e) {
    failed++
    console.error(`FAIL ${t.name}`)
    console.error(e)
  }
}
if (failed > 0) {
  console.error(`\n${failed} test(s) failed.`)
  process.exit(1)
}
console.log(`\n${tests.length} test(s) passed.`)
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd frontend && node tests/recentImports.test.mjs
```

Expected: ENOENT or "module not found" referencing `src/utils/recentImports.js`.

- [ ] **Step 3: Write minimal `recentImports.js` to make tests pass**

Create `frontend/src/utils/recentImports.js`:

```js
// Persisted "recent Excel-imported part batches" — the bridge between
// PartList.doImport and handcraft-order add-part flows.
//
// Storage shape (single localStorage key):
//   [
//     { batch_id, imported_at, operator,
//       parts: [{ part_id, name, image, unit, imported_qty }, ...] },
//     ...
//   ]
//
// Newest first. Pruned to MAX_BATCHES and MAX_AGE_MS on read.

export const STORAGE_KEY = 'allen_shop.recent_part_imports'
export const MAX_BATCHES = 5
export const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

const readRaw = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const writeRaw = (list) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
}

const prune = (list, now) => {
  const fresh = list.filter((b) => now - (b.imported_at || 0) <= MAX_AGE_MS)
  fresh.sort((a, b) => (b.imported_at || 0) - (a.imported_at || 0))
  return fresh.slice(0, MAX_BATCHES)
}

export const pushBatch = (parts, opts = {}) => {
  const now = opts.now ?? Date.now()
  const operator = opts.operator ?? ''
  const batch = {
    batch_id: `imp-${now}-${Math.random().toString(36).slice(2, 7)}`,
    imported_at: now,
    operator,
    parts: parts.map((p) => ({
      part_id: p.part_id,
      name: p.name ?? '',
      image: p.image ?? null,
      unit: p.unit ?? '个',
      imported_qty: Number(p.imported_qty ?? 0),
    })),
  }
  const next = prune([batch, ...readRaw()], now)
  writeRaw(next)
  return batch
}

export const getActiveBatches = (opts = {}) => {
  const now = opts.now ?? Date.now()
  return prune(readRaw(), now)
}

export const getBatchById = (batchId) => {
  return readRaw().find((b) => b.batch_id === batchId) ?? null
}

export const updateBatchPartImage = (batchId, partId, imageUrl) => {
  const list = readRaw()
  const batch = list.find((b) => b.batch_id === batchId)
  if (!batch) return
  const part = batch.parts.find((p) => p.part_id === partId)
  if (!part) return
  part.image = imageUrl ?? null
  writeRaw(list)
}
```

- [ ] **Step 4: Run the tests, confirm they pass**

```bash
cd frontend && node tests/recentImports.test.mjs
```

Expected: all "ok" lines, final "N test(s) passed.", exit 0.

If a test fails, fix the implementation, re-run.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/recentImports.js frontend/tests/recentImports.test.mjs
git commit -m "feat(handcraft): add recentImports localStorage util + tests

Pure-function module managing the 'recent part imports' batch list
that bridges PartList Excel imports to handcraft order detail.

Stores under 'allen_shop.recent_part_imports', max 5 batches,
7-day TTL, newest-first. Read paths are defensive against corrupt
JSON. Tests use the existing node:assert pattern (same as
partsSummarySort.test.mjs)."
```

---

## Task 2: `PartList.doImport` writes batch on success

**Files:**
- Modify: `frontend/src/views/parts/PartList.vue:608-645` (the `doImport` function and surrounding state)

`importPartsExcel` returns `data.results: Array<{row_number, part_id, name, image, action, stock_added}>`. Convert this to the batch's `parts` shape and call `pushBatch`.

We also need to remember the new `batch_id` so we can pass it to `BatchImageUpload` (Task 3 reads it back).

- [ ] **Step 1: Add the import**

At the top imports section of `PartList.vue` (find the existing `import { listParts, ... } from '@/api/parts'`), add a new import below it:

```js
import { pushBatch } from '@/utils/recentImports'
import { useAuthStore } from '@/stores/auth'
```

Then in the `<script setup>` body, near the existing `const message = useMessage()` line:

```js
const authStore = useAuthStore()
```

- [ ] **Step 2: Add a ref to remember the active batch id**

Find the state block where `const showBatchImageUpload = ref(false)` and `const batchImageParts = ref([])` are declared (around line 406). Add:

```js
const batchImageBatchId = ref(null)
```

- [ ] **Step 3: Wire `pushBatch` into `doImport`**

Find the `doImport` function (around line 608). Replace the body — locate the existing `if (partsWithoutImage.length > 0) { ... }` block and adjust:

OLD:
```js
const partsWithoutImage = (data.results || []).filter(r => !r.image)
if (partsWithoutImage.length > 0) {
  const doUpload = await new Promise(resolve => {
    dialog.info({ ... })
  })
  if (doUpload) {
    batchImageParts.value = partsWithoutImage
    showBatchImageUpload.value = true
  }
}
```

NEW:
```js
// Persist the import as a "batch" — feeds both the post-import
// image-upload step and the downstream handcraft attach flows
// (HandcraftDetail "最近导入" tab + BatchImageUpload submodal).
const allImported = (data.results || []).map((r) => ({
  part_id: r.part_id,
  name: r.name,
  image: r.image,
  unit: '个', // results don't carry unit; util will treat missing as '个'
  imported_qty: r.stock_added,
}))
const batch = allImported.length > 0
  ? pushBatch(allImported, { operator: authStore.user?.username || '' })
  : null

const partsWithoutImage = (data.results || []).filter((r) => !r.image)
if (partsWithoutImage.length > 0) {
  const doUpload = await new Promise((resolve) => {
    dialog.info({
      title: '上传图片',
      content: `有 ${partsWithoutImage.length} 个配件没有图片，是否现在上传？`,
      positiveText: '是',
      negativeText: '否',
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => resolve(false),
      onClose: () => resolve(false),
    })
  })
  if (doUpload) {
    batchImageParts.value = partsWithoutImage
    batchImageBatchId.value = batch?.batch_id ?? null
    showBatchImageUpload.value = true
  }
}
```

- [ ] **Step 4: Pass new props to `<BatchImageUpload>` in template**

Find the existing usage near line 234:

OLD:
```html
<BatchImageUpload
  v-model:show="showBatchImageUpload"
  :parts="batchImageParts"
/>
```

NEW:
```html
<BatchImageUpload
  v-model:show="showBatchImageUpload"
  :parts="batchImageParts"
  :batch-id="batchImageBatchId"
  triggered-by="import"
/>
```

- [ ] **Step 5: Smoke test in browser**

```bash
cd frontend && npm run dev
```

Open the parts page, import a small Excel (use the template + 2 rows). After import:

```bash
# In browser DevTools console:
JSON.parse(localStorage.getItem('allen_shop.recent_part_imports'))
```

Expected: an array with one batch object containing the imported parts and `imported_qty` matching the Excel "入库数量" column.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/parts/PartList.vue
git commit -m "feat(handcraft): persist Excel-import batches via recentImports util

doImport now pushes each successful Excel import as a batch into
localStorage. BatchImageUpload now receives the new batch_id and
triggered-by props so it can write back image URLs and (in the
next task) show the 'attach to handcraft order' button."
```

---

## Task 3: `BatchImageUpload` writes image URLs back to the batch

**Files:**
- Modify: `frontend/src/components/BatchImageUpload.vue` (entire file, ~155 lines)

Two changes: (1) declare new props `batchId` and `triggeredBy`; (2) on every successful upload or removal, call `updateBatchPartImage`. Skip the writeback when `batchId` is null (i.e. the modal was launched without an originating import — e.g. a future "manual补图" flow).

- [ ] **Step 1: Add new props**

Find the existing `defineProps` block:

OLD:
```js
const props = defineProps({
  show: Boolean,
  parts: { type: Array, default: () => [] },  // [{ part_id, name }]
})
```

NEW:
```js
const props = defineProps({
  show: Boolean,
  parts: { type: Array, default: () => [] },  // [{ part_id, name }]
  // When set, image upload/remove is mirrored into recentImports for the
  // matching batch — keeps the batch's image URLs fresh for downstream
  // handcraft attach flows.
  batchId: { type: String, default: null },
  // 'import' = triggered by PartList.doImport (enables the 'add to handcraft'
  //            button). 'manual' = standalone補图 (no extra button shown).
  triggeredBy: { type: String, default: 'manual' },
})
```

- [ ] **Step 2: Add the import**

At the top of the `<script setup>`:

```js
import { updateBatchPartImage } from '@/utils/recentImports'
```

- [ ] **Step 3: Mirror upload into the batch in `handlePaste`**

Find `handlePaste` (around line 95). After the existing `await updatePart(partId, { image: url })` line and `uploadedImages.value[partId] = url`, add the mirror call:

OLD (last few lines of try block):
```js
    await updatePart(partId, { image: url })
    uploadedImages.value[partId] = url
    message.success(`${partId} 图片上传成功`)
```

NEW:
```js
    await updatePart(partId, { image: url })
    uploadedImages.value[partId] = url
    if (props.batchId) updateBatchPartImage(props.batchId, partId, url)
    message.success(`${partId} 图片上传成功`)
```

- [ ] **Step 4: Mirror removal into the batch in `removeImage`**

Find `removeImage` (around line 120). After `await updatePart(partId, { image: null })`:

OLD:
```js
async function removeImage(partId) {
  try {
    await updatePart(partId, { image: null })
    delete uploadedImages.value[partId]
  } catch (err) {
    message.error(`删除失败: ${err.message || '未知错误'}`)
  }
}
```

NEW:
```js
async function removeImage(partId) {
  try {
    await updatePart(partId, { image: null })
    delete uploadedImages.value[partId]
    if (props.batchId) updateBatchPartImage(props.batchId, partId, null)
  } catch (err) {
    message.error(`删除失败: ${err.message || '未知错误'}`)
  }
}
```

- [ ] **Step 5: Smoke test**

```bash
cd frontend && npm run dev
```

In the browser:
1. Import an Excel with 2 parts that have no image
2. In the BatchImageUpload modal, paste an image into one part's upload area
3. Open DevTools console:

```js
JSON.parse(localStorage.getItem('allen_shop.recent_part_imports'))[0].parts
```

Expected: the part you pasted into now has `image: "https://..."` (the OSS URL); the other still has `image: null`.

Then click the "x" on the uploaded image to remove it; re-run the console check — that part's `image` should be back to `null`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/BatchImageUpload.vue
git commit -m "feat(handcraft): mirror batch-image uploads into recentImports

BatchImageUpload now writes image URL changes back into the
matching batch in recentImports (when batchId prop is set). Also
adds a triggeredBy prop — 'import' vs 'manual' — that the next
task uses to gate the 'attach to handcraft' button."
```

---

## Task 4: `RecentImportsPicker.vue` component (entry A's picker)

**Files:**
- Create: `frontend/src/components/RecentImportsPicker.vue`

A self-contained picker. Parent (`HandcraftDetail`) passes the current order's `items` (so we can mark "已在本单"). The component emits `attach` with a payload `{ rows: [{ part_id, qty, unit, _existingItemId, _existingQty }, ...] }` describing exactly what should be added/incremented.

The "attach" action itself (calling `addHandcraftPart` / `updateHandcraftPart`) lives in the parent, because it owns the order id and the loadData() refresh.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/RecentImportsPicker.vue`:

```vue
<template>
  <div>
    <div v-if="batches.length === 0" class="empty">
      <p style="font-size: 14px; color: #6b7280;">没有最近导入的批次</p>
      <p style="font-size: 12px; color: #9ca3af; margin-top: 4px;">
        到「商品 / 配件管理」页面用 Excel 导入一批后，这里就能批量挂入。
      </p>
    </div>

    <div v-else>
      <!-- Batch selector -->
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 10px;">
        <label style="font-size: 13px; color: #4b5563; min-width: 38px;">批次</label>
        <n-select
          v-model:value="selectedBatchId"
          :options="batchOptions"
          style="flex: 1;"
        />
      </div>

      <!-- Helper hint -->
      <div class="hint">
        📦 数量沿用导入时的"入库数量" · 修改高亮 · 已存在的明细将累加
      </div>

      <!-- Select-all + count -->
      <div class="select-all-bar">
        <n-checkbox
          :checked="allEligibleSelected"
          :indeterminate="someEligibleSelected && !allEligibleSelected"
          @update:checked="toggleSelectAll"
        >
          全选
        </n-checkbox>
        <span class="count">已选 {{ checkedCount }} / {{ rows.length }}</span>
      </div>

      <!-- Rows -->
      <div class="part-list">
        <div v-for="row in rows" :key="row.part_id" class="part-item">
          <n-checkbox v-model:checked="row._checked" />
          <img v-if="row.image" :src="row.image" class="thumb" />
          <div v-else class="thumb-empty">无图</div>
          <div class="meta">
            <div class="part-id">{{ row.part_id }}</div>
            <div class="part-name" :title="row.name">{{ row.name }}</div>
          </div>
          <div class="qty-cell">
            <n-input-number
              v-model:value="row.qty"
              :min="0"
              :precision="0"
              :step="1"
              size="small"
              :show-button="false"
              :class="{ modified: row.qty !== row.imported_qty }"
              style="width: 72px;"
            />
            <span class="unit">{{ row.unit || '个' }}</span>
          </div>
          <span v-if="row._existingItemId != null" class="badge-existing">已在本单</span>
        </div>
      </div>

      <div class="legend">
        <span><span class="dot dot-modified"></span>已修改</span>
        <span><span class="dot dot-existing"></span>已在本单（累加）</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { NSelect, NCheckbox, NInputNumber } from 'naive-ui'
import { getActiveBatches, getBatchById } from '@/utils/recentImports'

const props = defineProps({
  // Existing items in the current handcraft order — used to mark "已在本单"
  // and to calculate the post-attach qty for accumulation.
  // Shape: [{ id, part_id, qty, ... }]
  existingItems: { type: Array, default: () => [] },
})

const emit = defineEmits(['change'])

// --- Batches ---
const batches = ref(getActiveBatches())
const selectedBatchId = ref(batches.value[0]?.batch_id ?? null)

const batchOptions = computed(() =>
  batches.value.map((b) => {
    const date = new Date(b.imported_at)
    const pad = (n) => String(n).padStart(2, '0')
    const label =
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
      `${pad(date.getHours())}:${pad(date.getMinutes())} · ${b.parts.length} 件` +
      (b.operator ? ` · ${b.operator}` : '')
    return { label, value: b.batch_id }
  }),
)

// --- Rows (one per part in the selected batch) ---
const rows = ref([])

const refreshRows = () => {
  if (!selectedBatchId.value) {
    rows.value = []
    return
  }
  const batch = getBatchById(selectedBatchId.value)
  if (!batch) {
    rows.value = []
    return
  }
  rows.value = batch.parts.map((p) => {
    const existing = props.existingItems.find((it) => it.part_id === p.part_id)
    return {
      part_id: p.part_id,
      name: p.name,
      image: p.image,
      unit: p.unit || '个',
      imported_qty: p.imported_qty,
      qty: p.imported_qty,
      _existingItemId: existing ? existing.id : null,
      _existingQty: existing ? existing.qty : null,
      _checked: !existing, // default: tick only if not already in the order
    }
  })
  bubble()
}

watch(selectedBatchId, refreshRows, { immediate: true })
watch(() => props.existingItems, refreshRows)

// --- Selection helpers ---
const eligibleRows = computed(() => rows.value)
const checkedCount = computed(() => rows.value.filter((r) => r._checked).length)
const allEligibleSelected = computed(() =>
  eligibleRows.value.length > 0 &&
  eligibleRows.value.every((r) => r._checked),
)
const someEligibleSelected = computed(() =>
  eligibleRows.value.some((r) => r._checked),
)

const toggleSelectAll = (checked) => {
  for (const r of rows.value) r._checked = checked
  bubble()
}

// Watch row changes (qty, _checked) — emit summary up so the modal footer can
// show "新增 X · 累加 Y · 共 Z 件" and enable/disable the submit button.
watch(rows, bubble, { deep: true })

function bubble() {
  const checked = rows.value.filter((r) => r._checked)
  const newOnes = checked.filter((r) => r._existingItemId == null)
  const updateOnes = checked.filter((r) => r._existingItemId != null)
  const totalQty = checked.reduce((s, r) => s + (Number(r.qty) || 0), 0)
  const hasZeroQty = checked.some((r) => !r.qty || r.qty <= 0)
  emit('change', {
    rows: checked.map((r) => ({
      part_id: r.part_id,
      qty: Number(r.qty),
      unit: r.unit,
      _existingItemId: r._existingItemId,
      _existingQty: r._existingQty,
    })),
    newCount: newOnes.length,
    updateCount: updateOnes.length,
    totalQty,
    hasZeroQty,
  })
}
</script>

<style scoped>
.empty {
  padding: 36px 0;
  text-align: center;
}
.hint {
  background: #f7f9fa;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 10px;
}
.select-all-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 0; border-bottom: 1px solid #efeff5;
  margin-bottom: 4px;
}
.count { font-size: 12px; color: #888; }

.part-list {
  max-height: 360px;
  overflow-y: auto;
}
.part-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 4px; border-bottom: 1px solid #f5f5f5;
}
.part-item:hover { background: #fafafa; }
.thumb, .thumb-empty {
  width: 36px; height: 36px; border-radius: 4px; flex-shrink: 0;
  object-fit: cover;
}
.thumb-empty {
  border: 1px dashed #d9d9d9; background: #f5f5f5; color: #ccc;
  font-size: 10px; display: inline-flex; align-items: center; justify-content: center;
}
.meta { flex: 1; min-width: 0; }
.part-id { font-size: 12px; color: #888; font-family: ui-monospace, monospace; }
.part-name {
  font-size: 13.5px; color: #1f2937; margin-top: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.qty-cell {
  display: flex; align-items: center; gap: 4px; flex-shrink: 0;
}
.unit { font-size: 12px; color: #6b7280; min-width: 18px; }
.badge-existing {
  background: #fef3c7; color: #92400e;
  font-size: 10.5px; padding: 2px 6px; border-radius: 8px;
  flex-shrink: 0; white-space: nowrap;
}
:deep(.modified .n-input__input-el) {
  background: #fffbeb;
}
:deep(.modified .n-input) {
  border-color: #f0a020;
}

.legend {
  margin-top: 8px; font-size: 11px; color: #888;
  display: flex; gap: 14px; align-items: center;
}
.dot {
  display: inline-block; width: 8px; height: 8px;
  border-radius: 2px; margin-right: 4px; vertical-align: middle;
}
.dot-modified { background: #fffbeb; border: 1px solid #f0a020; }
.dot-existing { background: #fef3c7; border: 1px solid #fcd34d; }
</style>
```

- [ ] **Step 2: Build-check**

```bash
cd frontend && npm run build
```

Expected: build succeeds (template/script syntax OK). The component isn't wired up yet, so it won't be rendered, but it must compile.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/RecentImportsPicker.vue
git commit -m "feat(handcraft): add RecentImportsPicker component

Reusable picker UI for the 'recent imports' tab in HandcraftDetail.
Renders rows from the latest batch in localStorage, supports
multi-select and per-row qty editing (defaults to imported_qty,
modified rows highlight orange), and emits a 'change' event with
the current attach payload so the parent can render summary text
and enable/disable the submit button.

Component is created but not yet rendered — wiring lands in the
next task."
```

---

## Task 5: Wire `RecentImportsPicker` into `HandcraftDetail` modal as a tab

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue` (modal block at ~line 240, plus script setup at ~line 681 / 1147)

Wrap the existing add-modal contents in `<n-tabs>`. Add a "最近导入" tab containing `<RecentImportsPicker>`. The "确认添加" button stays for the single-add tab; for the recent-imports tab we add a new submit handler `attachRecentBatch()` (Task 6 implements the body — for this task we just stub it).

- [ ] **Step 1: Add imports**

In the `<script setup>` of `HandcraftDetail.vue`, find the existing imports near the top. Add:

```js
import { NTabs, NTabPane } from 'naive-ui'
import RecentImportsPicker from '@/components/RecentImportsPicker.vue'
```

(The existing `import { ... } from 'naive-ui'` line might need NTabs / NTabPane added to it instead — match the existing style. Search for `from 'naive-ui'` in the file and merge accordingly.)

Add the existing function imports for the new attach-update helper:

```js
import { addHandcraftPart, updateHandcraftPart, getHandcraft, getHandcraftParts, /* ...existing... */ } from '@/api/handcraft'
```

(`updateHandcraftPart` may not be in the current import list — verify and add it.)

- [ ] **Step 2: Add state for the recent-imports tab**

In the script setup, near the existing `addForm = ref(...)` block (~line 681), add:

```js
const addModalTab = ref('recent') // default tab; overridden in openAddModal
const recentAttachPayload = ref({ rows: [], newCount: 0, updateCount: 0, totalQty: 0, hasZeroQty: false })
const attachSubmitting = ref(false)

const onRecentChange = (payload) => {
  recentAttachPayload.value = payload
}
```

- [ ] **Step 3: Update `openAddModal` to set the default tab**

Find `openAddModal` (~line 1133). Replace with:

```js
const openAddModal = () => {
  addForm.value = { part_id: null, qty: 1, unit: '个', weight: null, weight_unit: 'kg', note: '' }
  // Default to "recent imports" if there's at least one fresh batch; otherwise "single".
  // We import getActiveBatches lazily in script setup — see top of file.
  addModalTab.value = getActiveBatches().length > 0 ? 'recent' : 'single'
  addModalVisible.value = true
}
```

And add the import at the top:

```js
import { getActiveBatches } from '@/utils/recentImports'
```

- [ ] **Step 4: Replace the modal body to use tabs**

Find the modal block at line 240–289. The current content is a `<form>` wrapping the existing form fields, plus a footer with "取消" / "确认添加".

Replace the modal body (between `<n-modal v-model:show="addModalVisible" ...>` and `</n-modal>`) with:

```html
    <n-modal v-model:show="addModalVisible" preset="card" title="添加配件明细" :style="{ width: isMobile ? '95vw' : '560px' }">
      <n-tabs v-model:value="addModalTab" type="line" animated>
        <n-tab-pane name="single" tab="单条添加">
          <form @submit.prevent="doAddItem">
            <n-form :label-placement="isMobile ? 'top' : 'left'" label-width="90">
              <n-form-item label="配件">
                <n-select
                  v-model:value="addForm.part_id"
                  :options="partOptions"
                  :render-label="renderOptionWithImage"
                  filterable
                  clearable
                  placeholder="选择配件"
                  @update:value="onAddPartSelect"
                />
              </n-form-item>
              <n-form-item label="数量">
                <n-input-number v-model:value="addForm.qty" :min="1" :precision="0" :step="1" style="width: 100%;" />
              </n-form-item>
              <n-form-item label="单位">
                <n-select v-model:value="addForm.unit" :options="unitOptions" />
              </n-form-item>
              <n-form-item label="重量">
                <div style="display: flex; gap: 8px; width: 100%;">
                  <n-input-number
                    v-model:value="addForm.weight"
                    :min="0"
                    :precision="2"
                    :step="0.1"
                    placeholder="可选"
                    clearable
                    style="flex: 1;"
                  />
                  <n-select
                    v-model:value="addForm.weight_unit"
                    :options="weightUnitOptions"
                    style="width: 90px;"
                  />
                </div>
              </n-form-item>
              <n-form-item label="备注">
                <n-input v-model:value="addForm.note" placeholder="备注（可选）" />
              </n-form-item>
            </n-form>
          </form>
        </n-tab-pane>

        <n-tab-pane name="recent" tab="最近导入">
          <RecentImportsPicker
            :existing-items="items"
            @change="onRecentChange"
          />
        </n-tab-pane>
      </n-tabs>

      <template #footer>
        <n-space justify="space-between" style="width: 100%;">
          <span v-if="addModalTab === 'recent' && recentAttachPayload.rows.length > 0" style="font-size: 12px; color: #6b7280;">
            新增 <strong>{{ recentAttachPayload.newCount }}</strong> 项 ·
            累加 <strong>{{ recentAttachPayload.updateCount }}</strong> 项 ·
            共 <strong>{{ recentAttachPayload.totalQty }}</strong> 件
          </span>
          <span v-else style="font-size: 12px; color: #9ca3af;">
            <span v-if="addModalTab === 'recent'">请勾选要加入的项</span>
          </span>

          <n-space>
            <n-button @click="addModalVisible = false">取消</n-button>
            <n-button
              v-if="addModalTab === 'single'"
              type="primary"
              :loading="addSubmitting"
              @click="doAddItem"
            >确认添加</n-button>
            <n-button
              v-else
              type="primary"
              :loading="attachSubmitting"
              :disabled="recentAttachPayload.rows.length === 0 || recentAttachPayload.hasZeroQty"
              @click="attachRecentBatch"
            >
              {{
                recentAttachPayload.hasZeroQty
                  ? '勾选项含数量 0'
                  : `加入 ${recentAttachPayload.rows.length} 项`
              }}
            </n-button>
          </n-space>
        </n-space>
      </template>
    </n-modal>
```

- [ ] **Step 5: Stub the attach handler (full body lands in Task 6)**

In script setup, near `doAddItem`:

```js
const attachRecentBatch = async () => {
  // Implemented in Task 6.
  console.log('attachRecentBatch payload:', recentAttachPayload.value)
}
```

- [ ] **Step 6: Smoke test the UI**

```bash
cd frontend && npm run dev
```

In the browser:
1. Open any pending handcraft order detail
2. Click "+ 添加配件" — modal should now show two tabs
3. The "最近导入" tab should be active (assuming a recent batch exists from earlier tests; if not, do an Excel import first to create one)
4. Pick rows, edit qty values — modified rows should show orange background on the qty input
5. The footer should show the running summary
6. Click "加入 N 项" — should print the payload to the console (no actual write yet)
7. Switch to "单条添加" tab — existing flow should still work end-to-end (write a single row and verify it appears in the table)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat(handcraft): add 'recent imports' tab to add-part modal

Wraps the existing add-part form in tabs and adds a 'recent
imports' tab backed by RecentImportsPicker. Footer summary
('新增 X · 累加 Y · 共 Z 件') and submit button switch based on
the active tab. Single-add path is unchanged. The actual attach
logic is stubbed — full implementation in the next task."
```

---

## Task 6: Implement `attachRecentBatch` — write to backend with concurrency limit

**Files:**
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue` (the `attachRecentBatch` stub from Task 5)

For each `_existingItemId == null` row → `addHandcraftPart`.
For each `_existingItemId != null` row → `updateHandcraftPart(orderId, itemId, { qty: _existingQty + qty, unit })`.
Concurrency limit 5; per-row failures are reported individually and don't stop other rows.

- [ ] **Step 1: Add a tiny concurrency helper inline**

In the script setup of `HandcraftDetail.vue`, near other helpers (or at the top of the script), add:

```js
// Run async fns with a max concurrency. Returns an array in the same order
// as `tasks`, where each entry is either { ok: true, value } or { ok: false, error }.
const runWithConcurrency = async (tasks, limit = 5) => {
  const results = new Array(tasks.length)
  let i = 0
  const workers = Array.from({ length: Math.min(limit, tasks.length) }, async () => {
    while (i < tasks.length) {
      const idx = i++
      try {
        results[idx] = { ok: true, value: await tasks[idx]() }
      } catch (error) {
        results[idx] = { ok: false, error }
      }
    }
  })
  await Promise.all(workers)
  return results
}
```

- [ ] **Step 2: Implement `attachRecentBatch`**

Replace the stub with:

```js
const attachRecentBatch = async () => {
  const payload = recentAttachPayload.value
  if (payload.rows.length === 0 || payload.hasZeroQty) return

  attachSubmitting.value = true
  const orderId = route.params.id

  // Re-validate the order is still pending (another tab might have sent it).
  try {
    const { data: latest } = await getHandcraft(orderId)
    if (latest.status !== 'pending') {
      message.error(`手工单已是 ${latest.status} 状态，无法再添加配件`)
      attachSubmitting.value = false
      return
    }
  } catch (_) {
    attachSubmitting.value = false
    return
  }

  // Build one task per row.
  const tasks = payload.rows.map((row) => async () => {
    if (row._existingItemId == null) {
      return addHandcraftPart(orderId, {
        part_id: row.part_id,
        qty: row.qty,
        unit: row.unit,
      })
    }
    return updateHandcraftPart(orderId, row._existingItemId, {
      qty: (Number(row._existingQty) || 0) + row.qty,
      unit: row.unit,
    })
  })

  const results = await runWithConcurrency(tasks, 5)

  let okNew = 0
  let okUpd = 0
  let failures = 0
  results.forEach((r, idx) => {
    const row = payload.rows[idx]
    if (r.ok) {
      if (row._existingItemId == null) okNew++
      else okUpd++
    } else {
      failures++
      const detail = r.error?.response?.data?.detail || r.error?.message || '未知错误'
      message.error(`${row.part_id} 加入失败：${detail}`)
    }
  })

  if (okNew + okUpd > 0) {
    message.success(`已新增 ${okNew} 项，累加 ${okUpd} 项${failures > 0 ? `（${failures} 项失败）` : ''}`)
  }
  if (okNew + okUpd > 0) {
    addModalVisible.value = false
    await loadData()
  }
  attachSubmitting.value = false
}
```

- [ ] **Step 3: End-to-end manual test — A workflow**

```bash
cd frontend && npm run dev
```

In the browser:
1. Import an Excel with 3 parts: PJ-DZ-T1 (qty=10), PJ-DZ-T2 (qty=20), PJ-DZ-T3 (qty=0). Skip image upload.
2. Open any pending handcraft order
3. "+ 添加配件" → "最近导入" tab
4. T3 should be visible with qty=0; if it's checked, the submit button should read "勾选项含数量 0" and be disabled
5. Uncheck T3 → button becomes "加入 2 项"
6. Click submit → toast "已新增 2 项，累加 0 项"
7. Verify the order's parts table now contains T1 (qty=10) and T2 (qty=20)

- [ ] **Step 4: End-to-end manual test — accumulation semantics**

8. Re-open "+ 添加配件" → "最近导入" — T1 and T2 should now show "已在本单" badges, defaults unchecked
9. Manually check T1 (its qty input still reads 10)
10. Submit → toast "已新增 0 项，累加 1 项"
11. Verify T1's qty in the parts table is now 20 (10 + 10)

- [ ] **Step 5: End-to-end manual test — per-row edit**

12. Re-open the modal; edit T2's qty input from 20 to 15 → input goes orange
13. Tooltip on hover: should show "导入时数量：20（已修改）" (browser title attribute set by RecentImportsPicker — verify in DevTools or by hovering)
14. Submit → verify T2 in parts table is now 35 (20 + 15)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/handcraft/HandcraftDetail.vue
git commit -m "feat(handcraft): implement batch attach from 'recent imports' tab

attachRecentBatch dispatches add/update calls with a 5-way
concurrency limit. Per-row failures are reported individually
and don't block siblings. Re-checks order.status before writing
(another tab might have sent the order). Successful writes
trigger loadData() to refresh the parts table."
```

---

## Task 7: `AttachToHandcraftModal.vue` (entry B's submodal)

**Files:**
- Create: `frontend/src/components/AttachToHandcraftModal.vue`

A standalone modal opened from `BatchImageUpload`. Two radio targets (existing pending order / new order). On confirm, calls handcraft APIs the same way as entry A (add/update on existing; createHandcraft on new).

- [ ] **Step 1: Create the component**

Create `frontend/src/components/AttachToHandcraftModal.vue`:

```vue
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
import { listHandcraft, createHandcraft, addHandcraftPart, updateHandcraftPart, getHandcraftParts } from '@/api/handcraft'
import { useIsMobile } from '@/composables/useIsMobile'

const props = defineProps({
  show: Boolean,
  // Batch parts: [{ part_id, name, image, unit, imported_qty }]
  batchParts: { type: Array, default: () => [] },
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

// --- Concurrency helper (duplicated from HandcraftDetail intentionally — small enough not to extract) ---
const runWithConcurrency = async (tasks, limit = 5) => {
  const results = new Array(tasks.length)
  let i = 0
  const workers = Array.from({ length: Math.min(limit, tasks.length) }, async () => {
    while (i < tasks.length) {
      const idx = i++
      try {
        results[idx] = { ok: true, value: await tasks[idx]() }
      } catch (error) {
        results[idx] = { ok: false, error }
      }
    }
  })
  await Promise.all(workers)
  return results
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
      // Need the current items to compute add vs update.
      const { data: currentItems } = await getHandcraftParts(targetOrderId)
      const tasks = partsPayload.map((p) => async () => {
        const existing = currentItems.find((it) => it.part_id === p.part_id)
        if (existing) {
          return updateHandcraftPart(targetOrderId, existing.id, {
            qty: (Number(existing.qty) || 0) + p.qty,
            unit: p.unit,
          })
        }
        return addHandcraftPart(targetOrderId, p)
      })
      const results = await runWithConcurrency(tasks, 5)
      const failures = results.filter((r) => !r.ok)
      const okCount = results.length - failures.length
      results.forEach((r, idx) => {
        if (!r.ok) {
          const detail = r.error?.response?.data?.detail || r.error?.message || '未知错误'
          message.error(`${partsPayload[idx].part_id} 加入失败：${detail}`)
        }
      })
      if (okCount > 0) {
        message.success(`已加入 ${okCount} 项${failures.length > 0 ? `（${failures.length} 项失败）` : ''}`)
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
```

- [ ] **Step 2: Build-check**

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AttachToHandcraftModal.vue
git commit -m "feat(handcraft): add AttachToHandcraftModal (entry B submodal)

Standalone modal that BatchImageUpload opens after import. Lets
the user pick an existing pending handcraft order or create a
new one, then writes the entire batch (qty=0 items skipped) and
navigates to the order detail. Filters parts by qty>0 to avoid
the backend's HandcraftPartIn.qty: Field(gt=0) constraint.

Component is created but not yet wired up — comes online in the
next task."
```

---

## Task 8: Wire `AttachToHandcraftModal` into `BatchImageUpload`

**Files:**
- Modify: `frontend/src/components/BatchImageUpload.vue`

The split button + dropdown menu live here. The submodal renders inside this component so it stays scoped to the import flow.

- [ ] **Step 1: Add import + state**

In the `<script setup>` of `BatchImageUpload.vue`, add:

```js
import AttachToHandcraftModal from '@/components/AttachToHandcraftModal.vue'
import { NDropdown } from 'naive-ui'
import { getBatchById } from '@/utils/recentImports'
```

And state:

```js
const showAttachModal = ref(false)
const showSplitMenu = ref(false)

// Read the live batch (with up-to-date image URLs) on demand so the submodal
// gets fresh data even if the user pasted images right before clicking.
const liveBatchParts = computed(() => {
  if (!props.batchId) return []
  const batch = getBatchById(props.batchId)
  return batch?.parts ?? []
})
```

You'll need `import { computed, ref } from 'vue'` if not already present.

- [ ] **Step 2: Add the split button to the footer**

Find the existing `<template #footer>` block:

OLD:
```html
<template #footer>
  <n-space justify="end">
    <n-button type="primary" @click="$emit('update:show', false)">完成</n-button>
  </n-space>
</template>
```

NEW:
```html
<template #footer>
  <n-space justify="end">
    <n-button @click="$emit('update:show', false)">完成</n-button>
    <n-button-group v-if="triggeredBy === 'import' && batchId">
      <n-button type="primary" @click="openAttach('new')">加入手工单</n-button>
      <n-dropdown trigger="click" :options="splitMenuOptions" @select="openAttach">
        <n-button type="primary" style="padding: 0 8px;">
          <span style="font-size: 10px;">▾</span>
        </n-button>
      </n-dropdown>
    </n-button-group>
  </n-space>
</template>
```

You'll need to import `NButtonGroup` from `naive-ui`.

- [ ] **Step 3: Add menu options + handler**

In the script setup:

```js
const splitMenuOptions = [
  { label: '加入已有 pending 单', key: 'existing' },
  { label: '新建一张', key: 'new' },
]

const initialAttachTarget = ref('new')
const openAttach = (key) => {
  initialAttachTarget.value = key
  showAttachModal.value = true
}
```

- [ ] **Step 4: Render the submodal inside the component**

Just before the closing `</n-modal>` of `BatchImageUpload`'s template, add:

```html
<AttachToHandcraftModal
  v-model:show="showAttachModal"
  :batch-parts="liveBatchParts"
/>
```

(`AttachToHandcraftModal` defaults its `target` to `'new'`. The `initialAttachTarget` ref is wired in case we ever want to pass it through; the simplest version doesn't pass it, since the spec says clicking the main button = "new" and clicking ▾ = pick. The dropdown items both open the same submodal, but the user can re-toggle the radio inside if needed. If you want strictly "the radio matches the menu item picked", add an `initial-target` prop to `AttachToHandcraftModal` and forward it — small change.)

For this task, accept the simple version. If the user complains about the radio default during E2E, we add `initial-target` then.

- [ ] **Step 5: End-to-end manual test — entry B "new"**

```bash
cd frontend && npm run dev
```

1. Import a small Excel with 3 parts (1 with qty=0)
2. After the "上传图片?" dialog click "是" — BatchImageUpload opens
3. Paste an image into one part to verify image-writeback still works (Task 3 regression)
4. Click "加入手工单" (the main button)
5. Submodal opens, default radio = "新建一张"
6. Type a new supplier name (e.g. "测试手工坊")
7. Preview should show "将带入 2 项 part · 共 X 件（1 项数量为 0，已跳过）"
8. Click "确认并跳转" — page navigates to `/handcraft/HC-XXXX`
9. Verify the new order has 2 part items (the qty=0 one is missing)

- [ ] **Step 6: End-to-end manual test — entry B "existing"**

10. Go back, import another Excel (2 parts, all with qty>0). Make sure one of them shares a part_id with an existing pending order.
11. In BatchImageUpload, click the ▾ → "加入已有 pending 单"
12. Select the supplier and order — preview confirms count
13. Click "确认并跳转" → land on the order detail
14. Verify: the shared part's qty was *incremented*, the new part_id was *added*

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/BatchImageUpload.vue
git commit -m "feat(handcraft): add 'attach to handcraft' split button

BatchImageUpload now exposes a split button when launched from
the import flow (triggeredBy='import' and batchId set). The main
button defaults to 'new order'; the ▾ dropdown lets the user
pick 'existing' instead. Both open AttachToHandcraftModal,
which handles the actual write + navigate."
```

---

## Task 9: End-to-end smoke run + final cleanup

**Files:**
- None new; this is a verification task.

Run the full spec §6 manual test list and patch any gaps surfaced.

- [ ] **Step 1: Test #1 (A workflow)** — covered in Task 6 step 3-4. Re-verify if needed.

- [ ] **Step 2: Test #2 (B workflow, existing order)** — covered in Task 8 step 6.

- [ ] **Step 3: Test #3 (B workflow, new order with empty-batch guard)**

When all parts in the batch have `imported_qty=0`, the submodal's "确认并跳转" button must disable (since `effectiveParts.length === 0`). Verify by:
1. Import an Excel where all rows have 入库数量=0
2. Trigger BatchImageUpload → click "加入手工单"
3. Submodal opens; preview shows "将带入 0 项"; submit button is disabled
4. Cancel — no order created

- [ ] **Step 4: Test #7 (expiration)**

In the browser console:

```js
const list = JSON.parse(localStorage.getItem('allen_shop.recent_part_imports'))
list.forEach((b) => { b.imported_at = Date.now() - 8 * 24 * 60 * 60 * 1000 })
localStorage.setItem('allen_shop.recent_part_imports', JSON.stringify(list))
```

Reload an open `HandcraftDetail` page → "+ 添加配件" → "最近导入" tab should show the empty state ("没有最近导入的批次").

- [ ] **Step 5: Run frontend tests + build**

```bash
cd frontend && node tests/recentImports.test.mjs && npm run build
```

Both must succeed.

- [ ] **Step 6: Final commit (only if anything was patched in this task)**

If no fixes were needed during E2E, skip the commit.

```bash
git add -p   # selectively stage any tweaks made during E2E
git commit -m "chore(handcraft): batch bridge E2E polish"
```

---

## Spec coverage check

| Spec section | Covered by |
|--------------|-----------|
| §1 Storage util + lifecycle | Task 1 (full coverage incl. tests) |
| §2 Entry A modal w/ tabs, qty edit, badges, qty=0 guard | Tasks 4–6 |
| §3 Entry B split button + submodal + qty=0 skip | Tasks 7–8 |
| §4 Effective qty / add+update mapping / concurrency | Tasks 6 & 7 |
| §5 File changes | All tasks combined match the table |
| §6 Test cases 1–7 | Task 9 step list |

---

## Out of scope (per spec §7)

- Backend `import_batch` table
- Cross-batch templates
- BatchImageUpload inline crop/rename
