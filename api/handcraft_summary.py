from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas.handcraft_summary import DispatchedListResponse, ReceivedListResponse
from services.handcraft_summary import list_dispatched, list_received

router = APIRouter(prefix="/api/handcraft-summary", tags=["handcraft-summary"])


def summary_filters(
    supplier_name: str | None = None, date_from: date | None = None, date_to: date | None = None,
    part_id: str | None = Query(None, max_length=200),
    output_id: str | None = Query(None, max_length=200),
    order_id: str | None = Query(None, max_length=200),
    archive: Literal["active", "archived", "all"] = "active",
    skip: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=200),
):
    return dict(supplier_name=supplier_name, date_from=date_from, date_to=date_to,
                part_id=part_id, output_id=output_id, order_id=order_id, archive=archive, skip=skip, limit=limit)


@router.get("/dispatched", response_model=DispatchedListResponse)
def dispatched(filters: dict = Depends(summary_filters),
               sort: Literal["dispatch_date_desc", "days_out_desc"] = "dispatch_date_desc",
               db: Session = Depends(get_db)):
    items, total = list_dispatched(db, **filters, sort=sort)
    return dict(items=items, total=total)


@router.get("/received", response_model=ReceivedListResponse)
def received(filters: dict = Depends(summary_filters), db: Session = Depends(get_db)):
    items, total = list_received(db, **filters)
    return dict(items=items, total=total)
