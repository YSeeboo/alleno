# api/plating_summary.py
from datetime import date as date_type
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas.plating_summary import DispatchedListResponse, ReceivedListResponse
from services.plating_summary import list_dispatched, list_received

router = APIRouter(prefix="/api/plating-summary", tags=["plating-summary"])


@router.get("/dispatched", response_model=DispatchedListResponse)
def api_list_dispatched(
    supplier_name: Optional[str] = Query(None),
    date_from: Optional[date_type] = Query(None),
    date_to: Optional[date_type] = Query(None),
    part_keyword: Optional[str] = Query(None),
    sort: Literal["dispatch_date_desc", "days_out_desc"] = Query("dispatch_date_desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items, total = list_dispatched(
        db, supplier_name=supplier_name,
        date_from=date_from, date_to=date_to,
        part_keyword=part_keyword, sort=sort,
        skip=skip, limit=limit,
    )
    return {"items": items, "total": total}


@router.get("/received", response_model=ReceivedListResponse)
def api_list_received(
    supplier_name: Optional[str] = Query(None),
    date_from: Optional[date_type] = Query(None),
    date_to: Optional[date_type] = Query(None),
    part_keyword: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    items, total = list_received(
        db, supplier_name=supplier_name,
        date_from=date_from, date_to=date_to,
        part_keyword=part_keyword,
        skip=skip, limit=limit,
    )
    return {"items": items, "total": total}
