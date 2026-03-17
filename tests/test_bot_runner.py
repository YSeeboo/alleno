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
    from services.part import create_part
    part = create_part(db, {"name": "铜扣", "category": "小配件"})
    add_stock(db, "part", part.id, 100.0, "入库")

    tool_resp, final_resp = _make_tool_response(
        "get_stock", "tool_1",
        {"item_type": "part", "item_id": part.id},
        f"{part.id} 当前库存为 100.00"
    )
    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=[tool_resp, final_resp])

    with patch("bot.agent.runner.anthropic.AsyncAnthropic", return_value=mock_client):
        result = await run_agent(f"{part.id} 还有多少？", db)

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
