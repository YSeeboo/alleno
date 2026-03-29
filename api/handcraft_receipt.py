from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.part import CostDiffItem
from services.cost_sync import (
    auto_set_initial_handcraft_cost,
    detect_handcraft_bead_cost_diffs,
    detect_handcraft_jewelry_cost_diffs,
)
from schemas.handcraft_receipt import (
    HandcraftReceiptAddItemsRequest,
    HandcraftReceiptCreate,
    HandcraftReceiptDeliveryImagesUpdate,
    HandcraftReceiptItemUpdate,
    HandcraftReceiptItemResponse,
    HandcraftReceiptResponse,
    HandcraftReceiptStatusUpdate,
)
from services.handcraft_receipt import (
    add_handcraft_receipt_items,
    create_handcraft_receipt,
    delete_handcraft_receipt,
    delete_handcraft_receipt_item,
    get_handcraft_receipt,
    get_handcraft_receipt_supplier_names,
    list_handcraft_receipts,
    update_handcraft_receipt_images,
    update_handcraft_receipt_item,
    update_handcraft_receipt_status,
)

router = APIRouter(prefix="/api/handcraft-receipts", tags=["handcraft-receipts"])


@router.get("/", response_model=list[HandcraftReceiptResponse])
def api_list_handcraft_receipts(supplier_name: Optional[str] = None, db: Session = Depends(get_db)):
    return list_handcraft_receipts(db, supplier_name=supplier_name)


@router.get("/suppliers", response_model=list[str])
def api_get_handcraft_receipt_supplier_names(db: Session = Depends(get_db)):
    return get_handcraft_receipt_supplier_names(db)


@router.post("/", response_model=HandcraftReceiptResponse, status_code=201)
def api_create_handcraft_receipt(body: HandcraftReceiptCreate, db: Session = Depends(get_db)):
    with service_errors():
        receipt = create_handcraft_receipt(
            db,
            supplier_name=body.supplier_name,
            items=[item.model_dump() for item in body.items],
            status=body.status,
            note=body.note,
        )
    # Detect diffs BEFORE auto-setting (so old values are still visible)
    cost_diffs = detect_handcraft_bead_cost_diffs(db, receipt)
    cost_diffs += detect_handcraft_jewelry_cost_diffs(db, receipt)
    # Then sync handcraft_cost for jewelry items
    for item in receipt.items:
        if item.item_type == "jewelry" and item.price is not None:
            auto_set_initial_handcraft_cost(db, item.item_id, float(item.price))
    resp = HandcraftReceiptResponse.model_validate(receipt)
    resp.cost_diffs = [CostDiffItem(**d) for d in cost_diffs]
    return resp


@router.post("/{receipt_id}/items", response_model=HandcraftReceiptResponse, status_code=201)
def api_add_handcraft_receipt_items(receipt_id: str, body: HandcraftReceiptAddItemsRequest, db: Session = Depends(get_db)):
    receipt = get_handcraft_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"HandcraftReceipt {receipt_id} not found")
    with service_errors():
        receipt = add_handcraft_receipt_items(
            db,
            receipt_id=receipt_id,
            items=[item.model_dump() for item in body.items],
        )
    # Detect diffs BEFORE auto-setting
    cost_diffs = detect_handcraft_bead_cost_diffs(db, receipt)
    cost_diffs += detect_handcraft_jewelry_cost_diffs(db, receipt)
    # Then sync
    for item in receipt.items:
        if item.item_type == "jewelry" and item.price is not None:
            auto_set_initial_handcraft_cost(db, item.item_id, float(item.price))
    resp = HandcraftReceiptResponse.model_validate(receipt)
    resp.cost_diffs = [CostDiffItem(**d) for d in cost_diffs]
    return resp


@router.get("/{receipt_id}", response_model=HandcraftReceiptResponse)
def api_get_handcraft_receipt(receipt_id: str, db: Session = Depends(get_db)):
    receipt = get_handcraft_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"HandcraftReceipt {receipt_id} not found")
    return receipt


@router.delete("/{receipt_id}", status_code=204)
def api_delete_handcraft_receipt(receipt_id: str, db: Session = Depends(get_db)):
    receipt = get_handcraft_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"HandcraftReceipt {receipt_id} not found")
    with service_errors():
        delete_handcraft_receipt(db, receipt_id)


@router.patch("/{receipt_id}/status", response_model=HandcraftReceiptResponse)
def api_update_handcraft_receipt_status(receipt_id: str, body: HandcraftReceiptStatusUpdate, db: Session = Depends(get_db)):
    receipt = get_handcraft_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"HandcraftReceipt {receipt_id} not found")
    with service_errors():
        receipt = update_handcraft_receipt_status(db, receipt_id, body.status)
    return receipt


@router.patch("/{receipt_id}/delivery-images", response_model=HandcraftReceiptResponse)
def api_update_handcraft_receipt_images(receipt_id: str, body: HandcraftReceiptDeliveryImagesUpdate, db: Session = Depends(get_db)):
    receipt = get_handcraft_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"HandcraftReceipt {receipt_id} not found")
    with service_errors():
        receipt = update_handcraft_receipt_images(db, receipt_id, body.delivery_images)
    return receipt


@router.put("/{receipt_id}/items/{item_id}", response_model=HandcraftReceiptItemResponse)
def api_update_handcraft_receipt_item(receipt_id: str, item_id: int, body: HandcraftReceiptItemUpdate, db: Session = Depends(get_db)):
    receipt = get_handcraft_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"HandcraftReceipt {receipt_id} not found")
    with service_errors():
        item = update_handcraft_receipt_item(db, receipt_id, item_id, body.model_dump(exclude_unset=True))
    return item


@router.delete("/{receipt_id}/items/{item_id}", status_code=204)
def api_delete_handcraft_receipt_item(receipt_id: str, item_id: int, db: Session = Depends(get_db)):
    receipt = get_handcraft_receipt(db, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"HandcraftReceipt {receipt_id} not found")
    with service_errors():
        delete_handcraft_receipt_item(db, receipt_id, item_id)
