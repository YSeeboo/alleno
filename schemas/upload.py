from typing import Optional

from pydantic import BaseModel


class UploadPolicyRequest(BaseModel):
    kind: str
    filename: str
    content_type: str = ""
    entity_id: Optional[str] = None


class UploadPolicyResponse(BaseModel):
    host: str
    key: str
    policy: str
    signature: str
    oss_access_key_id: str
    success_action_status: str = "200"
    public_url: str
    expire_at: int
