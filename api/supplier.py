from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._errors import service_errors
from api.deps import require_permission
from database import get_db
from schemas.supplier import SupplierCreate, SupplierUpdate, SupplierResponse
from services.supplier import (
    create_supplier,
    list_suppliers,
    update_supplier,
    delete_supplier,
)

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.post("/", response_model=SupplierResponse, status_code=201)
def api_create_supplier(body: SupplierCreate, db: Session = Depends(get_db)):
    with service_errors():
        return create_supplier(db, name=body.name, type=body.type)


@router.get("/", response_model=list[SupplierResponse])
def api_list_suppliers(type: Optional[str] = None, db: Session = Depends(get_db)):
    return list_suppliers(db, type=type)


@router.patch("/{supplier_id}", response_model=SupplierResponse, dependencies=[require_permission("users")])
def api_update_supplier(supplier_id: int, body: SupplierUpdate, db: Session = Depends(get_db)):
    with service_errors():
        return update_supplier(db, supplier_id, name=body.name)


@router.delete("/{supplier_id}", status_code=204, dependencies=[require_permission("users")])
def api_delete_supplier(supplier_id: int, db: Session = Depends(get_db)):
    with service_errors():
        delete_supplier(db, supplier_id)
