import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import Part
from services._helpers import _next_id


def test_next_id_first_row(db):
    """When table is empty, returns prefix-0001."""
    result = _next_id(db, Part, "PJ")
    assert result == "PJ-0001"


def test_next_id_increments(db):
    """When existing IDs present, returns max+1."""
    db.add(Part(id="PJ-0003", name="test"))
    db.add(Part(id="PJ-0001", name="test2"))
    db.flush()
    result = _next_id(db, Part, "PJ")
    assert result == "PJ-0004"


def test_next_id_custom_width(db):
    result = _next_id(db, Part, "PJ", width=6)
    assert result == "PJ-000001"
