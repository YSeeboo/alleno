# 采购单整单电镀 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从采购单详情一键创建电镀单，支持同厂家当天合并

**Architecture:** 纯前端功能。采购单详情页新增"创建电镀单"按钮 → 弹窗勾选配件 → 跳转新建电镀单页面（配件预填）→ 选供应商时检查同厂家当天是否已有 pending 电镀单 → 支持合并或新建。后端 API 无需修改（已有 `listPlating` 按 supplier_name 过滤 + `addPlatingItem` 追加明细）。

**Tech Stack:** Vue 3, Naive UI, Vue Router query params, existing plating API

---

### Task 1: 采购单详情 — 添加"创建电镀单"按钮和勾选弹窗

**Files:**
- Modify: `frontend/src/views/purchase-orders/PurchaseOrderDetail.vue`

- [ ] **Step 1: 在 header-extra 中添加"创建电镀单"按钮**

在 `frontend/src/views/purchase-orders/PurchaseOrderDetail.vue` 的 `<template #header-extra>` 区域（约 line 148），在"追加配件"按钮之前添加"创建电镀单"按钮：

```vue
<n-button
  v-if="order.items?.length > 0"
  size="small"
  type="warning"
  @click="openPlatingModal"
>
  创建电镀单
</n-button>
```

完整的 `<n-space>` 应变为：

```vue
<template #header-extra>
  <n-space>
    <n-button
      v-if="order.items?.length > 0"
      size="small"
      type="warning"
      @click="openPlatingModal"
    >
      创建电镀单
    </n-button>
    <n-button
      v-if="!isPaid() && canAccessParts"
      size="small"
      type="primary"
      @click="openAddItemModal"
    >
      追加配件
    </n-button>
    <n-button
      v-if="order.items?.length > 0"
      size="small"
      @click="openBatchLinkModal"
    >
      批量关联订单
    </n-button>
  </n-space>
</template>
```

- [ ] **Step 2: 添加勾选弹窗模板**

在已有的 modal 区域（如 `<!-- Add Item Modal -->` 附近）添加新弹窗：

```vue
<!-- Plating Modal -->
<n-modal v-model:show="platingModalVisible" preset="card" title="选择电镀配件" :style="{ width: isMobile ? '95vw' : '560px' }">
  <div style="font-size: 13px; color: #999; margin-bottom: 12px;">
    来源：{{ order.id }}（{{ order.vendor_name }}）· 勾选需要电镀的配件，数量可调整
  </div>
  <n-data-table
    :columns="platingSelectColumns"
    :data="platingSelectData"
    :row-key="(row) => row.part_id"
    size="small"
    :bordered="false"
  />
  <template #footer>
    <n-space justify="end">
      <n-button @click="platingModalVisible = false">取消</n-button>
      <n-button type="primary" :disabled="platingSelectedItems.length === 0" @click="goPlatingCreate">
        新建电镀单 →
      </n-button>
    </n-space>
  </template>
</n-modal>
```

- [ ] **Step 3: 添加弹窗逻辑（script 部分）**

在 `<script setup>` 中添加以下状态和函数：

```javascript
const platingModalVisible = ref(false)
const platingSelectData = ref([])

const openPlatingModal = () => {
  platingSelectData.value = (order.value.items || []).map((item) => ({
    part_id: item.part_id,
    part_name: item.part_name,
    qty: item.qty,
    unit: item.unit || '个',
    checked: true,
  }))
  platingModalVisible.value = true
}

const platingSelectedItems = computed(() =>
  platingSelectData.value.filter((r) => r.checked)
)

const platingSelectColumns = [
  {
    title: () => h(NCheckbox, {
      checked: platingSelectData.value.length > 0 && platingSelectData.value.every((r) => r.checked),
      indeterminate: platingSelectData.value.some((r) => r.checked) && !platingSelectData.value.every((r) => r.checked),
      onUpdateChecked: (val) => platingSelectData.value.forEach((r) => r.checked = val),
    }),
    key: 'checked',
    width: 50,
    render: (row) => h(NCheckbox, {
      checked: row.checked,
      onUpdateChecked: (val) => row.checked = val,
    }),
  },
  { title: '配件编号', key: 'part_id', width: 130 },
  { title: '配件名称', key: 'part_name' },
  {
    title: '电镀数量',
    key: 'qty',
    width: 120,
    render: (row) => h(NInputNumber, {
      value: row.qty,
      min: 1,
      precision: 0,
      step: 1,
      size: 'small',
      style: 'width: 100px',
      onUpdateValue: (val) => row.qty = val,
    }),
  },
  { title: '单位', key: 'unit', width: 60 },
]

const goPlatingCreate = () => {
  const items = platingSelectedItems.value.map(({ part_id, qty, unit }) => ({
    part_id, qty, unit,
  }))
  platingModalVisible.value = false
  router.push({
    path: '/plating/create',
    query: { prefill: JSON.stringify(items) },
  })
}
```

- [ ] **Step 4: 验证弹窗效果**

Run: `cd frontend && npm run dev`

手动验证：
1. 进入采购单详情页（有配件的采购单）
2. 看到"创建电镀单"橙色按钮在"追加配件"左侧
3. 点击后弹窗显示所有配件，默认全选
4. 可勾选/取消勾选，可修改数量
5. 点击"新建电镀单 →"后跳转到 `/plating/create?prefill=...`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/purchase-orders/PurchaseOrderDetail.vue
git commit -m "feat: add '创建电镀单' button and selection modal to PurchaseOrderDetail"
```

---

### Task 2: 新建电镀单页面 — 读取预填数据

**Files:**
- Modify: `frontend/src/views/plating/PlatingCreate.vue`

- [ ] **Step 1: 添加 route 并在 onMounted 中读取 prefill 参数**

在 `frontend/src/views/plating/PlatingCreate.vue` 的 `<script setup>` 中：

1. 添加 `useRoute` 导入（在已有的 `import { useRouter } from 'vue-router'` 行修改）：

```javascript
import { useRouter, useRoute } from 'vue-router'
```

2. 在 `const router = useRouter()` 下方添加：

```javascript
const route = useRoute()
```

3. 在 `onMounted` 回调中（约 line 280），在 parts/colors/suppliers 加载完成后，添加 prefill 逻辑：

```javascript
onMounted(async () => {
  try {
    const [partsRes, colorsRes, suppliersRes] = await Promise.all([
      listParts(), getColorVariants(), listSuppliers({ type: 'plating' }),
    ])
    allParts.value = partsRes.data
    partOptions.value = partsRes.data.map((p) => ({
      label: `${p.id} ${p.name}`,
      value: p.id,
      code: p.id,
      name: p.name,
      image: p.image,
      unit: p.unit,
    }))
    colorVariants.value = colorsRes.data
    supplierOptions.value = suppliersRes.data.map((s) => ({ label: s.name, value: s.name }))

    // Prefill from purchase order
    if (route.query.prefill) {
      try {
        const prefillItems = JSON.parse(route.query.prefill)
        if (Array.isArray(prefillItems) && prefillItems.length > 0) {
          items.splice(0, items.length)
          for (const pi of prefillItems) {
            const item = createEmptyItem()
            item.part_id = pi.part_id
            item.qty = pi.qty
            item.unit = pi.unit || '个'
            items.push(item)
          }
          // Trigger color variant lookup for each prefilled item
          for (const item of items) {
            if (item.part_id) {
              const part = allParts.value.find((p) => p.id === item.part_id)
              const existingCode = getPartColorCode(part)
              toggleColor(item, existingCode || 'G')
            }
          }
        }
      } catch (_) {
        // Invalid prefill JSON, ignore
      }
    }
  } catch (_) {
    // error already shown by axios interceptor
  }
})
```

- [ ] **Step 2: 验证预填效果**

Run: `cd frontend && npm run dev`

手动验证：
1. 从采购单详情勾选配件 → 跳转到新建电镀单页面
2. 电镀明细已预填勾选的配件，数量与采购单一致
3. 每个配件的颜色变体已自动查询并默认选中
4. 用户仍可手动添加/删除/修改明细行
5. 直接访问 `/plating/create`（无 prefill 参数）仍正常显示空表单

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/plating/PlatingCreate.vue
git commit -m "feat: support prefill plating items from purchase order via query params"
```

---

### Task 3: 同厂家当天合并逻辑

**Files:**
- Modify: `frontend/src/views/plating/PlatingCreate.vue`

- [ ] **Step 1: 添加 listPlating 和 addPlatingItem 导入**

在 `frontend/src/views/plating/PlatingCreate.vue` 的导入区域，修改 plating API 导入：

```javascript
import { createPlating, listPlating, addPlatingItem } from '@/api/plating'
```

- [ ] **Step 2: 添加合并检查状态和逻辑**

在 `<script setup>` 中添加以下状态和函数：

```javascript
const mergeCandidate = ref(null) // { id, supplier_name, created_at, itemCount }
const checkingMerge = ref(false)

const checkSameDayOrder = async (supplier) => {
  if (!supplier?.trim()) {
    mergeCandidate.value = null
    return
  }
  checkingMerge.value = true
  try {
    const { data: orders } = await listPlating({ supplier_name: supplier, status: 'pending' })
    const today = new Date().toISOString().slice(0, 10)
    const match = orders.find((o) => o.created_at?.slice(0, 10) === today)
    if (match) {
      mergeCandidate.value = {
        id: match.id,
        supplier_name: match.supplier_name,
        created_at: match.created_at,
      }
    } else {
      mergeCandidate.value = null
    }
  } catch (_) {
    mergeCandidate.value = null
  } finally {
    checkingMerge.value = false
  }
}
```

- [ ] **Step 3: 在供应商选择变化时触发检查**

给模板中的供应商 `<n-select>` 添加 `@update:value` 事件处理。找到供应商 select（约 line 10-17），添加事件：

```vue
<n-select
  v-model:value="supplierName"
  :options="supplierOptions"
  filterable
  tag
  placeholder="选择或输入电镀厂名称"
  :style="{ width: isMobile ? '100%' : '300px' }"
  @update:value="checkSameDayOrder"
/>
```

- [ ] **Step 4: 添加合并提示 UI**

在供应商表单下方（`</n-form>` 之后、`<n-card title="电镀明细">` 之前）添加合并提示：

```vue
<n-alert
  v-if="mergeCandidate"
  type="warning"
  style="margin-bottom: 16px;"
  :title="`该厂家今天已有电镀单`"
>
  <div style="margin-bottom: 8px;">
    <strong>{{ mergeCandidate.supplier_name }}</strong> 今天已有电镀单
    <strong>{{ mergeCandidate.id }}</strong>（待发出）。是否将当前配件合并到该电镀单？
  </div>
  <n-space size="small">
    <n-button type="primary" size="small" :loading="merging" @click="doMerge">
      合并到 {{ mergeCandidate.id }}
    </n-button>
    <n-button size="small" @click="mergeCandidate = null">仍然新建</n-button>
  </n-space>
</n-alert>
```

需要在 Naive UI 导入中添加 `NAlert`：

```javascript
import { NSpace, NButton, NSelect, NInput, NInputNumber, NForm, NFormItem, NCard, NH2, NDatePicker, NAlert } from 'naive-ui'
```

- [ ] **Step 5: 实现合并函数**

```javascript
const merging = ref(false)

const doMerge = async () => {
  if (!mergeCandidate.value) return
  const validItems = items.filter((i) => i.part_id)
  if (validItems.length === 0) {
    message.warning('请至少有一条有效明细')
    return
  }
  merging.value = true
  try {
    const orderId = mergeCandidate.value.id
    for (const item of validItems) {
      const { _selectedColor, _variantInfo, _variantLoading, _creatingVariant, _reqSeq, ...clean } = item
      await addPlatingItem(orderId, clean)
    }
    message.success(`已合并 ${validItems.length} 项配件到 ${orderId}`)
    router.push(`/plating/${orderId}`)
  } catch (e) {
    message.error(e.response?.data?.detail || '合并失败')
  } finally {
    merging.value = false
  }
}
```

- [ ] **Step 6: 验证合并流程**

Run: `cd frontend && npm run dev`

手动验证：
1. 先创建一个 pending 状态的电镀单（供应商如"鑫达电镀"），创建日期为今天
2. 从采购单详情 → 创建电镀单 → 跳转到新建电镀单页面
3. 选择供应商"鑫达电镀"，应出现黄色提示框
4. 点击"合并到 EP-xxxx" → 配件追加到已有电镀单 → 跳转到电镀单详情
5. 点击"仍然新建" → 提示消失，正常新建
6. 选择一个今天没有电镀单的供应商 → 无提示，正常新建

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/plating/PlatingCreate.vue
git commit -m "feat: check and offer merge when same supplier has pending plating order today"
```

---

### Task 4: 端到端验证与清理

**Files:**
- Review: `frontend/src/views/purchase-orders/PurchaseOrderDetail.vue`
- Review: `frontend/src/views/plating/PlatingCreate.vue`

- [ ] **Step 1: 完整流程验证**

Run: `cd frontend && npm run dev`

完整测试路径：
1. 创建一个采购单，包含 3 个配件
2. 进入采购单详情 → 点击"创建电镀单"
3. 弹窗中取消勾选 1 个配件，修改另一个的数量
4. 点"新建电镀单 →"→ 确认预填 2 个配件，数量正确
5. 选择供应商、提交 → 创建成功，跳转到电镀单详情
6. 返回采购单详情，再次点"创建电镀单"→ 勾选剩余配件
7. 跳转新建电镀单页面，选同一个供应商 → 合并提示出现
8. 点"合并" → 配件追加成功

- [ ] **Step 2: 边界情况验证**

- 采购单无配件时：不应显示"创建电镀单"按钮（已有 `v-if="order.items?.length > 0"`）
- 弹窗中全部取消勾选：按钮应禁用（已有 `:disabled="platingSelectedItems.length === 0"`）
- 直接访问 `/plating/create` 无 prefill：应正常显示空表单
- 供应商选择后又清空：合并提示应消失

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "feat: purchase order to plating — complete flow"
```
