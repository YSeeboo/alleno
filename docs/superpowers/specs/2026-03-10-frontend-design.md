# Allen Shop 前端管理页面设计文档

**日期：** 2026-03-10
**阶段：** Phase 6 — Frontend Management UI
**工作目录：** `/Users/ycb/workspace/allen_shop/frontend`

---

## 1. 技术选型

| 层级 | 技术 |
|------|------|
| 框架 | Vue 3 + Vite (`npm create vite@latest . -- --template vue`) |
| UI 组件库 | Naive UI |
| 路由 | Vue Router 4 |
| 状态管理 | Pinia（仅用于全局 message 实例） |
| HTTP 客户端 | Axios |
| 图标 | @vicons/ionicons5 |

---

## 2. 项目结构

```
frontend/
├── src/
│   ├── api/
│   │   ├── index.js        # axios 实例 + 响应拦截器
│   │   ├── parts.js
│   │   ├── jewelries.js
│   │   ├── bom.js
│   │   ├── inventory.js
│   │   ├── orders.js
│   │   ├── plating.js
│   │   └── handcraft.js
│   ├── composables/        # useLoading 等复用逻辑
│   ├── layouts/
│   │   └── DefaultLayout.vue
│   ├── router/
│   │   └── index.js
│   ├── views/
│   │   ├── Dashboard.vue
│   │   ├── parts/
│   │   │   ├── PartList.vue
│   │   │   └── PartDetail.vue
│   │   ├── jewelries/
│   │   │   ├── JewelryList.vue
│   │   │   └── JewelryDetail.vue
│   │   ├── orders/
│   │   │   ├── OrderList.vue
│   │   │   ├── OrderCreate.vue
│   │   │   └── OrderDetail.vue
│   │   ├── plating/
│   │   │   ├── PlatingList.vue
│   │   │   ├── PlatingCreate.vue
│   │   │   └── PlatingDetail.vue
│   │   ├── handcraft/
│   │   │   ├── HandcraftList.vue
│   │   │   ├── HandcraftCreate.vue
│   │   │   └── HandcraftDetail.vue
│   │   └── InventoryLog.vue
│   ├── App.vue
│   └── main.js
├── package.json
└── vite.config.js
```

---

## 3. 后端补充（与前端同步完成）

`api/orders.py` 增加：

```
GET /api/orders/   ?status=&customer_name=   返回订单列表
```

用于支持订单列表页和 Dashboard 统计"待处理订单数"。

---

## 4. API 层设计

### src/api/index.js

```js
const api = axios.create({ baseURL: 'http://localhost:8000/api' })

// 响应拦截器：非 2xx 时用 message.error 弹出 detail 字段，继续 reject
```

### 各业务文件约定

函数只做请求，不处理 loading/错误，由页面组件控制。

| 文件 | 封装的端点 |
|------|----------|
| parts.js | GET/POST /parts/, GET/PATCH/DELETE /parts/:id |
| jewelries.js | GET/POST /jewelries/, GET/PATCH/DELETE /jewelries/:id, PATCH /jewelries/:id/status |
| bom.js | PUT/GET/DELETE /bom/:jewelry_id/:part_id |
| inventory.js | POST add/deduct, GET stock/log |
| orders.js | POST/GET(list) /orders/, GET/PATCH /orders/:id, GET items/parts-summary |
| plating.js | POST/GET(list) /plating/, GET /plating/:id, POST send/receive |
| handcraft.js | POST/GET(list) /handcraft/, GET /handcraft/:id, POST send/receive |

---

## 5. 布局（DefaultLayout.vue）

- `n-layout` 水平分割
- 左侧：`n-layout-sider`（240px，可折叠）+ `n-menu`，7 个一级菜单项带图标
- 顶部：`n-layout-header`（64px）显示"Allen Shop 管理系统"
- 右侧：`n-layout-content`（内边距 24px）+ `<router-view>`

---

## 6. 路由

| 路径 | 组件 |
|------|------|
| `/` | Dashboard |
| `/parts` | PartList |
| `/parts/:id` | PartDetail |
| `/jewelries` | JewelryList |
| `/jewelries/:id` | JewelryDetail |
| `/orders` | OrderList |
| `/orders/create` | OrderCreate |
| `/orders/:id` | OrderDetail |
| `/plating` | PlatingList |
| `/plating/create` | PlatingCreate |
| `/plating/:id` | PlatingDetail |
| `/handcraft` | HandcraftList |
| `/handcraft/create` | HandcraftCreate |
| `/handcraft/:id` | HandcraftDetail |
| `/inventory-log` | InventoryLog |

---

## 7. 页面规格

### Dashboard

4 张统计卡片（`n-grid :cols="4"`）：

| 卡片 | 数据来源 | 跳转 |
|------|---------|------|
| 低库存配件 | 所有配件库存 < 10 的件数 | `/parts` |
| 待处理订单 | GET /api/orders?status=待生产 | `/orders` |
| 进行中电镀单 | GET /api/plating?status=processing | `/plating` |
| 进行中手工单 | GET /api/handcraft?status=processing | `/handcraft` |

加载时显示 `n-spin`，点击整张卡片跳转。

### PartList

- `n-data-table` 列：配件名称、类目、颜色、单位、单件成本、当前库存、默认电镀工艺、操作
- 顶部：名称搜索框 + 类目筛选 + "新增配件"按钮
- 操作：编辑（Modal）、快速入库（Modal，reason 固定"采购入库"）、删除（popconfirm）
- 新增/编辑共用同一个 `n-modal` 内嵌 `n-form`

### PartDetail

- 上方：配件基本信息卡片
- 下方：库存流水表格（时间、变动数量、原因、备注），正数绿色负数红色

### JewelryList

- 列：饰品名称、类目、颜色、零售价、批发价、当前库存、状态、操作
- 状态列用 `n-switch` 直接切换，调用 `PATCH /api/jewelries/:id/status`
- 操作：编辑、查看详情、删除

### JewelryDetail

- 上方：饰品基本信息
- 下方：BOM 配置表
  - 列：配件名称、每件用量、操作（删除）
  - 底部添加行：配件下拉搜索 + 用量输入 + 确认
  - 用量 inline 编辑，失焦后调用 `PUT /api/bom`

### OrderList

- 列：订单号、客户名、状态（`n-tag` 不同颜色）、总金额、创建时间
- 状态筛选 + "新建订单"按钮
- 点击行跳转详情

### OrderCreate

- 客户名输入框
- 动态订单行：饰品下拉搜索、数量、单价（自动填批发价可修改）、备注、删除行
- 实时计算合计金额
- 提交按钮

### OrderDetail

- 左上：基本信息 + 状态流转按钮（只显示下一步）
- 右上：饰品清单表格
- 下方：配件汇总表格（调用 `/parts-summary` 后关联配件名称）

### PlatingList

- 列：电镀单号、电镀厂、状态（n-tag：pending=灰/processing=蓝/completed=绿）、创建时间
- 状态筛选 + "新建电镀单"按钮

### PlatingCreate

- 电镀厂名称、备注
- 动态明细行：配件下拉搜索、发出数量、电镀方式、备注

### PlatingDetail

- 基本信息 + 当前状态
- pending 时显示"确认发出"按钮
- 明细表格：配件名、发出数量、已收回数量、进度（`n-progress`）、电镀方式、状态
- processing 时每行末尾：数量输入框 + "登记收回"（仅非已收回行）

### HandcraftList — 同电镀单结构

### HandcraftCreate

- 手工商家名称、备注
- 发出配件区：配件下拉搜索、实际发出数量、BOM 理论用量（选填）
- 预期收回饰品区：饰品下拉搜索、预期数量

### HandcraftDetail

- 配件明细表：配件名、实际发出量、BOM 理论量、差异（正负着色）
- 成品明细表：饰品名、预期数量、已收回数量、进度（`n-progress`）、状态
- processing 时成品行显示：数量输入框 + "登记收回"

### InventoryLog

- 顶部：品类下拉（配件/饰品）+ 编号输入框 + 查询按钮
- 表格：时间、品类、编号、变动数量（正绿负红）、原因、备注

---

## 8. 通用规范

1. 所有异步请求加 loading 状态（操作前设 true，finally 设 false）
2. 成功：`message.success('操作成功')`；失败：拦截器统一弹出，页面无需重复
3. 删除必须 `n-popconfirm` 二次确认
4. 空数据显示 `n-empty`
5. 金额 `.toFixed(2)`，数量变动正数 `#18a058` 绿色，负数 `#d03050` 红色

---

## 9. 完成标准

1. `npm run dev` 启动无报错，所有页面可访问
2. 完整链路跑通（真实后端，不使用 mock）：
   - 新增配件 → 入库 → 详情页查看流水
   - 新建饰品 → 配置 BOM → 新建订单 → 查看配件汇总
   - 新建电镀单 → 发出 → 分两次登记收回 → 状态变 completed
   - 新建手工单 → 发出 → 分两次登记成品收回 → 状态变 completed
3. Dashboard 统计卡片数据准确反映数据库状态
