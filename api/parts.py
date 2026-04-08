from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from schemas.part import BatchCostUpdateRequest, BatchCostUpdateResponse, BatchCostUpdateResultItem, PartCreate, FindOrCreateVariantResponse, PartCostLogResponse, PartImportResponse, PartResponse, PartUpdate, PartVariantCreate
from schemas.part_bom import PartBomSet
from services.part import COLOR_VARIANTS, create_part, create_part_variant, find_or_create_variant, get_part, list_part_cost_logs, list_part_variants, list_parts, update_part, update_part_cost, delete_part
from services.part_bom import set_part_bom, get_part_bom, delete_part_bom_item
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


@router.get("/color-variants")
def api_get_color_variants():
    return COLOR_VARIANTS


@router.post("/batch-update-costs", response_model=BatchCostUpdateResponse)
def api_batch_update_costs(body: BatchCostUpdateRequest, db: Session = Depends(get_db)):
    results = []
    updated_count = 0
    with service_errors():
        for item in body.updates:
            log = update_part_cost(db, item.part_id, item.field, item.value, source_id=item.source_id)
            updated = log is not None
            if updated:
                updated_count += 1
            results.append(BatchCostUpdateResultItem(
                part_id=item.part_id,
                field=item.field,
                updated=updated,
            ))
    return BatchCostUpdateResponse(updated_count=updated_count, results=results)


@router.delete("/bom/{bom_id}", status_code=204)
def api_delete_part_bom(bom_id: str, db: Session = Depends(get_db)):
    with service_errors():
        delete_part_bom_item(db, bom_id)


@router.get("/{part_id}/bom")
def api_get_part_bom(part_id: str, db: Session = Depends(get_db)):
    return get_part_bom(db, part_id)


@router.post("/{part_id}/bom")
def api_set_part_bom(part_id: str, body: PartBomSet, db: Session = Depends(get_db)):
    with service_errors():
        return set_part_bom(db, part_id, body.child_part_id, body.qty_per_unit)


@router.post("/{part_id}/find-or-create-variant", response_model=FindOrCreateVariantResponse)
def api_find_or_create_variant(part_id: str, body: PartVariantCreate, db: Session = Depends(get_db)):
    with service_errors():
        return find_or_create_variant(db, part_id, body.color_code, body.spec)


@router.post("/{part_id}/create-variant", response_model=PartResponse, status_code=201)
def api_create_part_variant(part_id: str, body: PartVariantCreate, db: Session = Depends(get_db)):
    with service_errors():
        return create_part_variant(db, part_id, body.color_code, body.spec)


@router.get("/{part_id}/variants", response_model=List[PartResponse])
def api_list_part_variants(part_id: str, db: Session = Depends(get_db)):
    with service_errors():
        return list_part_variants(db, part_id)


@router.get("/{part_id}/cost-logs", response_model=list[PartCostLogResponse])
def api_get_part_cost_logs(part_id: str, db: Session = Depends(get_db)):
    part = get_part(db, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail=f"Part {part_id} not found")
    return list_part_cost_logs(db, part_id)


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
