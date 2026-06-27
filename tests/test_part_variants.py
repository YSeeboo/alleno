import pytest
from services.part import create_part, create_part_variant
from services.part import get_part
from services.part import COLOR_VARIANTS, COLOR_CODES, COLOR_SUFFIXES


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


def test_color_variants_has_five_enriched_entries():
    by_code = {c["code"]: c for c in COLOR_VARIANTS}
    assert set(by_code) == {"G", "S", "RG", "K14", "SV"}
    for c in COLOR_VARIANTS:
        assert set(c) >= {"code", "label", "method", "badge", "common"}
    assert by_code["G"]["common"] is True
    assert by_code["K14"]["common"] is False
    assert by_code["SV"]["common"] is False
    assert by_code["K14"]["label"] == "14K金"
    assert by_code["K14"]["method"] == "14K金"
    assert by_code["K14"]["badge"] == "#CBA94B"
    assert by_code["SV"]["label"] == "银色"
    assert by_code["SV"]["method"] == "银"
    assert by_code["SV"]["badge"] == "#9AA7B0"


def test_color_derived_maps_include_new_colors():
    assert COLOR_CODES["K14"] == "14K金"
    assert COLOR_CODES["SV"] == "银色"
    assert "14K金" in COLOR_SUFFIXES
    assert "银色" in COLOR_SUFFIXES


def test_create_variant_k14(db):
    root = create_part(db, {"name": "吊坠A", "category": "吊坠"})
    v = create_part_variant(db, root.id, color_code="K14")
    assert v.id == f"{root.id}-K14"
    assert v.name == "吊坠A_14K金"
    assert v.color == "14K金"


def test_create_variant_sv(db):
    root = create_part(db, {"name": "吊坠B", "category": "吊坠"})
    v = create_part_variant(db, root.id, color_code="SV")
    assert v.id == f"{root.id}-SV"
    assert v.name == "吊坠B_银色"
    assert v.color == "银色"


def test_create_variant_existing_g_unaffected(db):
    root = create_part(db, {"name": "吊坠C", "category": "吊坠"})
    v = create_part_variant(db, root.id, color_code="G")
    assert v.id == f"{root.id}-G"
    assert v.name == "吊坠C_金色"


def test_create_variant_invalid_code_raises(db):
    root = create_part(db, {"name": "吊坠D", "category": "吊坠"})
    with pytest.raises(ValueError):
        create_part_variant(db, root.id, color_code="ZZ")
