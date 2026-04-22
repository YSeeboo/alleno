# Mobile Responsive Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 35+ Vue pages usable on mobile devices (320px-768px) without breaking existing desktop layout.

**Architecture:** Add a `useIsMobile()` composable for JS-level breakpoint detection, plus global CSS media queries. Apply mobile adaptations progressively: layout first, then batch-fix common patterns (modals, filter bars, forms, tables), then handle complex pages individually. No component rewrites — adapt existing components with responsive props and CSS overrides.

**Tech Stack:** Vue 3 Composition API, Naive UI responsive props, CSS media queries, `window.matchMedia`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `frontend/src/composables/useIsMobile.js` | **NEW** — reactive `isMobile` ref (breakpoint 768px) |
| `frontend/src/styles/responsive.css` | **NEW** — global mobile CSS overrides |
| `frontend/src/App.vue` | Import responsive.css |
| `frontend/src/layouts/DefaultLayout.vue` | Mobile sidebar drawer + auto-collapse |
| `frontend/src/views/login/LoginPage.vue` | Responsive card width |
| `frontend/src/views/Dashboard.vue` | Responsive grid cols |
| `frontend/src/styles/global.css` | Filter bar mobile wrap |
| All list pages (9 files) | Filter bar + table responsive |
| All detail pages (10 files) | Descriptions cols, modal widths, form widths |
| All create pages (6 files) | Form input widths, grid stacking |
| Shared components (3 files) | Modal widths |
| Kanban (3 files) | Already partially done, fix modals |

---

## Task 1: Create `useIsMobile` composable

**Files:**
- Create: `frontend/src/composables/useIsMobile.js`

- [ ] **Step 1: Create the composable**

```js
// frontend/src/composables/useIsMobile.js
import { ref, onMounted, onUnmounted } from 'vue'

export function useIsMobile(breakpoint = 768) {
  const isMobile = ref(false)
  let mql

  function update(e) {
    isMobile.value = e.matches
  }

  onMounted(() => {
    mql = window.matchMedia(`(max-width: ${breakpoint}px)`)
    isMobile.value = mql.matches
    mql.addEventListener('change', update)
  })

  onUnmounted(() => {
    mql?.removeEventListener('change', update)
  })

  return { isMobile }
}
```

- [ ] **Step 2: Verify file created**

Run: `cat frontend/src/composables/useIsMobile.js`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/composables/useIsMobile.js
git commit -m "feat: add useIsMobile composable for responsive breakpoint detection"
```

---

## Task 2: Create global responsive CSS

**Files:**
- Create: `frontend/src/styles/responsive.css`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Create responsive.css with mobile overrides**

```css
/* frontend/src/styles/responsive.css */

/* ===== Global Mobile Overrides (max-width: 768px) ===== */
@media (max-width: 768px) {

  /* --- Layout --- */
  .n-layout-content {
    padding: 12px !important;
  }

  /* --- Filter bars: stack vertically --- */
  .filter-bar {
    flex-direction: column;
    align-items: stretch !important;
    gap: 8px;
  }
  .filter-bar > * {
    width: 100% !important;
  }
  .filter-bar .n-input,
  .filter-bar .n-select {
    width: 100% !important;
  }
  .filter-bar-end {
    margin-top: 4px;
  }

  /* --- Page header: tighter spacing --- */
  .page-header {
    padding: 0 0 8px 0;
  }
  .page-title {
    font-size: 18px !important;
  }

  /* --- Modals: full-width on mobile --- */
  .n-modal {
    width: 95vw !important;
    max-width: 95vw !important;
  }

  /* --- Forms: full-width inputs --- */
  .n-form-item .n-input,
  .n-form-item .n-select,
  .n-form-item .n-input-number,
  .n-form-item .n-date-picker {
    width: 100% !important;
  }

  /* --- Data tables: horizontal scroll --- */
  .n-data-table-wrapper {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  /* --- Cards: reduce padding --- */
  .n-card .n-card__content {
    padding: 12px !important;
  }

  /* --- Descriptions: force single column --- */
  .n-descriptions .n-descriptions-table-wrapper table {
    display: block;
  }

  /* --- Inline fixed-width inputs in tables/forms --- */
  .n-input-number {
    min-width: 80px;
  }

  /* --- NSpace: allow wrapping --- */
  .n-space {
    flex-wrap: wrap !important;
  }
}
```

- [ ] **Step 2: Import responsive.css in App.vue**

In `frontend/src/App.vue`, add the import after the existing global.css import:

```js
import './styles/responsive.css'
```

- [ ] **Step 3: Verify build succeeds**

Run: `cd frontend && npm run build`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles/responsive.css frontend/src/App.vue
git commit -m "feat: add global responsive CSS for mobile adaptation"
```

---

## Task 3: Mobile-adapt DefaultLayout (sidebar drawer)

**Files:**
- Modify: `frontend/src/layouts/DefaultLayout.vue`

- [ ] **Step 1: Add useIsMobile and drawer behavior**

In `<script setup>`, add:

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

Change the existing `collapsed` ref behavior — on mobile, sidebar should start collapsed and act as an overlay:

```js
// Replace or update the existing collapsed logic:
const collapsed = ref(true)

watch(isMobile, (mobile) => {
  collapsed.value = mobile
}, { immediate: true })
```

Add a `watch` import if not present, and a function to close sidebar on mobile navigation:

```js
import { ref, h, computed, watch } from 'vue'

function handleMenuUpdate(key) {
  router.push(key)
  if (isMobile.value) {
    collapsed.value = true
  }
}
```

- [ ] **Step 2: Update template for mobile sidebar overlay**

Replace the `<n-layout-sider>` block. On mobile, wrap sider in a drawer overlay; on desktop, keep current behavior:

```html
<!-- Mobile overlay backdrop -->
<div
  v-if="isMobile && !collapsed"
  class="sidebar-overlay"
  @click="collapsed = true"
/>

<n-layout-sider
  v-if="!isMobile || !collapsed"
  bordered
  collapse-mode="width"
  :collapsed="collapsed"
  :collapsed-width="isMobile ? 0 : 52"
  :width="240"
  :native-scrollbar="false"
  :style="{
    height: 'calc(100vh - 52px)',
    position: isMobile ? 'fixed' : 'static',
    top: isMobile ? '52px' : undefined,
    left: '0',
    zIndex: isMobile ? 1000 : undefined,
  }"
>
```

Update the menu's `@update:value` to use `handleMenuUpdate`:

```html
<n-menu
  :value="$route.path"
  :options="filteredMenuOptions"
  :collapsed="collapsed"
  :collapsed-width="52"
  :collapsed-icon-size="20"
  @update:value="handleMenuUpdate"
/>
```

- [ ] **Step 3: Update header for mobile**

Reduce header padding on mobile. Update the header style binding:

```html
<n-layout-header
  bordered
  :style="{
    height: '52px',
    padding: isMobile ? '0 12px' : '0 24px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    background: '#0F172A',
  }"
>
```

Hide the brand text "ALLENOP" on very small screens — keep only the icon:

```html
<span v-if="!isMobile" style="font-size:20px; font-weight:700; letter-spacing:2px; color:#fff;">ALLENOP</span>
```

- [ ] **Step 4: Reduce content padding on mobile**

Update `n-layout-content` style:

```html
<n-layout-content :style="{ padding: isMobile ? '12px' : '28px' }">
```

- [ ] **Step 5: Add sidebar-overlay CSS**

```css
.sidebar-overlay {
  position: fixed;
  top: 52px;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 999;
}
```

- [ ] **Step 6: Verify in browser at 375px width**

Run: `cd frontend && npm run dev`
Open browser devtools, toggle device toolbar to 375px width. Verify:
- Sidebar is hidden by default
- Hamburger button opens sidebar as overlay
- Clicking menu item navigates and closes sidebar
- Content area uses full width

- [ ] **Step 7: Commit**

```bash
git add frontend/src/layouts/DefaultLayout.vue
git commit -m "feat: mobile-responsive sidebar with drawer overlay"
```

---

## Task 4: Mobile-adapt LoginPage

**Files:**
- Modify: `frontend/src/views/login/LoginPage.vue`

- [ ] **Step 1: Replace fixed 360px card width with responsive width**

In `<style scoped>`, change:

```css
/* Old */
.login-card {
  width: 360px;
}

/* New */
.login-card {
  width: 360px;
  max-width: 90vw;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/login/LoginPage.vue
git commit -m "feat: responsive login card width"
```

---

## Task 5: Mobile-adapt Dashboard

**Files:**
- Modify: `frontend/src/views/Dashboard.vue`

- [ ] **Step 1: Add useIsMobile and responsive grid cols**

In `<script setup>`, add:

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

In template, change the `n-grid`:

```html
<!-- Old -->
<n-grid :cols="4" :x-gap="16" :y-gap="16">

<!-- New -->
<n-grid :cols="isMobile ? 2 : 4" :x-gap="12" :y-gap="12">
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/Dashboard.vue
git commit -m "feat: responsive dashboard grid (2 cols on mobile)"
```

---

## Task 6: Mobile-adapt InventoryOverview

**Files:**
- Modify: `frontend/src/views/InventoryOverview.vue`

- [ ] **Step 1: Add useIsMobile**

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

- [ ] **Step 2: Remove fixed widths on filter inputs**

Replace inline `style="width: 220px"` and `style="width: 140px"` on the filter bar inputs with no width (the global CSS `.filter-bar > *` will handle full-width on mobile). Keep the desktop widths by using conditional styles:

```html
<n-input
  v-model:value="keyword"
  placeholder="搜索名称/ID"
  clearable
  :style="{ width: isMobile ? '100%' : '220px' }"
/>
<n-select
  v-model:value="filterType"
  :options="typeOptions"
  clearable
  placeholder="类型"
  :style="{ width: isMobile ? '100%' : '140px' }"
/>
```

- [ ] **Step 3: Make modal responsive**

Change modal preset width:

```html
<n-modal
  v-model:show="showStockModal"
  preset="dialog"
  :style="{ width: isMobile ? '90vw' : '380px' }"
  ...
>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/InventoryOverview.vue
git commit -m "feat: responsive inventory overview (filters, modal)"
```

---

## Task 7: Mobile-adapt InventoryLog

**Files:**
- Modify: `frontend/src/views/InventoryLog.vue`

- [ ] **Step 1: Add useIsMobile and responsive filter widths**

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

Replace all fixed-width filter inputs:

```html
<n-select ... :style="{ width: isMobile ? '100%' : '100px' }" />
<n-input ... :style="{ width: isMobile ? '100%' : '160px' }" />
<n-input ... :style="{ width: isMobile ? '100%' : '140px' }" />
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/InventoryLog.vue
git commit -m "feat: responsive inventory log filters"
```

---

## Task 8: Mobile-adapt all List pages (batch)

All 9 list pages share the same pattern: filter-bar with fixed-width selects + data table. Apply the same changes to each.

**Files:**
- Modify: `frontend/src/views/orders/OrderList.vue`
- Modify: `frontend/src/views/parts/PartList.vue`
- Modify: `frontend/src/views/jewelries/JewelryList.vue`
- Modify: `frontend/src/views/plating/PlatingList.vue`
- Modify: `frontend/src/views/handcraft/HandcraftList.vue`
- Modify: `frontend/src/views/purchase-orders/PurchaseOrderList.vue`
- Modify: `frontend/src/views/plating-receipts/PlatingReceiptList.vue`
- Modify: `frontend/src/views/handcraft-receipts/HandcraftReceiptList.vue`
- Modify: `frontend/src/views/suppliers/SupplierList.vue`

- [ ] **Step 1: For each file, add useIsMobile import**

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

- [ ] **Step 2: Replace fixed-width filter inputs with responsive widths**

For every `style="width: Xpx"` on filter bar inputs/selects, replace with:

```html
:style="{ width: isMobile ? '100%' : 'Xpx' }"
```

Specific files and their fixed widths:
- **OrderList.vue**: status select `140px`
- **PartList.vue**: search input `200px`, category select `160px`
- **JewelryList.vue**: search input `200px`, status select `140px`
- **PlatingList.vue**: status select `140px`, supplier select `160px`
- **HandcraftList.vue**: status select `140px`, supplier select `160px`
- **PurchaseOrderList.vue**: vendor select `160px`
- **PlatingReceiptList.vue**: vendor select `160px`
- **HandcraftReceiptList.vue**: supplier select `160px`
- **SupplierList.vue**: search input `240px`

- [ ] **Step 3: Make modals responsive in PartList, JewelryList, UserList, SupplierList**

For every `n-modal` or modal-like element with a fixed `style="width: Xpx"`:

```html
:style="{ width: isMobile ? '95vw' : 'Xpx' }"
```

Specific modal widths to fix:
- **PartList.vue**: create/edit modal `480px`, stock modal `360px`, import modal `560px`
- **JewelryList.vue**: create/edit modal `480px`, template modal `520px`
- **UserList.vue**: create/edit modal `480px`
- **SupplierList.vue**: create/edit modal `400px`

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/orders/OrderList.vue \
  frontend/src/views/parts/PartList.vue \
  frontend/src/views/jewelries/JewelryList.vue \
  frontend/src/views/plating/PlatingList.vue \
  frontend/src/views/handcraft/HandcraftList.vue \
  frontend/src/views/purchase-orders/PurchaseOrderList.vue \
  frontend/src/views/plating-receipts/PlatingReceiptList.vue \
  frontend/src/views/handcraft-receipts/HandcraftReceiptList.vue \
  frontend/src/views/suppliers/SupplierList.vue \
  frontend/src/views/users/UserList.vue
git commit -m "feat: responsive filter bars and modals for all list pages"
```

---

## Task 9: Mobile-adapt all Create pages (batch)

All create pages share the pattern: `max-width: 800-1000px` container, fixed-width form inputs, and sometimes multi-column grids.

**Files:**
- Modify: `frontend/src/views/orders/OrderCreate.vue`
- Modify: `frontend/src/views/plating/PlatingCreate.vue`
- Modify: `frontend/src/views/handcraft/HandcraftCreate.vue`
- Modify: `frontend/src/views/purchase-orders/PurchaseOrderCreate.vue`
- Modify: `frontend/src/views/plating-receipts/PlatingReceiptCreate.vue`
- Modify: `frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue`
- Modify: `frontend/src/views/jewelry-templates/JewelryTemplateCreate.vue`

- [ ] **Step 1: For each file, add useIsMobile**

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

- [ ] **Step 2: Make form label placement responsive**

For all `n-form` with `label-placement="left"`, add conditional:

```html
<n-form :label-placement="isMobile ? 'top' : 'left'" ...>
```

This stacks labels above inputs on mobile, giving full width to inputs.

- [ ] **Step 3: Replace fixed-width form inputs with responsive widths**

For every `style="width: Xpx"` on form inputs (n-input, n-select, n-date-picker, n-input-number), replace with:

```html
:style="{ width: isMobile ? '100%' : 'Xpx' }"
```

Key files:
- **OrderCreate.vue**: customer input `300px`, date picker `300px`, item selects `220px`, qty `90px`, price `120px`, remarks `160px`
- **PlatingCreate.vue**: supplier `300px`, date `300px`, detail inputs `110px`/`90px`/`140px`
- **HandcraftCreate.vue**: supplier `300px`, date `360px`, various inputs
- **PurchaseOrderCreate.vue**: vendor `300px`, date `300px`, item inputs various
- **PlatingReceiptCreate.vue**: vendor `300px`, date `300px`, filter inputs
- **HandcraftReceiptCreate.vue**: vendor `300px`, date `300px`, filter inputs
- **JewelryTemplateCreate.vue**: name input, part selects

- [ ] **Step 4: Stack HandcraftCreate 2-column grid on mobile**

In `HandcraftCreate.vue`, change the `n-grid`:

```html
<!-- Old -->
<n-grid :cols="2" :x-gap="16">

<!-- New -->
<n-grid :cols="isMobile ? 1 : 2" :x-gap="16">
```

- [ ] **Step 5: Make item row inputs narrower on mobile**

For OrderCreate, PlatingCreate, PurchaseOrderCreate — the item detail rows have multiple inputs in a flex row. On mobile, keep them in a row but allow them to shrink:

For inline qty/price inputs that use fixed widths like `90px`, `110px`, `120px` — change to min-width instead on mobile. The simplest approach is to keep small fixed widths (they fit on 320px screens) but make the wider selects/inputs responsive:

```html
<!-- Selects in item rows: make them flexible -->
:style="{ width: isMobile ? '100%' : '220px' }"
```

For receipt create pages (PlatingReceiptCreate, HandcraftReceiptCreate), the max-width container should also adapt:

```html
:style="{ maxWidth: isMobile ? '100%' : '1000px' }"
```

- [ ] **Step 6: Verify build**

Run: `cd frontend && npm run build`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/orders/OrderCreate.vue \
  frontend/src/views/plating/PlatingCreate.vue \
  frontend/src/views/handcraft/HandcraftCreate.vue \
  frontend/src/views/purchase-orders/PurchaseOrderCreate.vue \
  frontend/src/views/plating-receipts/PlatingReceiptCreate.vue \
  frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue \
  frontend/src/views/jewelry-templates/JewelryTemplateCreate.vue
git commit -m "feat: responsive form layouts for all create pages"
```

---

## Task 10: Mobile-adapt Detail pages — Descriptions & common patterns

All detail pages use `n-descriptions :column="3"` and have fixed-width modals. Fix these common patterns first.

**Files:**
- Modify: `frontend/src/views/parts/PartDetail.vue`
- Modify: `frontend/src/views/jewelries/JewelryDetail.vue`
- Modify: `frontend/src/views/orders/OrderDetail.vue`
- Modify: `frontend/src/views/plating/PlatingDetail.vue`
- Modify: `frontend/src/views/handcraft/HandcraftDetail.vue`
- Modify: `frontend/src/views/purchase-orders/PurchaseOrderDetail.vue`
- Modify: `frontend/src/views/plating-receipts/PlatingReceiptDetail.vue`
- Modify: `frontend/src/views/handcraft-receipts/HandcraftReceiptDetail.vue`
- Modify: `frontend/src/views/jewelry-templates/JewelryTemplateDetail.vue`

- [ ] **Step 1: For each file, add useIsMobile**

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

- [ ] **Step 2: Make n-descriptions responsive in all detail pages**

For every `<n-descriptions :column="3"` or `:column="2"`, replace with:

```html
<n-descriptions :column="isMobile ? 1 : 3" ...>
```

Files with `:column="3"`: PartDetail, JewelryDetail, OrderDetail, PlatingDetail, HandcraftDetail, PurchaseOrderDetail, PlatingReceiptDetail, HandcraftReceiptDetail, JewelryTemplateDetail

- [ ] **Step 3: Make all modals responsive in detail pages**

For every modal with a fixed `style="width: Xpx"`, replace with:

```html
:style="{ width: isMobile ? '95vw' : 'Xpx' }"
```

Key modal widths:
- **OrderDetail.vue**: batch modal `620px`, supplier modal `440px`, BOM modal `720px`, jewelry info modal `520px`, cutting stats modal `600px`
- **PlatingDetail.vue**: add item modal `500px`, link modal `600px`, batch link modal `600px`, loss modal `420px`
- **HandcraftDetail.vue**: add/edit modal `500px`, link modals `600px`, cutting stats `600px`, loss modal `420px`
- **PurchaseOrderDetail.vue**: edit modal `500px`, add modal `500px`, link modal `600px`, cost diff modal
- **PlatingReceiptDetail.vue**: edit modal, add modal, loss modal
- **HandcraftReceiptDetail.vue**: edit modal, add modal, loss modal
- **JewelryDetail.vue**: template modal `520px`

- [ ] **Step 4: Make inline filter/edit inputs responsive in detail pages**

For fixed-width inputs used in detail page headers, card-extra areas, and inline editing sections — replace with responsive widths:

```html
:style="{ width: isMobile ? '100%' : 'Xpx' }"
```

- [ ] **Step 5: Fix delivery images grid on mobile**

In PlatingDetail, HandcraftDetail, PurchaseOrderDetail, PlatingReceiptDetail, HandcraftReceiptDetail — the delivery images use 88x88px cards in a flex-wrap grid. On mobile, reduce to 72x72px:

```html
:style="{ width: isMobile ? '72px' : '88px', height: isMobile ? '72px' : '88px' }"
```

- [ ] **Step 6: Fix PartDetail price history popover**

The popover has `min-width: 460px`. On mobile, remove the min-width:

```html
:style="{ minWidth: isMobile ? 'auto' : '460px' }"
```

- [ ] **Step 7: Verify build**

Run: `cd frontend && npm run build`

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/parts/PartDetail.vue \
  frontend/src/views/jewelries/JewelryDetail.vue \
  frontend/src/views/orders/OrderDetail.vue \
  frontend/src/views/plating/PlatingDetail.vue \
  frontend/src/views/handcraft/HandcraftDetail.vue \
  frontend/src/views/purchase-orders/PurchaseOrderDetail.vue \
  frontend/src/views/plating-receipts/PlatingReceiptDetail.vue \
  frontend/src/views/handcraft-receipts/HandcraftReceiptDetail.vue \
  frontend/src/views/jewelry-templates/JewelryTemplateDetail.vue
git commit -m "feat: responsive descriptions, modals, and inputs for all detail pages"
```

---

## Task 11: Mobile-adapt Kanban pages

**Files:**
- Modify: `frontend/src/views/kanban/KanbanBoard.vue`
- Modify: `frontend/src/views/kanban/VendorDetailModal.vue`
- Modify: `frontend/src/views/kanban/ReceiptModal.vue`

- [ ] **Step 1: KanbanBoard — already has media queries, just fix max-width**

The board already has responsive grid (3→2→1 cols). Remove the `max-width: 1100px` constraint on mobile:

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

```html
<div :style="{ maxWidth: isMobile ? '100%' : '1100px', margin: '0 auto' }">
```

And make the filter select responsive:

```html
<n-select ... :style="{ width: isMobile ? '100%' : '160px' }" />
```

- [ ] **Step 2: VendorDetailModal — already has max-width: 95vw, verify tables scroll**

The modal width `720px` already has `max-width: 95vw`, which is good. Add `useIsMobile` to conditionally hide less-important table columns:

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

Optionally hide the `created_at` column on mobile in the orders table:

```js
const ordersColumns = computed(() => {
  const cols = [/* ... existing columns ... */]
  if (isMobile.value) {
    return cols.filter(c => c.key !== 'created_at')
  }
  return cols
})
```

- [ ] **Step 3: ReceiptModal — form label placement**

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

```html
<n-form :label-placement="isMobile ? 'top' : 'left'" ...>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/kanban/KanbanBoard.vue \
  frontend/src/views/kanban/VendorDetailModal.vue \
  frontend/src/views/kanban/ReceiptModal.vue
git commit -m "feat: responsive kanban board and modals"
```

---

## Task 12: Mobile-adapt shared components

**Files:**
- Modify: `frontend/src/components/BatchImageUpload.vue`
- Modify: `frontend/src/components/ImageUploadModal.vue`
- Modify: `frontend/src/components/picking/PickingSimulationModal.vue`

- [ ] **Step 1: BatchImageUpload — responsive modal width**

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

Change modal width from `680px` to responsive:

```html
:style="{ width: isMobile ? '95vw' : '680px' }"
```

- [ ] **Step 2: ImageUploadModal — already has max-width: 92vw**

This modal is already mostly responsive. No changes needed unless the internal layout breaks. Verify visually.

- [ ] **Step 3: PickingSimulationModal — responsive modal**

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

Make modal width responsive and ensure table scrolls horizontally.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/BatchImageUpload.vue \
  frontend/src/components/ImageUploadModal.vue \
  frontend/src/components/picking/PickingSimulationModal.vue
git commit -m "feat: responsive shared component modals"
```

---

## Task 13: Mobile-adapt JewelryTemplateList

**Files:**
- Modify: `frontend/src/views/jewelry-templates/JewelryTemplateList.vue`

- [ ] **Step 1: Add useIsMobile (no filter bar, but table columns may need trimming)**

```js
import { useIsMobile } from '@/composables/useIsMobile'
const { isMobile } = useIsMobile()
```

On mobile, hide `created_at` column to save space:

```js
const columns = computed(() => {
  const cols = [/* existing columns */]
  if (isMobile.value) {
    return cols.filter(c => c.key !== 'created_at')
  }
  return cols
})
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/jewelry-templates/JewelryTemplateList.vue
git commit -m "feat: responsive jewelry template list"
```

---

## Task 14: Final verification and cleanup

- [ ] **Step 1: Run full build**

```bash
cd frontend && npm run build
```

- [ ] **Step 2: Visual check all pages at 375px width**

Run dev server and check each page category in browser devtools at 375px:
- Login page
- Dashboard
- All list pages (orders, parts, jewelries, plating, handcraft, purchase orders, receipts, suppliers, users, templates)
- All create pages
- All detail pages
- Kanban board
- Modals and dialogs

- [ ] **Step 3: Fix any remaining overflow issues**

If any page still has horizontal overflow at 375px, identify the offending element and add responsive width.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "fix: remaining mobile responsive adjustments"
```
