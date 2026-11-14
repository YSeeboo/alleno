from contextlib import contextmanager

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api._errors import service_errors
from api.deps import get_current_user, require_permission
from database import get_db
from models.jewelry_structure import JewelryStructure, JewelryStructureBatch
from schemas.jewelry_structure import BatchConfirm, BatchInput, SchemeWrite, StructureUpdate, StructureWrite
from services import jewelry_structure as service

router = APIRouter(prefix="/api/jewelry-structures", tags=["jewelry-structures"])


@contextmanager
def errors():
    with service_errors():
        try:
            yield
        except service.StructureConflict as e:
            raise HTTPException(status_code=409, detail=str(e))
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))


@router.get("/")
def list_structures(db: Session = Depends(get_db)):
    return [service.serialize(s) for s in db.query(JewelryStructure).order_by(JewelryStructure.id.desc()).all()]


@router.post("/", status_code=201)
def create_structure(body: StructureWrite, db: Session = Depends(get_db)):
    with errors():
        return service.save_structure(db, body)


@router.get("/batches", dependencies=[require_permission("jewelries")])
def list_batches(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return [b.result for b in db.query(JewelryStructureBatch).filter_by(user_id=user.id)
            .order_by(JewelryStructureBatch.id.desc()).limit(20).all()]


@router.put("/{structure_id}")
def update_structure(structure_id: int, body: StructureUpdate, db: Session = Depends(get_db)):
    with errors():
        return service.save_structure(db, body, structure_id)


@router.delete("/{structure_id}", status_code=204)
def delete_structure(structure_id: int, revision: int = Query(ge=1), db: Session = Depends(get_db)):
    with errors():
        service.delete_structure(db, structure_id, revision)


@router.post("/{structure_id}/schemes", status_code=201)
def create_scheme(structure_id: int, body: SchemeWrite, db: Session = Depends(get_db)):
    with errors():
        return service.save_scheme(db, structure_id, body)


@router.put("/{structure_id}/schemes/{scheme_id}")
def update_scheme(structure_id: int, scheme_id: int, body: SchemeWrite, db: Session = Depends(get_db)):
    with errors():
        return service.save_scheme(db, structure_id, body, scheme_id)


@router.delete("/{structure_id}/schemes/{scheme_id}")
def delete_scheme(structure_id: int, scheme_id: int, revision: int = Query(ge=1), db: Session = Depends(get_db)):
    with errors():
        return service.delete_scheme(db, structure_id, scheme_id, revision)


@router.post("/preview", dependencies=[require_permission("jewelries")])
def preview(body: BatchInput, user=Depends(get_current_user), db: Session = Depends(get_db)):
    with errors():
        return service.preview_batch(db, body, user.id)


@router.post("/confirm", dependencies=[require_permission("jewelries")])
def confirm(body: BatchConfirm, user=Depends(get_current_user), db: Session = Depends(get_db)):
    with errors():
        return service.confirm_batch(db, body, user.id)
