"""Reject writes through detail endpoints, while preserving historical reads."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models.plating_order import PlatingOrder
from models.handcraft_order import HandcraftOrder


def _guard(model):
    def guard(request: Request, db: Session = Depends(get_db)):
        order_id = request.path_params.get("order_id")
        if not order_id or request.method in ("GET", "HEAD", "OPTIONS"):
            return
        # PDF exports use POST to carry rendering parameters; they do not write.
        if request.method == "POST" and request.url.path.endswith("/pdf"):
            return
        order = db.get(model, order_id)
        if order is not None and order.archived_at is not None:
            raise HTTPException(409, f"单据 {order_id} 已历史归档，不可修改；请先由管理员恢复归档")
    return guard


guard_plating_archive = _guard(PlatingOrder)
guard_handcraft_archive = _guard(HandcraftOrder)
