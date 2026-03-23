from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderDeliveryImagesUpdate,
    PurchaseOrderItemAddonCreate,
    PurchaseOrderItemAddonResponse,
    PurchaseOrderItemAddonUpdate,
    PurchaseOrderItemUpdate,
    PurchaseOrderItemResponse,
    PurchaseOrderResponse,
    PurchaseOrderStatusUpdate,
)
from services.purchase_order import (
    create_purchase_order,
    create_purchase_item_addon,
    delete_purchase_item,
    delete_purchase_item_addon,
    delete_purchase_order,
    get_purchase_order,
    get_vendor_names,
    list_purchase_orders,
    update_purchase_item,
    update_purchase_item_addon,
    update_purchase_order_images,
    update_purchase_order_status,
)

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])


@router.get("/", response_model=list[PurchaseOrderResponse])
def api_list_purchase_orders(vendor_name: Optional[str] = None, db: Session = Depends(get_db)):
    return list_purchase_orders(db, vendor_name=vendor_name)


@router.get("/vendors", response_model=list[str])
def api_get_vendor_names(db: Session = Depends(get_db)):
    return get_vendor_names(db)


@router.post("/", response_model=PurchaseOrderResponse, status_code=201)
def api_create_purchase_order(body: PurchaseOrderCreate, db: Session = Depends(get_db)):
    with service_errors():
        order = create_purchase_order(
            db,
            vendor_name=body.vendor_name,
            items=[item.model_dump() for item in body.items],
            status=body.status,
            note=body.note,
        )
    return order


@router.get("/{order_id}", response_model=PurchaseOrderResponse)
def api_get_purchase_order(order_id: str, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    return order


@router.delete("/{order_id}", status_code=204)
def api_delete_purchase_order(order_id: str, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        delete_purchase_order(db, order_id)


@router.patch("/{order_id}/status", response_model=PurchaseOrderResponse)
def api_update_purchase_order_status(order_id: str, body: PurchaseOrderStatusUpdate, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        order = update_purchase_order_status(db, order_id, body.status)
    return order


@router.patch("/{order_id}/delivery-images", response_model=PurchaseOrderResponse)
def api_update_purchase_order_images(order_id: str, body: PurchaseOrderDeliveryImagesUpdate, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        order = update_purchase_order_images(db, order_id, body.delivery_images)
    return order


@router.put("/{order_id}/items/{item_id}", response_model=PurchaseOrderItemResponse)
def api_update_purchase_item(order_id: str, item_id: int, body: PurchaseOrderItemUpdate, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        item = update_purchase_item(db, order_id, item_id, body.model_dump(exclude_unset=True))
    return item


@router.delete("/{order_id}/items/{item_id}", status_code=204)
def api_delete_purchase_item(order_id: str, item_id: int, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        delete_purchase_item(db, order_id, item_id)


@router.post("/{order_id}/items/{item_id}/addons", response_model=PurchaseOrderItemAddonResponse, status_code=201)
def api_create_addon(order_id: str, item_id: int, body: PurchaseOrderItemAddonCreate, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        addon = create_purchase_item_addon(
            db, order_id, item_id,
            type=body.type, qty=body.qty, unit=body.unit, price=body.price,
        )
    return addon


@router.put("/{order_id}/items/{item_id}/addons/{addon_id}", response_model=PurchaseOrderItemAddonResponse)
def api_update_addon(order_id: str, item_id: int, addon_id: int, body: PurchaseOrderItemAddonUpdate, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        addon = update_purchase_item_addon(
            db, order_id, item_id, addon_id,
            **body.model_dump(exclude_unset=True),
        )
    return addon


@router.delete("/{order_id}/items/{item_id}/addons/{addon_id}", status_code=204)
def api_delete_addon(order_id: str, item_id: int, addon_id: int, db: Session = Depends(get_db)):
    order = get_purchase_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"PurchaseOrder {order_id} not found")
    with service_errors():
        delete_purchase_item_addon(db, order_id, item_id, addon_id)
