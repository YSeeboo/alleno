from services._helpers import keyword_filter
from models.part import Part
from models.plating_order import PlatingOrder


def _make_parts(db, names):
    """Helper: create parts with the given Chinese names, one per category prefix."""
    parts = []
    for i, name in enumerate(names):
        p = Part(id=f"PJ-DZ-{i + 1:05d}", name=name, category="吊坠")
        db.add(p)
        parts.append(p)
    db.flush()
    return parts


def _query_parts(db, keyword):
    clause = keyword_filter(keyword, Part.name, Part.id)
    q = db.query(Part)
    if clause is not None:
        q = q.filter(clause)
    return q.order_by(Part.id).all()


def test_keyword_filter_none_returns_none():
    assert keyword_filter(None, Part.name) is None


def test_keyword_filter_empty_string_returns_none():
    assert keyword_filter("", Part.name) is None


def test_keyword_filter_whitespace_only_returns_none():
    assert keyword_filter("   ", Part.name) is None
    assert keyword_filter("\t\n ", Part.name) is None
    assert keyword_filter("　　", Part.name) is None  # U+3000 full-width


def test_keyword_filter_single_token_finds_substring(db):
    _make_parts(db, ["背镂空满钻桃心", "纯银链条", "简约吊坠"])
    results = _query_parts(db, "桃心")
    assert len(results) == 1
    assert results[0].name == "背镂空满钻桃心"


def test_keyword_filter_multi_token_half_width_space(db):
    """Primary regression: '背镂空 桃心' must find '背镂空满钻桃心'."""
    _make_parts(db, ["背镂空满钻桃心", "背镂空圆环", "满钻桃心吊坠"])
    results = _query_parts(db, "背镂空 桃心")
    assert len(results) == 1
    assert results[0].name == "背镂空满钻桃心"


def test_keyword_filter_multi_token_full_width_space(db):
    """全角空格 U+3000 must also split tokens."""
    _make_parts(db, ["背镂空满钻桃心", "背镂空圆环"])
    results = _query_parts(db, "背镂空　桃心")
    assert len(results) == 1
    assert results[0].name == "背镂空满钻桃心"


def test_keyword_filter_multi_token_and_semantics(db):
    """Both tokens must match — a non-existent second token yields empty."""
    _make_parts(db, ["背镂空满钻桃心"])
    results = _query_parts(db, "桃心 不存在的词")
    assert results == []


def test_keyword_filter_case_insensitive_ascii(db):
    _make_parts(db, ["taoxin ring"])
    results = _query_parts(db, "TAOXIN")
    assert len(results) == 1


def test_keyword_filter_mixed_id_and_name_token(db):
    """'PJ-DZ 桃心' should find a PJ-DZ-xxx record whose name contains 桃心."""
    parts = _make_parts(db, ["桃心吊坠", "圆环吊坠"])
    results = _query_parts(db, "PJ-DZ 桃心")
    assert len(results) == 1
    assert results[0].name == "桃心吊坠"


def test_keyword_filter_consecutive_whitespace_filtered(db):
    """Multiple spaces between tokens should not produce empty tokens."""
    _make_parts(db, ["背镂空满钻桃心"])
    results = _query_parts(db, "背镂空   桃心")
    assert len(results) == 1


def test_keyword_filter_single_column_and_semantics(db):
    """AND semantics must hold when only one column is passed."""
    db.add(PlatingOrder(id="EP-0001", supplier_name="老王北京电镀厂", status="pending"))
    db.add(PlatingOrder(id="EP-0002", supplier_name="老王上海电镀厂", status="pending"))
    db.add(PlatingOrder(id="EP-0003", supplier_name="老李北京电镀厂", status="pending"))
    db.flush()

    clause = keyword_filter("老王 北京", PlatingOrder.supplier_name)
    assert clause is not None
    results = db.query(PlatingOrder).filter(clause).all()
    assert len(results) == 1
    assert results[0].supplier_name == "老王北京电镀厂"
