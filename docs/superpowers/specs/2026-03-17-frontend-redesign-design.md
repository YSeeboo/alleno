# Frontend Redesign — Plane.so 风格重构

**日期：** 2026-03-17
**范围：** 全面重构（视觉 + 布局 + 组件模式）
**参考：** https://plane.so/
**技术栈：** Vue 3 + Naive UI（保留）+ 深度 themeOverrides 定制

---

## 1. 色彩系统

### 核心调色板

| 角色 | Token | 颜色值 |
|------|-------|--------|
| Sidebar / Header 背景 | `color-sidebar` | `#0F172A` |
| 内容区背景 | `color-content-bg` | `#F8FAFC` |
| Surface（卡片/表格/弹窗） | `color-surface` | `#FFFFFF` |
| 主色 Primary | `color-primary` | `#6366F1` |
| 主色 Hover | `color-primary-hover` | `#4F46E5` |
| 主色 Pressed | `color-primary-pressed` | `#4338CA` |
| 文字主色 | `color-text-primary` | `#0F172A` |
| 文字次要 | `color-text-secondary` | `#64748B` |
| 文字辅助 | `color-text-muted` | `#94A3B8` |
| 边框 | `color-border` | `#E2E8F0` |
| 菜单激活背景 | `color-menu-active-bg` | `rgba(99,102,241,0.12)` |
| 菜单悬停背景 | `color-menu-hover-bg` | `rgba(255,255,255,0.05)` |

### 状态 Badge 颜色

| 状态 | 背景色 | 文字色 | 竖线色（看板） |
|------|--------|--------|----------------|
| 待发出 / 待生产 / 待处理 | `#FEF3C7` | `#92400E` | `#F59E0B` |
| 进行中 / 待收回 | `#EEF2FF` | `#3730A3` | `#6366F1` |
| 已完成 / 已收回 | `#D1FAE5` | `#065F46` | `#10B981` |
| 低库存 / 异常 | `#FEE2E2` | `#991B1B` | — |

---

## 2. 布局结构

### 顶部 Header

- **高度：** 52px（原 60px）
- **背景：** `#0F172A`，与侧边栏无缝连接，取消分隔线
- **品牌区（左）：** `◈ ALLENOP`，icon 颜色 `#6366F1`，文字 `font-weight: 800`，`letter-spacing: 0.1em`，颜色 `#F1F5F9`
- **操作区（右）：** 帮助 icon + 设置 icon，颜色 `#475569`（视觉占位，暂不实现功能）

### 左侧 Sidebar

- **展开宽度：** 240px（原 220px）
- **折叠宽度：** 52px
- **背景：** `#0F172A`
- **分组结构（4 组）：**
  - `工作台`：进度看板、仪表盘
  - `商品`：配件管理、饰品管理
  - `生产`：订单管理、电镀单、手工单
  - `库存`：库存总表、库存流水
- **分组标签样式：** `10px uppercase font-weight: 600 color: #475569`，padding 上方 16px
- **菜单项高度：** 36px
- **激活态：** 左侧 `2px solid #6366F1` 竖线 + `rgba(99,102,241,0.12)` 背景 + `#6366F1` 文字 + icon
- **悬停态：** `rgba(255,255,255,0.05)` 背景
- **折叠时：** 仅显示 icon，分组标签隐藏

### 内容区 Page Header（每页统一）

```
[面包屑：父级 / 当前页]           ← 12px, #94A3B8
[页面标题]                         ← 18px, font-weight: 600, #0F172A
──────────────────────────────────  ← 1px #E2E8F0 分隔线
[过滤栏：搜索框 + 筛选器 + 主操作按钮（右对齐）]
```

- 面包屑与标题之间间距 4px
- 分隔线下方 16px 为过滤栏
- 主操作按钮（如"新增配件"）固定在过滤栏最右侧

---

## 3. 列表页 / 表格

### 表格样式

- **行高：** 40px（Naive UI `size="small"`）
- **表头背景：** `#F8FAFC`，文字 `#64748B`，`font-weight: 600`
- **行悬停：** `#F1F5F9`
- **边框：** 仅保留水平分隔线 `#E2E8F0`，取消竖线（`bordered: false` 已有，确认保持）

### 状态显示

所有状态字段改为内联 Badge 组件：

```html
<span class="badge badge-amber">• 待发出</span>
<span class="badge badge-indigo">• 进行中</span>
<span class="badge badge-green">• 已完成</span>
```

样式：`border-radius: 9999px; padding: 2px 8px; font-size: 11px; font-weight: 500`

### 操作列

操作按钮从文字按钮改为图标按钮 + 更多下拉：

| 操作 | 实现 |
|------|------|
| 详情 | `→` icon 按钮，直接跳转 |
| 编辑 | `✎` icon 按钮，hover tooltip |
| 更多（入库、修正库存、删除） | `⋮` 下拉菜单，删除保留 popconfirm |

### 过滤栏布局

```
[🔍 搜索...]  [筛选器 ▾]  [筛选器 ▾]  ...  →→→  [+ 主操作]
```

---

## 4. 看板页

### 泳道标题

```
▌ 待发出                                      3
▌ 待收回                                      5
▌ 已收回                                     12
```

- 左侧 `3px` 彩色竖线（见状态颜色表）
- 标题 `13px font-weight: 600 color: #0F172A`
- 右侧数量 `12px #94A3B8`
- 底部分隔线改为无，靠竖线区分层级

### 供应商卡片

- **高度：** ~72px（扁平化）
- **背景：** `#FFFFFF`
- **边框：** `1px solid #E2E8F0`
- **悬停：** `border-color: #6366F1` + `box-shadow: 0 0 0 3px rgba(99,102,241,0.1)`
- **类型 Badge：** 电镀 → indigo，手工 → amber
- 卡片内布局：供应商名（14px bold）+ 类型 badge 在同一行，配件种类数量在第二行（12px `#64748B`）

### 顶部工具栏

- 筛选从 radio-button 组改为 `n-select` 下拉（节省空间）
- "收回"按钮保持 primary 样式

---

## 5. 实现范围

以下文件需要修改：

| 文件 | 改动类型 |
|------|----------|
| `frontend/src/App.vue` | 全量替换 `themeOverrides`（新调色板） |
| `frontend/src/layouts/DefaultLayout.vue` | Header 高度/品牌区；Sidebar 分组标签；菜单配置 |
| `frontend/src/views/Dashboard.vue` | 卡片配色换靛紫系 |
| `frontend/src/views/parts/PartList.vue` | 操作列改图标按钮；状态 badge；过滤栏 |
| `frontend/src/views/jewelries/JewelryList.vue` | 同上 |
| `frontend/src/views/orders/OrderList.vue` | 状态 badge；操作列 |
| `frontend/src/views/plating/PlatingList.vue` | 状态 badge；操作列 |
| `frontend/src/views/handcraft/HandcraftList.vue` | 状态 badge；操作列 |
| `frontend/src/views/kanban/KanbanBoard.vue` | 泳道标题；卡片悬停；工具栏 |
| `frontend/src/views/InventoryOverview.vue` | 状态 badge；过滤栏 |
| 所有页面 `<style>` | `.page-title`、`.page-header` 统一为新 page header 结构 |

新增共享样式（方式 A：`App.vue` 全局 `<style>`；方式 B：新建 `src/styles/global.css`）：
- `.badge` 及各状态变体
- `.page-header` / `.page-title` / `.page-breadcrumb` 统一类
- `.icon-btn` 图标按钮基础样式

---

## 6. 不在范围内

- 路由结构、API 层不变
- 详情页（PartDetail、PlatingDetail 等）本次不改，保持现状
- 后端无任何改动
- 不引入新依赖
