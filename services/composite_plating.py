from sqlalchemy.orm import Session

from models.part import Part
from models.part_bom import PartBom
from models.plating_order import CompositePlatingTarget
from services._helpers import _next_id
from services.part import COLOR_VARIANTS
from services.part_bom import recalc_part_unit_cost


_COLORS = {c["code"]: c for c in COLOR_VARIANTS}


def _color(color_code):
    color = _COLORS.get(color_code)
    if color is None:
        raise ValueError("请选择有效的电镀颜色")
    return color


def _bom_rows(db, part_ids):
    return db.query(PartBom).filter(PartBom.parent_part_id.in_(part_ids)).order_by(PartBom.id).all()


def _validate_target(db, source, target, color, unit):
    if not target.is_composite or target.color != color["label"] or target.spec != source.spec:
        raise ValueError(f"镀色组合件 {target.id} 的颜色、规格或组合属性不匹配")
    if (source.unit or "个") != (target.unit or "个") or (unit is not None and unit != (source.unit or "个")):
        raise ValueError("整件送镀的发出、收回及明细单位必须一致")
    source_bom, target_bom = [], []
    for row in _bom_rows(db, [source.id, target.id]):
        (source_bom if row.parent_part_id == source.id else target_bom).append((row.child_part_id, row.qty_per_unit))
    if not source_bom or sorted(source_bom) != sorted(target_bom):
        raise ValueError(f"镀色组合件 {target.id} 与发出组合件的 BOM 不一致，请先核对两份 BOM")


def composite_plating_target(db: Session, part_id: str, color_code: str, *, create=False):
    color = _color(color_code)
    q = db.query(Part).filter_by(id=part_id)
    # Serialize confirmation for the same source. The DB keys also enforce
    # exactly one registered SKU per source/color and one owner per target.
    source = (q.with_for_update(key_share=True).populate_existing() if create else q).first()
    if source is None or not source.is_composite:
        raise ValueError("仅组合件可使用整件送镀")
    if db.query(CompositePlatingTarget).filter_by(target_part_id=part_id).first() is not None:
        raise ValueError("请选原组合件发出，暂不支持镀色组合件再次送镀")
    if source.color == color["label"]:
        raise ValueError("请选择与发出组合件不同的电镀颜色")

    link = db.get(CompositePlatingTarget, (part_id, color_code))
    unit = source.unit or "个"
    if link:
        target = db.get(Part, link.target_part_id)
        _validate_target(db, source, target, color, unit)
        return {"part": target, "unit": unit, "plating_method": color["method"], "created": False}

    rows = _bom_rows(db, [part_id])
    if not rows:
        raise ValueError("发出组合件还没有 BOM，请先保存子配件清单")
    target_id = f"{part_id}-EP-{color_code}"
    target_name = f"{source.name}（{color['label']}整镀）"
    if db.get(Part, target_id) is not None:
        raise ValueError(f"建议编号 {target_id} 已被占用，不能自动作为收回组合件")
    result = dict(part=None, suggested_id=target_id, suggested_name=target_name,
                  unit=unit, plating_method=color["method"], created=False)
    if not create:
        return result

    target = Part(id=target_id, name=target_name, unit=unit, color=color["label"],
                  category=source.category, image=source.image, spec=source.spec,
                  is_composite=True, assembly_cost=source.assembly_cost,
                  size_tier=source.size_tier, buffer_ratio_override=source.buffer_ratio_override,
                  buffer_floor_override=source.buffer_floor_override)
    db.add(target)
    db.flush()
    for row in rows:
        db.add(PartBom(id=_next_id(db, PartBom, "PB"), parent_part_id=target_id,
                       child_part_id=row.child_part_id, qty_per_unit=row.qty_per_unit))
    db.add(CompositePlatingTarget(source_part_id=part_id, color_code=color_code, target_part_id=target_id))
    db.flush()
    recalc_part_unit_cost(db, target_id)
    return {**result, "part": target, "created": True}


def validate_plating_target(db: Session, part_id, receive_id, method, unit, *,
                            allow_incomplete=False, check_normal_family=False, infer_method=False):
    source = db.get(Part, part_id)
    if source is None:
        raise ValueError(f"Part not found: {part_id}")
    target = db.get(Part, receive_id) if receive_id is not None else None
    if receive_id is not None and target is None:
        raise ValueError(f"Part not found: {receive_id}")
    if not source.is_composite:
        if target is not None and target.is_composite:
            raise ValueError("普通配件不能收回为组合件")
        if check_normal_family and target is not None and (
            (source.parent_part_id or source.id) != (target.parent_part_id or target.id)
        ):
            raise ValueError("收回配件必须与发出配件属于同一配件族")
        return method

    if target is None:
        if allow_incomplete:
            return method
        raise ValueError(f"组合件 {source.id} 请先选择整件送镀的收回编号")
    link = db.query(CompositePlatingTarget).filter_by(target_part_id=target.id, source_part_id=source.id).first()
    if link is None:
        raise ValueError("收回配件必须是该发出组合件对应的镀色组合件")
    color = _color(link.color_code)
    if not method and infer_method:
        method = color["method"]
    if method != color["method"] or source.color == color["label"]:
        raise ValueError("电镀颜色必须与收回组合件匹配，并与发出组合件不同")
    _validate_target(db, source, target, color, unit)
    return method
