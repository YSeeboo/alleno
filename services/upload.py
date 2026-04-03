import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from config import settings
from schemas.upload import UploadPolicyResponse

ALLOWED_KINDS = {
    "part": "parts",
    "jewelry": "jewelries",
    "plating": "plating-orders",
    "handcraft": "handcraft-orders",
    "purchase-orders": "purchase-orders",
    "plating-receipts": "plating-receipts",
    "handcraft-receipts": "handcraft-receipts",
    "jewelry-template": "jewelry-templates",
    "order": "orders",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value or "").strip("-").lower()
    return cleaned or "item"


def _normalize_extension(filename: str, content_type: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in ALLOWED_EXTENSIONS:
        return ext

    fallback_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    if content_type in fallback_map:
        return fallback_map[content_type]
    raise ValueError("仅支持 jpg、jpeg、png、webp、gif 格式图片")


def build_upload_policy(kind: str, filename: str, content_type: str = "", entity_id: Optional[str] = None) -> UploadPolicyResponse:
    if not settings.oss_enabled:
        raise ValueError("OSS 未配置完成")
    if kind not in ALLOWED_KINDS:
        raise ValueError("仅支持配件、饰品、电镀单、电镀回收单、手工单、手工回收单和采购单图片上传")

    ext = _normalize_extension(filename, content_type)
    now = datetime.now(timezone.utc)
    expire_at = int(time.time()) + 600
    prefix = ALLOWED_KINDS[kind]
    entity_segment = _safe_name(entity_id or "draft")
    key = f"{prefix}/{entity_segment}/{now.strftime('%Y%m%d')}/{uuid.uuid4().hex}{ext}"

    policy_dict = {
        "expiration": datetime.fromtimestamp(expire_at, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conditions": [
            {"bucket": settings.OSS_BUCKET},
            ["starts-with", "$key", f"{prefix}/"],
            ["content-length-range", 1, MAX_UPLOAD_SIZE],
            ["starts-with", "$Content-Type", "image/"],
            {"success_action_status": "200"},
        ],
    }
    policy = base64.b64encode(json.dumps(policy_dict).encode("utf-8")).decode("utf-8")
    digest = hmac.new(settings.OSS_ACCESS_KEY_SECRET.encode("utf-8"), policy.encode("utf-8"), hashlib.sha1).digest()
    signature = base64.b64encode(digest).decode("utf-8")

    return UploadPolicyResponse(
        host=settings.oss_upload_host,
        key=key,
        policy=policy,
        signature=signature,
        oss_access_key_id=settings.OSS_ACCESS_KEY_ID,
        public_url=f"{settings.oss_public_base_url}/{key}",
        expire_at=expire_at,
    )
