from typing import Optional

from sqlalchemy.orm import Session

from models.bom import Bom
from models.jewelry import Jewelry
from services._helpers import _next_id, _next_id_by_category, keyword_filter

_VALID_STATUSES = {"active", "inactive"}

JEWELRY_CATEGORIES = {
    "套装": "SP-SET",
    "单件": "SP-PCS",
    "单对": "SP-PAIR",
}


_JEWELRY_MODEL_FIELDS = {c.key for c in Jewelry.__table__.columns}


def create_jewelry(db: Session, data: dict) -> Jewelry:
    category = data.get("category")
    if category not in JEWELRY_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Must be one of: {list(JEWELRY_CATEGORIES.keys())}"
        )
    prefix = JEWELRY_CATEGORIES[category]
    model_data = {k: v for k, v in data.items() if k in _JEWELRY_MODEL_FIELDS}
    jewelry = Jewelry(id=_next_id_by_category(db, Jewelry, prefix), **model_data)
    db.add(jewelry)
    db.flush()
    return jewelry


def get_jewelry(db: Session, jewelry_id: str) -> Optional[Jewelry]:
    return db.query(Jewelry).filter(Jewelry.id == jewelry_id).first()


def list_jewelries(db: Session, category: str = None, status: str = None, name: str = None) -> list:
    q = db.query(Jewelry)
    if category is not None:
        q = q.filter(Jewelry.category == category)
    if status is not None:
        q = q.filter(Jewelry.status == status)
    clause = keyword_filter(name, Jewelry.name, Jewelry.id)
    if clause is not None:
        q = q.filter(clause)
    return q.order_by(Jewelry.id.desc()).all()


def update_jewelry(db: Session, jewelry_id: str, data: dict) -> Jewelry:
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")
    # Category changes are disallowed because the jewelry ID encodes the category
    # (e.g. SP-SET-00001 means 套装). Allowing a category change would make the
    # ID misleading and break the ID-format contract.
    if "category" in data:
        raise ValueError(
            "Category cannot be changed after creation — the jewelry ID encodes the category."
        )
    for key, value in data.items():
        if key in _JEWELRY_MODEL_FIELDS:
            setattr(jewelry, key, value)
    db.flush()
    return jewelry


def set_status(db: Session, jewelry_id: str, status: str) -> Jewelry:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {_VALID_STATUSES}")
    return update_jewelry(db, jewelry_id, {"status": status})


def delete_jewelry(db: Session, jewelry_id: str) -> None:
    jewelry = get_jewelry(db, jewelry_id)
    if jewelry is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")
    db.delete(jewelry)
    db.flush()


def _suffix_to_num(s: str) -> int:
    """双射 26 进制：A->1, Z->26, AA->27。"""
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def _num_to_suffix(n: int) -> str:
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(ord("A") + r) + out
    return out


def _next_sibling_suffix(db: Session, group: str) -> str:
    """扫描同组已有后缀成员，返回下一个可用字母后缀。"""
    prefix = f"{group}-"
    members = db.query(Jewelry).filter(Jewelry.style_group == group).all()
    nums = []
    for m in members:
        if m.id.startswith(prefix):
            suf = m.id[len(prefix):]
            if suf.isalpha() and suf.isupper():
                nums.append(_suffix_to_num(suf))
    return _num_to_suffix((max(nums) + 1) if nums else 1)


def add_jewelry_sibling(db: Session, base_id: str, override_data: dict) -> Jewelry:
    """以 base_id 为参照创建一条同款饰品（同 style_group，带后缀 ID，复制 BOM）。"""
    base = get_jewelry(db, base_id)
    if base is None:
        raise ValueError(f"Jewelry not found: {base_id}")
    # 不嵌套：解析到基准组键
    group = base.style_group or base.id
    group_base = base if group == base.id else get_jewelry(db, group)
    # 回填基准自身的 style_group（首次成组）
    if group_base is not None and group_base.style_group is None:
        group_base.style_group = group
        db.flush()

    suffix = _next_sibling_suffix(db, group)
    new_id = f"{group}-{suffix}"

    src = group_base if group_base is not None else base
    base_data = {
        "name": src.name,
        "image": src.image,
        "structure_image": src.structure_image,
        "category": src.category,
        "color": src.color,
        "unit": src.unit,
        "retail_price": src.retail_price,
        "wholesale_price": src.wholesale_price,
        "handcraft_cost": src.handcraft_cost,
    }
    safe_override = {k: v for k, v in (override_data or {}).items() if k != "category"}
    merged = {**base_data, **safe_override}
    fields = {k: v for k, v in merged.items() if k in _JEWELRY_MODEL_FIELDS and k != "style_group"}

    sibling = Jewelry(id=new_id, style_group=group, **fields)
    db.add(sibling)
    db.flush()

    for src_bom in db.query(Bom).filter(Bom.jewelry_id == src.id).all():
        db.add(Bom(
            id=_next_id(db, Bom, "BM"),
            jewelry_id=new_id,
            part_id=src_bom.part_id,
            qty_per_unit=src_bom.qty_per_unit,
        ))
    db.flush()
    return sibling


def copy_jewelry(db: Session, source_id: str, override_data: dict) -> Jewelry:
    """Clone a jewelry's basic info + BOM rows into a new jewelry record.

    - Raises ValueError if source_id does not exist.
    - Category is always inherited from source (any 'category' key in
      override_data is ignored).
    - Inventory log is NOT cloned; the new jewelry starts at stock 0.
    - status defaults to 'active'.
    """
    source = get_jewelry(db, source_id)
    if source is None:
        raise ValueError(f"Jewelry not found: {source_id}")

    base_data = {
        "name": source.name,
        "image": source.image,
        "structure_image": source.structure_image,
        "category": source.category,
        "color": source.color,
        "unit": source.unit,
        "retail_price": source.retail_price,
        "wholesale_price": source.wholesale_price,
        "handcraft_cost": source.handcraft_cost,
    }
    safe_override = {k: v for k, v in (override_data or {}).items() if k != "category"}
    merged = {**base_data, **safe_override}

    new_jewelry = create_jewelry(db, merged)

    src_boms = db.query(Bom).filter(Bom.jewelry_id == source_id).all()
    for src_bom in src_boms:
        new_bom = Bom(
            id=_next_id(db, Bom, "BM"),
            jewelry_id=new_jewelry.id,
            part_id=src_bom.part_id,
            qty_per_unit=src_bom.qty_per_unit,
        )
        db.add(new_bom)
    db.flush()
    return new_jewelry
