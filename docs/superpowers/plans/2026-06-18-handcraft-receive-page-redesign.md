# 手工回收页重构（B2 前端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 按 mockup 重构「新建手工回收单」页（`HandcraftReceiptCreate.vue`）：头部双列、去配件/产出 tab（主表只留待回收饰品）、配件回收改弹窗（纯退料无单价）、待回收列表固定高度、底部常驻操作栏、手工单独立成列点开弹窗、回执码查询、配件不足提示；并做移动端适配。

**Architecture:** 单页改造为主，配合 B1 已就绪的后端契约。无新增后端。后端契约（B1，已在 `main`）：
- `GET /handcraft/items/pending-receive?receipt_code=XXXXX` → 仅该回执单的待回收项（`listHandcraftPendingReceiveItems({receipt_code})` 已透传 params）。
- 回执响应含 `parts_shortfall: [{part_id, part_name, shortfall_qty}]`（产出项 BOM 配件不足）。
- 配件回收为纯退料：回执 part 行**不再带价格**（前端配件弹窗不放单价输入）。

**Tech Stack:** Vue 3 + Naive UI + Pinia。**前端无单元测试框架**（`frontend/package.json` 无 test 脚本）——每个任务以 `cd frontend && npm run build` 通过 + 人工核验为准。

---

## 关键既有事实（实现者须知）

- **目标文件**：`frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue`（当前 ~543 行）。**先完整读一遍**再改。
- **视觉规范 = 已提交的 mockup**：`docs/superpowers/mockups/handcraft-receipt-mockup.html`。它含 4 个画面（桌面主页 / 桌面回执码查询 / 桌面手工单弹窗 / 桌面配件回收弹窗 + 手机主页 + 手机配件 sheet），主题色已是应用的靛紫 `#6366F1`。布局/间距/类名以 mockup 为准；本计划负责数据/逻辑/接线。
- **API 客户端**（均已存在，无需新增）：
  - `import { listHandcraftPendingReceiveItems, createHandcraftReceipt } from '@/api/handcraftReceipts'`
  - `import { getHandcraftSuppliers, getHandcraftByReceiptCode, getHandcraft, getHandcraftParts, getHandcraftJewelries } from '@/api/handcraft'`
  - `listHandcraftPendingReceiveItems(params)` 透传 `{ supplier_name, keyword, date_on, receipt_code }`。
  - 待回收项每行字段：`id`(part_item 或 jewelry_item 的 id)、`handcraft_order_id`、`supplier_name`、`item_id`、`item_name`、`item_image`、`item_type`('part'|'jewelry')、`is_output`(bool)、`is_composite`、`color`、`qty`、`received_qty`、`unit`、`created_at`。**配件行 `is_output=false`；产出行 `is_output=true`**。
- **当前页的提交已支持 parts+jewelry 合并为一张回执**：`submit()` 把 `partCheckedKeys + jewelryCheckedKeys` 合成一个 `items` 数组、单次 `createHandcraftReceipt`。B2 沿用"一张单含产出+配件退料"，但配件改由弹窗选择、且不带价格。
- **rowKey 约定**（沿用当前页）：`${row.is_output ? 'output' : row.item_type}_${row.id}`；提交时 `is_output` → `handcraft_jewelry_item_id`，否则 `handcraft_part_item_id`。
- **现有 cost-diff 弹窗**（手工费成本变动确认）必须保留，提交成功后照常处理（`handleCostDiffs`）。
- **fmtMoney / fmtPrice / parseNum / renderNamedImage** 来自 `@/utils/ui`；`useIsMobile` 来自 `@/composables/useIsMobile`（当前页已用）。

## File Structure

- **Modify** `frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue` — 页面主体（头部、主表、操作栏、提交、回执码、shortfall、移动端）。
- **Create** `frontend/src/views/handcraft-receipts/PartReturnModal.vue` — 配件回收弹窗（桌面 dialog / 手机 sheet）。
- **Create** `frontend/src/components/HandcraftOrderPeekModal.vue` — 手工单只读详情弹窗（点「手工单」列打开）。

> 拆出两个子组件让主页面聚焦、各组件单一职责；与既有组件目录风格一致（`frontend/src/components/*Modal.vue`）。

---

### Task 1: 头部双列布局 + 回执码查询

**File:** `frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue`

参考 mockup「桌面 · 主页面」头部与「桌面 · 回执编码查询」画面。

- [ ] **Step 1: 头部表单改双列**

把当前 `<n-form>` 头部（手工商家 / 备注 / 创建时间，单列）改为两行双列布局（桌面 `grid-template-columns: 1fr 1fr`，移动端单列）：第一行「手工商家 | 回执编码」，第二行「创建时间 | 备注」。商家用既有 `<n-select filterable tag>`；新增回执编码 `<n-input>`（主色描边，placeholder「扫码或输入 5 位编码」，下方 hint「填入后仅展示该单待回收项；也可只填编码查询」）。用 `useIsMobile` 切换列数（桌面 grid 双列，移动端纵向堆叠），样式对照 mockup 的 `.hgrid` / `.receipt-inp` / `.hint`。

- [ ] **Step 2: 回执码查询逻辑**

新增 state：
```javascript
const receiptCode = ref('')
const scopeCode = ref(null)      // 已生效的回执码过滤；null = 商家模式
const supplierLocked = ref(false) // 回执码模式下锁定商家
```
新增方法（输入框 `@keyup.enter` 或失焦触发）：
```javascript
const applyReceiptCode = async () => {
  const code = receiptCode.value.trim().toUpperCase()
  if (!code) { return }
  if (code.length !== 5) { message.warning('请输入 5 位回执编号'); return }
  try {
    const { data: order } = await getHandcraftByReceiptCode(code)
    supplierName.value = order.supplier_name
    supplierLocked.value = true
    scopeCode.value = code
    partCheckedKeys.value = []
    jewelryCheckedKeys.value = []
    await fetchPendingItems()
  } catch (_) {
    message.error(`无此回执编号：${code}`)
  }
}
const clearReceiptScope = async () => {
  scopeCode.value = null
  supplierLocked.value = false
  receiptCode.value = ''
  await fetchPendingItems()
}
```
在 `fetchPendingItems` 的 params 里带上 scope：
```javascript
const params = { supplier_name: supplierName.value }
if (scopeCode.value) params.receipt_code = scopeCode.value
if (filterKeyword.value) params.keyword = filterKeyword.value
if (filterDateOn.value) params.date_on = ...
```
商家 `<n-select>` 在 `supplierLocked.value` 为 true 时 `disabled`。回执码生效时，在「待回收饰品」卡片上方显示蓝色 scope 条「仅显示回执单 {{scopeCode}} 的待回收项 ✕清除」（对照 mockup `.scope-banner`，点 ✕ 调 `clearReceiptScope`）。

导入：`import { getHandcraftByReceiptCode } from '@/api/handcraft'`（与既有 `getHandcraftSuppliers` 同处）。

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功，无未定义引用/模板错误。

- [ ] **Step 4: 人工核验**（`python main.py` + `npm run dev`）

- 头部双列（桌面）/ 堆叠（窄屏）。
- 选商家 → 列表按商家加载（原行为）。
- 输入有效回执码回车 → 商家自动带出并锁定、列表仅该单、出现 scope 条；点 ✕清除 → 回到商家模式、商家解锁。
- 无效回执码 → 「无此回执编号」提示。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue
git commit -m "feat(handcraft-ui): 2-col header + receipt-code scoped query on receive page"
```

---

### Task 2: 去 tab，主表只留待回收饰品 + 固定高度 + 手工单列

**File:** `HandcraftReceiptCreate.vue`

参考 mockup「桌面 · 主页面」的待回收饰品表。

- [ ] **Step 1: 移除 tab，主表数据源改为仅产出项**

删除 `activeTab` 的 `<n-radio-group>`（配件/产出 tab）。主表只渲染产出项：把绑定数据从 `currentPendingItems` 改为 `pendingJewelryItems`（即 `is_output=true` 的行），列用 `jewelryPendingColumns`。卡片标题改为「待回收饰品」，副标题「该商家制作中的产出项」。配件行（`pendingPartItems`）不再在主表显示——它们移到 Task 3 的弹窗。`fetchPendingItems` 仍按 `is_output` 分流到 `pendingPartItems` / `pendingJewelryItems`（当前已如此），保留。

- [ ] **Step 2: 列表固定高度可滚动**

把主表 `<n-data-table>` 外层包一个固定高度滚动容器（对照 mockup `.list-wrap`/`.list-scroll`，桌面 `max-height: 280px; overflow-y:auto`；或用 `<n-data-table :max-height="280" />` 的内建滚动）。确保提交栏不被行数顶下去（Task 4 的 sticky 操作栏配合）。

- [ ] **Step 3: 加「手工单」列（金额之后、最后一列）**

在 `jewelryPendingColumns` 末尾（单价/金额列之后）追加一列：
```javascript
{
  title: '手工单',
  key: 'handcraft_order_id',
  width: 110,
  render: (row) => h('span', {
    style: 'color:#6366F1; font-weight:600; cursor:pointer; border-bottom:1px dashed #c7cbf5;',
    onClick: () => openOrderPeek(row.handcraft_order_id),
  }, [row.handcraft_order_id, ' 🗗']),
},
```
（`openOrderPeek` 在 Task 5 实现；本任务可先定义为 `const openOrderPeek = () => {}` 占位，Task 5 填充——但提交前确保 build 通过。）若产出项行内此前在别处显示了 handcraft_order_id，保持产出项名称单元只显 `item_id`（SP-xxxx），手工单号只在新列出现。

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build` — 成功。

- [ ] **Step 5: 人工核验**：主表只剩产出项、标题「待回收饰品」、表头有「手工单」列且为主色可点链接、列表区超出时内部滚动。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue
git commit -m "feat(handcraft-ui): remove tabs, jewelry-only fixed-height table + 手工单 column"
```

---

### Task 3: 配件回收弹窗（纯退料，无单价）+ 常驻回执条

**Files:**
- Create: `frontend/src/views/handcraft-receipts/PartReturnModal.vue`
- Modify: `HandcraftReceiptCreate.vue`

参考 mockup「桌面 · 配件回收弹窗」与「手机 · 配件回收 sheet」。

- [ ] **Step 1: 新建 PartReturnModal.vue**

Props：`show`(bool), `parts`(array, 即 `pendingPartItems`), `selections`(object, `{partItemId: qty}`), `isMobile`(bool)。Emits：`update:show`、`confirm`(payload: `{partItemId: qty}`)、`cancel`。

内容（对照 mockup）：
- 标题「配件回收」+ 副标题「该商家发出的配件余料，勾选并填写回收数量」。
- 名称/编号筛选 `<n-input>`（前端本地过滤 `parts`，按 `item_name`/`item_id` 包含）。
- 每个配件行：复选框 + 缩略图（`renderNamedImage` 或 `<n-image>` 支持点击放大，`item_image`）+ 名称/编号/颜色 + 「剩余 = qty - received_qty」+ 回收数量 `<n-input-number :min="0.0001" :max="qty-received_qty" :precision="4">`。**无单价输入**。
- 内部维护 `localSel`（进入时由 `selections` 初始化），勾选切换 + 数量输入更新 `localSel`。
- footer：「已选 N 项」+ 取消（emit cancel，关闭不改）+ 确定（emit confirm(localSel)，关闭）。
- 桌面用 `<n-modal preset="card">`；移动端（`isMobile`）用底部 sheet 样式（对照 mockup `.sheet`）。

- [ ] **Step 2: 主页面接入弹窗 + 常驻回执条**

在 `HandcraftReceiptCreate.vue`：
```javascript
import PartReturnModal from './PartReturnModal.vue'
const partModalShow = ref(false)
const partReturnSel = reactive({})   // {partItemId: qty}
const partReturnCount = computed(() => Object.keys(partReturnSel).length)
const onPartConfirm = (sel) => {
  // 用新选择整体替换
  Object.keys(partReturnSel).forEach(k => delete partReturnSel[k])
  Object.entries(sel).forEach(([k, v]) => { if (v > 0) partReturnSel[k] = v })
  partModalShow.value = false
}
```
- 在「待回收饰品」卡片右上角放「＋ 配件回收」按钮（带角标 `partReturnCount`），点击 `partModalShow = true`。
- 卡片标题下方放**常驻回执条**（对照 mockup `.parts-recap`）：显示「配件回收 · N 项：<名称 ×数量, …>」+「编辑」（点开弹窗）。N=0 时显示占位「未选配件退料」。名称由 `pendingPartItems` 按 id 查。
- `<part-return-modal :show="partModalShow" :parts="pendingPartItems" :selections="partReturnSel" :is-mobile="isMobile" @confirm="onPartConfirm" @cancel="partModalShow=false" @update:show="partModalShow=$event" />`

- [ ] **Step 3: 构建验证** `cd frontend && npm run build` — 成功。

- [ ] **Step 4: 人工核验**：按钮打开弹窗；弹窗列出该商家配件余料、可筛选、可勾选填数量、无单价；确定后回执条常驻显示已选；编辑可改；取消不改。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/handcraft-receipts/PartReturnModal.vue frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue
git commit -m "feat(handcraft-ui): part-return modal (surplus only, no price) + persistent recap"
```

---

### Task 4: 底部常驻操作栏 + 提交（含 parts_shortfall 提示）

**File:** `HandcraftReceiptCreate.vue`

参考 mockup `.actionbar`（桌面）/ `.m-action`（手机）。

- [ ] **Step 1: 操作栏 UI**

把「总金额」「付款状态」「提交」整合进一个 sticky 底部条（桌面 `position: sticky; bottom:0`；移动端固定视口底部含 `env(safe-area-inset-bottom)`）。总金额用大号主色数字；付款状态用 segmented（未付款/已付款）；提交用主色实心大按钮（对照 mockup `.submit`/`.m-submit`）。

`totalAmount` 计算只累加**产出项**（jewelry）的 `qty×price`（配件退料无价格，不计入）：
```javascript
const totalAmount = computed(() => {
  let sum = 0
  for (const key of jewelryCheckedKeys.value) {
    const input = itemInputs[key]
    if (input) sum += (input.qty || 0) * (input.price || 0)
  }
  return fmtMoney(sum)
})
```

- [ ] **Step 2: 提交组装（产出项 + 配件退料合并为一张回执）**

重写 `submit()`：
```javascript
const submit = async () => {
  if (!supplierName.value?.trim()) { message.warning('请输入商家名称'); return }
  const items = []
  // 产出项（勾选的待回收饰品）
  for (const key of jewelryCheckedKeys.value) {
    const id = parseInt(key.split('_')[1], 10)
    const pending = pendingJewelryItems.value.find(p => p.id === id)
    if (!pending) continue
    const input = itemInputs[key]
    if (!input?.qty || input.qty <= 0) { message.warning(`请填写「${pending.item_name}」的回收数量`); return }
    items.push({
      handcraft_jewelry_item_id: pending.id,
      qty: input.qty,
      weight: input.weight != null ? input.weight : null,
      weight_unit: input.weight != null ? (input.weight_unit || 'g') : null,
      price: input.price != null ? input.price : null,
      unit: input.unit || '个',
    })
  }
  // 配件退料（弹窗选择，无价格）
  for (const [pidStr, qty] of Object.entries(partReturnSel)) {
    if (!qty || qty <= 0) continue
    const pending = pendingPartItems.value.find(p => String(p.id) === String(pidStr))
    items.push({
      handcraft_part_item_id: parseInt(pidStr, 10),
      qty,
      unit: pending?.unit || '个',
    })
  }
  if (items.length === 0) { message.warning('请至少选择一项待回收饰品或配件退料'); return }

  submitting.value = true
  try {
    const payload = { supplier_name: supplierName.value.trim(), items, status: status.value, note: note.value }
    const createdAt = tsToDateStr(createdAtTs.value)
    if (createdAt) payload.created_at = createdAt
    const { data } = await createHandcraftReceipt(payload)
    // #3：配件不足提示
    if (Array.isArray(data.parts_shortfall) && data.parts_shortfall.length) {
      const lines = data.parts_shortfall.map(s => `${s.part_name}：缺 ${s.shortfall_qty}`).join('；')
      message.warning(`部分产出项所需配件不足：${lines}`, { duration: 8000 })
    }
    message.success('创建成功')
    handleCostDiffs(data)   // 既有成本变动确认流程
  } finally {
    submitting.value = false
  }
}
```

- [ ] **Step 3: 构建验证** — 成功。

- [ ] **Step 4: 人工核验**：操作栏常驻底部不被列表顶走；总金额只随产出项单价×数量变化；提交把产出项+配件退料一并建单；配件不足时出现黄色提示；cost-diff 弹窗仍正常。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue
git commit -m "feat(handcraft-ui): sticky action bar + combined submit + parts-shortfall warning"
```

---

### Task 5: 手工单只读详情弹窗

**Files:**
- Create: `frontend/src/components/HandcraftOrderPeekModal.vue`
- Modify: `HandcraftReceiptCreate.vue`（填充 `openOrderPeek`）

参考 mockup「桌面 · 手工单详情弹窗」。

- [ ] **Step 1: 新建 HandcraftOrderPeekModal.vue**

Props：`show`(bool), `orderId`(string|null)。Emits：`update:show`。
`watch(orderId)`：非空时并发拉取 `getHandcraft(orderId)`（订单基本信息：id、receipt_code、supplier_name、status、created_at）、`getHandcraftParts(orderId)`、`getHandcraftJewelries(orderId)`，存本地 ref，`loading` 控制。
渲染（`<n-modal preset="card" title="手工单 {{orderId}}">`）：
- 顶部：回执码 / 商家 / 状态 pill（制作中/已完成等）/ 创建时间。
- 「产出项」列表（jewelries：名称 + 饰品/组合标签 + 已收回/总数）。
- 「发出配件」列表（parts：名称 + 数量）。
- footer：关闭（emit update:show false）+「打开完整手工单 ↗」（`router.push('/handcraft/' + orderId)`）。
纯只读，不带任何编辑。

- [ ] **Step 2: 主页面接入**

```javascript
import HandcraftOrderPeekModal from '@/components/HandcraftOrderPeekModal.vue'
const peekShow = ref(false)
const peekOrderId = ref(null)
const openOrderPeek = (orderId) => { peekOrderId.value = orderId; peekShow.value = true }
```
模板加 `<handcraft-order-peek-modal :show="peekShow" :order-id="peekOrderId" @update:show="peekShow=$event" />`。（替换 Task 2 里的 `openOrderPeek` 占位。）

- [ ] **Step 3: 构建验证** — 成功。

- [ ] **Step 4: 人工核验**：点主表「手工单」列的 `HC-xxxx 🗗` → 弹出只读详情（基本信息 + 产出项 + 发出配件）；「打开完整手工单」跳转 `/handcraft/:id`；关闭正常。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/HandcraftOrderPeekModal.vue frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue
git commit -m "feat(handcraft-ui): read-only handcraft-order peek modal from 手工单 column"
```

---

### Task 6: 移动端适配

**Files:** `HandcraftReceiptCreate.vue`、`PartReturnModal.vue`

参考 mockup「手机 · 主页面」与「手机 · 配件回收 sheet」。

- [ ] **Step 1: 主页面移动端**

用 `useIsMobile` 的 `isMobile`：
- 头部双列在移动端堆叠为单列（Task 1 已用 grid，移动端改 `grid-template-columns: 1fr`）。
- 主表在移动端从 `<n-data-table>` 切换为卡片列表（每个产出项一张卡：缩略图 + 名称/编号 + 「手工单」内联可点 + 勾选；勾选后展开「本次回收 / 单价 / 金额」输入行）。对照 mockup `.m-card`。
- 操作栏移动端固定视口底部（含安全区）：总金额 + segmented 一行，提交整宽按钮一行。

- [ ] **Step 2: 配件弹窗移动端**

`PartReturnModal` 在 `isMobile` 时用底部 sheet（`.sheet`/`.sheet-card`），行用卡片样式、回收数量整宽输入；footer 取消/确定整宽。

- [ ] **Step 3: 构建验证** — 成功。

- [ ] **Step 4: 人工核验**（窄视口 / 设备模拟）：头部堆叠；产出项卡片可勾选填数；操作栏固定底部不遮挡；配件回收以底部 sheet 弹出。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/handcraft-receipts/HandcraftReceiptCreate.vue frontend/src/views/handcraft-receipts/PartReturnModal.vue
git commit -m "feat(handcraft-ui): mobile layout for receive page + part-return sheet"
```

---

### Task 7: 整页构建 + 回归核验

- [ ] **Step 1: 整页构建**

Run: `cd frontend && npm run build`
Expected: 构建成功，无错误。

- [ ] **Step 2: 端到端人工核验清单**

- 商家模式：选商家 → 产出项列表 + 配件回收弹窗都按商家加载。
- 回执码模式：输入码 → 仅该单产出项 + 该单配件；scope 条 + 清除。
- 提交一张含「产出项 + 配件退料」的回收单成功；配件不足出现提示；cost-diff 弹窗正常；跳转回执详情。
- 手工单弹窗只读正常。
- 桌面/移动端两套布局均可用。

---

## Self-Review

**1. Spec coverage（对照问题 1/2 + A方案的前端面）：**
- 头部双列（商家/回执码/创建时间/备注）→ Task 1 ✅
- 回执码输入仅展示该单 + 只填码查询 → Task 1（`scopeCode` + `receipt_code` param + scope 条）✅
- 去 tab、主表只留待回收饰品、固定高度 → Task 2 ✅
- 配件回收改弹窗（图片+放大、名称/编号筛选、勾选填量、无单价、确定/取消）+ 回执条常驻 → Task 3 ✅
- 总金额/付款/提交更突出 + 底部常驻 → Task 4 ✅
- 配件不足提示（B1 的 parts_shortfall）→ Task 4 ✅
- 手工单独立成列、金额之后、点开弹窗（只读）→ Task 2（列）+ Task 5（弹窗）✅
- A方案：配件回收无单价 → Task 3（弹窗无 price 输入）+ Task 4（提交 part 行不带 price）✅
- 移动端非照搬 → Task 6 ✅

**2. Placeholder scan：** 逻辑/状态/API/提交组装均给出完整代码；模板/CSS 以已提交 mockup 为准（明确引用文件 + 类名）。`openOrderPeek` 在 Task 2 占位、Task 5 填充，已注明并要求 build 通过。

**3. Type/契约一致：**
- `partReturnSel` 形状 `{partItemId: qty}` 在 Task 3（onPartConfirm）与 Task 4（提交组装）一致。
- 提交 items：产出项用 `handcraft_jewelry_item_id`、配件退料用 `handcraft_part_item_id`（无 price）——与 B1 后端 `_resolve_order_item` 接受的字段一致。
- `parts_shortfall` 读取 `{part_name, shortfall_qty}` 与 B1 响应字段一致。
- 子组件 props/emits（PartReturnModal、HandcraftOrderPeekModal）在创建任务与接入任务命名一致。

**4. 依赖顺序：** Task 1→2→3→4 顺序推进；Task 5 填充 Task 2 的占位；Task 6 依赖 1-5 的结构；Task 7 收尾。建议按序执行。
