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
