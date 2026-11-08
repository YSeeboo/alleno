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
| Bot | Feishu (Lark) webhook + cards (no Telegram dep — `requirements.txt` has no `python-telegram-bot`) |
| AI Agent | DeepSeek chat-completions via the `openai` SDK (`bot/agent/runner.py`, model `deepseek-chat`, max 10 tool-call iterations) |
| AI Vision | Qwen-VL via Dashscope OpenAI-compatible endpoint (`bot/vision.py`, model `qwen-vl-plus`, requires `DASHSCOPE_API_KEY`) |
| Auth | JWT (PyJWT) + bcrypt password hashing; per-module permission strings checked by `api/deps.py` |
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
Entry (Frontend / Feishu webhook) → FastAPI router (permission-gated) → service function → SQLAlchemy session

### Key Files
- `main.py` — lifespan: rotates ephemeral `JWT_SECRET_KEY` if default, runs `Base.metadata.create_all()`, `ensure_schema_compat()`, then `_init_admin()` (creates `admin` user with a random one-shot password logged at WARN if absent). Registers every router with a `require_permission(...)` dependency.
- `database.py` — engine, `SessionLocal`, `Base`, `get_db()` (commit-on-success / rollback-on-exception), `ensure_schema_compat()`
- `config.py` — Pydantic `BaseSettings`; validates `DATABASE_URL` must be PostgreSQL; exposes `feishu_whitelist_ids`, `oss_enabled`, `oss_upload_host`, `oss_public_base_url` properties
- `time_utils.py` — `now_beijing()` returns naive datetime in Asia/Shanghai; used as column defaults
- `api/_errors.py` — `service_errors()` context manager: `ValueError` → HTTP 400, `RuntimeError` → HTTP 500
- `api/deps.py` — `get_current_user`, `require_permission("name")`, `require_any_permission(...)`; permission strings are the module name (`parts`, `jewelries`, `inventory`, `orders`, `plating`, `handcraft`, `restock`, `kanban`, `purchase_orders`, `sorting`, `users`)
- `db_safety.py` — `assert_safe_test_database_url()`; tests call this before redirecting `database.engine` so a misconfigured `TEST_DATABASE_URL` can never hit the main DB

### Service Layer
All service functions are stateless pure functions: `create_*(db, ...)`, `get_*(db, ...)`, `list_*(db, ...)`, `update_*(db, ...)`, `delete_*(db, ...)`. They call `db.flush()` (not `db.commit()`); commit is owned by `get_db()`. Business errors raise `ValueError`; the API layer catches them via `service_errors()`.

### ID Generation
Backed by the `id_counter` table (one row per prefix, atomic `INSERT ... ON CONFLICT ... DO UPDATE` to claim the next number). Two helpers in `services/_helpers.py`:
- `_next_id(db, Model, "EP")` → `EP-0001` (simple sequential, 4-digit)
- `_next_id_by_category(db, Model, "PJ-DZ")` → `PJ-DZ-00001` (category-scoped, 5-digit)

Part IDs are category-scoped: `PJ-DZ-` (吊坠), `PJ-LT-` (链条), `PJ-X-` (小配件). All other IDs use simple sequential: `SP-` (jewelry), `BM-` (BOM), `OR-` (orders), `EP-` (plating), `HC-` (handcraft).

**Part variant IDs**: a single root part can have variant rows whose IDs append a color tag and/or spec suffix — e.g. `PJ-DZ-00001-G` (root + 金色), `PJ-DZ-00001-G-45cm`, `PJ-LT-00008-45cm` (spec only). The variant suffix is part of the primary key; treat `part_id` as opaque text and don't parse it for business logic.

### Inventory Model
There is **no stock column**. Current stock is always `SELECT SUM(change_qty) FROM inventory_log WHERE item_type=? AND item_id=?`. Every stock change (入库, 出库, 电镀发出, 电镀收回, 手工发出, 手工完成, 盘点修正, …) appends a row with a reason string. `deduct_stock()` raises `ValueError` if the balance would go negative.

### Category Validation
`PART_CATEGORIES` and `JEWELRY_CATEGORIES` dicts in `services/part.py` and `services/jewelry.py` map Chinese category names to ID prefixes. `create_*` validates against this dict; `update_*` blocks category changes entirely.

### Order Lifecycles

**Plating orders** (`EP-`): `pending` → `processing` (via `POST /send`, deducts stock) → `completed` (auto-triggered when all items reach `received_qty >= qty` via `POST /receive`). PATCH /status is disabled for all transitions.

**Handcraft orders** (`HC-`): same state machine. Parts are sent (deduct stock); finished jewelry items are received (add stock). `bom_qty` on part items is a reference value only — not used for stock calculations.

**State machine rule**: all transitions go through dedicated endpoints (`POST /send`, `POST /receive`). `PATCH /{id}/status` rejects all transitions to enforce this.

### Bot / Agent Architecture
Feishu is the only chat surface — there is no Telegram integration.
- `api/feishu.py` — webhook entry (`/api/feishu/webhook`); dispatches text → `run_agent()` and image → `analyze_image()` as FastAPI background tasks, then sends the result back via Feishu API. Feishu **Encrypt Key must be empty**; verification uses `FEISHU_VERIFICATION_TOKEN`. The same URL also receives `card.action.trigger` events.
- `bot/agent/runner.py` — DeepSeek agentic loop (`run_agent()`); model `deepseek-chat` via `openai.AsyncOpenAI(base_url="https://api.deepseek.com")`, max 10 iterations
- `bot/agent/tools.py` — callable tools (`TOOLS` array + `execute_tool()` dispatcher) for stock/order/plating/handcraft operations
- `bot/vision.py` — image analysis via **Qwen-VL Plus** on Dashscope's OpenAI-compatible endpoint; needs `DASHSCOPE_API_KEY`. Feishu image download uses `FEISHU_APP_ID`/`FEISHU_APP_SECRET` tenant token.
- `bot/purchase_parser.py`, `bot/purchase_resolver.py`, `bot/purchase_draft_store.py` — pipeline for parsing natural-language 采购单 messages, resolving part candidates against the DB, and persisting drafts pending card confirmation
- `bot/feishu_cards.py`, `bot/feishu_card_handler.py` — interactive card payloads and the action-trigger router
- `bot/middleware.py` — whitelist enforced via `FEISHU_WHITELIST` (comma-separated `open_id`s); empty = unrestricted

### Schema Conventions
- Pydantic schemas live in `schemas/` with `ConfigDict(from_attributes=True)`
- `Optional[float] = Field(None, gt=0)` for qty fields that must be positive when provided
- `bom_qty` on handcraft parts is `Optional[float] = None` (reference value, 0 and null both valid)
- All response schemas include `id` and any timestamp fields

### Additive Migrations
`ensure_schema_compat()` in `database.py` runs at startup and adds columns that exist in the model definitions but are missing from the live table (e.g. `delivery_images`, `image`). Use this pattern for additive schema changes instead of full Alembic migrations.

### Auth & Permissions
JWT via `PyJWT` + bcrypt-hashed passwords. The first startup creates an `admin` user with a random URL-safe password printed to the logs at WARN level (`_init_admin()` in `main.py`). The `JWT_SECRET_KEY` defaults to a sentinel; if left as the default, lifespan replaces it with a random ephemeral secret (tokens invalidate on restart) — set `JWT_SECRET_KEY` in `.env` for persistence. Every non-auth router in `main.py` is wrapped with `require_permission("<module>")` (or `require_any_permission(...)`); the permission strings are the keys to use when granting access via the users API. Tests bypass auth by overriding `get_current_user` (see `client` fixture).

### Test Fixtures
In `tests/conftest.py`:
- **Safety pattern (do not break)**: conftest calls `assert_safe_test_database_url(TEST_DATABASE_URL)` and then rewrites `database.engine` / `database.SessionLocal` to the test engine **before** importing `main`. `main.lifespan` runs `create_all()` and `ensure_schema_compat()` on `database.engine`, so any import-order change could write to the production DB.
- `db` — truncates all tables before each test; use for service-layer unit tests
- `client` — `TestClient` with overridden `get_db` (shared session with `db`) and `get_current_user` (returns a fake admin with all permissions); use for API tests
- `client_real_get_db` — `TestClient` using the real `get_db()` generator; use when testing commit/rollback behaviour
