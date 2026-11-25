from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models.bom import Bom
from models.jewelry import Jewelry
from models.part import Part
from schemas.bom import BomCopyPreview, BomCopyRequest, BomCopyResult, BomCopySources, BomQty, BomResponse
from services.bom import (
    BomCopyConflict, BomCopyNotFound, copy_bom_items, delete_bom_item, get_bom,
    list_bom_copy_sources, preview_bom_copy, set_bom,
)
from api._errors import service_errors
from api.deps import require_permission

router = APIRouter(prefix="/api/bom", tags=["bom"])


@router.get("/{jewelry_id}/copy-sources", response_model=BomCopySources, dependencies=[require_permission("jewelries")])
def api_list_copy_sources(
    jewelry_id: str, q: str = Query("", max_length=120), offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=50), db: Session = Depends(get_db),
):
    try:
        return list_bom_copy_sources(db, jewelry_id, q, offset, limit)
    except BomCopyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{jewelry_id}/copy-preview/{source_id}", response_model=BomCopyPreview, dependencies=[require_permission("jewelries")])
def api_preview_bom_copy(jewelry_id: str, source_id: str, db: Session = Depends(get_db)):
    try:
        with service_errors():
            return preview_bom_copy(db, jewelry_id, source_id)
    except BomCopyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{jewelry_id}/copy", response_model=BomCopyResult, dependencies=[require_permission("jewelries")])
def api_copy_bom(jewelry_id: str, body: BomCopyRequest, db: Session = Depends(get_db)):
    try:
        with service_errors():
            return copy_bom_items(db, jewelry_id, body)
    except BomCopyNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BomCopyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
