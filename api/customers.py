"""Customer name suggest endpoint.

No CRUD — customer_name lives as free text on other models. This is purely a
read-side helper for pickers (used by the HC breakdown matrix and bulk-assign
popover).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from services.customer import list_distinct_customer_names

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("/names", response_model=list[str])
def api_list_customer_names(
    q: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[str]:
    return list_distinct_customer_names(db, query=q, limit=limit)
