# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Allen Shop** is a jewelry shop management system (饰品店管理系统). It manages raw material parts (配件), finished jewelry products (饰品), BOM relationships, inventory, customer orders, plating orders (电镀单), and handcraft orders (手工单).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLAlchemy |
| Database | PostgreSQL (docker-compose provides PG 16) |
| Frontend | Vue 3.5 + Vite 7 + Naive UI + Pinia |
| Bot | Feishu Bot + python-telegram-bot v20+ |
| AI Agent | DeepSeek API (agentic loop with tool calling in `bot/agent/`) |
| AI Vision | Anthropic Claude API (image analysis in `bot/vision.py`) |
| File/Export | openpyxl (Excel), ReportLab (PDF), oss2 (Aliyun OSS uploads) |

## Commands

### Backend
```bash
python main.py                # start dev server (uvicorn, port 8000, --reload)
pytest                        # run all tests
pytest tests/test_api_parts.py                                              # single file
pytest tests/test_api_parts.py::test_create_part_valid_category_generates_prefixed_id  # single test
```

### Frontend
```bash
cd frontend
npm install      # first time setup
npm run dev      # dev server (port 5173)
npm run build    # production build → dist/
```

### Database
```bash
docker-compose up -d   # start PostgreSQL (localhost:5432, db: allen_shop, user/pass: allen)
```
Tests require a separate test DB. Set `TEST_DATABASE_URL` (default: `postgresql://allen:allen@localhost:5432/allen_shop_test`). The test fixture calls `create_all()` and `TRUNCATE ... RESTART IDENTITY CASCADE` between tests.

### Deployment
```bash
./deploy_aliyun_update.sh   # rsync → remote venv + pip install → DB migrate → frontend build → systemd restart
```
Configurable via env vars: `REMOTE_HOST`, `REMOTE_DIR`, `BACKEND_SERVICE`, `FRONTEND_DEPLOY_DIR`.

## Architecture

### Request Flow
Entry (Frontend / Telegram Bot / Feishu Bot) → FastAPI router → service function → SQLAlchemy session

### Key Files
- `main.py` — lifespan calls `Base.metadata.create_all()` then `ensure_schema_compat()` on startup
- `database.py` — engine, `SessionLocal`, `Base`, `get_db()`, `ensure_schema_compat()`
- `config.py` — Pydantic `BaseSettings`; validates `DATABASE_URL` must be PostgreSQL
- `time_utils.py` — `now_beijing()` returns naive datetime in Asia/Shanghai; used as column defaults
- `api/_errors.py` — `service_errors()` context manager: `ValueError` → HTTP 400, `RuntimeError` → HTTP 500

### Service Layer
All service functions are stateless pure functions: `create_*(db, ...)`, `get_*(db, ...)`, `list_*(db, ...)`, `update_*(db, ...)`, `delete_*(db, ...)`. They call `db.flush()` (not `db.commit()`); commit is owned by `get_db()`. Business errors raise `ValueError`; the API layer catches them via `service_errors()`.

### ID Generation
Two helpers in `services/_helpers.py`:
- `_next_id(db, Model, "EP")` → `EP-0001` (simple sequential, 4-digit)
- `_next_id_by_category(db, Model, "PJ-DZ")` → `PJ-DZ-00001` (category-scoped, 5-digit)

Part IDs are category-scoped: `PJ-DZ-` (吊坠), `PJ-LT-` (链条), `PJ-X-` (小配件). All other IDs use simple sequential: `SP-` (jewelry), `BM-` (BOM), `OR-` (orders), `EP-` (plating), `HC-` (handcraft).

### Inventory Model
There is **no stock column**. Current stock is always `SELECT SUM(change_qty) FROM inventory_log WHERE item_type=? AND item_id=?`. Every stock change (入库, 出库, 电镀发出, 电镀收回, 手工发出, 手工完成, 盘点修正, …) appends a row with a reason string. `deduct_stock()` raises `ValueError` if the balance would go negative.

### Category Validation
`PART_CATEGORIES` and `JEWELRY_CATEGORIES` dicts in `services/part.py` and `services/jewelry.py` map Chinese category names to ID prefixes. `create_*` validates against this dict; `update_*` blocks category changes entirely.

### Order Lifecycles

**Plating orders** (`EP-`): `pending` → `processing` (via `POST /send`, deducts stock) → `completed` (auto-triggered when all items reach `received_qty >= qty` via `POST /receive`). PATCH /status is disabled for all transitions.

**Handcraft orders** (`HC-`): same state machine. Parts are sent (deduct stock); finished jewelry items are received (add stock). `bom_qty` on part items is a reference value only — not used for stock calculations.

**State machine rule**: all transitions go through dedicated endpoints (`POST /send`, `POST /receive`). `PATCH /{id}/status` rejects all transitions to enforce this.

### Bot / Agent Architecture
- `bot/agent/runner.py` — DeepSeek agentic loop (`run_agent()`), max 10 tool-call iterations
- `bot/agent/tools.py` — ~15 callable tools (stock_check, create_order, send_plating, etc.) with `execute_tool()` dispatcher
- `bot/handlers.py` — Telegram message routing and command parsing
- `bot/vision.py` — Image analysis via Claude API
- Feishu webhook (`api/feishu.py`) runs `run_agent()` as a background task, sends result back
- User whitelist enforced via `FEISHU_WHITELIST` env var

### Schema Conventions
- Pydantic schemas live in `schemas/` with `ConfigDict(from_attributes=True)`
- `Optional[float] = Field(None, gt=0)` for qty fields that must be positive when provided
- `bom_qty` on handcraft parts is `Optional[float] = None` (reference value, 0 and null both valid)
- All response schemas include `id` and any timestamp fields

### Additive Migrations
`ensure_schema_compat()` in `database.py` runs at startup and adds columns that exist in the model definitions but are missing from the live table (e.g. `delivery_images`, `image`). Use this pattern for additive schema changes instead of full Alembic migrations.

### Test Fixtures
In `tests/conftest.py`:
- `db` — truncates all tables before each test; use for service-layer unit tests
- `client` — `TestClient` with overridden `get_db` using the same session as `db`; use for API tests
- `client_real_get_db` — `TestClient` using the real `get_db()` generator; use when testing commit/rollback behaviour
