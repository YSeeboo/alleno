from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.restock import (
    RestockHistoryItem,
    RestockMarkPartDoneRequest,
    RestockMarkPartDoneResponse,
    RestockRequestCreate,
    RestockRequestPatch,
    RestockRequestRead,
    RestockSummaryItem,
)
from services.restock import (
    create_from_picking,
    create_manual,
    delete_pending,
    list_history,
    list_pending_summary,
    mark_done,
    mark_part_done,
)

router = APIRouter(prefix="/api/restock-requests", tags=["restock"])


@router.post("", response_model=RestockRequestRead)
def api_create_restock(payload: RestockRequestCreate, db: Session = Depends(get_db)):
    if payload.handcraft_order_id is None:
        # First version: handcraft_order_id is required from the UI even though
        # the schema permits null (reserved for future use).
        with service_errors():
            raise ValueError("handcraft_order_id 不能为空")
    with service_errors():
        if payload.source == "picking":
            return create_from_picking(db, payload.part_id, payload.handcraft_order_id)
        return create_manual(db, payload.part_id, payload.handcraft_order_id, payload.note)


@router.patch("/{request_id}", response_model=RestockRequestRead)
def api_mark_done(request_id: int, payload: RestockRequestPatch, db: Session = Depends(get_db)):
    # The schema fixes status to literal "done" so we don't need to branch.
    with service_errors():
        return mark_done(db, request_id)


@router.delete("/{request_id}", status_code=204)
def api_delete_pending(request_id: int, db: Session = Depends(get_db)):
    with service_errors():
        delete_pending(db, request_id)


@router.post("/mark-part-done", response_model=RestockMarkPartDoneResponse)
def api_mark_part_done(payload: RestockMarkPartDoneRequest, db: Session = Depends(get_db)):
    with service_errors():
        count = mark_part_done(db, payload.part_id)
    return RestockMarkPartDoneResponse(updated=count)


@router.get("/summary", response_model=list[RestockSummaryItem])
def api_list_summary(db: Session = Depends(get_db)):
    return list_pending_summary(db)


@router.get("/history", response_model=list[RestockHistoryItem])
def api_list_history(
    part_id: Optional[str] = None,
    handcraft_order_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return list_history(db, part_id=part_id, handcraft_order_id=handcraft_order_id, limit=limit)
