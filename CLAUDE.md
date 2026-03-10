# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Allen Shop** is a jewelry shop management system (饰品店管理系统) for a small accessories business. It manages raw material parts (配件), finished jewelry products (饰品), bill-of-materials relationships, inventory tracking, and customer orders.

Two access channels:
- **Frontend management UI** — web-based daily operations
- **Telegram Bot** — natural language queries and operations via Claude Agent + Tools

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI |
| ORM | SQLAlchemy |
| Database | SQLite (dev) → PostgreSQL (prod) |
| Bot | python-telegram-bot v20+ |
| AI | Anthropic Claude API |

## Planned Project Structure

```
allen_shop/
├── main.py                  # FastAPI app entry point
├── config.py                # Environment variable configuration
├── models/                  # SQLAlchemy ORM models
│   ├── part.py
│   ├── jewelry.py
│   ├── bom.py
│   ├── order.py
│   ├── inventory_log.py
│   ├── plating_order.py
│   └── handcraft_order.py
├── services/                # Business logic layer
│   ├── part.py
│   ├── jewelry.py
│   ├── bom.py
│   ├── inventory.py
│   ├── order.py
│   ├── plating.py           # 电镀单创建、发出、收回
│   └── handcraft.py         # 手工单创建、发出配件、收回饰品
├── api/                     # FastAPI routers
│   ├── parts.py
│   ├── jewelries.py
│   ├── bom.py
│   ├── inventory.py
│   ├── orders.py
│   ├── plating.py
│   └── handcraft.py
├── bot/                     # Telegram Bot
│   ├── handlers.py          # Message routing
│   ├── middleware.py        # User whitelist, rate limiting
│   └── agent/
│       ├── runner.py        # Claude Agent agentic loop
│       └── tools.py         # Tool definitions callable by Bot
└── frontend/                # Web management UI (TBD)
```

## Architecture

Four-tier architecture:
1. **Entry Layer** — Frontend UI + Telegram Bot
2. **API Layer** — FastAPI REST endpoints shared by both entry channels
3. **Service Layer** — Business logic (`part_service`, `jewelry_service`, `bom_service`, `inventory_service`, `order_service`)
4. **Data Layer** — SQLite/PostgreSQL via SQLAlchemy

## Key Domain Concepts

**ID formats:** `PJ-XXXX` (parts), `SP-XXXX` (jewelry), `BM-XXXX` (BOM records), `OR-XXXX` (orders), `EP-XXXX` (plating orders), `HC-XXXX` (handcraft orders)

**Inventory design:** No standalone inventory column — current stock is computed as `SELECT SUM(change_qty) WHERE item_id = ?` from `inventory_log`. This audit-first approach ensures full traceability.

**BOM relationship:** Each jewelry item is composed of parts with fixed quantities (`qty_per_unit`). The `produce(jewelry_id, qty)` operation deducts parts from inventory per BOM and adds to jewelry stock.

**Order flow:** Create order → generate order items (jewelry + price snapshots) → generate parts summary (aggregate BOM across all items) → production → fulfillment → status update to completed.

**Price snapshot:** `order_item.unit_price` captures price at order time to prevent historical records from being affected by future price changes.

**Plating flow:** Create `plating_order` → add `plating_order_item` rows (part_id + qty + plating_method) → mark parts as sent (deduct inventory, reason=电镀发出) → receive in batches: each partial receipt updates `received_qty` and logs to `inventory_log` (reason=电镀收回); item `status` flips to 已收回 when `received_qty >= qty`. `plating_method` is stored per order item because the same part may be plated differently across batches.

**Handcraft flow:** Create `handcraft_order` → add `handcraft_part_item` rows (manually entered qty, not auto-calculated from BOM; `bom_qty` stored as reference only) → send parts (deduct inventory, reason=手工发出) → receive finished jewelry in batches via `handcraft_jewelry_item`: each partial receipt updates `received_qty` and logs to `inventory_log` (reason=手工完成); item `status` flips to 已收回 when `received_qty >= qty`. Actual quantities intentionally differ from BOM.

## Service Layer Interfaces

### `inventory_service`
```python
add_stock(item_type, item_id, qty, note)     # 入库
deduct_stock(item_type, item_id, qty, note)  # 出库
produce(jewelry_id, qty)                     # 按 BOM 扣配件，成品 +qty
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

## Telegram Bot

- Runs in polling mode
- Driven by Claude Agent + Tools agentic loop (`bot/agent/runner.py`)
- Supports natural language: e.g., "PJ-0012 还有多少？", "生产 SP-0005 10 件"
- `bot/middleware.py` enforces user whitelist to block unauthorized access

## Development Status

- [x] Database schema design
- [ ] SQLAlchemy models
- [ ] Inventory service layer
- [ ] Order service layer
- [ ] FastAPI endpoints
- [ ] Telegram Bot skeleton (polling mode)
- [ ] Claude Agent + Tools integration
- [ ] Frontend management page
