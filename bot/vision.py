import base64
import logging

import httpx
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

_FEISHU_API = "https://open.feishu.cn/open-apis"
_VISION_MODEL = "qwen-vl-plus"
_VISION_PROMPT = (
    "请描述这张图片中的物品，重点说明：外观特征、颜色、材质、形状。"
    "如果是饰品或配件，请详细描述其细节，用简洁的中文回答。"
)


async def download_feishu_image(message_id: str, image_key: str, token: str) -> bytes:
    """Download image bytes from Feishu message."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_FEISHU_API}/im/v1/messages/{message_id}/resources/{image_key}",
            params={"type": "image"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content


async def analyze_image(image_bytes: bytes) -> str:
    """Send image to Qwen-VL and return description."""
    b64 = base64.b64encode(image_bytes).decode()
    client = AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    response = await client.chat.completions.create(
        model=_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }
        ],
    )
    return response.choices[0].message.content or "无法识别图片内容"
