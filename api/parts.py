from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas.part import PartCreate, PartUpdate, PartResponse
from services.part import create_part, get_part, list_parts, update_part, delete_part
from api._errors import service_errors

router = APIRouter(prefix="/api/parts", tags=["parts"])


@router.post("/", response_model=PartResponse, status_code=201)
def api_create_part(body: PartCreate, db: Session = Depends(get_db)):
    with service_errors():
        part = create_part(db, body.model_dump())
    return part


@router.get("/", response_model=list[PartResponse])
def api_list_parts(category: str = None, db: Session = Depends(get_db)):
    with service_errors():
        return list_parts(db, category=category)


@router.get("/{part_id}", response_model=PartResponse)
def api_get_part(part_id: str, db: Session = Depends(get_db)):
    part = get_part(db, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail=f"Part {part_id} not found")
    return part


@router.patch("/{part_id}", response_model=PartResponse)
def api_update_part(part_id: str, body: PartUpdate, db: Session = Depends(get_db)):
    part = get_part(db, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail=f"Part {part_id} not found")
    with service_errors():
        part = update_part(db, part_id, body.model_dump(exclude_unset=True))
    return part


@router.delete("/{part_id}", status_code=204)
def api_delete_part(part_id: str, db: Session = Depends(get_db)):
    part = get_part(db, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail=f"Part {part_id} not found")
    with service_errors():
        delete_part(db, part_id)
