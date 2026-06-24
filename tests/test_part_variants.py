import pytest
from services.part import create_part, create_part_variant
from services.part import get_part


def test_composite_root_rejects_variant(db):
    p = create_part(db, {"name": "套底托", "category": "小配件"})
    get_part(db, p.id).is_composite = True
    db.flush()
    with pytest.raises(ValueError, match="组合件不支持变体"):
        create_part_variant(db, p.id, color_code="G")


def test_create_part_with_composite_parent_rejected(db):
    parent = create_part(db, {"name": "组合父", "category": "小配件"})
    get_part(db, parent.id).is_composite = True
    db.flush()
    with pytest.raises(ValueError, match="组合件不支持变体"):
        create_part(db, {"name": "子件", "category": "小配件", "parent_part_id": parent.id})
