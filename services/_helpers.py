from sqlalchemy import text
from sqlalchemy.orm import Session

# Fast path: counter already exists, atomic increment
_INCREMENT_SQL = text("""
    UPDATE id_counter
    SET last_number = last_number + 1
    WHERE prefix = :prefix
    RETURNING last_number
""")

# Slow path: first-time init with upsert (handles concurrent first-init)
_UPSERT_SQL = text("""
    INSERT INTO id_counter (prefix, last_number)
    VALUES (:prefix, :init_val + 1)
    ON CONFLICT (prefix) DO UPDATE
        SET last_number = id_counter.last_number + 1
    RETURNING last_number
""")


def _next_id(db: Session, model, prefix: str, width: int = 4) -> str:
    """Return the next sequential ID, never reusing deleted IDs. Concurrency-safe."""
    row = db.execute(_INCREMENT_SQL, {"prefix": prefix}).first()
    if row is None:
        init_val = _max_number(db.query(model.id).all())
        row = db.execute(_UPSERT_SQL, {"prefix": prefix, "init_val": init_val}).first()
    return f"{prefix}-{row[0]:0{width}d}"


def _next_id_by_category(db: Session, model, prefix: str) -> str:
    """Return the next sequential ID scoped to a category prefix. Concurrency-safe."""
    row = db.execute(_INCREMENT_SQL, {"prefix": prefix}).first()
    if row is None:
        init_val = _max_number(db.query(model.id).filter(model.id.like(f"{prefix}-%")).all())
        row = db.execute(_UPSERT_SQL, {"prefix": prefix, "init_val": init_val}).first()
    return f"{prefix}-{row[0]:05d}"


def _max_number(rows) -> int:
    max_n = 0
    for (row_id,) in rows:
        try:
            n = int(row_id.split("-")[-1])
            if n > max_n:
                max_n = n
        except (ValueError, IndexError):
            pass
    return max_n
