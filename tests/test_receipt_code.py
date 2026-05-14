import pytest

from services.handcraft import _gen_receipt_code, _RECEIPT_CODE_ALPHABET
from models.handcraft_order import HandcraftOrder


def test_gen_receipt_code_is_5_chars(db):
    code = _gen_receipt_code(db)
    assert len(code) == 5


def test_gen_receipt_code_uses_safe_alphabet(db):
    code = _gen_receipt_code(db)
    assert all(c in _RECEIPT_CODE_ALPHABET for c in code)
    # ensure ambiguous chars are excluded
    assert all(c not in code for c in "0OIL1")


def test_gen_receipt_code_raises_after_too_many_collisions(db, monkeypatch):
    import services.handcraft as svc
    fixed = "AAAAA"

    def stub_choice(_alphabet):
        return fixed[0]  # always 'A', so generated code is always "AAAAA"
    monkeypatch.setattr(svc.secrets, "choice", stub_choice)

    db.add(HandcraftOrder(id="HC-T2", supplier_name="王", status="pending", receipt_code=fixed))
    db.flush()
    with pytest.raises(RuntimeError, match="无法生成唯一回执码"):
        _gen_receipt_code(db, max_tries=3)


from services.handcraft import create_handcraft_order


def test_create_handcraft_order_assigns_receipt_code(db):
    from models.part import Part
    db.add(Part(id="PJ-DZ-00001", name="测试", category="吊坠"))
    db.flush()
    order = create_handcraft_order(
        db,
        supplier_name="王师傅",
        parts=[{"part_id": "PJ-DZ-00001", "qty": 10}],
    )
    assert order.receipt_code is not None
    assert len(order.receipt_code) == 5


def test_create_handcraft_order_auto_merge_does_not_regenerate_code(db):
    from models.part import Part
    db.add(Part(id="PJ-DZ-00002", name="测试2", category="吊坠"))
    db.flush()
    first = create_handcraft_order(
        db, supplier_name="陈师傅",
        parts=[{"part_id": "PJ-DZ-00002", "qty": 5}],
    )
    original_code = first.receipt_code
    second = create_handcraft_order(
        db, supplier_name="陈师傅",
        parts=[{"part_id": "PJ-DZ-00002", "qty": 7}],
    )
    # auto-merge: same id and same code
    assert second.id == first.id
    assert second.receipt_code == original_code


def test_link_supplier_assigns_receipt_code(db):
    """End-to-end: creating HC via order_todo.link_supplier sets a receipt_code."""
    from tests.helpers import seed_order_with_batch
    from services.order_todo import link_supplier
    order_id, batch_id = seed_order_with_batch(db)
    result = link_supplier(db, order_id, batch_id, "王师傅")
    hc = db.query(HandcraftOrder).filter_by(id=result["handcraft_order_id"]).first()
    assert hc.receipt_code is not None
    assert len(hc.receipt_code) == 5
