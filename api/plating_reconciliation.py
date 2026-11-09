from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.plating_reconciliation import ReconciliationPriceUpdate, ReconciliationResponse
from services.plating_reconciliation import build_reconciliation_excel, list_reconciliation, update_price

router = APIRouter(prefix="/api/plating-reconciliation", tags=["plating-reconciliation"])


def reconciliation_filters(
    vendor_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status: Literal["未付款", "已付款"] | None = None,
):
    return dict(vendor_name=vendor_name, date_from=date_from, date_to=date_to, status=status)


@router.get("/", response_model=ReconciliationResponse)
def api_list_reconciliation(
    filters: dict = Depends(reconciliation_filters), skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db),
):
    with service_errors():
        return list_reconciliation(db, skip=skip, limit=limit, **filters)


@router.patch("/items/{item_id}", status_code=204)
def api_update_price(item_id: int, body: ReconciliationPriceUpdate, db: Session = Depends(get_db)):
    with service_errors():
        update_price(db, item_id, body.override_price)


@router.get("/excel")
def api_export_reconciliation(filters: dict = Depends(reconciliation_filters), db: Session = Depends(get_db)):
    with service_errors():
        content = build_reconciliation_excel(db, **filters)
    filename = "电镀商家对账.xlsx"
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="reconciliation.xlsx"; filename*=UTF-8\'\'{quote(filename)}'})
