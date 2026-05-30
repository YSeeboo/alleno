"""Customer name suggestion service.

There is no Customer master table — `customer_name` is a free-text column on
two models: `Order` (sales orders) and `HandcraftJewelryItem` (manual customer
attribution on a handcraft order's jewelry row). This service unions and
dedupes both sources for a downstream picker.

Note: `HandcraftOrder` does NOT have a `customer_name` column; an HC's
effective customer is derived per-jewelry-item via `OrderItemLink →
Order.customer_name`, which is already covered by the `Order` source above.
"""
from sqlalchemy.orm import Session

from models.order import Order
from models.handcraft_order import HandcraftJewelryItem


def list_distinct_customer_names(
    db: Session, query: str | None = None, limit: int = 50,
) -> list[str]:
    """Return sorted distinct customer names from the two known sources.

    `query` filters substring (case-insensitive). Empty / whitespace-only
    names are excluded defensively even though the source tables generally
    validate non-empty.
    """
    order_q = db.query(Order.customer_name).filter(
        Order.customer_name.isnot(None), Order.customer_name != ""
    )
    hcji_q = db.query(HandcraftJewelryItem.customer_name).filter(
        HandcraftJewelryItem.customer_name.isnot(None),
        HandcraftJewelryItem.customer_name != "",
    )
    union_q = order_q.union(hcji_q)
    rows = union_q.all()
    names = sorted({r[0] for r in rows if r[0] and r[0].strip()})
    if query:
        q = query.strip().lower()
        names = [n for n in names if q in n.lower()]
    return names[:limit]
