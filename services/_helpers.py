from sqlalchemy.orm import Session


def _next_id(db: Session, model, prefix: str, width: int = 4) -> str:
    """Return the next formatted ID for a model with string PKs like 'PJ-0001'."""
    rows = db.query(model.id).all()
    max_n = 0
    for (row_id,) in rows:
        try:
            n = int(row_id.split("-")[-1])
            if n > max_n:
                max_n = n
        except (ValueError, IndexError):
            pass
    return f"{prefix}-{max_n + 1:0{width}d}"


def _next_id_by_category(db: Session, model, prefix: str) -> str:
    """Return the next formatted ID scoped to a category prefix like 'PJ-DZ-00001'."""
    rows = db.query(model.id).filter(model.id.like(f"{prefix}-%")).all()
    max_n = 0
    for (row_id,) in rows:
        try:
            n = int(row_id.split("-")[-1])
            if n > max_n:
                max_n = n
        except (ValueError, IndexError):
            pass
    return f"{prefix}-{max_n + 1:05d}"
