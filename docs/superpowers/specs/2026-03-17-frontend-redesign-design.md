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
| 菜单悬停背景 | `color-menu-hover-bg` | `rgba(255,255,255,0.08)` |

> 悬停背景使用 `0.08` 而非更低值，确保在深色侧边栏上与激活态有可感知的视觉差异。

### 状态 Badge 颜色

| 状态 | 背景色 | 文字色 | 竖线色（看板） |
|------|--------|--------|----------------|
| 待发出 / 待生产 / 待处理 | `#FEF3C7` | `#92400E` | `#F59E0B` |
| 进行中 / 待收回 | `#EEF2FF` | `#3730A3` | `#6366F1` |
| 已完成 / 已收回 | `#D1FAE5` | `#065F46` | `#10B981` |
| 低库存 / 异常 | `#FEE2E2` | `#991B1B` | — |

### Dashboard 卡片颜色映射

仪表盘四张统计卡片的 `color` 属性替换如下（保持语义区分）：

| 卡片 | 原色 | 新色 |
|------|------|------|
| 低库存配件 | `#C4952A` | `#F59E0B`（amber，表示警告） |
| 待生产订单 | `#3D7EBF` | `#6366F1`（indigo，主色） |
| 进行中电镀单 | `#6B5B95` | `#8B5CF6`（violet，区分电镀） |
| 进行中手工单 | `#4A8C6F` | `#10B981`（emerald，区分手工） |

### Naive UI themeOverrides 完整映射

`App.vue` 的 `themeOverrides` 完整替换，所有现有组件 key 均保留并更新：

```js
{
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
    headerBorderColor: '#0F172A',   // 与背景同色，视觉消除分隔线
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
    borderRadius: '12px',          // 保持原值
  },
  Button: {
    borderRadius: '8px',           // 保持原值
  },
  Input: {
    borderRadius: '8px',           // 保持原值
  },
  Modal: {
    borderRadius: '16px',          // 保持原值
  },
}
```

---

## 2. 布局结构

### 顶部 Header

- **高度：** 52px（原 60px）
  - 更新 `n-layout-header` 的 `style="height: 52px"`
  - 同时更新内层 `n-layout` 的高度计算：`style="height: calc(100vh - 52px)"`
- **背景：** `#0F172A`，与侧边栏无缝连接
- **品牌区（左）：** 品牌 icon（Unicode `U+25C8` ◈，White Diamond Containing Black Small Diamond）+ `ALLENOP`，icon 颜色 `#6366F1`，文字 `font-weight: 800`，`letter-spacing: 0.1em`，颜色 `#F1F5F9`
- **操作区（右）：** 帮助 icon + 设置 icon，颜色 `#475569`（视觉占位，暂不实现功能）
- `headerBorderColor` 设为 `#0F172A`（同背景色），视觉上消除分隔线

### 左侧 Sidebar

- **展开宽度：** 240px（原 220px，需更新 `n-layout-sider` 的 `:width` prop）
- **折叠宽度：** 52px（原 64px，需同时更新 `n-layout-sider` 的 `:collapsed-width` prop 和 `n-menu` 的 `:collapsed-width` prop）
- **背景：** `#0F172A`
- **分组结构（4 组）：**
  - `工作台`：进度看板、仪表盘
  - `商品`：配件管理、饰品管理
  - `生产`：订单管理、电镀单、手工单
  - `库存`：库存总表、库存流水
- **分组标签样式：** `10px uppercase font-weight: 600 color: #475569`，padding 上方 16px
- **菜单项高度：** 36px
- **激活态：** 左侧 `2px solid #6366F1` 竖线 + `rgba(99,102,241,0.12)` 背景 + `#6366F1` 文字 + icon
- **悬停态：** `rgba(255,255,255,0.08)` 背景
- **折叠时：** 仅显示 icon，分组标签隐藏
- **菜单 key 值不变**：`n-menu` 的 `value`（activeKey）仍使用路由第一段（`kanban`、`parts` 等），分组只是视觉层包装，不影响 key 匹配逻辑。

### 内容区 Page Header（大多数列表页统一）

**有父级的列表页**（配件管理、饰品管理、订单管理、电镀单、手工单、库存总表）：

```
[面包屑：父级 / 当前页]           ← 12px, #94A3B8
[页面标题]                         ← 18px, font-weight: 600, #0F172A
──────────────────────────────────  ← 1px #E2E8F0 分隔线
[过滤栏：搜索框 + 筛选器 + 主操作按钮（右对齐）]
```

- 面包屑与标题之间间距 4px
- 分隔线下方 16px 为过滤栏
- 主操作按钮（如"新增配件"）固定在过滤栏最右侧

**顶级页面例外**（仪表盘、库存流水、进度看板）：无上级父页面，省略面包屑行，仅保留标题行 + 分隔线：

```
[页面标题]                         ← 18px, font-weight: 600, #0F172A
──────────────────────────────────
```

**看板页额外例外：** `KanbanBoard.vue` 的过滤器（类型选择）和"收回"按钮位于标题同行右侧，不在分隔线下方：

```
[进度看板]                  [类型筛选 ▾]  [收回]
──────────────────────────────────
[泳道内容]
```

---

## 3. 列表页 / 表格

### 表格样式

- **行高：** 40px（Naive UI `size="small"`）
- **表头背景：** `#F8FAFC`，文字 `#64748B`，`font-weight: 600`
- **行悬停：** `#F1F5F9`
- **边框：** 仅保留水平分隔线 `#E2E8F0`，取消竖线（`bordered: false` 已有，确认保持）

### 状态显示

所有状态字段改为内联 Badge 组件（共享 `.badge` 类）：

```html
<span class="badge badge-amber">• 待发出</span>
<span class="badge badge-indigo">• 进行中</span>
<span class="badge badge-green">• 已完成</span>
<span class="badge badge-red">• 低库存</span>
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
- 取消原有底部 `border-bottom` 分隔线，靠竖线颜色区分泳道

### 供应商卡片

- **高度：** ~72px（扁平化）
- **背景：** `#FFFFFF`
- **边框：** `1px solid #E2E8F0`
- **悬停：** `border-color: #6366F1` + `box-shadow: 0 0 0 3px rgba(99,102,241,0.1)`（取消原红色悬停）
- **类型 Badge：** 电镀 → indigo，手工 → amber
- 卡片内布局：供应商名（14px bold）+ 类型 badge 在同一行，配件种类数量在第二行（12px `#64748B`）

### 顶部工具栏

- 筛选从 `n-radio-group` 改为 `n-select` 下拉（节省空间）
- "收回"按钮保持 primary 样式

---

## 5. 实现范围

### 修改文件

| 文件 | 改动类型 |
|------|----------|
| `frontend/src/App.vue` | 全量替换 `themeOverrides`；更新 `body` 背景色为 `#F8FAFC` |
| `frontend/src/main.js` | 引入 `./styles/global.css` |
| `frontend/src/styles/global.css` | 新建：`.badge` 变体；`.page-header` / `.page-breadcrumb`；`.icon-btn` |
| `frontend/src/layouts/DefaultLayout.vue` | Header 高度 60→52px（`n-layout-header` style + `calc(100vh - 52px)`）；品牌区（◈ 图标）；Sidebar 展开宽度 220→240px；折叠宽度 64→52px（`n-layout-sider` + `n-menu` 两处 prop）；分组菜单配置；移除 `content-style` 中的 `background: #F6F5F1` 内联色（由 themeOverrides 接管） |
| `frontend/src/views/Dashboard.vue` | 四张卡片 `color` 按新颜色映射更新 |
| `frontend/src/views/parts/PartList.vue` | 操作列改图标按钮；状态 badge；过滤栏；page header 结构 |
| `frontend/src/views/jewelries/JewelryList.vue` | 同上 |
| `frontend/src/views/orders/OrderList.vue` | 状态 badge；操作列；page header 结构 |
| `frontend/src/views/plating/PlatingList.vue` | 状态 badge；操作列；page header 结构 |
| `frontend/src/views/handcraft/HandcraftList.vue` | 状态 badge；操作列；page header 结构 |
| `frontend/src/views/kanban/KanbanBoard.vue` | 泳道标题（竖线+数量）；卡片悬停；工具栏改 select |
| `frontend/src/views/InventoryOverview.vue` | 状态 badge；过滤栏；page header 结构 |
| `frontend/src/views/InventoryLog.vue` | page header 结构统一（标题样式对齐） |

### 共享样式方案

**选择方式 B：新建 `frontend/src/styles/global.css`**，在 `main.js` 中 `import './styles/global.css'` 引入。

`global.css` 包含：
- `.badge`、`.badge-amber`、`.badge-indigo`、`.badge-green`、`.badge-red`
- `.page-header`、`.page-breadcrumb`、`.page-title`
- `.icon-btn`（图标按钮基础样式）

`App.vue` 的全局 `<style>` 仅保留 `* { box-sizing: border-box; }` 和 `body { margin: 0; background: #F8FAFC; }`。

---

## 6. 不在范围内

- 路由结构、API 层不变
- 详情页（PartDetail、JewelryDetail、PlatingDetail、HandcraftDetail、OrderDetail）本次不改，保持现状
- 后端无任何改动
- 不引入新依赖
- `InventoryLog.vue` 仅统一 page header 样式，不改其他逻辑
