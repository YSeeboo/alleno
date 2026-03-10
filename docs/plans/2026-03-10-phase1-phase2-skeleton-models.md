# Allen Shop Phase 1 & 2: Project Skeleton + Database Models

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Bootstrap the Allen Shop project with a working FastAPI skeleton and all SQLAlchemy ORM models, so `uvicorn main:app` starts cleanly and auto-creates the SQLite database with all tables.

**Architecture:** Four-tier FastAPI app (Entry → API → Service → Data). Phase 1 creates the project skeleton with `requirements.txt`, `config.py`, `database.py`, `main.py`, and empty `__init__.py` stubs for `models/`, `services/`, `api/`, `bot/`. Phase 2 adds all seven SQLAlchemy model files plus an `__init__.py` that imports them all so `Base.metadata.create_all()` discovers every table.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy (declarative), pydantic-settings, SQLite (dev), python-telegram-bot, anthropic

---

## Task 1: requirements.txt

**Files:**
- Create: `requirements.txt`

**Step 1: Create the file**

```
fastapi
uvicorn[standard]
sqlalchemy
python-telegram-bot
anthropic
pydantic-settings
python-dotenv
```

**Step 2: Verify**

```bash
cat requirements.txt
```

Expected: seven dependency lines, no version pins.

---

## Task 2: config.py

**Files:**
- Create: `config.py`

**Step 1: Write config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./allen_shop.db"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WHITELIST: str = ""
    ANTHROPIC_API_KEY: str = ""

    @property
    def telegram_whitelist_ids(self) -> list[int]:
        if not self.TELEGRAM_WHITELIST:
            return []
        return [int(uid.strip()) for uid in self.TELEGRAM_WHITELIST.split(",") if uid.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

**Step 2: Verify Python parses it**

```bash
python -c "from config import settings; print(settings.DATABASE_URL)"
```

Expected: `sqlite:///./allen_shop.db`

---

## Task 3: database.py

**Files:**
- Create: `database.py`

**Step 1: Write database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Step 2: Verify**

```bash
python -c "from database import engine, Base, get_db; print('OK')"
```

Expected: `OK`

---

## Task 4: models/part.py — 配件表

**Files:**
- Create: `models/part.py`

**Step 1: Write models/part.py**

```python
from sqlalchemy import Column, Numeric, String

from database import Base


class Part(Base):
    __tablename__ = "part"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    image = Column(String, nullable=True)
    category = Column(String, nullable=True)
    color = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    unit_cost = Column(Numeric(10, 2), nullable=True)
    plating_process = Column(String, nullable=True)
```

---

## Task 5: models/jewelry.py — 饰品表

**Files:**
- Create: `models/jewelry.py`

**Step 1: Write models/jewelry.py**

```python
from sqlalchemy import Column, Numeric, String

from database import Base


class Jewelry(Base):
    __tablename__ = "jewelry"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    image = Column(String, nullable=True)
    category = Column(String, nullable=True)
    color = Column(String, nullable=True)
    retail_price = Column(Numeric(10, 2), nullable=True)
    wholesale_price = Column(Numeric(10, 2), nullable=True)
    status = Column(String, nullable=False, default="active")
```

---

## Task 6: models/bom.py — BOM 表

**Files:**
- Create: `models/bom.py`

**Step 1: Write models/bom.py**

```python
from sqlalchemy import Column, ForeignKey, Numeric, String

from database import Base


class Bom(Base):
    __tablename__ = "bom"

    id = Column(String, primary_key=True)
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty_per_unit = Column(Numeric(10, 4), nullable=False)
```

---

## Task 7: models/order.py — 订单表 & 订单明细表

**Files:**
- Create: `models/order.py`

**Step 1: Write models/order.py**

```python
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from database import Base


class Order(Base):
    __tablename__ = "order"

    id = Column(String, primary_key=True)
    customer_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="待生产")
    total_amount = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OrderItem(Base):
    __tablename__ = "order_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String, ForeignKey("order.id"), nullable=False)
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    remarks = Column(Text, nullable=True)
```

---

## Task 8: models/inventory_log.py — 库存流水表

**Files:**
- Create: `models/inventory_log.py`

**Step 1: Write models/inventory_log.py**

```python
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text

from database import Base


class InventoryLog(Base):
    __tablename__ = "inventory_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_type = Column(String, nullable=False)   # part / jewelry
    item_id = Column(String, nullable=False)
    change_qty = Column(Numeric(10, 4), nullable=False)
    reason = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

Note: No FK constraints — `item_id` is polymorphic, distinguished by `item_type`.

---

## Task 9: models/plating_order.py — 电镀订单主表 & 明细表

**Files:**
- Create: `models/plating_order.py`

**Step 1: Write models/plating_order.py**

```python
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from database import Base


class PlatingOrder(Base):
    __tablename__ = "plating_order"

    id = Column(String, primary_key=True)
    supplier_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)


class PlatingOrderItem(Base):
    __tablename__ = "plating_order_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plating_order_id = Column(String, ForeignKey("plating_order.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty = Column(Numeric(10, 4), nullable=False)
    received_qty = Column(Numeric(10, 4), nullable=True, default=0)
    status = Column(String, nullable=False, default="未送出")
    plating_method = Column(String, nullable=True)
    note = Column(Text, nullable=True)
```

---

## Task 10: models/handcraft_order.py — 手工订单主表、配件明细、成品明细

**Files:**
- Create: `models/handcraft_order.py`

**Step 1: Write models/handcraft_order.py**

```python
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text

from database import Base


class HandcraftOrder(Base):
    __tablename__ = "handcraft_order"

    id = Column(String, primary_key=True)
    supplier_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True)


class HandcraftPartItem(Base):
    __tablename__ = "handcraft_part_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    handcraft_order_id = Column(String, ForeignKey("handcraft_order.id"), nullable=False)
    part_id = Column(String, ForeignKey("part.id"), nullable=False)
    qty = Column(Numeric(10, 4), nullable=False)
    bom_qty = Column(Numeric(10, 4), nullable=True)
    note = Column(Text, nullable=True)


class HandcraftJewelryItem(Base):
    __tablename__ = "handcraft_jewelry_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    handcraft_order_id = Column(String, ForeignKey("handcraft_order.id"), nullable=False)
    jewelry_id = Column(String, ForeignKey("jewelry.id"), nullable=False)
    qty = Column(Integer, nullable=False)
    received_qty = Column(Integer, nullable=True, default=0)
    status = Column(String, nullable=False, default="未送出")
    note = Column(Text, nullable=True)
```

---

## Task 11: models/__init__.py — 统一导出

**Files:**
- Create: `models/__init__.py`

**Step 1: Write models/__init__.py**

```python
from .part import Part
from .jewelry import Jewelry
from .bom import Bom
from .order import Order, OrderItem
from .inventory_log import InventoryLog
from .plating_order import PlatingOrder, PlatingOrderItem
from .handcraft_order import HandcraftOrder, HandcraftPartItem, HandcraftJewelryItem

__all__ = [
    "Part",
    "Jewelry",
    "Bom",
    "Order",
    "OrderItem",
    "InventoryLog",
    "PlatingOrder",
    "PlatingOrderItem",
    "HandcraftOrder",
    "HandcraftPartItem",
    "HandcraftJewelryItem",
]
```

---

## Task 12: services/__init__.py, api/__init__.py, bot stubs

**Files:**
- Create: `services/__init__.py`
- Create: `api/__init__.py`
- Create: `bot/__init__.py`
- Create: `bot/handlers.py`
- Create: `bot/middleware.py`
- Create: `bot/agent/__init__.py`
- Create: `bot/agent/runner.py`
- Create: `bot/agent/tools.py`

**Step 1: Create all stub files**

`services/__init__.py` — empty

`api/__init__.py` — empty

`bot/__init__.py` — empty

`bot/handlers.py`:
```python
# Telegram bot message handlers (to be implemented)
```

`bot/middleware.py`:
```python
# User whitelist and rate limiting middleware (to be implemented)
```

`bot/agent/__init__.py` — empty

`bot/agent/runner.py`:
```python
# Claude Agent agentic loop (to be implemented)
```

`bot/agent/tools.py`:
```python
# Tool definitions callable by the bot (to be implemented)
```

---

## Task 13: main.py — FastAPI app entry point

**Files:**
- Create: `main.py`

**Step 1: Write main.py**

```python
import uvicorn
from fastapi import FastAPI

import models  # noqa: F401 — ensures all models are registered with Base.metadata
from database import Base, engine

app = FastAPI(title="Allen Shop", description="饰品店管理系统")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


# TODO: register routers
# from api import parts, jewelries, bom, inventory, orders, plating, handcraft
# app.include_router(parts.router)
# app.include_router(jewelries.router)
# ...


@app.get("/")
def root():
    return {"status": "ok", "app": "Allen Shop"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

**Step 2: Install dependencies**

```bash
pip install fastapi uvicorn[standard] sqlalchemy pydantic-settings python-dotenv
```

**Step 3: Start the server**

```bash
uvicorn main:app --reload
```

Expected output (no errors):
```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

**Step 4: Verify database was created**

```bash
python -c "
import sqlite3, sys
conn = sqlite3.connect('allen_shop.db')
tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\").fetchall()
expected = {'bom','handcraft_jewelry_item','handcraft_order','handcraft_part_item',
            'inventory_log','jewelry','order','order_item','part',
            'plating_order','plating_order_item'}
found = {t[0] for t in tables}
missing = expected - found
if missing:
    print('MISSING:', missing); sys.exit(1)
print('All', len(found), 'tables present:', sorted(found))
conn.close()
"
```

Expected: `All 11 tables present: [...]`

---

## Completion Criteria

- [ ] `uvicorn main:app` starts without errors
- [ ] `allen_shop.db` is auto-created on startup
- [ ] All 11 tables present in the database
- [ ] No service or API logic implemented (stubs only)
- [ ] No extra files beyond the specified structure
