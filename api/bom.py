from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.bom import Bom
from models.jewelry import Jewelry
from models.part import Part
from schemas.bom import BomQty, BomResponse
from services.bom import set_bom, get_bom, delete_bom_item
from api._errors import service_errors

router = APIRouter(prefix="/api/bom", tags=["bom"])


@router.put("/{jewelry_id}/{part_id}", response_model=BomResponse)
def api_upsert_bom(jewelry_id: str, part_id: str, body: BomQty, db: Session = Depends(get_db)):
    jewelry = db.query(Jewelry).filter(Jewelry.id == jewelry_id).first()
    if jewelry is None:
        raise HTTPException(status_code=400, detail=f"Jewelry not found: {jewelry_id}")
    part = db.query(Part).filter(Part.id == part_id).first()
    if part is None:
        raise HTTPException(status_code=400, detail=f"Part not found: {part_id}")
    with service_errors():
        row = set_bom(db, jewelry_id, part_id, body.qty_per_unit)
    return row


@router.get("/{jewelry_id}", response_model=List[BomResponse])
def api_get_bom(jewelry_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return get_bom(db, jewelry_id)


@router.delete("/{jewelry_id}/{part_id}", status_code=204)
def api_delete_bom(jewelry_id: str, part_id: str, db: Session = Depends(get_db)):
    bom = db.query(Bom).filter(Bom.jewelry_id == jewelry_id, Bom.part_id == part_id).first()
    if bom is None:
        raise HTTPException(status_code=404, detail=f"BOM entry {jewelry_id}/{part_id} not found")
    with service_errors():
        delete_bom_item(db, bom.id)
