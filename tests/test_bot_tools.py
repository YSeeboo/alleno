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
    part = create_part(db, {"name": "铜扣", "category": "小配件"})
    add_stock(db, "part", part.id, 100.0, "入库")
    result = execute_tool("get_stock", {"item_type": "part", "item_id": part.id}, db)
    assert "100" in result


def test_execute_tool_get_stock_log(db):
    from bot.agent.tools import execute_tool
    part = create_part(db, {"name": "铜扣", "category": "小配件"})
    add_stock(db, "part", part.id, 100.0, "入库")
    result = execute_tool("get_stock_log", {"item_type": "part", "item_id": part.id}, db)
    assert "入库" in result


def test_execute_tool_unknown_tool(db):
    from bot.agent.tools import execute_tool
    result = execute_tool("nonexistent_tool", {}, db)
    assert "unknown tool" in result.lower() or "未知" in result


def test_execute_tool_handles_service_error(db):
    """deduct_stock from empty inventory returns error string, not exception."""
    from bot.agent.tools import execute_tool
    part = create_part(db, {"name": "铜扣", "category": "小配件"})
    result = execute_tool("deduct_stock", {
        "item_type": "part", "item_id": part.id, "qty": 999.0, "reason": "出库"
    }, db)
    assert isinstance(result, str)
    # Should be an error message, not raise


def test_execute_tool_get_parts_summary(db):
    """get_parts_summary returns a formatted multi-line string, not an error.
    Regression: prior code did `for k, v in summary.items()` but
    get_parts_summary has returned list[dict] for a long time, so the bot
    path silently returned 'list object has no attribute items' for every
    parts summary call."""
    from bot.agent.tools import execute_tool
    from services.jewelry import create_jewelry
    from services.bom import set_bom

    part_a = create_part(db, {"name": "A珠", "category": "小配件"})
    jewelry = create_jewelry(db, {"name": "项链", "retail_price": 100.0, "category": "单件"})
    set_bom(db, jewelry.id, part_a.id, 5)
    # Create order via the API would commit; service-level path is enough
    # for this regression because the bug was in formatting, not the query.
    from services.order import create_order
    order = create_order(
        db,
        customer_name="客户",
        items=[{"jewelry_id": jewelry.id, "quantity": 10, "unit_price": 5.0}],
    )
    db.flush()

    result = execute_tool("get_parts_summary", {"order_id": order.id}, db)
    assert isinstance(result, str)
    assert "错误" not in result, f"unexpected error: {result}"
    assert "list" not in result.lower(), f"raw repr leaked: {result}"
    assert part_a.id in result
    # Format check: should mention 总需求 and one of the status tags
    assert "总需求" in result
    assert ("缺料" in result) or ("全局紧张" in result) or ("充足" in result)
