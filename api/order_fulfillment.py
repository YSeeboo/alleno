from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from api._errors import service_errors
from api.deps import require_permission
from database import get_db
from schemas.order_fulfillment import FulfillmentActivation, ReservationUpdate, ShipmentCreate, ShipmentConfirm
from services import order_fulfillment as service

router = APIRouter(prefix="/api/fulfillment", tags=["fulfillment"], dependencies=[require_permission("orders")])


@router.get("/orders")
def summaries(order_ids: str, db: Session = Depends(get_db)):
    with service_errors():
        return service.batch_summaries(db, order_ids.split(",")[:500])


@router.get("/orders/{order_id}")
def summary(order_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return service.order_summary(db, order_id)


@router.post("/orders/{order_id}/activate")
def activate(order_id: str, body: FulfillmentActivation, db: Session = Depends(get_db)):
    with service_errors():
        return service.activate(db, order_id, body.confirmed_no_prior_shipments)


@router.put("/orders/{order_id}/reservations/{line_id}")
def reserve(order_id: str, line_id: int, body: ReservationUpdate, db: Session = Depends(get_db)):
    with service_errors():
        return service.reserve(db, order_id, line_id, body.quantity, body.expected_quantity)


@router.get("/shipments")
def shipments(order_id: str | None = None, db: Session = Depends(get_db)):
    return service.list_shipments(db, order_id)


@router.post("/shipments", status_code=201)
def create(body: ShipmentCreate, db: Session = Depends(get_db)):
    with service_errors():
        return service.create_shipment(db, body.model_dump())


@router.get("/shipments/{shipment_id}")
def detail(shipment_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return service.shipment_view(db, shipment_id)


@router.post("/shipments/{shipment_id}/confirm")
def confirm(shipment_id: str, body: ShipmentConfirm, db: Session = Depends(get_db)):
    with service_errors():
        return service.confirm_shipment(db, shipment_id, body.actual_goods_checked)


@router.post("/shipments/{shipment_id}/void")
def void(shipment_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return service.void_shipment(db, shipment_id)
