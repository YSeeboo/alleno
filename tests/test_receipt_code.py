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
