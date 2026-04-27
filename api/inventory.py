from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.inventory import InventoryOverviewItem, LogEntryResponse, PaginatedLogResponse, StockResponse
from services.inventory import add_stock, batch_get_stock, deduct_stock, get_inventory_overview, get_stock, get_stock_log, list_stock_logs

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


class StockAdjust(BaseModel):
    qty: float
    reason: str
    note: Optional[str] = None


@router.get("/logs", response_model=PaginatedLogResponse)
def api_list_stock_logs(
    item_type: Optional[str] = Query(None),
    item_id: Optional[str] = Query(None),
    reason: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    with service_errors():
        return list_stock_logs(db, item_type=item_type, item_id=item_id, reason=reason, name=name, limit=limit, offset=offset)


@router.post("/{item_type}/{item_id}/add", response_model=StockResponse)
def api_add_stock(item_type: str, item_id: str, body: StockAdjust, db: Session = Depends(get_db)):
    with service_errors():
        add_stock(db, item_type, item_id, body.qty, body.reason, body.note)
        stock = get_stock(db, item_type, item_id)
    return StockResponse(item_type=item_type, item_id=item_id, current=stock)


@router.post("/{item_type}/{item_id}/deduct", response_model=StockResponse)
def api_deduct_stock(item_type: str, item_id: str, body: StockAdjust, db: Session = Depends(get_db)):
    with service_errors():
        deduct_stock(db, item_type, item_id, body.qty, body.reason, body.note)
        stock = get_stock(db, item_type, item_id)
    return StockResponse(item_type=item_type, item_id=item_id, current=stock)


@router.get("/{item_type}/{item_id}", response_model=StockResponse)
def api_get_stock(item_type: str, item_id: str, db: Session = Depends(get_db)):
    with service_errors():
        stock = get_stock(db, item_type, item_id)
    return StockResponse(item_type=item_type, item_id=item_id, current=stock)


class BatchStockRequest(BaseModel):
    item_type: str
    item_ids: List[str]


@router.post("/batch-stock", response_model=dict[str, float])
def api_batch_get_stock(body: BatchStockRequest, db: Session = Depends(get_db)):
    with service_errors():
        return batch_get_stock(db, body.item_type, body.item_ids)


@router.get("/overview", response_model=List[InventoryOverviewItem])
def api_get_inventory_overview(
    item_type: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    in_stock_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    with service_errors():
        return get_inventory_overview(db, item_type=item_type, name=name, in_stock_only=in_stock_only)


@router.get("/{item_type}/{item_id}/log", response_model=List[LogEntryResponse])
def api_get_stock_log(item_type: str, item_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return get_stock_log(db, item_type, item_id)
