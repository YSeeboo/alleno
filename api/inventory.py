from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.inventory import LogEntryResponse, StockResponse
from services.inventory import add_stock, deduct_stock, get_stock, get_stock_log

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


class StockAdjust(BaseModel):
    qty: float
    reason: str
    note: str = None


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


@router.get("/{item_type}/{item_id}/log", response_model=List[LogEntryResponse])
def api_get_stock_log(item_type: str, item_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return get_stock_log(db, item_type, item_id)
