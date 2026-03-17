# Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Allen Shop frontend from warm-gold SaaS style to Plane.so-inspired cool indigo/slate SaaS style, keeping Vue 3 + Naive UI as the foundation.

**Architecture:** All changes are purely visual — no routing, API, or backend logic changes. A shared `global.css` provides `.badge`, `.page-header`, and `.icon-btn` utility classes. Naive UI's `themeOverrides` drives component-level theming. Each page gets a unified Page Header structure (breadcrumb + title + divider + filter bar).

**Tech Stack:** Vue 3, Naive UI 2.44+, Vue Router 4, Vite 7, @vicons/ionicons5

**Spec:** `docs/superpowers/specs/2026-03-17-frontend-redesign-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/styles/global.css` | **Create** | `.badge` variants, `.page-header`/`.page-breadcrumb`/`.page-title`, `.icon-btn` |
| `frontend/src/main.js` | Modify | Add `import './styles/global.css'` |
| `frontend/src/App.vue` | Modify | Replace `themeOverrides` with new palette; update `body` background |
| `frontend/src/layouts/DefaultLayout.vue` | Modify | Header 52px, brand ◈, sidebar dimensions, grouped menu |
| `frontend/src/views/Dashboard.vue` | Modify | Card colors remapped to new palette |
| `frontend/src/views/parts/PartList.vue` | Modify | Page header, filter bar, icon action buttons, status badges |
| `frontend/src/views/jewelries/JewelryList.vue` | Modify | Page header, filter bar, icon action buttons, status badges |
| `frontend/src/views/orders/OrderList.vue` | Modify | Page header, status badge, row-click navigation preserved |
| `frontend/src/views/plating/PlatingList.vue` | Modify | Page header, status badge |
| `frontend/src/views/handcraft/HandcraftList.vue` | Modify | Page header, status badge |
| `frontend/src/views/InventoryOverview.vue` | Modify | Page header, filter bar, status badge for zero-stock |
| `frontend/src/views/InventoryLog.vue` | Modify | Replace `n-h2` with `.page-title` style |
| `frontend/src/views/kanban/KanbanBoard.vue` | Modify | Swimlane colored border + count, card hover, filter → n-select |

---

## Task 1: Create shared global.css and wire into main.js

**Files:**
- Create: `frontend/src/styles/global.css`
- Modify: `frontend/src/main.js`

This is purely additive — no existing behavior changes.

- [ ] **Step 1: Create `frontend/src/styles/global.css`**

```css
/* ─── Badge ─────────────────────────────────────────── */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 9999px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.6;
  white-space: nowrap;
}

.badge-amber  { background: #FEF3C7; color: #92400E; }
.badge-indigo { background: #EEF2FF; color: #3730A3; }
.badge-green  { background: #D1FAE5; color: #065F46; }
.badge-red    { background: #FEE2E2; color: #991B1B; }
.badge-gray   { background: #F1F5F9; color: #475569; }

/* ─── Page Header ────────────────────────────────────── */
.page-header {
  margin-bottom: 20px;
}

.page-breadcrumb {
  font-size: 12px;
  color: #94A3B8;
  margin-bottom: 4px;
}

.page-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 600;
  color: #0F172A;
  letter-spacing: -0.01em;
}

.page-divider {
  height: 1px;
  background: #E2E8F0;
  margin-bottom: 16px;
}

/* ─── Filter Bar ─────────────────────────────────────── */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.filter-bar-end {
  margin-left: auto;
}

/* ─── Icon Button ────────────────────────────────────── */
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid #E2E8F0;
  background: transparent;
  color: #64748B;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  padding: 0;
}

.icon-btn:hover {
  background: #F1F5F9;
  color: #0F172A;
  border-color: #CBD5E1;
}

.icon-btn.danger:hover {
  background: #FEE2E2;
  color: #991B1B;
  border-color: #FECACA;
}
```

- [ ] **Step 2: Add CSS import to `frontend/src/main.js`**

Replace:
```js
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

createApp(App).use(createPinia()).use(router).mount('#app')
```

With:
```js
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/global.css'

createApp(App).use(createPinia()).use(router).mount('#app')
```

- [ ] **Step 3: Verify dev server starts without errors**

```bash
cd frontend && npm run dev
```

Expected: No compilation errors. Open browser — existing layout unchanged visually (no components use the new classes yet).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/styles/global.css frontend/src/main.js
git commit -m "feat: add global.css with badge, page-header, icon-btn utility classes"
```

---

## Task 2: Replace themeOverrides in App.vue

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Replace the entire `themeOverrides` constant and update body background**

The current `App.vue` has `themeOverrides` with a gold-warm palette. Replace the `<script setup>` block and `<style>` block entirely:

```vue
<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { NConfigProvider, NMessageProvider, NDialogProvider } from 'naive-ui'

const themeOverrides = {
  common: {
    primaryColor: '#6366F1',
    primaryColorHover: '#4F46E5',
    primaryColorPressed: '#4338CA',
    primaryColorSuppl: '#6366F1',
    borderRadius: '8px',
    borderRadiusMedium: '8px',
    borderRadiusSmall: '6px',
  },
  Layout: {
    color: '#F8FAFC',
    headerColor: '#0F172A',
    headerBorderColor: '#0F172A',
    siderColor: '#0F172A',
    siderBorderColor: '#1E293B',
  },
  Menu: {
    color: 'transparent',
    colorInverted: 'transparent',
    itemTextColor: '#94A3B8',
    itemTextColorActive: '#6366F1',
    itemTextColorActiveHover: '#4F46E5',
    itemTextColorHover: '#E2E8F0',
    itemTextColorChildActive: '#6366F1',
    itemIconColor: '#64748B',
    itemIconColorActive: '#6366F1',
    itemIconColorHover: '#E2E8F0',
    itemIconColorChildActive: '#6366F1',
    itemColorActive: 'rgba(99,102,241,0.12)',
    itemColorActiveHover: 'rgba(99,102,241,0.16)',
    itemColorHover: 'rgba(255,255,255,0.08)',
    dividerColor: '#1E293B',
  },
  DataTable: {
    thColor: '#F8FAFC',
    tdColorHover: '#F1F5F9',
    borderColor: '#E2E8F0',
    thTextColor: '#64748B',
    thFontWeight: '600',
  },
  Card: {
    color: '#FFFFFF',
    borderColor: '#E2E8F0',
    borderRadius: '12px',
  },
  Button: {
    borderRadius: '8px',
  },
  Input: {
    borderRadius: '8px',
  },
  Modal: {
    borderRadius: '16px',
  },
}
</script>

<style>
* { box-sizing: border-box; }
body { margin: 0; background: #F8FAFC; }
</style>
```

- [ ] **Step 2: Verify in browser**

Open app. The sidebar and header should now appear deep navy `#0F172A`. Content background should be cool `#F8FAFC`. Primary buttons should be indigo. Menu items should be muted `#94A3B8` text with indigo active state.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: replace themeOverrides with indigo/slate Plane-inspired palette"
```

---

## Task 3: Redesign DefaultLayout.vue

**Files:**
- Modify: `frontend/src/layouts/DefaultLayout.vue`

Changes: header height 52px, brand ◈ icon, sidebar 240px/52px, grouped menu, remove inline background.

- [ ] **Step 1: Replace DefaultLayout.vue entirely**

```vue
<template>
  <n-layout style="height: 100vh">
    <n-layout-header
      bordered
      style="height: 52px; padding: 0 20px; display: flex; align-items: center; justify-content: space-between;"
    >
      <div class="brand">
        <span class="brand-icon">◈</span>
        <span class="brand-name">ALLENOP</span>
      </div>
      <div class="header-actions">
        <button class="icon-btn" title="帮助">?</button>
        <button class="icon-btn" title="设置">⚙</button>
      </div>
    </n-layout-header>

    <n-layout has-sider style="height: calc(100vh - 52px)">
      <n-layout-sider
        bordered
        collapse-mode="width"
        :collapsed-width="52"
        :width="240"
        :collapsed="collapsed"
        show-trigger
        @collapse="collapsed = true"
        @expand="collapsed = false"
      >
        <n-menu
          :collapsed="collapsed"
          :collapsed-width="52"
          :collapsed-icon-size="20"
          :options="menuOptions"
          :value="activeKey"
          :indent="16"
          @update:value="handleSelect"
        />
      </n-layout-sider>

      <n-layout-content content-style="padding: 28px; overflow-y: auto;">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup>
import { ref, computed, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NLayout, NLayoutHeader, NLayoutSider, NLayoutContent, NMenu } from 'naive-ui'
import {
  HomeOutline, ExtensionPuzzleOutline, DiamondOutline, ReceiptOutline,
  ColorWandOutline, HammerOutline, ListOutline, GridOutline, CubeOutline,
} from '@vicons/ionicons5'

const router = useRouter()
const route = useRoute()
const collapsed = ref(false)

const icon = (Comp) => () => h(Comp)

const menuOptions = [
  {
    type: 'group',
    label: '工作台',
    key: 'group-workspace',
    children: [
      { label: '进度看板', key: 'kanban', icon: icon(GridOutline) },
      { label: '仪表盘',   key: 'dashboard', icon: icon(HomeOutline) },
    ],
  },
  {
    type: 'group',
    label: '商品',
    key: 'group-products',
    children: [
      { label: '配件管理', key: 'parts',     icon: icon(ExtensionPuzzleOutline) },
      { label: '饰品管理', key: 'jewelries', icon: icon(DiamondOutline) },
    ],
  },
  {
    type: 'group',
    label: '生产',
    key: 'group-production',
    children: [
      { label: '订单管理', key: 'orders',    icon: icon(ReceiptOutline) },
      { label: '电镀单',   key: 'plating',   icon: icon(ColorWandOutline) },
      { label: '手工单',   key: 'handcraft', icon: icon(HammerOutline) },
    ],
  },
  {
    type: 'group',
    label: '库存',
    key: 'group-inventory',
    children: [
      { label: '库存总表', key: 'inventory',     icon: icon(CubeOutline) },
      { label: '库存流水', key: 'inventory-log', icon: icon(ListOutline) },
    ],
  },
]

const activeKey = computed(() => {
  const seg = route.path.split('/')[1]
  return seg || 'dashboard'
})

const handleSelect = (key) => {
  router.push(key === 'dashboard' ? '/' : `/${key}`)
}
</script>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-icon {
  color: #6366F1;
  font-size: 16px;
  line-height: 1;
}

.brand-name {
  color: #F1F5F9;
  font-size: 15px;
  font-weight: 800;
  letter-spacing: 0.1em;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Override icon-btn colors for dark header context */
.header-actions .icon-btn {
  border-color: #334155;
  color: #475569;
  background: transparent;
}

.header-actions .icon-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #94A3B8;
  border-color: #475569;
}

/* Sidebar group label styling */
:deep(.n-menu .n-menu-item-group-title) {
  font-size: 10px !important;
  font-weight: 600 !important;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #475569 !important;
  padding-left: 16px !important;
}

/* Active item left border accent */
:deep(.n-menu .n-menu-item-content--selected) {
  border-left: 2px solid #6366F1;
}

:deep(.n-menu .n-menu-item-content:not(.n-menu-item-content--selected)) {
  border-left: 2px solid transparent;
}
</style>
```

- [ ] **Step 2: Verify in browser**

- Header should be 52px navy with ◈ ALLENOP brand
- Sidebar shows 4 group labels (工作台/商品/生产/库存)
- Active menu item has indigo left border + indigo text
- Collapsing sidebar collapses to 52px icon-only
- All 9 routes still navigable

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layouts/DefaultLayout.vue
git commit -m "feat: redesign layout — 52px header, grouped sidebar, indigo active accent"
```

---

## Task 4: Update Dashboard.vue card colors

**Files:**
- Modify: `frontend/src/views/Dashboard.vue`

Only the four `color` values in the `cards` array and the `.page-title` style need to change.

- [ ] **Step 1: Update card colors and page header**

In `Dashboard.vue`, replace the `cards` reactive array and the `<style>` block:

In `<script setup>`, change the `cards` array color values:
```js
const cards = reactive([
  { key: 'low-stock',      title: '低库存配件',   value: null, loading: true, route: '/parts',     color: '#F59E0B', icon: ExtensionPuzzleOutline },
  { key: 'pending-orders', title: '待生产订单',   value: null, loading: true, route: '/orders',    color: '#6366F1', icon: ReceiptOutline },
  { key: 'plating',        title: '进行中电镀单', value: null, loading: true, route: '/plating',   color: '#8B5CF6', icon: ColorWandOutline },
  { key: 'handcraft',      title: '进行中手工单', value: null, loading: true, route: '/handcraft', color: '#10B981', icon: HammerOutline },
])
```

Replace the template's `.page-header` block:
```html
<div class="page-header">
  <h2 class="page-title">仪表盘</h2>
  <div class="page-divider"></div>
</div>
```

In `<style scoped>`, remove the old `.page-title`, `.page-subtitle`, and `.page-header` rules entirely. The global `global.css` now owns `.page-title`, `.page-header`, and `.page-divider`. Only keep styles that are Dashboard-specific (`.cards-grid`, `.stat-card`, `.card-body`, etc.).

- [ ] **Step 2: Verify in browser**

Dashboard cards should show amber/indigo/violet/emerald accent bars and values. No gold color anywhere.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/Dashboard.vue
git commit -m "feat: update dashboard card colors to new indigo/amber/violet/emerald palette"
```

---

## Task 5: Redesign PartList.vue

**Files:**
- Modify: `frontend/src/views/parts/PartList.vue`

Changes: page header with breadcrumb + divider, filter bar layout, icon action buttons (detail arrow, edit pencil, more dropdown), status badge for low-stock.

- [ ] **Step 1: Replace the `<template>` block**

```html
<template>
  <div>
    <!-- Page Header -->
    <div class="page-header">
      <div class="page-breadcrumb">商品 / 配件管理</div>
      <h2 class="page-title">配件管理</h2>
      <div class="page-divider"></div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <n-input v-model:value="searchName" placeholder="搜索配件名称" clearable style="width: 200px;" @update:value="load" />
      <n-select
        v-model:value="searchCategory"
        :options="[{ label: '全部', value: '' }, ...PART_CATEGORIES.map(c => ({ label: c, value: c }))]"
        placeholder="筛选类目"
        clearable
        style="width: 160px;"
        @update:value="load"
      />
      <div class="filter-bar-end">
        <n-button type="primary" @click="openCreate">+ 新增配件</n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" size="small" />
      <n-empty v-else-if="!loading" description="暂无数据" style="margin-top: 24px;" />
    </n-spin>

    <!-- Create / Edit Modal -->
    <n-modal v-model:show="showModal" preset="card" :title="editingId ? '编辑配件' : '新增配件'" style="width: 480px;">
      <n-form ref="formRef" :model="form" label-placement="left" label-width="100">
        <n-form-item label="名称" path="name" :rule="{ required: true, message: '请输入名称' }">
          <n-input v-model:value="form.name" />
        </n-form-item>
        <n-form-item label="图片">
          <n-space vertical style="width: 100%;">
            <n-space align="center" style="width: 100%;">
              <n-input v-model:value="form.image" placeholder="上传后自动填充，也可手动输入 URL" />
              <n-button @click="showUploadModal = true">上传图片</n-button>
            </n-space>
            <n-image
              v-if="form.image"
              :src="form.image"
              alt="配件图片"
              :width="72"
              :height="72"
              object-fit="cover"
              style="border-radius: 12px; border: 1px solid #E2E8F0; overflow: hidden; display: block; cursor: zoom-in;"
            />
          </n-space>
        </n-form-item>
        <n-form-item label="类目" path="category" :rule="{ required: true, message: '请选择类目' }">
          <n-select v-model:value="form.category" :options="PART_CATEGORIES.map(c => ({ label: c, value: c }))" clearable placeholder="请选择类目" />
        </n-form-item>
        <n-form-item label="颜色"><n-input v-model:value="form.color" /></n-form-item>
        <n-form-item label="默认单位">
          <n-select v-model:value="form.default_unit" :options="PART_UNITS.map(u => ({ label: u, value: u }))" clearable placeholder="请选择默认单位" />
        </n-form-item>
        <n-form-item label="单件成本">
          <n-input-number v-model:value="form.unit_cost" :min="0" :precision="2" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="默认电镀工艺"><n-input v-model:value="form.plating_process" /></n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </n-space>
      </template>
    </n-modal>

    <ImageUploadModal
      v-model:show="showUploadModal"
      kind="part"
      :entity-id="editingId"
      @uploaded="handleImageUploaded"
    />

    <!-- Quick Stock-In Modal -->
    <n-modal v-model:show="showStockModal" preset="card" title="快速入库" style="width: 360px;">
      <n-form label-placement="left" label-width="80">
        <n-form-item label="数量">
          <n-input-number v-model:value="stockQty" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="备注">
          <n-input v-model:value="stockNote" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showStockModal = false">取消</n-button>
          <n-button type="primary" :loading="stocking" @click="doStock">入库</n-button>
        </n-space>
      </template>
    </n-modal>

    <n-modal v-model:show="showAdjustModal" preset="card" title="修正库存" style="width: 420px;">
      <n-form label-placement="left" label-width="90">
        <n-form-item label="当前库存"><n-text>{{ currentStock }}</n-text></n-form-item>
        <n-form-item label="目标库存">
          <n-input-number v-model:value="targetStockQty" :min="0" style="width: 100%;" />
        </n-form-item>
        <n-form-item label="差值"><n-text>{{ stockDiffLabel }}</n-text></n-form-item>
        <n-form-item label="原因"><n-input v-model:value="adjustReason" /></n-form-item>
        <n-form-item label="备注"><n-input v-model:value="adjustNote" /></n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showAdjustModal = false">取消</n-button>
          <n-button type="primary" :loading="adjusting" @click="doAdjustStock">确认修正</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>
```

- [ ] **Step 2: Update imports and `columns` in `<script setup>`**

Add `NDropdown` to imports. Add `useDialog`. The existing file already imports `NSpace`, `NButton`, `NInput`, `NInputNumber`, `NSelect`, `NForm`, `NFormItem`, `NModal`, `NDataTable`, `NSpin`, `NEmpty`, `NPopconfirm`, `NImage`, `NText` — keep all of these, just add `NDropdown`:

```js
import {
  NSpace, NButton, NInput, NInputNumber, NSelect, NForm, NFormItem,
  NModal, NDataTable, NSpin, NEmpty, NPopconfirm, NImage, NText, NDropdown,
} from 'naive-ui'
import { useMessage, useDialog } from 'naive-ui'
```

Add `const dialog = useDialog()` alongside the existing `const message = useMessage()` line.

Replace the `columns` array. Note: `dialog` is captured by closure in the render function, so it must be declared at the top level of `<script setup>` (not inside `columns`):

```js
const columns = [
  { title: '编号', key: 'id', width: 100 },
  {
    title: '配件',
    key: 'name',
    minWidth: 180,
    render: (row) => renderNamedImage(row.name, row.image, row.name),
  },
  { title: '类目', key: 'category' },
  { title: '颜色', key: 'color' },
  { title: '单件成本', key: 'unit_cost', width: 90, render: (r) => r.unit_cost?.toFixed(2) ?? '-' },
  {
    title: '当前库存',
    key: 'stock',
    width: 100,
    render: (r) => r.stock < 10
      ? h('span', { class: 'badge badge-red' }, `• ${r.stock}`)
      : h('span', { style: { color: '#0F172A', fontWeight: 600 } }, r.stock),
  },
  { title: '默认电镀', key: 'plating_process' },
  {
    title: '操作',
    key: 'actions',
    width: 120,
    render: (row) => {
      const moreOptions = [
        { label: '入库', key: 'stock' },
        { label: '修正库存', key: 'adjust' },
        { type: 'divider', key: 'd1' },
        { label: '删除', key: 'delete' },
      ]
      const handleMore = (key) => {
        if (key === 'stock')  openStock(row)
        if (key === 'adjust') openAdjustStock(row)
        if (key === 'delete') dialog.warning({
          title: '确认删除',
          content: `确认删除 ${row.name}？`,
          positiveText: '删除',
          negativeText: '取消',
          onPositiveClick: () => doDelete(row.id),
        })
      }
      return h(NSpace, { size: 6 }, () => [
        h('button', { class: 'icon-btn', title: '详情', onClick: () => router.push(`/parts/${row.id}`) }, '→'),
        h('button', { class: 'icon-btn', title: '编辑', onClick: () => openEdit(row) }, '✎'),
        h(NDropdown, { options: moreOptions, trigger: 'click', onSelect: handleMore },
          () => h('button', { class: 'icon-btn', title: '更多操作' }, '⋮')),
      ])
    },
  },
]
```

- [ ] **Step 3: Verify in browser**

- Page header shows "商品 / 配件管理" breadcrumb + "配件管理" title + divider
- Filter bar: search input left, "新增配件" button right
- Table rows are more compact (`size="small"`)
- Low-stock items show red badge (< 10 stock)
- Action column shows `→` `✎` `⋮` icon buttons
- `⋮` dropdown shows 入库 / 修正库存 / 删除
- Delete triggers a confirmation dialog

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/parts/PartList.vue
git commit -m "feat: redesign PartList — page header, icon actions, low-stock badge"
```

---

## Task 6: Redesign JewelryList.vue

**Files:**
- Modify: `frontend/src/views/jewelries/JewelryList.vue`

Same pattern as PartList. JewelryList has no "入库" action (only 修正库存 + 删除 in more menu). Status column uses `NSwitch` toggle — keep it, no badge needed.

- [ ] **Step 1: Replace the filter/header section in `<template>`**

Replace the opening `<div>` and `<n-space>` toolbar with:

```html
<div>
  <!-- Page Header -->
  <div class="page-header">
    <div class="page-breadcrumb">商品 / 饰品管理</div>
    <h2 class="page-title">饰品管理</h2>
    <div class="page-divider"></div>
  </div>

  <!-- Filter Bar -->
  <div class="filter-bar">
    <n-select
      v-model:value="filterStatus"
      :options="statusOptions"
      clearable
      placeholder="筛选状态"
      style="width: 140px;"
      @update:value="load"
    />
    <n-select
      v-model:value="searchCategory"
      :options="[{ label: '全部', value: '' }, ...JEWELRY_CATEGORIES.map(c => ({ label: c, value: c }))]"
      placeholder="筛选类目"
      clearable
      style="width: 160px;"
      @update:value="load"
    />
    <div class="filter-bar-end">
      <n-button type="primary" @click="openCreate">+ 新增饰品</n-button>
    </div>
  </div>
  <!-- Keep the rest of the existing template unchanged: the n-spin/n-data-table block,
       all n-modal blocks, and the ImageUploadModal component. Only the opening section
       (the outer opening <div> through the filter bar closing </div>) is replaced above.
       The outer <div> opened in this snippet is closed by the existing </div></template> at
       the bottom of the file — do NOT add an extra closing tag. -->
```

- [ ] **Step 2: Replace the `columns` operations render**

Add `NDropdown` to imports. Update the `columns` actions render:

```js
import {
  NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem,
  NModal, NDataTable, NSpin, NSwitch, NEmpty, NPopconfirm, NImage, NText, NDropdown,
} from 'naive-ui'
import { useMessage, useDialog } from 'naive-ui'
const dialog = useDialog()
```

Replace the `columns` actions entry:
```js
{
  title: '操作',
  key: 'actions',
  width: 100,
  render: (row) => {
    const moreOptions = [
      { label: '修正库存', key: 'adjust' },
      { type: 'divider', key: 'd1' },
      { label: '删除', key: 'delete' },
    ]
    const handleMore = (key) => {
      if (key === 'adjust') openAdjustStock(row)
      if (key === 'delete') dialog.warning({
        title: '确认删除',
        content: `确认删除 ${row.name}？`,
        positiveText: '删除',
        negativeText: '取消',
        onPositiveClick: () => doDelete(row.id),
      })
    }
    return h(NSpace, { size: 6 }, () => [
      h('button', { class: 'icon-btn', title: '详情', onClick: () => router.push(`/jewelries/${row.id}`) }, '→'),
      h('button', { class: 'icon-btn', title: '编辑', onClick: () => openEdit(row) }, '✎'),
      h(NDropdown, { options: moreOptions, trigger: 'click', onSelect: handleMore },
        () => h('button', { class: 'icon-btn', title: '更多' }, '⋮')),
    ])
  },
},
```

Also add `size="small"` to `n-data-table`.

- [ ] **Step 3: Verify in browser** — breadcrumb, filter bar, icon buttons all correct.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/jewelries/JewelryList.vue
git commit -m "feat: redesign JewelryList — page header, filter bar, icon actions"
```

---

## Task 7: Redesign OrderList.vue

**Files:**
- Modify: `frontend/src/views/orders/OrderList.vue`

OrderList uses row-click for navigation (no separate detail button). Status uses `NTag` → replace with `.badge`. Add page header + filter bar.

- [ ] **Step 1: Replace the full `<template>` block**

```html
<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">生产 / 订单管理</div>
      <h2 class="page-title">订单管理</h2>
      <div class="page-divider"></div>
    </div>

    <div class="filter-bar">
      <n-select
        v-model:value="filterStatus"
        :options="statusOptions"
        clearable
        placeholder="筛选状态"
        style="width: 140px;"
        @update:value="load"
      />
      <div class="filter-bar-end">
        <n-button type="primary" @click="router.push('/orders/create')">+ 新建订单</n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table
        v-if="orders.length > 0"
        :columns="columns"
        :data="orders"
        :bordered="false"
        size="small"
        :row-props="rowProps"
      />
      <n-empty v-else-if="!loading" description="暂无订单" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>
```

- [ ] **Step 2: Update imports and columns**

Remove `NTag`. Replace `columns` status render with badge:

```js
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { NSpace, NButton, NSelect, NDataTable, NSpin, NEmpty } from 'naive-ui'
import { listOrders } from '@/api/orders'
```

```js
const statusBadge = {
  '待生产': 'badge-amber',
  '生产中': 'badge-indigo',
  '已完成': 'badge-green',
}

const columns = [
  { title: '订单号', key: 'id' },
  { title: '客户名', key: 'customer_name' },
  {
    title: '状态',
    key: 'status',
    render: (r) => h('span', { class: `badge ${statusBadge[r.status] || 'badge-gray'}` }, `• ${r.status}`),
  },
  { title: '总金额', key: 'total_amount', render: (r) => r.total_amount?.toFixed(2) ?? '-' },
  { title: '创建时间', key: 'created_at', render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
]
```

- [ ] **Step 3: Verify in browser** — status shows colored badges, rows still clickable to detail.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/orders/OrderList.vue
git commit -m "feat: redesign OrderList — page header, filter bar, status badges"
```

---

## Task 8: Redesign PlatingList.vue and HandcraftList.vue

**Files:**
- Modify: `frontend/src/views/plating/PlatingList.vue`
- Modify: `frontend/src/views/handcraft/HandcraftList.vue`

Both files are nearly identical — same status values, same column structure.

- [ ] **Step 1: Update PlatingList.vue**

Replace `<template>`:

```html
<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">生产 / 电镀单</div>
      <h2 class="page-title">电镀单</h2>
      <div class="page-divider"></div>
    </div>

    <div class="filter-bar">
      <n-select v-model:value="filterStatus" :options="statusOptions" clearable placeholder="筛选状态"
        style="width: 140px;" @update:value="load" />
      <div class="filter-bar-end">
        <n-button type="primary" @click="router.push('/plating/create')">+ 新建电镀单</n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" size="small" :row-props="rowProps" />
      <n-empty v-else-if="!loading" description="暂无电镀单" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>
```

Update imports (remove `NTag`) and replace status render in `columns`:

```js
import { ref, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NSelect, NDataTable, NSpin, NEmpty } from 'naive-ui'
import { listPlating } from '@/api/plating'
```

Keep the existing `statusLabel` and `statusType` declarations — they remain in the file and are used by the new render. Only add `statusBadgeClass` and replace `columns`:

```js
// Keep existing:
// const statusType = { pending: 'default', processing: 'info', completed: 'success' }
// const statusLabel = { pending: '待发出', processing: '进行中', completed: '已完成' }

const statusBadgeClass = { pending: 'badge-amber', processing: 'badge-indigo', completed: 'badge-green' }

const columns = [
  { title: '电镀单号', key: 'id' },
  { title: '电镀厂', key: 'supplier_name' },
  {
    title: '状态',
    key: 'status',
    render: (r) => h('span', { class: `badge ${statusBadgeClass[r.status] || 'badge-gray'}` },
      `• ${statusLabel[r.status] || r.status}`),
  },
  { title: '创建时间', key: 'created_at', render: (r) => new Date(r.created_at).toLocaleString('zh-CN') },
]
```

- [ ] **Step 2: Update HandcraftList.vue**

Apply the same changes as PlatingList with these differences:
- Breadcrumb: `生产 / 手工单`
- Title: `手工单`
- Route: `/handcraft/create`
- Button label: `+ 新建手工单`
- API import: `listHandcraft` from `@/api/handcraft`
- Column title: `{ title: '手工商家', key: 'supplier_name' }` (NOT "电镀厂")
- Empty message: `暂无手工单`

The `statusLabel`, `statusBadgeClass`, and `columns` structure are identical to PlatingList.

- [ ] **Step 3: Verify both pages in browser** — badges show correct amber/indigo/green per status.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/plating/PlatingList.vue frontend/src/views/handcraft/HandcraftList.vue
git commit -m "feat: redesign PlatingList and HandcraftList — page header, status badges"
```

---

## Task 9: Redesign InventoryOverview.vue and InventoryLog.vue

**Files:**
- Modify: `frontend/src/views/InventoryOverview.vue`
- Modify: `frontend/src/views/InventoryLog.vue`

- [ ] **Step 1: Update InventoryOverview.vue template**

Replace the opening section:

```html
<template>
  <div>
    <div class="page-header">
      <div class="page-breadcrumb">库存 / 库存总表</div>
      <h2 class="page-title">库存总表</h2>
      <div class="page-divider"></div>
    </div>

    <div class="filter-bar">
      <n-select
        v-model:value="itemType"
        :options="itemTypeOptions"
        style="width: 140px;"
        placeholder="全部品类"
        clearable
      />
      <n-input
        v-model:value="searchName"
        placeholder="搜索编号或名称"
        clearable
        style="width: 220px;"
        @keydown.enter="load"
      />
      <n-switch v-model:value="inStockOnly" />
      <span style="line-height: 34px; color: #64748B; font-size: 13px;">仅看有库存</span>
      <div class="filter-bar-end">
        <n-button type="primary" :loading="loading" @click="load">查询</n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <n-data-table v-if="rows.length > 0" :columns="columns" :data="rows" :bordered="false" size="small" />
      <n-empty v-else-if="!loading" description="暂无库存数据" style="margin-top: 24px;" />
    </n-spin>
  </div>
</template>
```

Remove `NH2`, `NText`, `NSpace` from imports (all three become unused after template changes). Update `current` column render to use badge:

```js
{
  title: '当前库存',
  key: 'current',
  width: 100,
  render: (row) => row.current > 0
    ? h('span', { style: { color: '#065F46', fontWeight: 700 } }, row.current)
    : h('span', { class: 'badge badge-gray' }, '• 0'),
},
```

- [ ] **Step 2: Update InventoryLog.vue**

Replace `<n-h2>库存流水查询</n-h2>` with:

```html
<div class="page-header">
  <h2 class="page-title">库存流水查询</h2>
  <div class="page-divider"></div>
</div>
```

Remove `NH2` from imports.

- [ ] **Step 3: Verify both pages in browser**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/InventoryOverview.vue frontend/src/views/InventoryLog.vue
git commit -m "feat: redesign InventoryOverview and InventoryLog — page headers, filter bar"
```

---

## Task 10: Redesign KanbanBoard.vue

**Files:**
- Modify: `frontend/src/views/kanban/KanbanBoard.vue`

Changes: page header (no breadcrumb, filter + button on same row as title), swimlane colored left border + count badge, card hover indigo, filter type → `n-select`.

- [ ] **Step 1: Replace the `<template>` block**

```html
<template>
  <div class="kanban-page">
    <!-- Page Header with inline toolbar -->
    <div class="page-header kanban-header">
      <h2 class="page-title">进度看板</h2>
      <div class="kanban-toolbar">
        <n-select
          v-model:value="filterType"
          :options="filterOptions"
          style="width: 120px;"
          @update:value="reloadAll"
        />
        <n-button type="primary" @click="receiptVisible = true">收回</n-button>
      </div>
    </div>
    <div class="page-divider" style="margin-bottom: 28px;"></div>

    <!-- Swimlane rows -->
    <div v-for="row in kanbanRows" :key="row.status" class="kanban-section">
      <div class="section-header">
        <div class="section-title-wrap">
          <div class="section-accent" :style="{ background: row.accentColor }"></div>
          <span class="section-title">{{ row.label }}</span>
        </div>
        <span class="section-count">{{ row.cards.length }}</span>
      </div>

      <div v-if="row.cards.length > 0" class="cards-grid">
        <div
          v-for="card in row.cards"
          :key="`${card.vendor_name}-${card.order_type}`"
          class="vendor-card"
          @click="openDetail(card)"
        >
          <div class="card-header">
            <span class="supplier-name">{{ card.vendor_name }}</span>
            <span :class="`badge ${card.order_type === 'plating' ? 'badge-indigo' : 'badge-amber'}`">
              {{ card.order_type === 'plating' ? '• 电镀' : '• 手工' }}
            </span>
          </div>
          <div v-if="row.status !== 'pending_dispatch'" class="card-meta">
            {{ card.order_type === 'plating' ? '配件种类' : '待收回种类' }}：{{ card.part_count ?? '-' }} 种
          </div>
        </div>
      </div>

      <n-empty v-else-if="!row.loading" description="暂无数据" style="margin: 12px 0 20px;" />
      <div v-if="row.loading" class="row-loading"><n-spin size="small" /></div>
      <div :ref="(el) => setSentinel(el, row)" class="sentinel" />
    </div>

    <VendorDetailModal v-model:show="detailVisible" :vendor="selectedVendor" />
    <ReceiptModal v-model:show="receiptVisible" @success="reloadAll" />
  </div>
</template>
```

- [ ] **Step 2: Update `<script setup>`**

Remove `NRadioGroup`, `NRadioButton` from imports. Add `NSelect`. Add `filterOptions` and `accentColor` to `kanbanRows`:

```js
import { NButton, NSpin, NEmpty, NSelect } from 'naive-ui'
```

Keep all other existing declarations (`ref`, `reactive`, `onMounted`, `onUnmounted`, `loadMore`, `reloadAll`, `setSentinel`, `observers`, `detailVisible`, `selectedVendor`, `openDetail`, `receiptVisible`). Update only the following:

```js
const filterType = ref('all')   // keep existing declaration, value unchanged

const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '电镀', value: 'plating' },
  { label: '手工', value: 'handcraft' },
]

const kanbanRows = reactive([
  { status: 'pending_dispatch', label: '待发出', accentColor: '#F59E0B', cards: [], page: 1, hasMore: true, loading: false },
  { status: 'pending_return',   label: '待收回', accentColor: '#6366F1', cards: [], page: 1, hasMore: true, loading: false },
  { status: 'returned',         label: '已收回', accentColor: '#10B981', cards: [], page: 1, hasMore: true, loading: false },
])
```

- [ ] **Step 3: Replace `<style scoped>`**

```css
<style scoped>
.kanban-page {
  max-width: 1100px;
}

.page-header.kanban-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-header.kanban-header .page-title {
  margin: 0;
}

.kanban-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.kanban-section {
  margin-bottom: 32px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.section-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-accent {
  width: 3px;
  height: 16px;
  border-radius: 2px;
  flex-shrink: 0;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #0F172A;
  letter-spacing: 0.02em;
}

.section-count {
  font-size: 12px;
  color: #94A3B8;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

@media (max-width: 860px) { .cards-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .cards-grid { grid-template-columns: 1fr; } }

.vendor-card {
  background: #FFFFFF;
  border-radius: 10px;
  border: 1px solid #E2E8F0;
  padding: 14px 16px;
  cursor: pointer;
  min-height: 72px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  transition: border-color 0.15s, box-shadow 0.15s;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.vendor-card:hover {
  border-color: #6366F1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.supplier-name {
  font-size: 14px;
  font-weight: 600;
  color: #0F172A;
  max-width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-meta {
  font-size: 12px;
  color: #64748B;
}

.row-loading {
  display: flex;
  justify-content: center;
  padding: 12px 0;
}

.sentinel { height: 1px; }
</style>
```

- [ ] **Step 4: Verify in browser**

- "进度看板" title with filter dropdown and "收回" button on same row
- Swimlane headers show colored left accent bar (amber/indigo/green) + count
- Cards show flat 72px height with indigo hover glow
- Type badges show `badge-indigo` for 电镀, `badge-amber` for 手工

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/kanban/KanbanBoard.vue
git commit -m "feat: redesign KanbanBoard — swimlane accents, flat cards, indigo hover, select filter"
```

---

## Task 11: Final visual verification pass

- [ ] **Step 1: Check all pages load without console errors**

Navigate through every page: 进度看板, 仪表盘, 配件管理, 饰品管理, 订单管理, 电镀单, 手工单, 库存总表, 库存流水.

- [ ] **Step 2: Check sidebar collapse/expand**

Toggle sidebar collapse — all icons visible at 52px, group labels hidden.

- [ ] **Step 3: Check primary color consistency**

All primary buttons should be indigo `#6366F1`. No residual gold anywhere.

- [ ] **Step 4: Final commit**

Stage only the frontend source files changed in this redesign:

```bash
git add \
  frontend/src/styles/global.css \
  frontend/src/main.js \
  frontend/src/App.vue \
  frontend/src/layouts/DefaultLayout.vue \
  frontend/src/views/Dashboard.vue \
  frontend/src/views/parts/PartList.vue \
  frontend/src/views/jewelries/JewelryList.vue \
  frontend/src/views/orders/OrderList.vue \
  frontend/src/views/plating/PlatingList.vue \
  frontend/src/views/handcraft/HandcraftList.vue \
  frontend/src/views/kanban/KanbanBoard.vue \
  frontend/src/views/InventoryOverview.vue \
  frontend/src/views/InventoryLog.vue
git commit -m "chore: frontend redesign complete — Plane.so inspired Indigo/Slate theme"
```
