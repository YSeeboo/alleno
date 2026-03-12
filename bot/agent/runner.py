import json
import logging

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from bot.agent.tools import TOOLS, execute_tool
from config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是 Allen Shop 的智能助手，帮助店主管理配件库存、饰品、订单、电镀单和手工单。
用简洁的中文回复。数字保留两位小数。
ID 格式：PJ-配件，SP-饰品，OR-订单，EP-电镀单，HC-手工单。"""

_MODEL = "deepseek-chat"
_MAX_ITERATIONS = 10


async def run_agent(user_message: str, db: Session) -> str:
    """Run the DeepSeek agentic loop and return the final text response."""
    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    for _ in range(_MAX_ITERATIONS):
        response = await client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        choice = response.choices[0]
        msg = choice.message

        # Append assistant turn
        assistant_turn = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_turn["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_turn)

        if choice.finish_reason == "stop":
            return msg.content or ""

        if choice.finish_reason == "tool_calls":
            for tc in msg.tool_calls:
                try:
                    inputs = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    inputs = {}
                result = execute_tool(tc.function.name, inputs, db)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

    return "处理超时，请重试。"
