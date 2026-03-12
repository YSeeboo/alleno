from fastapi import APIRouter, Depends, HTTPException

from database import get_db
from schemas.upload import UploadPolicyRequest, UploadPolicyResponse
from services.upload import build_upload_policy

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/policy", response_model=UploadPolicyResponse)
def api_get_upload_policy(body: UploadPolicyRequest, _db=Depends(get_db)):
    try:
        return build_upload_policy(
            kind=body.kind,
            filename=body.filename,
            content_type=body.content_type,
            entity_id=body.entity_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
