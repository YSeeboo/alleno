"""Cargo sorting endpoints for sorting workers (分拣员).
Mounted separately from handcraft_router so the 'sorting' permission can grant
access to these endpoints without granting access to handcraft management."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas.handcraft import CargoSortingSuppliersResponse
from services.handcraft import list_suppliers_with_sorting

# Same URL prefix as handcraft_router so URLs are unchanged:
# GET /api/handcraft/suppliers-with-sorting
router = APIRouter(prefix="/api/handcraft", tags=["cargo-sorting"])


@router.get("/suppliers-with-sorting", response_model=CargoSortingSuppliersResponse)
def api_list_suppliers_with_sorting(db: Session = Depends(get_db)):
    return {"suppliers": list_suppliers_with_sorting(db)}
