from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api._errors import service_errors
from database import get_db
from schemas.jewelry_template import (
    JewelryTemplateCreate,
    JewelryTemplateResponse,
    JewelryTemplateUpdate,
)
from services.jewelry_template import (
    create_template,
    delete_template,
    get_template,
    list_templates,
    update_template,
    apply_template_to_jewelry,
)

router = APIRouter(prefix="/api/jewelry-templates", tags=["jewelry-templates"])


@router.get("/", response_model=list[JewelryTemplateResponse])
def api_list_templates(db: Session = Depends(get_db)):
    return list_templates(db)


@router.post("/", response_model=JewelryTemplateResponse, status_code=201)
def api_create_template(body: JewelryTemplateCreate, db: Session = Depends(get_db)):
    with service_errors():
        return create_template(db, body.model_dump())


@router.get("/{template_id}", response_model=JewelryTemplateResponse)
def api_get_template(template_id: int, db: Session = Depends(get_db)):
    result = get_template(db, template_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"JewelryTemplate {template_id} not found")
    return result


@router.patch("/{template_id}", response_model=JewelryTemplateResponse)
def api_update_template(template_id: int, body: JewelryTemplateUpdate, db: Session = Depends(get_db)):
    result = get_template(db, template_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"JewelryTemplate {template_id} not found")
    with service_errors():
        return update_template(db, template_id, body.model_dump(exclude_unset=True))


@router.delete("/{template_id}", status_code=204)
def api_delete_template(template_id: int, db: Session = Depends(get_db)):
    result = get_template(db, template_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"JewelryTemplate {template_id} not found")
    with service_errors():
        delete_template(db, template_id)


@router.post("/{template_id}/apply/{jewelry_id}", status_code=200)
def api_apply_template(template_id: int, jewelry_id: str, db: Session = Depends(get_db)):
    """将模板导入到饰品的 BOM"""
    with service_errors():
        boms = apply_template_to_jewelry(db, template_id, jewelry_id)
    return {"applied": len(boms)}
