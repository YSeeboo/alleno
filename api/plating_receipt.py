# api/plating_receipt.py
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.part import CostDiffItem
from services.cost_sync import detect_plating_cost_diffs
from schemas.plating_receipt import (
    PlatingReceiptAddItemsRequest,
    PlatingReceiptCreate,
    PlatingReceiptDeliveryImagesUpdate,
    PlatingReceiptItemUpdate,
    PlatingReceiptItemResponse,
    PlatingReceiptResponse,
    PlatingReceiptStatusUpdate,
)
from services.plating_receipt import (
    add_plating_receipt_items,
    create_plating_receipt,
    delete_plating_receipt,
    delete_plating_receipt_item,
    get_plating_receipt,
    get_receipt_vendor_names,
    list_plating_receipts,
    update_plating_receipt_images,
    update_plating_receipt_item,
    update_plating_receipt_status,
)

router = APIRouter(prefix="/api/plating-receipts", tags=["plating-receipts"])


@router.get("/", response_model=list[PlatingReceiptResponse])
def api_list_plating_receipts(vendor_name: Optional[str] = None, db: Session = Depends(get_db)):
    return list_plating_receipts(db, vendor_name=vendor_name)


@router.get("/vendors", response_model=list[str])
def api_get_receipt_vendor_names(db: Session = Depends(get_db)):
    return get_receipt_vendor_names(db)


@router.post("/", response_model=PlatingReceiptResponse, status_code=201)
def api_create_plating_receipt(body: PlatingReceiptCreate, db: Session = Depends(get_db)):
    with service_errors():
        receipt = create_plating_receipt(
            db,
            vendor_name=body.vendor_name,
            items=[item.model_dump() for item in body.items],
            status=body.status,
            note=body.note,
        )
    cost_diffs = detect_plating_cost_diffs(db, receipt)
    resp = PlatingReceiptResponse.model_validate(receipt)
    resp.cost_diffs = [CostDiffItem(**d) for d in cost_diffs]
    return resp


@router.post("/{receipt_id}/items", response_model=PlatingReceiptResponse, status_code=201)
def api_add_plating_receipt_items(receipt_id: str, body: PlatingReceiptAddItemsRequest, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        receipt = add_plating_receipt_items(
            db,
            receipt_id=receipt_id,
            items=[item.model_dump() for item in body.items],
        )
    cost_diffs = detect_plating_cost_diffs(db, receipt)
    resp = PlatingReceiptResponse.model_validate(receipt)
    resp.cost_diffs = [CostDiffItem(**d) for d in cost_diffs]
    return resp


@router.get("/{receipt_id}", response_model=PlatingReceiptResponse)
def api_get_plating_receipt(receipt_id: str, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    return receipt


@router.delete("/{receipt_id}", status_code=204)
def api_delete_plating_receipt(receipt_id: str, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        delete_plating_receipt(db, receipt_id)


@router.patch("/{receipt_id}/status", response_model=PlatingReceiptResponse)
def api_update_plating_receipt_status(receipt_id: str, body: PlatingReceiptStatusUpdate, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        receipt = update_plating_receipt_status(db, receipt_id, body.status)
    return receipt


@router.patch("/{receipt_id}/delivery-images", response_model=PlatingReceiptResponse)
def api_update_plating_receipt_images(receipt_id: str, body: PlatingReceiptDeliveryImagesUpdate, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        receipt = update_plating_receipt_images(db, receipt_id, body.delivery_images)
    return receipt


@router.put("/{receipt_id}/items/{item_id}", response_model=PlatingReceiptItemResponse)
def api_update_plating_receipt_item(receipt_id: str, item_id: int, body: PlatingReceiptItemUpdate, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        item = update_plating_receipt_item(db, receipt_id, item_id, body.model_dump(exclude_unset=True))
    return item


@router.delete("/{receipt_id}/items/{item_id}", status_code=204)
def api_delete_plating_receipt_item(receipt_id: str, item_id: int, db: Session = Depends(get_db)):
    receipt = get_plating_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"PlatingReceipt {receipt_id} not found")
    with service_errors():
        delete_plating_receipt_item(db, receipt_id, item_id)
