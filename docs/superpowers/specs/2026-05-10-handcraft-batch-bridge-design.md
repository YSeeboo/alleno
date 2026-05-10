# Handcraft Batch Bridge — Design

## 背景与问题

向新建/编辑中的手工单中"发出一批新到货的吊坠"，当前路径需要跨页且逐条挂入：

1. **导入配件**：`PartList.vue` → 上传 Excel → `importPartsExcel` 写入 N 个 part
2. **添加图片**：`BatchImageUpload` 组件中逐个粘贴图片
3. **挂入手工单**：跳到 `HandcraftDetail.vue`，"+ 添加配件" 模态一次只能选一条 part 加，重复 N 次

第 3 步在 N 较大时（一批新吊坠常 10–30 个）非常痛。痛点同时存在于两个工作流：

- 工作流 A：先有一批新吊坠 → 再挂到某张手工单
- 工作流 B：手工单已建好 → 中途发现需要的 part 不在 part 表里 → 临时 import → 回挂

## 目标

提供一座"批次桥"：把"刚通过 Excel 导入的一批 part"作为一个可被多处引用的批次，在任意一侧都能整批接通到手工单。

**非目标：**
- 不引入完整的"批次"业务实体（不入库、不参与统计、不影响审计）
- 不替代现有"+ 添加配件"单条流程，只在它旁边新增批量入口
- 不动后端：`addHandcraftPart` / `updateHandcraftPart` 已能满足"新增 + 累加"语义

## 总体架构

```
        ┌────────────────────────────┐
        │  PartList.doImport()       │
        │  importPartsExcel → results│
        └─────────────┬──────────────┘
                      │ push 一条批次
                      ▼
        ┌────────────────────────────┐
        │  localStorage              │
        │  allen_shop.recent_part_imports
        │  最近 5 个批次 / 7 天      │
        └──┬──────────────────────┬──┘
           │                      │
           │ 消费                 │ 消费
           ▼                      ▼
  ┌─────────────────┐    ┌─────────────────────┐
  │ 入口 B          │    │ 入口 A              │
  │ BatchImageUpload│    │ HandcraftDetail     │
  │ "加入手工单▾"   │    │ "+ 添加配件"        │
  │                 │    │   tab "最近导入"    │
  │ → 选已有/新建   │    │ → 多选 + 整批挂入   │
  └─────────────────┘    └─────────────────────┘
```

## §1. 数据层：批次存储

**结论：前端 localStorage，无后端改动。**

### 存储结构

```js
// localStorage key: allen_shop.recent_part_imports
[
  {
    batch_id: "imp-20260510-1422",   // 时间戳派生，仅本地用
    imported_at: 1715332920000,       // ms timestamp，用于排序与过期
    operator: "ycb",                  // 当前登录用户名（仅展示，可空）
    parts: [                          // importPartsExcel 返回 results 的子集
      // imported_qty 来自后端 PartImportRowResult.stock_added（即 Excel "入库数量" 列）
      // 这是本批次每个 part 在手工单中的"默认 qty"——不再让用户在前端填一个统一值
      { part_id: "PJ-DZ-00231", name: "玫瑰金小吊坠", image: null,         unit: "个", imported_qty: 50 },
      { part_id: "PJ-DZ-00232", name: "...",         image: "https://...", unit: "个", imported_qty: 30 },
      // ...
    ]
  },
  // ...
]
```

### 保留策略

- 最多 5 个批次，超出按 `imported_at` 升序淘汰
- 单个批次超过 7 天自动过期（读取时过滤）
- 整体存储上限保守估计 < 50 KB

### 写入时机

| 事件 | 行为 |
|------|------|
| `PartList.doImport` 成功返回 | push 一条新批次到列表头部 |
| `BatchImageUpload` 上传成功一张图 | 回写当前活动批次内对应 `parts[i].image` |
| `BatchImageUpload` 删除一张图 | 回写 `parts[i].image = null` |

### 为何不进后端

- `Part.created_at` + 时间窗查询能算"最近导入的 part"，但会把"手动单条新增"和"Excel 导入"混在一起，破坏批次语义
- 这是个"几分钟到几天的快捷桥"，不是审计意义上的批次
- 若将来要"昨天的批次还能召回 / 多设备同步"，再加 `import_batch` 表，前端组件不变

## §2. 入口 A：手工单详情侧

**仅在 `HandcraftDetail.vue` 注入。`HandcraftCreate.vue` 不加**——创建页是 BOM 驱动的"按产出展开"，强插批量挂入会破坏分组语义。

### UX

把现有 `addModalVisible` 模态改造为 tab 形式：

```
┌─ 添加配件明细 ──────────────────────────────┐
│ [单条添加]  [最近导入 12]                    │
│                                              │
│ 批次：2026-05-10 14:22 · 12 件 · ycb ▾       │ ← 下拉切换批次
│                                              │
│ 📦 数量沿用导入时的"入库数量" · 修改高亮 ·   │
│    已存在的明细将累加                         │
│                                              │
│ ☐ 全选                  已选 9 / 12          │
│ ──────────────────────────────────────────  │
│ ☑ [img] PJ-DZ-00231 玫瑰金小吊坠   [50] 个   │
│ ☑ [img] PJ-DZ-00232 银色心形吊坠   [30] 个   │
│ ☐ [img] PJ-DZ-00233 金色月亮吊坠   [20] 个 [已在本单] │ ← 默认不勾
│ ☑ [img] PJ-DZ-00234 珍珠垂坠款    [100]  个   │
│ ☑ [img] PJ-DZ-00236 复古币（无图） [12] 个   │
│ ...                                          │
│                                              │
│ 新增 9 项 · 累加 0 项 · 共 N 件   [取消] [加入 9 项] │
└──────────────────────────────────────────────┘
```

### 关键交互

- 入口可见性：保持现有规则——`+ 添加配件` 按钮仅在 `order.status === 'pending'` 显示
- 当 `recent_part_imports` 为空：tab 内显示空状态 + 引导文字"去 PartList 导入一批"
- **每行 qty 字段独立**：初始值 = `parts[i].imported_qty`，用户可逐行修改；改过的 qty 输入框橙色高亮（边框 `#f0a020`，背景 `#fffbeb`），鼠标悬停 tooltip 显示原始导入值
- "已在本单"徽章（背景 `#fef3c7`，颜色 `#92400e`）：用 `items.find(i => i.part_id === ...)` 比对；**默认不勾**，用户可手动勾选触发累加
- 当 `imported_qty === 0`（Excel 该列空白）：qty 输入框初始值 0，加入时按 0 提交会被后端拒（`HandcraftPartIn.qty: Field(gt=0)`），所以提交前前端校验：勾选项中存在 qty ≤ 0 时，禁用"加入"按钮并提示"勾选项中存在数量为 0，请填写"
- 全选时排除"已在本单"的项；指示器（checked / indeterminate / unchecked）三态联动
- 底部摘要实时显示："新增 X 项 · 累加 Y 项 · 共 Z 件"
- 关闭模态不清空批次，用户可换张单再用

### 单条添加 tab

= 现有 `addForm` 表单原封不动，作为"单条添加" tab 的内容。默认 tab 取决于：

- 若有 < 7 天批次 → 默认打开"最近导入"
- 否则 → 打开"单条添加"

## §3. 入口 B：导入器收口

`BatchImageUpload` footer 增按钮：

```
┌─ 批量上传配件图片 ───────────────────┐
│ ... 表格上传区 ...                   │
│                                       │
│            [完成]  [加入手工单 ▾]    │
└──────────────────────────────────────┘
```

### Footer 按钮

`BatchImageUpload` 右下角"完成"按钮旁加一个 **split button**：「加入手工单 ▾」。点击主按钮 = 默认走"新建一张"（高频路径）；点击 ▾ 展开下拉菜单：

- 加入已有 pending 单 → 弹子模态，单选状态停在"已有"
- 新建一张 → 弹子模态，单选状态停在"新建"

### 子模态

```
┌─ 加入到手工单 ─────────────────┐
│ ○ 加入已有 pending 单           │
│   ┌─ 选中后展开 ────────────┐   │
│   │ 商家   [金运手工 ▾]     │   │ ← listSuppliers(type=handcraft)
│   │ 手工单 [HC-0042 ▾]      │   │ ← 联动 listHandcraft(supplier=...)
│   └────────────────────────┘   │
│                                  │
│ ◉ 新建一张                       │ ← 默认选中
│   ┌─ 选中后展开 ────────────┐   │
│   │ 商家名称 [_______________]│ ← 同 HandcraftCreate 的 supplierName，filterable+tag
│   │ 备注    [_______________] │
│   └────────────────────────┘   │
│                                  │
│ 📦 将带入 12 项 part · 共 378 件 │ ← 沿用 Excel "入库数量"
│                                  │
│         [取消]  [确认并跳转]     │
└──────────────────────────────────┘
```

### 行为

- 数量与单位**完全沿用 imported_qty / unit**——子模态不提供"每项数量"字段；如果用户想逐行调，请先点"完成"关掉本组件，再用入口 A 的"最近导入" tab（那里支持逐行编辑）。这是有意的简化：B 入口追求"一键直送"，调整粒度交给 A 入口
- 顶部预览栏实时显示："将带入 N 项 · 共 X 件"。批次中 `imported_qty === 0` 的项**会被跳过**并在预览旁附小字提示（如："1 项数量为 0，已跳过"），避免后端 `qty: Field(gt=0)` 报错
- "确认并跳转"：
  - 已有单：循环 `addHandcraftPart` / `updateHandcraftPart`（详见 §4）
  - 新建：一次性 `createHandcraft({ supplier_name, parts: [...], jewelries: [] })`，把批次内所有 part（除 qty=0 的）直接作为 parts payload 传入。**不能先建空单再挂**——后端 schema 要求 `parts` 至少 1 项（`schemas/handcraft.py:38`）
- 写入完成 → `router.push('/handcraft/{id}')`
- 用户点"完成"跳过此步：批次已在 localStorage，之后能从入口 A 取回
- "加入手工单"按钮**仅在本次组件打开是 `doImport` 链式触发时显示**——通过 prop `triggered-by="import"` 区分；从 PartList 上方手动调起的"补图"场景不显示该按钮

## §4. 写入语义

每条 part 待写入的 qty 称为 `effectiveQty`：

- **入口 A**：`effectiveQty` = 用户在该行 qty 输入框中的当前值（初始值 = `imported_qty`）
- **入口 B**：`effectiveQty` = `imported_qty` 原值（B 入口不提供编辑）

| 场景 | API 调用 |
|------|---------|
| 入口 A / 入口 B「已有单」：批次内 part 不在本单 | `addHandcraftPart(orderId, { part_id, qty: effectiveQty, unit })` |
| 入口 A / 入口 B「已有单」：批次内 part 已在本单 | `updateHandcraftPart(orderId, item.id, { qty: item.qty + effectiveQty, unit })` |
| 入口 B「新建」 | `createHandcraft({ supplier_name, parts: [{part_id, qty: effectiveQty, unit}, ...], jewelries: [] })` 一次性写入；后续循环逻辑不需要 |

### 默认值

- qty：来源 = `parts[i].imported_qty`（即后端 `PartImportRowResult.stock_added`，对应 Excel "入库数量"列）
- 单位：取 `parts[i].unit || '个'`；入口 A 的每行可单独修改；入口 B 不提供修改
- `bom_qty`：留空。批量挂入的 part 不来自 BOM，与现有"+ 添加配件"单条流程一致（该流程也无 bom_qty 字段）
- `weight` / `weight_unit` / `note`：留空，用户挂入后可在主表逐行编辑

### 跳过 qty=0 的项

后端约束 `HandcraftPartIn.qty: Field(gt=0)`，所以 `effectiveQty <= 0` 的项必须在前端被过滤：

- 入口 A：在"加入"按钮按下时校验勾选项，如有 qty<=0 → 禁用按钮 + 行内红色提示"数量必须大于 0"，让用户改
- 入口 B：自动过滤，预览栏附小字"X 项数量为 0，已跳过"

### 并发与错误

- 前端 `Promise.all` 并发上限 5（用 p-limit 或简单分批）
- 任一失败：单独 `message.error("PJ-DZ-00231 加入失败：...")`，不阻塞其他
- 全部完成后总 toast：`"已新增 X 项，累加 Y 项"`（失败的 Z 项已单独提示）
- 写入完成后 `loadDetail()` 刷新 items

### 边界

- 单元测试覆盖：空批次、全部已在本单、part 已被删除（API 400）、网络中断
- 手动验证：在 `order.status` 改变（如另一标签页发出此单）时不能继续挂入——通过先 `getHandcraft(id)` 校验 status 二次确认
- 同一 part_id 在本单已有**多行**时（用户曾手动单条重复加过），累加只作用于**第一条匹配项**；用户若想分行记录，请用"单条添加" tab

## §5. 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `frontend/src/utils/recentImports.js` | 新增 | localStorage 读写、过期清理、push/update 工具函数 |
| `frontend/src/components/RecentImportsPicker.vue` | 新增 | 复用的批次挑选 UI（A 和 B 都用） |
| `frontend/src/views/parts/PartList.vue` | 改 | `doImport` 成功后写批次到 localStorage |
| `frontend/src/components/BatchImageUpload.vue` | 改 | 上传/删除图片时回写批次；新增 prop `triggered-by`；新增"加入手工单"按钮和子模态 |
| `frontend/src/views/handcraft/HandcraftDetail.vue` | 改 | "+ 添加配件" 模态改 tab；嵌入 `RecentImportsPicker`；批量挂入逻辑 |
| `frontend/src/api/handcraft.js` | 不动 | 现有 `addHandcraftPart` / `updateHandcraftPart` 足够 |
| 后端 | 不动 | — |

## §6. 测试策略

### 单元

- `utils/recentImports.js`：push、过期、淘汰、parts 图片回写
- `RecentImportsPicker.vue`：默认勾选逻辑、"已在本单"标记、空状态

### 端到端（手动）

1. **A 工作流**：先在 PartList 导入 12 个 part → 不上图直接关 → 去任意 pending 手工单 → "+ 添加配件" → "最近导入" → 全选 → 确认 → 验证 12 项已加入
2. **B 工作流**：建一张空 pending 手工单 → 去 PartList 导入 5 个 part → 上图 → BatchImageUpload 点"加入手工单" → 选这张单 → 跳转回详情验证
3. **新建工作流**：导入 → BatchImageUpload "加入手工单" → 选"新建" → 输入新商家名 → 一次性 createHandcraft 带 parts → 跳转到新单验证（注意：批次为空时此路径不可用，按钮应置灰）
4. **累加语义**：手工单已有 PJ-DZ-00231 qty=3 → 入口 A 批次内该 part `imported_qty=2` → 用户保持默认勾选并提交 → 验证该项变 5（3+2）
5. **逐行调整**：入口 A 把 PJ-DZ-00234 的 qty 从导入值 100 改成 80 → 行高亮橙色 → 提交 → 验证该项写入 80
6. **qty=0 过滤**：入口 B 批次中 PJ-DZ-00241 `imported_qty=0` → 预览栏显示"1 项数量为 0，已跳过" → 提交后该 part 不出现在新单上
7. **过期**：人为篡改 localStorage 把批次 imported_at 改到 8 天前 → 重开 modal 验证不再出现

## §7. 不在本期范围

- 后端批次表（`import_batch`）—— 当 localStorage 出现"找不回昨天批次"的真实抱怨时再做
- 跨工作流的"批次复用模板"（同一批 part 在不同手工单上有相似 qty 配置）
- BatchImageUpload 内联裁剪 / 重命名 —— 与本桥无关
