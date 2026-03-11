import anthropic
from sqlalchemy.orm import Session

from bot.agent.tools import TOOLS, execute_tool
from config import settings

_SYSTEM_PROMPT = """你是 Allen Shop 的智能助手，帮助店主管理配件库存、饰品、订单、电镀单和手工单。
用简洁的中文回复。数字保留两位小数。
ID 格式：PJ-配件，SP-饰品，OR-订单，EP-电镀单，HC-手工单。"""

_MODEL = "claude-sonnet-4-5-20250929"
_MAX_ITERATIONS = 10


async def run_agent(user_message: str, db: Session) -> str:
    """Run the Claude agentic loop and return the final text response."""
    client = anthropic.AsyncAnthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        **({"base_url": settings.ANTHROPIC_BASE_URL} if settings.ANTHROPIC_BASE_URL else {}),
    )
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
