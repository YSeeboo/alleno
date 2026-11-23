from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas.handcraft_summary import DispatchedListResponse, ReceivedListResponse
from services.handcraft_summary import list_dispatched, list_received
from schemas.handcraft_output import OutputOverview, OutputSourceList, OutputReceiptList, OutputOptions
from services.handcraft_output import output_overview, output_sources, output_receipts, output_options

router = APIRouter(prefix="/api/handcraft-summary", tags=["handcraft-summary"])


def _output_keys(values):
    for value in values or []:
        kind, separator, product_id = value.partition(":")
        if kind not in ("jewelry", "part") or not separator or not product_id.strip() or len(product_id) > 200:
            raise HTTPException(422, "产出必须使用 jewelry:编号 或 part:编号")
    return list(dict.fromkeys(values or []))


def output_filters(
    supplier_names: list[str] | None = Query(None, max_length=100),
    output_keys: list[str] | None = Query(None, max_length=100),
    date_from: date | None = None, date_to: date | None = None,
    progress: Literal["all", "unreceived", "partial", "settled"] = "all",
    archive: Literal["active", "archived", "all"] = "active",
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "开始日期不能晚于结束日期")
    if any(not name.strip() or len(name) > 200 for name in supplier_names or []):
        raise HTTPException(422, "商家名称必须为 1–200 个字符")
    return dict(supplier_names=list(dict.fromkeys(supplier_names or [])), output_keys=_output_keys(output_keys),
                date_from=date_from, date_to=date_to, progress=progress, archive=archive)


@router.get("/output-overview", response_model=OutputOverview)
def overview(filters: dict = Depends(output_filters),
             view: Literal["merchant", "product"] = "merchant",
             skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=50),
             db: Session = Depends(get_db)):
    return output_overview(db, **filters, view=view, skip=skip, limit=limit)


@router.get("/output-sources", response_model=OutputSourceList)
def sources(supplier_name: str = Query(..., min_length=1, max_length=200),
            output_key: str = Query(..., min_length=1, max_length=210),
            unit: str = Query("", max_length=100), filters: dict = Depends(output_filters),
            skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db)):
    _output_keys([output_key])
    return output_sources(db, supplier_name=supplier_name, output_key=output_key, unit=unit,
                          **filters, skip=skip, limit=limit)


@router.get("/output-sources/{source_id}/receipts", response_model=OutputReceiptList)
def source_receipts(source_id: int, skip: int = Query(0, ge=0),
                    limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    result = output_receipts(db, source_id, skip=skip, limit=limit)
    if result is None:
        raise HTTPException(404, "已发出的产出来源不存在")
    return result


@router.get("/output-options", response_model=OutputOptions)
def options(q: str = Query("", max_length=200),
            selected_keys: list[str] | None = Query(None, max_length=100),
            db: Session = Depends(get_db)):
    return output_options(db, q=q, selected_keys=_output_keys(selected_keys))


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
