from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from schemas.part import PartCreate, PartImportResponse, PartResponse, PartUpdate, PartVariantCreate
from services.part import create_part, create_part_variant, get_part, list_part_variants, list_parts, update_part, delete_part
from services.part_import import build_parts_import_template, import_parts_excel
from api._errors import service_errors

router = APIRouter(prefix="/api/parts", tags=["parts"])


@router.post("/", response_model=PartResponse, status_code=201)
def api_create_part(body: PartCreate, db: Session = Depends(get_db)):
    with service_errors():
        part = create_part(db, body.model_dump())
    return part


@router.get("/", response_model=List[PartResponse])
def api_list_parts(category: str = None, name: str = None, parent_part_id: str = None, db: Session = Depends(get_db)):
    with service_errors():
        return list_parts(db, category=category, name=name, parent_part_id=parent_part_id)


@router.post("/import", response_model=PartImportResponse)
async def api_import_parts(
    request: Request,
    filename: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    file_bytes = await request.body()
    with service_errors():
        return import_parts_excel(db, file_bytes=file_bytes, filename=filename)


@router.get("/import-template")
def api_download_parts_import_template(_db: Session = Depends(get_db)):
    file_bytes = build_parts_import_template()
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="parts-import-template.xlsx"'},
    )


@router.post("/{part_id}/create-variant", response_model=PartResponse, status_code=201)
def api_create_part_variant(part_id: str, body: PartVariantCreate, db: Session = Depends(get_db)):
    with service_errors():
        return create_part_variant(db, part_id, body.color_code)


@router.get("/{part_id}/variants", response_model=List[PartResponse])
def api_list_part_variants(part_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return list_part_variants(db, part_id)


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
