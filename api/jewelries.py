from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas.jewelry import JewelryCreate, JewelryUpdate, JewelryResponse, StatusUpdate
from services.jewelry import create_jewelry, get_jewelry, list_jewelries, update_jewelry, delete_jewelry, set_status
from api._errors import service_errors

router = APIRouter(prefix="/api/jewelries", tags=["jewelries"])


@router.post("/", response_model=JewelryResponse, status_code=201)
def api_create_jewelry(body: JewelryCreate, db: Session = Depends(get_db)):
    with service_errors():
        jewelry = create_jewelry(db, body.model_dump())
    return jewelry


@router.get("/", response_model=List[JewelryResponse])
def api_list_jewelries(status: Optional[str] = None, category: Optional[str] = None, db: Session = Depends(get_db)):
    with service_errors():
        return list_jewelries(db, status=status, category=category)


@router.get("/{jewelry_id}", response_model=JewelryResponse)
def api_get_jewelry(jewelry_id: str, db: Session = Depends(get_db)):
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise HTTPException(status_code=404, detail=f"Jewelry {jewelry_id} not found")
    return jewelry


@router.patch("/{jewelry_id}/status", response_model=JewelryResponse)
def api_set_status(jewelry_id: str, body: StatusUpdate, db: Session = Depends(get_db)):
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise HTTPException(status_code=404, detail=f"Jewelry {jewelry_id} not found")
    with service_errors():
        jewelry = set_status(db, jewelry_id, body.status)
    return jewelry


@router.patch("/{jewelry_id}", response_model=JewelryResponse)
def api_update_jewelry(jewelry_id: str, body: JewelryUpdate, db: Session = Depends(get_db)):
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise HTTPException(status_code=404, detail=f"Jewelry {jewelry_id} not found")
    with service_errors():
        jewelry = update_jewelry(db, jewelry_id, body.model_dump(exclude_unset=True))
    return jewelry


@router.delete("/{jewelry_id}", status_code=204)
def api_delete_jewelry(jewelry_id: str, db: Session = Depends(get_db)):
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise HTTPException(status_code=404, detail=f"Jewelry {jewelry_id} not found")
    with service_errors():
        delete_jewelry(db, jewelry_id)
