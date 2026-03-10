# Allen Shop — 饰品店管理系统

## 项目背景

Allen Shop 是一个面向小型饰品店的一体化管理系统。店铺同时管理原材料配件与成品饰品，每件成品由若干配件按固定用量组合而成（BOM 关系）。

系统支持两个入口：
- **前端管理页面**：用于日常的商品管理、订单录入、库存维护
- **Telegram Bot**：用于随时随地查询库存、处理订单、执行常用操作

---

## 核心业务流程

```
采购配件
    → 配件库存入库
组装饰品
    → 饰品库存入库
接到客户订单
    → 创建订单 & 订单明细（饰品 × 数量）
    → 生成订单表（饰品清单 + 价格）
    → 生成配件汇总表（统计本批订单共需多少配件）

安排生产
    → 按 BOM 扣减配件库存
    → 饰品成品库存 +1

发货/销售
    → 饰品库存 -1
    → 订单状态更新为已完成
```

---

## 数据库设计

### 配件表 `part` (PJ-XXXX)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR | 主键，格式 PJ-0001 |
| name | VARCHAR | 配件名称 |
| image | VARCHAR | 图片路径/URL |
| category | VARCHAR | 类目 |
| color | VARCHAR | 颜色 |
| unit | VARCHAR | 计量单位（个/克/米） |
| unit_cost | DECIMAL | 单件成本 |
| plating_process | VARCHAR | 电镀工艺 |

### 饰品表 `jewelry` (SP-XXXX)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR | 主键，格式 SP-0001 |
| name | VARCHAR | 饰品名称 |
| image | VARCHAR | 图片路径/URL |
| category | VARCHAR | 类目 |
| color | VARCHAR | 颜色 |
| retail_price | DECIMAL | 零售价 |
| wholesale_price | DECIMAL | 批发价 |
| status | ENUM | 上架状态：active / inactive |

### BOM 表 `bom` (BM-XXXX)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR | 主键，格式 BM-0001 |
| jewelry_id | VARCHAR | 关联饰品表 |
| part_id | VARCHAR | 关联配件表 |
| qty_per_unit | DECIMAL | 生产 1 件饰品需要的配件数量 |

### 订单表 `order` (OR-XXXX)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR | 主键，格式 OR-0001 |
| customer_name | VARCHAR | 客户名称/标识 |
| status | ENUM | 待生产 / 生产中 / 已完成 |
| total_amount | DECIMAL | 订单总金额 |
| created_at | DATETIME | 创建时间 |

### 订单明细表 `order_item`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| order_id | VARCHAR | 关联订单表 |
| jewelry_id | VARCHAR | 关联饰品表 |
| quantity | INTEGER | 数量 |
| unit_price | DECIMAL | 下单时价格快照（防止改价影响历史） |
| remarks | TEXT | 备注 |

### 库存流水表 `inventory_log`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| item_type | ENUM | part / jewelry |
| item_id | VARCHAR | 关联配件或饰品 id |
| change_qty | DECIMAL | 变动数量（正=入库，负=出库） |
| reason | VARCHAR | 采购入库 / 生产消耗 / 销售出库 / 盘点修正 / 电镀发出 / 电镀收回 / 手工发出 / 手工完成 |
| note | TEXT | 备注 |
| created_at | DATETIME | 操作时间 |

> 当前库存 = `SELECT SUM(change_qty) WHERE item_id = ?`，无需单独维护库存字段，历史完整可追溯。

---

### 电镀订单主表 `plating_order` (EP-XXXX)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR | 主键，格式 EP-0001 |
| supplier_name | VARCHAR | 电镀厂名称 |
| status | ENUM | pending / processing / completed |
| created_at | DATETIME | 创建时间 |
| completed_at | DATETIME | 完成时间（nullable） |
| note | TEXT | 备注 |

### 电镀订单明细 `plating_order_item`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| plating_order_id | VARCHAR | FK → plating_order |
| part_id | VARCHAR | FK → part |
| qty | DECIMAL | 发出数量 |
| received_qty | DECIMAL | 已收回数量（nullable，分批收回累加） |
| status | ENUM | 未送出 / 电镀中 / 已收回 |
| plating_method | VARCHAR | 本次电镀方式（同一配件可能不同批次镀不同色） |
| note | TEXT | 备注 |

> 同一张电镀单支持分批收回：每次收回部分数量时更新 `received_qty`，当 `received_qty >= qty` 时将 `status` 置为已收回，并在 `inventory_log` 记录 `reason=电镀收回`（正）。发出时记录 `reason=电镀发出`（负）。

---

### 手工订单主表 `handcraft_order` (HC-XXXX)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR | 主键，格式 HC-0001 |
| supplier_name | VARCHAR | 手工商家名称 |
| status | ENUM | pending / processing / completed |
| created_at | DATETIME | 创建时间 |
| completed_at | DATETIME | 完成时间（nullable） |
| note | TEXT | 备注 |

### 手工配件明细 `handcraft_part_item`（发出的配件）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| handcraft_order_id | VARCHAR | FK → handcraft_order |
| part_id | VARCHAR | FK → part |
| qty | DECIMAL | 实际发出数量 |
| bom_qty | DECIMAL | BOM 理论用量（nullable，仅供参考对比） |
| note | TEXT | 备注 |

### 手工成品明细 `handcraft_jewelry_item`（收回的饰品）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| handcraft_order_id | VARCHAR | FK → handcraft_order |
| jewelry_id | VARCHAR | FK → jewelry |
| qty | INTEGER | 预期收回数量 |
| received_qty | INTEGER | 已收回数量（nullable，分批收回累加） |
| status | ENUM | 未送出 / 制作中 / 已收回 |
| note | TEXT | 备注 |

> 每次分批收回时更新 `received_qty`，当 `received_qty >= qty` 时将 `status` 置为已收回，并在 `inventory_log` 记录 `reason=手工完成`（正）。

---

## 系统架构

```
┌─────────────────────────────────────────────┐
│              接入层 (Entry Layer)             │
│                                             │
│   ┌─────────────┐      ┌─────────────────┐  │
│   │  前端管理页面  │      │  Telegram Bot   │  │
│   └──────┬──────┘      └────────┬────────┘  │
└──────────┼──────────────────────┼───────────┘
           │                      │
           ▼                      ▼
┌─────────────────────────────────────────────┐
│               API 层 (FastAPI)               │
│   REST API，前端和 Bot 共同依赖               │
└───────────────────┬─────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│             服务层 (Service Layer)            │
│                                             │
│  part_service      jewelry_service          │
│  bom_service       inventory_service        │
│  order_service                              │
└───────────────────┬─────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│               数据层 (Database)              │
│           SQLite (开发) / PostgreSQL (生产)   │
└─────────────────────────────────────────────┘
```

---

## 项目结构

```
allen_shop/
├── main.py                      # 应用入口，启动 FastAPI
├── config.py                    # 环境变量配置
│
├── models/                      # 数据库模型 (SQLAlchemy ORM)
│   ├── part.py
│   ├── jewelry.py
│   ├── bom.py
│   ├── order.py
│   ├── inventory_log.py
│   ├── plating_order.py
│   └── handcraft_order.py
│
├── services/                    # 业务服务层
│   ├── part.py                  # 配件 CRUD
│   ├── jewelry.py               # 饰品 CRUD，上下架
│   ├── bom.py                   # BOM 管理
│   ├── inventory.py             # 库存入库/出库/生产/查询
│   ├── order.py                 # 订单创建、订单表、配件汇总表
│   ├── plating.py               # 电镀单创建、发出、收回
│   └── handcraft.py             # 手工单创建、发出配件、收回饰品
│
├── api/                         # FastAPI 路由
│   ├── parts.py
│   ├── jewelries.py
│   ├── bom.py
│   ├── inventory.py
│   ├── orders.py
│   ├── plating.py
│   └── handcraft.py
│
├── bot/                         # Telegram Bot
│   ├── handlers.py              # 消息处理，路由分发
│   ├── middleware.py            # 用户白名单、限流
│   └── agent/
│       ├── runner.py            # Claude Agent agentic loop
│       └── tools.py             # Bot 可调用的 tools 定义
│
└── frontend/                    # 前端管理页面（待定技术栈）
```

---

## 服务层接口

### `inventory_service`（初期优先实现）

```python
add_stock(item_type, item_id, qty, note)     # 入库
deduct_stock(item_type, item_id, qty, note)  # 出库
produce(jewelry_id, qty)                     # 生产：按 BOM 扣配件，成品 +qty
get_stock(item_type, item_id)                # 查询当前库存
get_stock_log(item_type, item_id)            # 查询流水历史
```

### `order_service`

```python
create_order(customer_name, items)           # 创建订单
get_order_items(order_id)                    # 获取订单表（饰品清单）
get_parts_summary(order_id)                  # 生成配件汇总表
update_order_status(order_id, status)        # 更新订单状态
```

---

## Telegram Bot 功能

Bot 通过 Claude Agent + Tools 驱动，支持自然语言操作：

| 功能 | 示例指令 |
|------|---------|
| 查库存 | "PJ-0012 还有多少？" |
| 入库 | "PJ-0012 入库 200 个" |
| 查订单 | "OR-0023 的配件汇总" |
| 生产 | "生产 SP-0005 10 件" |

Bot 用户需在白名单内，防止未授权访问。

---

## 开发路线

- [x] 数据库表结构设计
- [ ] 数据库模型（SQLAlchemy）
- [ ] 库存服务层（add_stock / deduct_stock / produce）
- [ ] 订单服务层（create_order / get_parts_summary）
- [ ] FastAPI 接口
- [ ] Telegram Bot 骨架（polling 模式）
- [ ] Claude Agent + Tools 接入
- [ ] 前端管理页面

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI |
| 数据库 | SQLite（开发）→ PostgreSQL（生产） |
| ORM | SQLAlchemy |
| Bot 框架 | python-telegram-bot v20+ |
| AI | Anthropic Claude API |
| 部署 | 本地（开发期），视需求迁移云服务器 |
