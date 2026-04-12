from typing import Optional

from sqlalchemy.orm import Session

from models.jewelry_template import JewelryTemplate, JewelryTemplateItem
from models.part import Part
from services.bom import set_bom


def _require_part(db: Session, part_id: str) -> None:
    if db.get(Part, part_id) is None:
        raise ValueError(f"Part not found: {part_id}")


def _enrich_items(db: Session, items: list[JewelryTemplateItem]) -> list[dict]:
    """返回 enriched dict 列表。"""
    results = []
    for item in items:
        part = db.get(Part, item.part_id)
        results.append({
            "id": item.id,
            "template_id": item.template_id,
            "part_id": item.part_id,
            "qty_per_unit": float(item.qty_per_unit),
            "part_name": part.name if part else None,
            "part_image": part.image if part else None,
            "part_is_composite": part.is_composite if part else None,
        })
    return results


def create_template(db: Session, data: dict) -> dict:
    for item in data["items"]:
        _require_part(db, item["part_id"])

    template = JewelryTemplate(
        name=data["name"],
        image=data.get("image"),
        note=data.get("note"),
    )
    db.add(template)
    db.flush()

    for item in data["items"]:
        db.add(JewelryTemplateItem(
            template_id=template.id,
            part_id=item["part_id"],
            qty_per_unit=item["qty_per_unit"],
        ))
    db.flush()

    return get_template(db, template.id)


def get_template(db: Session, template_id: int) -> Optional[dict]:
    template = db.get(JewelryTemplate, template_id)
    if template is None:
        return None
    enriched_items = _enrich_items(db, template.items)
    return {
        "id": template.id,
        "name": template.name,
        "image": template.image,
        "note": template.note,
        "created_at": template.created_at,
        "items": enriched_items,
        "item_count": len(enriched_items),
    }


def list_templates(db: Session) -> list[dict]:
    templates = db.query(JewelryTemplate).order_by(JewelryTemplate.id.desc()).all()
    return [get_template(db, t.id) for t in templates]


def update_template(db: Session, template_id: int, data: dict) -> dict:
    template = db.get(JewelryTemplate, template_id)
    if template is None:
        raise ValueError(f"JewelryTemplate not found: {template_id}")

    for field in ("name", "image", "note"):
        if field in data:
            setattr(template, field, data[field])

    # 如果提供了 items，全量替换
    if "items" in data and data["items"] is not None:
        if len(data["items"]) == 0:
            raise ValueError("模板至少需要一个配件")
        for item in data["items"]:
            _require_part(db, item["part_id"])
        # 删除旧的
        db.query(JewelryTemplateItem).filter(
            JewelryTemplateItem.template_id == template_id
        ).delete(synchronize_session=False)
        db.flush()
        # 添加新的
        for item in data["items"]:
            db.add(JewelryTemplateItem(
                template_id=template_id,
                part_id=item["part_id"],
                qty_per_unit=item["qty_per_unit"],
            ))

    db.flush()
    return get_template(db, template_id)


def delete_template(db: Session, template_id: int) -> None:
    template = db.get(JewelryTemplate, template_id)
    if template is None:
        raise ValueError(f"JewelryTemplate not found: {template_id}")
    db.delete(template)
    db.flush()


def apply_template_to_jewelry(db: Session, template_id: int, jewelry_id: str) -> list:
    """将模板的配件导入到饰品的 BOM 中（upsert）。"""
    template = db.get(JewelryTemplate, template_id)
    if template is None:
        raise ValueError(f"JewelryTemplate not found: {template_id}")

    results = []
    for item in template.items:
        bom = set_bom(db, jewelry_id, item.part_id, float(item.qty_per_unit))
        results.append(bom)
    return results
