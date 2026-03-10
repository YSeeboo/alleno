# Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a Telegram bot with whitelist/rate-limit middleware, a Claude-powered agentic tool loop, and a FastAPI lifespan integration.

**Architecture:** `bot/middleware.py` holds two `BaseMiddleware` subclasses; `bot/agent/tools.py` defines the 12 Claude tools and an `execute_tool` dispatcher; `bot/agent/runner.py` runs the async agentic loop using `anthropic.AsyncAnthropic`; `bot/handlers.py` wires message handling; `main.py` starts the bot in a background thread from FastAPI's lifespan event.

**Tech Stack:** python-telegram-bot v20+ (`BaseMiddleware`, `ApplicationBuilder`), Anthropic Python SDK (`AsyncAnthropic`), SQLAlchemy Session (shared with API layer via `SessionLocal`).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `bot/middleware.py` | Implement | `WhitelistMiddleware`, `RateLimitMiddleware` |
| `bot/agent/tools.py` | Implement | `TOOLS` list (12 tool defs) + `execute_tool()` dispatcher |
| `bot/agent/runner.py` | Implement | `run_agent(user_message, db) -> str` async agentic loop |
| `bot/handlers.py` | Implement | `handle_message`, `handle_error` |
| `main.py` | Modify | Start bot in background thread from lifespan; only if token set |
| `tests/test_bot_middleware.py` | Create | Unit tests for whitelist + rate limiting |
| `tests/test_bot_tools.py` | Create | Unit tests for `execute_tool` routing |
| `tests/test_bot_runner.py` | Create | Unit tests for agentic loop with mocked Anthropic client |

---

## Chunk 1: Middleware

### Task 1: WhitelistMiddleware and RateLimitMiddleware

**Files:**
- Implement: `bot/middleware.py`
- Create: `tests/test_bot_middleware.py`

**Context:** `python-telegram-bot` v20 `BaseMiddleware` is at `telegram.ext.BaseMiddleware`. Override `process_update(update, next_handler)`. The `block=True` constructor arg tells the framework to await the middleware before processing the next update.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bot_middleware.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_update(user_id: int, text: str = "hello"):
    """Build a minimal mock Update object."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = text
    return update


@pytest.mark.asyncio
async def test_whitelist_allows_listed_user():
    from bot.middleware import WhitelistMiddleware
    with patch("bot.middleware.settings") as mock_settings:
        mock_settings.telegram_whitelist_ids = [111]
        mw = WhitelistMiddleware()
        update = _make_update(111)
        next_handler = AsyncMock()
        await mw.process_update(update, next_handler)
        next_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_whitelist_blocks_unlisted_user():
    from bot.middleware import WhitelistMiddleware
    with patch("bot.middleware.settings") as mock_settings:
        mock_settings.telegram_whitelist_ids = [111]
        mw = WhitelistMiddleware()
        update = _make_update(999)
        next_handler = AsyncMock()
        await mw.process_update(update, next_handler)
        next_handler.assert_not_awaited()
        update.message.reply_text.assert_awaited_once_with("无权限访问")


@pytest.mark.asyncio
async def test_whitelist_empty_allows_all():
    """Empty whitelist means no restriction."""
    from bot.middleware import WhitelistMiddleware
    with patch("bot.middleware.settings") as mock_settings:
        mock_settings.telegram_whitelist_ids = []
        mw = WhitelistMiddleware()
        update = _make_update(999)
        next_handler = AsyncMock()
        await mw.process_update(update, next_handler)
        next_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limit_allows_first_message():
    from bot.middleware import RateLimitMiddleware
    mw = RateLimitMiddleware()
    update = _make_update(111)
    next_handler = AsyncMock()
    await mw.process_update(update, next_handler)
    next_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limit_silently_blocks_rapid_second():
    from bot.middleware import RateLimitMiddleware
    mw = RateLimitMiddleware()
    update = _make_update(111)
    next_handler = AsyncMock()
    await mw.process_update(update, next_handler)  # first — allowed
    next_handler.reset_mock()
    await mw.process_update(update, next_handler)  # immediate second — blocked
    next_handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_rate_limit_allows_after_cooldown():
    from bot.middleware import RateLimitMiddleware
    mw = RateLimitMiddleware()
    update = _make_update(111)
    next_handler = AsyncMock()
    # Set last_seen to 5 seconds ago
    mw._last_seen[111] = time.time() - 5.0
    await mw.process_update(update, next_handler)
    next_handler.assert_awaited_once()
```

- [ ] **Step 2: Run to verify failures**

```bash
cd /Users/ycb/workspace/allen_shop && DATABASE_URL=sqlite:///./test.db python -m pytest tests/test_bot_middleware.py -v
```
Expected: ImportError or AttributeError — middleware not implemented.

- [ ] **Step 3: Implement `bot/middleware.py`**

```python
import time
from typing import Callable, Dict

from telegram import Update
from telegram.ext import BaseMiddleware

from config import settings


class WhitelistMiddleware(BaseMiddleware):
    """Allow only users whose Telegram user_id is in the whitelist.

    If the whitelist is empty, all users are allowed (useful for development).
    """

    def __init__(self):
        super().__init__(block=True)

    async def process_update(self, update: Update, next_handler: Callable) -> None:
        whitelist = settings.telegram_whitelist_ids
        if whitelist:
            user_id = update.effective_user.id if update.effective_user else None
            if user_id not in whitelist:
                if update.message:
                    await update.message.reply_text("无权限访问")
                return
        await next_handler(update)


class RateLimitMiddleware(BaseMiddleware):
    """Allow each user at most 1 message per 3 seconds.

    Excess messages are silently ignored (no reply sent).
    """

    COOLDOWN_SECONDS = 3.0

    def __init__(self):
        super().__init__(block=True)
        self._last_seen: Dict[int, float] = {}

    async def process_update(self, update: Update, next_handler: Callable) -> None:
        user_id = update.effective_user.id if update.effective_user else None
        if user_id is not None:
            now = time.time()
            last = self._last_seen.get(user_id, 0.0)
            if now - last < self.COOLDOWN_SECONDS:
                return  # silent ignore
            self._last_seen[user_id] = now
        await next_handler(update)
```

- [ ] **Step 4: Install pytest-asyncio if not present**

```bash
cd /Users/ycb/workspace/allen_shop && python -m pip install pytest-asyncio --quiet
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && DATABASE_URL=sqlite:///./test.db python -m pytest tests/test_bot_middleware.py -v
```

If `asyncio mode` error, add to `tests/conftest.py`:
```python
import pytest
# at bottom of file
```
And create/update `pytest.ini` or `pyproject.toml` with:
```
[pytest]
asyncio_mode = auto
```
Or add a `pytest.ini` file:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 6: Commit**

```bash
git add bot/middleware.py tests/test_bot_middleware.py
git commit -m "feat: implement whitelist and rate-limit Telegram middleware"
```

---

## Chunk 2: Tool definitions and execute_tool dispatcher

### Task 2: Tools

**Files:**
- Implement: `bot/agent/tools.py`
- Create: `tests/test_bot_tools.py`

**Context:** The `TOOLS` list is in Anthropic SDK format — each entry is a dict with `name`, `description`, `input_schema`. The `execute_tool` function dispatches to service functions and returns a human-readable string. It must never raise — all exceptions become error strings.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bot_tools.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.part import create_part
from services.inventory import add_stock


def test_tools_list_has_required_tools(db):
    from bot.agent.tools import TOOLS
    tool_names = {t["name"] for t in TOOLS}
    required = {
        "get_stock", "get_stock_log", "add_stock", "deduct_stock",
        "get_order", "get_order_items", "get_parts_summary", "update_order_status",
        "get_plating_order", "receive_plating_items",
        "get_handcraft_order", "receive_handcraft_jewelries",
    }
    assert required.issubset(tool_names)


def test_tools_have_required_keys(db):
    from bot.agent.tools import TOOLS
    for tool in TOOLS:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"


def test_execute_tool_get_stock(db):
    from bot.agent.tools import execute_tool
    create_part(db, {"name": "铜扣"})
    add_stock(db, "part", "PJ-0001", 100.0, "入库")
    result = execute_tool("get_stock", {"item_type": "part", "item_id": "PJ-0001"}, db)
    assert "100" in result


def test_execute_tool_get_stock_log(db):
    from bot.agent.tools import execute_tool
    add_stock(db, "part", "PJ-0001", 100.0, "入库")
    result = execute_tool("get_stock_log", {"item_type": "part", "item_id": "PJ-0001"}, db)
    assert "入库" in result


def test_execute_tool_unknown_tool(db):
    from bot.agent.tools import execute_tool
    result = execute_tool("nonexistent_tool", {}, db)
    assert "unknown tool" in result.lower() or "未知" in result


def test_execute_tool_handles_service_error(db):
    """deduct_stock from empty inventory returns error string, not exception."""
    from bot.agent.tools import execute_tool
    result = execute_tool("deduct_stock", {
        "item_type": "part", "item_id": "PJ-0001", "qty": 999.0, "reason": "出库"
    }, db)
    assert "库存不足" in result or "error" in result.lower()
```

- [ ] **Step 2: Run to verify failures**

```bash
cd /Users/ycb/workspace/allen_shop && DATABASE_URL=sqlite:///./test.db python -m pytest tests/test_bot_tools.py -v
```

- [ ] **Step 3: Implement `bot/agent/tools.py`**

```python
"""
Tool definitions for the Claude agent and the execute_tool dispatcher.
"""
import json
from typing import Any, Dict

from sqlalchemy.orm import Session

from services import inventory as inv_svc
from services import order as order_svc
from services import plating as plating_svc
from services import handcraft as handcraft_svc


# ---------------------------------------------------------------------------
# Tool definitions (Anthropic SDK format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_stock",
        "description": "查询配件或饰品的当前库存数量",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_type": {"type": "string", "description": "part 或 jewelry"},
                "item_id": {"type": "string", "description": "物品 ID，如 PJ-0001"},
            },
            "required": ["item_type", "item_id"],
        },
    },
    {
        "name": "get_stock_log",
        "description": "查询配件或饰品的最近 20 条库存流水记录",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_type": {"type": "string"},
                "item_id": {"type": "string"},
            },
            "required": ["item_type", "item_id"],
        },
    },
    {
        "name": "add_stock",
        "description": "手动入库：增加配件或饰品的库存",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_type": {"type": "string"},
                "item_id": {"type": "string"},
                "qty": {"type": "number", "description": "入库数量（正数）"},
                "reason": {"type": "string", "description": "入库原因"},
                "note": {"type": "string"},
            },
            "required": ["item_type", "item_id", "qty", "reason"],
        },
    },
    {
        "name": "deduct_stock",
        "description": "手动出库：减少配件或饰品的库存",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_type": {"type": "string"},
                "item_id": {"type": "string"},
                "qty": {"type": "number"},
                "reason": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["item_type", "item_id", "qty", "reason"],
        },
    },
    {
        "name": "get_order",
        "description": "查询订单的基本信息（状态、金额、客户名称等）",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单 ID，如 OR-0001"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "get_order_items",
        "description": "查询订单中的饰品清单",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "get_parts_summary",
        "description": "查询订单所需配件的汇总（按 BOM 计算各配件总需求量）",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "update_order_status",
        "description": "更新订单状态，可选值：待生产、生产中、已完成",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "status": {"type": "string", "enum": ["待生产", "生产中", "已完成"]},
            },
            "required": ["order_id", "status"],
        },
    },
    {
        "name": "get_plating_order",
        "description": "查询电镀单的状态和明细（包括各配件发出量、已收回量）",
        "input_schema": {
            "type": "object",
            "properties": {
                "plating_order_id": {"type": "string", "description": "电镀单 ID，如 EP-0001"},
            },
            "required": ["plating_order_id"],
        },
    },
    {
        "name": "receive_plating_items",
        "description": "登记电镀收回：记录已收回的配件数量",
        "input_schema": {
            "type": "object",
            "properties": {
                "plating_order_id": {"type": "string"},
                "receipts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "plating_order_item_id": {"type": "integer"},
                            "qty": {"type": "number"},
                        },
                        "required": ["plating_order_item_id", "qty"],
                    },
                },
            },
            "required": ["plating_order_id", "receipts"],
        },
    },
    {
        "name": "get_handcraft_order",
        "description": "查询手工单的状态和明细",
        "input_schema": {
            "type": "object",
            "properties": {
                "handcraft_order_id": {"type": "string", "description": "手工单 ID，如 HC-0001"},
            },
            "required": ["handcraft_order_id"],
        },
    },
    {
        "name": "receive_handcraft_jewelries",
        "description": "登记手工成品收回：记录已完成的饰品数量",
        "input_schema": {
            "type": "object",
            "properties": {
                "handcraft_order_id": {"type": "string"},
                "receipts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "handcraft_jewelry_item_id": {"type": "integer"},
                            "qty": {"type": "integer"},
                        },
                        "required": ["handcraft_jewelry_item_id", "qty"],
                    },
                },
            },
            "required": ["handcraft_order_id", "receipts"],
        },
    },
]


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _to_str(obj: Any) -> str:
    """Convert a service return value to a human-readable string."""
    if obj is None:
        return "未找到"
    if isinstance(obj, (int, float, str)):
        return str(obj)
    if isinstance(obj, dict):
        return json.dumps(obj, ensure_ascii=False, indent=2)
    if isinstance(obj, list):
        if not obj:
            return "（无记录）"
        rows = []
        for item in obj[:20]:  # cap at 20 items
            if hasattr(item, "__dict__"):
                rows.append({k: v for k, v in item.__dict__.items() if not k.startswith("_")})
            else:
                rows.append(str(item))
        return json.dumps(rows, ensure_ascii=False, default=str, indent=2)
    if hasattr(obj, "__dict__"):
        data = {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
        return json.dumps(data, ensure_ascii=False, default=str, indent=2)
    return str(obj)


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------

def execute_tool(tool_name: str, tool_input: Dict[str, Any], db: Session) -> str:
    """Dispatch a tool call to the corresponding service function.

    Always returns a string. Never raises — exceptions become error messages.
    """
    try:
        if tool_name == "get_stock":
            result = inv_svc.get_stock(db, tool_input["item_type"], tool_input["item_id"])
            return f"当前库存：{result}"

        elif tool_name == "get_stock_log":
            logs = inv_svc.get_stock_log(db, tool_input["item_type"], tool_input["item_id"])
            return _to_str(logs[:20])

        elif tool_name == "add_stock":
            log = inv_svc.add_stock(
                db,
                tool_input["item_type"],
                tool_input["item_id"],
                tool_input["qty"],
                tool_input["reason"],
                tool_input.get("note"),
            )
            return f"入库成功：+{tool_input['qty']}，当前库存 {inv_svc.get_stock(db, tool_input['item_type'], tool_input['item_id'])}"

        elif tool_name == "deduct_stock":
            inv_svc.deduct_stock(
                db,
                tool_input["item_type"],
                tool_input["item_id"],
                tool_input["qty"],
                tool_input["reason"],
                tool_input.get("note"),
            )
            return f"出库成功：-{tool_input['qty']}，当前库存 {inv_svc.get_stock(db, tool_input['item_type'], tool_input['item_id'])}"

        elif tool_name == "get_order":
            order = order_svc.get_order(db, tool_input["order_id"])
            return _to_str(order)

        elif tool_name == "get_order_items":
            items = order_svc.get_order_items(db, tool_input["order_id"])
            return _to_str(items)

        elif tool_name == "get_parts_summary":
            summary = order_svc.get_parts_summary(db, tool_input["order_id"])
            return json.dumps(summary, ensure_ascii=False, indent=2)

        elif tool_name == "update_order_status":
            order = order_svc.update_order_status(db, tool_input["order_id"], tool_input["status"])
            return f"订单 {tool_input['order_id']} 状态已更新为：{order.status}"

        elif tool_name == "get_plating_order":
            order = plating_svc.get_plating_order(db, tool_input["plating_order_id"])
            return _to_str(order)

        elif tool_name == "receive_plating_items":
            updated = plating_svc.receive_plating_items(
                db, tool_input["plating_order_id"], tool_input["receipts"]
            )
            return f"已登记收回 {len(updated)} 条明细"

        elif tool_name == "get_handcraft_order":
            order = handcraft_svc.get_handcraft_order(db, tool_input["handcraft_order_id"])
            return _to_str(order)

        elif tool_name == "receive_handcraft_jewelries":
            updated = handcraft_svc.receive_handcraft_jewelries(
                db, tool_input["handcraft_order_id"], tool_input["receipts"]
            )
            return f"已登记收回 {len(updated)} 件饰品"

        else:
            return f"未知工具：{tool_name}"

    except Exception as e:
        return f"执行失败：{e}"
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && DATABASE_URL=sqlite:///./test.db python -m pytest tests/test_bot_tools.py -v
```

- [ ] **Step 5: Commit**

```bash
git add bot/agent/tools.py tests/test_bot_tools.py
git commit -m "feat: implement bot tool definitions and execute_tool dispatcher"
```

---

## Chunk 3: Agentic loop, handlers, main.py integration

### Task 3: Runner (agentic loop)

**Files:**
- Implement: `bot/agent/runner.py`
- Create: `tests/test_bot_runner.py`

**Context:** Uses `anthropic.AsyncAnthropic`. The loop exits on `stop_reason == "end_turn"` (return last text block) or after 10 iterations. Tool calls are processed synchronously within the async function using `execute_tool`. The model id is `claude-opus-4-5`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_bot_runner.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_text_response(text: str):
    """Mock a Claude response with stop_reason=end_turn and a text block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [block]
    return response


def _make_tool_response(tool_name: str, tool_id: str, tool_input: dict, follow_up_text: str):
    """Mock a Claude response that makes one tool call then ends."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = tool_id
    tool_block.name = tool_name
    tool_block.input = tool_input

    tool_response = MagicMock()
    tool_response.stop_reason = "tool_use"
    tool_response.content = [tool_block]

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = follow_up_text
    final_response = MagicMock()
    final_response.stop_reason = "end_turn"
    final_response.content = [text_block]

    return tool_response, final_response


@pytest.mark.asyncio
async def test_runner_single_turn(db):
    """End-turn response returns text immediately."""
    from bot.agent.runner import run_agent
    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=_make_text_response("库存是 100"))

    with patch("bot.agent.runner.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await run_agent("PJ-0001 还有多少？", db)

    assert result == "库存是 100"
    assert mock_client.messages.create.call_count == 1


@pytest.mark.asyncio
async def test_runner_tool_use_loop(db):
    """Tool use: runner executes tool, sends result, gets final response."""
    from bot.agent.runner import run_agent
    from services.inventory import add_stock
    add_stock(db, "part", "PJ-0001", 100.0, "入库")

    tool_resp, final_resp = _make_tool_response(
        "get_stock", "tool_1",
        {"item_type": "part", "item_id": "PJ-0001"},
        "PJ-0001 当前库存为 100.00"
    )
    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=[tool_resp, final_resp])

    with patch("bot.agent.runner.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await run_agent("PJ-0001 还有多少？", db)

    assert "100" in result
    assert mock_client.messages.create.call_count == 2


@pytest.mark.asyncio
async def test_runner_max_iterations(db):
    """Loop exits after 10 iterations even if model keeps calling tools."""
    from bot.agent.runner import run_agent

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "t1"
    tool_block.name = "get_stock"
    tool_block.input = {"item_type": "part", "item_id": "PJ-0001"}

    infinite_tool_response = MagicMock()
    infinite_tool_response.stop_reason = "tool_use"
    infinite_tool_response.content = [tool_block]

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=infinite_tool_response)

    with patch("bot.agent.runner.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await run_agent("loop forever", db)

    assert "超时" in result or "重试" in result
    assert mock_client.messages.create.call_count == 10
```

- [ ] **Step 2: Run to verify failures**

```bash
cd /Users/ycb/workspace/allen_shop && DATABASE_URL=sqlite:///./test.db python -m pytest tests/test_bot_runner.py -v
```

- [ ] **Step 3: Implement `bot/agent/runner.py`**

```python
import anthropic
from sqlalchemy.orm import Session

from bot.agent.tools import TOOLS, execute_tool
from config import settings

_SYSTEM_PROMPT = """你是 Allen Shop 的智能助手，帮助店主管理配件库存、饰品、订单、电镀单和手工单。
用简洁的中文回复。数字保留两位小数。
ID 格式：PJ-配件，SP-饰品，OR-订单，EP-电镀单，HC-手工单。"""

_MODEL = "claude-opus-4-5"
_MAX_ITERATIONS = 10


async def run_agent(user_message: str, db: Session) -> str:
    """Run the Claude agentic loop and return the final text response."""
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": user_message}]

    for _ in range(_MAX_ITERATIONS):
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        if response.stop_reason == "tool_use":
            # Append assistant turn
            messages.append({"role": "assistant", "content": response.content})
            # Execute each tool call and collect results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_text = execute_tool(block.name, block.input, db)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })
            messages.append({"role": "user", "content": tool_results})

    return "处理超时，请重试。"
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/ycb/workspace/allen_shop && DATABASE_URL=sqlite:///./test.db python -m pytest tests/test_bot_runner.py -v
```

- [ ] **Step 5: Commit**

```bash
git add bot/agent/runner.py tests/test_bot_runner.py
git commit -m "feat: implement Claude agentic loop in run_agent"
```

---

### Task 4: Message handler

**Files:**
- Implement: `bot/handlers.py`

No automated tests (requires live Telegram connection); logic is verified via the runner tests. The code is short and straightforward.

- [ ] **Step 1: Implement `bot/handlers.py`**

```python
import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.agent.runner import run_agent

logger = logging.getLogger(__name__)

_MAX_MSG_LEN = 4096


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process an incoming text message through the Claude agent."""
    db_factory = context.bot_data.get("db_factory")
    if db_factory is None:
        await update.message.reply_text("系统未就绪，请稍后重试。")
        return

    db = db_factory()
    try:
        text = update.message.text or ""
        response = await run_agent(text, db)
        db.commit()
    except Exception as exc:
        logger.exception("run_agent failed: %s", exc)
        db.rollback()
        response = "处理失败，请稍后重试。"
    finally:
        db.close()

    # Split long responses to respect Telegram's 4096-char limit
    for i in range(0, max(len(response), 1), _MAX_MSG_LEN):
        await update.message.reply_text(response[i : i + _MAX_MSG_LEN])


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify the user if possible."""
    logger.error("Telegram error: %s", context.error, exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("处理失败，请稍后重试。")
```

- [ ] **Step 2: Verify imports are clean**

```bash
cd /Users/ycb/workspace/allen_shop && DATABASE_URL=sqlite:///./test.db python -c "from bot.handlers import handle_message, handle_error; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add bot/handlers.py
git commit -m "feat: implement Telegram message handler with long-message splitting"
```

---

### Task 5: main.py — bot integration

**Files:**
- Modify: `main.py`

**Context:** The bot runs in a background thread using `threading.Thread`. It is only started if `TELEGRAM_BOT_TOKEN` is set (to avoid crashing in dev/test environments without a token). The `run_polling()` call blocks its thread. The FastAPI `lifespan` starts the thread as a daemon so it dies when the main process exits.

- [ ] **Step 1: Update `main.py`**

Replace the full `main.py` with:

```python
import logging
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

import models  # noqa: F401
from config import settings
from database import Base, SessionLocal, engine

from api import parts, jewelries, bom, inventory, orders, plating, handcraft

logger = logging.getLogger(__name__)


def start_bot() -> None:
    """Start the Telegram bot in blocking polling mode.

    Runs in a daemon thread so it exits when the main process exits.
    Only called when TELEGRAM_BOT_TOKEN is configured.
    """
    from telegram.ext import ApplicationBuilder, MessageHandler, filters

    from bot.handlers import handle_message, handle_error
    from bot.middleware import WhitelistMiddleware, RateLimitMiddleware

    bot_app = (
        ApplicationBuilder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .build()
    )
    bot_app.add_middleware(WhitelistMiddleware())
    bot_app.add_middleware(RateLimitMiddleware())
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    bot_app.add_error_handler(handle_error)
    bot_app.bot_data["db_factory"] = SessionLocal
    bot_app.run_polling()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.TELEGRAM_BOT_TOKEN:
        thread = threading.Thread(target=start_bot, daemon=True, name="telegram-bot")
        thread.start()
        logger.info("Telegram bot started in background thread")
    else:
        logger.info("TELEGRAM_BOT_TOKEN not set — bot disabled")
    yield


app = FastAPI(title="Allen Shop", description="饰品店管理系统", lifespan=lifespan)

app.include_router(parts.router, prefix="/api")
app.include_router(jewelries.router, prefix="/api")
app.include_router(bom.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(plating.router, prefix="/api")
app.include_router(handcraft.router, prefix="/api")


@app.get("/")
def root():
    return {"status": "ok", "app": "Allen Shop"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 2: Verify imports clean (no bot token needed)**

```bash
cd /Users/ycb/workspace/allen_shop && DATABASE_URL=sqlite:///./test.db python -c "from main import app; print('OK')"
```

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/ycb/workspace/allen_shop && DATABASE_URL=sqlite:///./test.db python -m pytest tests/ -v
```
Expected: all tests pass (bot thread not started in tests because no TELEGRAM_BOT_TOKEN).

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: integrate Telegram bot into FastAPI lifespan (background thread)"
```

- [ ] **Step 5: Final push**

```bash
git add -A
git commit -m "feat: Phase 5 complete — Telegram bot with middleware, tools, and agentic loop" --allow-empty
git push origin main
```
