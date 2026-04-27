import re
from typing import List, Optional

from sqlalchemy.orm import Session

from decimal import Decimal, ROUND_HALF_UP

from models.part import Part, PartCostLog
from services._helpers import _next_id_by_category, keyword_filter

COLOR_VARIANTS = [
    {"code": "G", "label": "金色"},
    {"code": "S", "label": "白K"},
    {"code": "RG", "label": "玫瑰金"},
]
COLOR_SUFFIXES = [v["label"] for v in COLOR_VARIANTS]

_VARIANT_SPEC_REGEX = re.compile(r"^\d+(\.\d+)?(cm|mm|m)$")
# Matches names like xxx_金色_45cm / xxx_白K_17.5cm — a variant masquerading as a root.
_COLOR_PLUS_SPEC_NAME_REGEX = re.compile(
    r"_(" + "|".join(COLOR_SUFFIXES) + r")_\d+(\.\d+)?(cm|mm|m)$"
)

_COST_FIELDS = {"purchase_cost", "bead_cost", "plating_cost"}
_Q7 = Decimal("0.0000001")


def _is_color_variant(name: str) -> bool:
    return any(name.endswith(f"_{suffix}") for suffix in COLOR_SUFFIXES)


def _looks_like_orphan_variant_name(name: str) -> bool:
    """Name pattern suggests the record is really a variant, not a root.

    Covers:
      - color-only suffix:   xxx_金色 / xxx_白K / xxx_玫瑰金
      - color+spec suffix:   xxx_金色_45cm / xxx_白K_17.5cm
    Spec-only (xxx_45cm) is NOT matched here — too easy to false-positive on
    legitimate root names. No real occurrences of spec-only orphans in
    production (per audit), so we keep the check conservative.
    """
    return _is_color_variant(name) or bool(_COLOR_PLUS_SPEC_NAME_REGEX.search(name))


PART_CATEGORIES = {
    "吊坠": "PJ-DZ",
    "链条": "PJ-LT",
    "小配件": "PJ-X",
}

# Default size_tier inferred from category prefix when caller omits size_tier.
# Used in create_part and the schema-compat backfill for existing rows.
DEFAULT_SIZE_TIER_BY_PREFIX = {
    "PJ-DZ": "medium",
    "PJ-LT": "medium",
    "PJ-X": "small",
}


def create_part(db: Session, data: dict) -> Part:
    category = data.get("category")
    if category not in PART_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Must be one of: {list(PART_CATEGORIES.keys())}"
        )
    parent_part_id = data.get("parent_part_id")
    if parent_part_id is not None:
        parent = db.get(Part, parent_part_id)
        if parent is None:
            raise ValueError(f"Parent part not found: {parent_part_id}")
        if parent.parent_part_id is not None:
            raise ValueError("不支持多层嵌套：目标配件已有父配件")
    data.pop("unit_cost", None)
    if "spec" in data:
        data["spec"] = (data["spec"].strip() if data["spec"] else None) or None
    prefix = PART_CATEGORIES[category]
    if data.get("size_tier") is None:
        data["size_tier"] = DEFAULT_SIZE_TIER_BY_PREFIX.get(prefix, "small")
    part = Part(id=_next_id_by_category(db, Part, prefix), **data)
    db.add(part)
    db.flush()
    return part


def get_part(db: Session, part_id: str) -> Optional[Part]:
    return db.query(Part).filter(Part.id == part_id).first()


def list_parts(db: Session, category: str = None, name: str = None, parent_part_id: str = None) -> List[Part]:
    q = db.query(Part)
    if category is not None:
        q = q.filter(Part.category == category)
    clause = keyword_filter(name, Part.name, Part.id)
    if clause is not None:
        q = q.filter(clause)
    if parent_part_id is not None:
        q = q.filter(Part.parent_part_id == parent_part_id)
    return q.order_by(Part.id.desc()).all()


def update_part(db: Session, part_id: str, data: dict) -> Part:
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    # Category changes are disallowed because the part ID encodes the category
    # (e.g. PJ-DZ-00001 means 吊坠). Allowing a category change would make the
    # ID misleading and break the ID-format contract.
    if "category" in data:
        raise ValueError(
            "Category cannot be changed after creation — the part ID encodes the category."
        )
    # Frontend "clear selection" UX often sends null; size_tier is NOT NULL
    # so treat explicit None as omission rather than letting the DB raise.
    if "size_tier" in data and data["size_tier"] is None:
        data.pop("size_tier")
    if (_is_color_variant(part.name) or part.parent_part_id is not None):
        if "color" in data:
            new_color = data["color"]
            # Empty string = frontend disabled field, treat as no-op
            if new_color != "" and new_color != part.color:
                raise ValueError("变体配件不可修改颜色")
        data.pop("color", None)
    if part.parent_part_id is not None:
        if "parent_part_id" in data:
            new_parent = data["parent_part_id"]
            # Empty string = frontend disabled field, treat as no-op
            if new_parent != "" and new_parent != part.parent_part_id:
                raise ValueError("变体配件不可修改父配件关系")
        data.pop("parent_part_id", None)
    if "parent_part_id" in data and data["parent_part_id"] is not None:
        if data["parent_part_id"] == part_id:
            raise ValueError("配件不能指向自身作为父配件")
        parent = db.get(Part, data["parent_part_id"])
        if parent is None:
            raise ValueError(f"Parent part not found: {data['parent_part_id']}")
        if parent.parent_part_id is not None:
            raise ValueError("不支持多层嵌套：目标配件已有父配件")
        has_children = db.query(Part).filter(Part.parent_part_id == part_id).first() is not None
        if has_children:
            raise ValueError("不支持多层嵌套：当前配件已有子配件，不能再挂到其他配件下")
    data.pop("unit_cost", None)
    assembly_cost_changed = "assembly_cost" in data
    size_tier_changed = "size_tier" in data
    if "spec" in data:
        data["spec"] = (data["spec"].strip() if data["spec"] else None) or None
    for key, value in data.items():
        setattr(part, key, value)
    db.flush()
    if assembly_cost_changed:
        from services.part_bom import recalc_part_unit_cost
        recalc_part_unit_cost(db, part_id)
    # When a root part's size_tier changes, propagate to all variants —
    # BOMs commonly reference variant IDs and the buffer rule reads
    # part.size_tier directly, so divergent tiers between root and variant
    # would silently apply different buffer rules to the same product line.
    if size_tier_changed and part.parent_part_id is None:
        db.query(Part).filter(Part.parent_part_id == part_id).update(
            {"size_tier": part.size_tier}, synchronize_session=False
        )
        db.flush()
    return part


COLOR_CODES = {v["code"]: v["label"] for v in COLOR_VARIANTS}
_LABEL_TO_CODE = {v["label"]: v["code"] for v in COLOR_VARIANTS}


def _validate_variant_request(db: Session, part_id: str, color_code: Optional[str] = None, spec: Optional[str] = None):
    """Validate part exists and params are valid. Returns (source_part, root_part, color_label_or_None, spec_or_None)."""
    # Normalize spec: strip whitespace, treat blank as None
    if spec is not None:
        spec = spec.strip() or None
    if spec is not None and not _VARIANT_SPEC_REGEX.match(spec):
        raise ValueError(
            f"规格格式不合法 '{spec}'。仅支持 \\d+(\\.\\d+)?(cm|mm|m)，例如 45cm、17.5cm、8mm"
        )
    if not color_code and not spec:
        raise ValueError("必须提供 color_code 或 spec 中的至少一个")
    color = None
    if color_code:
        color = COLOR_CODES.get(color_code)
        if color is None:
            raise ValueError(
                f"Invalid color_code '{color_code}'. Must be one of: {list(COLOR_CODES.keys())}"
            )
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    # Always resolve to root — all variants are flat siblings under root
    source = part
    root = part
    if root.parent_part_id is not None:
        # When creating spec-only from a color variant, inherit its color
        if not color and root.color:
            color = root.color
        root = get_part(db, root.parent_part_id)
    elif _looks_like_orphan_variant_name(root.name):
        # Name pattern alone is the reliable signal: a legit root can have
        # color='金色' or spec='45cm' populated (API allows it), but its NAME
        # won't end with `_金色` or `_金色_45cm`.
        raise ValueError(
            "该配件疑似未挂载的变体（名称含颜色 / 颜色+规格后缀），请先修正数据"
        )
    return source, root, color, spec


def _build_variant_name(root_name: str, color: Optional[str], spec: Optional[str]) -> str:
    parts = [root_name]
    if color:
        parts.append(color)
    if spec:
        parts.append(spec)
    return "_".join(parts)


def _next_variant_id(root: Part, color: Optional[str], spec: Optional[str]) -> str:
    """Build variant ID as {root_id}-{color_code}[-{spec}].

    Examples:
        root PJ-DZ-00001 + color 金色        -> PJ-DZ-00001-G
        root PJ-DZ-00001 + color 金色 + 45cm -> PJ-DZ-00001-G-45cm
        root PJ-LT-00008 + spec only 45cm    -> PJ-LT-00008-45cm

    Relies on variant suffix shape never colliding with flat {prefix}-NNNNN IDs
    (flat IDs contain only digits after the last dash).
    """
    segments = [root.id]
    if color:
        code = _LABEL_TO_CODE.get(color)
        if code is None:
            raise ValueError(f"未知颜色 '{color}'（不在 COLOR_VARIANTS 中）")
        segments.append(code)
    if spec:
        segments.append(spec)
    return "-".join(segments)


def _find_existing_variant(db: Session, part_id: str, variant_name: str, color: Optional[str], spec: Optional[str] = None):
    """Find existing variant matching (name, color, spec) exactly.

    Search order:
      1) children of part_id whose name + color + spec ALL match
      2) orphans in same category (no parent) whose name + color + spec ALL match

    Crucially, if a child's name matches but color/spec does not, that child is
    treated as corrupted data and skipped — we do NOT return it for reuse.
    """
    def _match(candidate: Part) -> bool:
        return (
            (candidate.color or None) == color
            and (candidate.spec or None) == spec
        )

    # 1) Children of the target parent with matching name
    children = (
        db.query(Part)
        .filter(
            Part.parent_part_id == part_id,
            Part.name == variant_name,
        )
        .all()
    )
    for child in children:
        if _match(child):
            return child
    # Any name-matching child that fails color/spec check is corrupted — skip dedup.

    # 2) Fallback: orphans in the same category
    parent = db.get(Part, part_id)
    if parent is None:
        return None
    orphans = (
        db.query(Part)
        .filter(
            Part.name == variant_name,
            Part.id != part_id,
            Part.category == parent.category,
            Part.parent_part_id.is_(None),
        )
        .all()
    )
    for orphan in orphans:
        if _match(orphan):
            orphan.parent_part_id = part_id
            db.flush()
            return orphan
    return None


def create_part_variant(db: Session, part_id: str, color_code: Optional[str] = None, spec: Optional[str] = None) -> Part:
    source, root, color, spec = _validate_variant_request(db, part_id, color_code, spec)
    variant_name = _build_variant_name(root.name, color, spec)
    existing = _find_existing_variant(db, root.id, variant_name, color, spec)
    if existing is not None:
        if spec and existing.unit != "条":
            existing.unit = "条"
            db.flush()
        return existing
    # Same-color derivation (e.g. xx_金色 → xx_金色_45cm): inherit source's attributes
    # Cross-color (e.g. xx_金色 → xx_白K): inherit from root to avoid pollution
    same_color = source.id != root.id and (not color or color == source.color)
    donor = source if same_color else root
    variant = Part(
        id=_next_variant_id(root, color, spec),
        name=variant_name,
        category=root.category,
        unit="条" if spec else donor.unit,
        purchase_cost=donor.purchase_cost,
        bead_cost=donor.bead_cost,
        plating_cost=donor.plating_cost,
        plating_process=donor.plating_process,
        image=donor.image,
        color=color,
        spec=spec,
        parent_part_id=root.id,
        size_tier=donor.size_tier,
    )
    _recalc_unit_cost(variant)
    db.add(variant)
    db.flush()
    return variant


def find_or_create_variant(db: Session, part_id: str, color_code: Optional[str] = None, spec: Optional[str] = None) -> dict:
    _source, root, color, spec = _validate_variant_request(db, part_id, color_code, spec)
    variant_name = _build_variant_name(root.name, color, spec)
    existing = _find_existing_variant(db, root.id, variant_name, color, spec)
    if existing is not None:
        return {"part": existing, "suggested_name": None}
    return {"part": None, "suggested_name": variant_name}


def list_part_variants(db: Session, part_id: str) -> List[Part]:
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    root_id = part.parent_part_id if part.parent_part_id is not None else part_id
    variants = (
        db.query(Part)
        .filter(Part.parent_part_id == root_id)
        .order_by(Part.id.desc())
        .all()
    )
    if part.parent_part_id is not None:
        # Include the root part when querying from a variant
        root = db.get(Part, root_id)
        return [root] + variants if root else variants
    return variants


def delete_part(db: Session, part_id: str) -> None:
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")
    has_children = db.query(Part).filter(Part.parent_part_id == part_id).first() is not None
    if has_children:
        raise ValueError("该配件存在颜色变体，请先删除所有变体后再删除根配件")
    db.delete(part)
    db.flush()


def _recalc_unit_cost(part: Part) -> None:
    purchase = Decimal(str(part.purchase_cost or 0))
    bead = Decimal(str(part.bead_cost or 0))
    plating = Decimal(str(part.plating_cost or 0))
    total = purchase + bead + plating
    part.unit_cost = total if total else None


def _recalc_unit_cost_and_propagate(db: Session, part: Part) -> None:
    """Recalc unit_cost and propagate to parent parts that reference this part."""
    _recalc_unit_cost(part)
    from services.part_bom import recalc_parents_of_child
    recalc_parents_of_child(db, part.id)


def update_part_cost(
    db: Session, part_id: str, field: str, value: float, source_id: Optional[str] = None,
) -> Optional[PartCostLog]:
    # handcraft_cost targets Jewelry, not Part
    if field == "handcraft_cost":
        return _update_jewelry_handcraft_cost(db, part_id, value, source_id)

    if field not in _COST_FIELDS:
        raise ValueError(f"无效的成本字段: {field}")
    part = get_part(db, part_id)
    if part is None:
        raise ValueError(f"Part not found: {part_id}")

    old_field_value = getattr(part, field)
    old_unit_cost = part.unit_cost

    new_value = Decimal(str(value)).quantize(_Q7, rounding=ROUND_HALF_UP)

    old_comparable = Decimal(str(old_field_value)).quantize(_Q7, rounding=ROUND_HALF_UP) if old_field_value is not None else None
    if old_comparable == new_value:
        return None

    setattr(part, field, new_value)
    _recalc_unit_cost_and_propagate(db, part)

    log = PartCostLog(
        part_id=part_id,
        field=field,
        cost_before=old_field_value,
        cost_after=new_value,
        unit_cost_before=old_unit_cost,
        unit_cost_after=part.unit_cost,
        source_id=source_id,
    )
    db.add(log)
    db.flush()
    return log


def _update_jewelry_handcraft_cost(
    db: Session, jewelry_id: str, value: float, source_id: Optional[str] = None,
) -> Optional[PartCostLog]:
    """Update handcraft_cost on Jewelry model.

    Returns a transient PartCostLog (not persisted) to signal success,
    since PartCostLog.part_id has FK to part table and cannot store jewelry IDs.
    """
    from models.jewelry import Jewelry
    jewelry = db.get(Jewelry, jewelry_id)
    if jewelry is None:
        raise ValueError(f"Jewelry not found: {jewelry_id}")

    old_value = jewelry.handcraft_cost
    new_value = Decimal(str(value)).quantize(_Q7, rounding=ROUND_HALF_UP)

    old_comparable = Decimal(str(old_value)).quantize(_Q7, rounding=ROUND_HALF_UP) if old_value is not None else None
    if old_comparable == new_value:
        return None

    jewelry.handcraft_cost = new_value
    db.flush()

    # Return a transient object to indicate update happened (not added to session)
    return PartCostLog(
        part_id=jewelry_id,
        field="handcraft_cost",
        cost_before=old_value,
        cost_after=new_value,
    )


def list_part_cost_logs(db: Session, part_id: str) -> list[PartCostLog]:
    return (
        db.query(PartCostLog)
        .filter(PartCostLog.part_id == part_id)
        .order_by(PartCostLog.created_at.desc())
        .all()
    )
