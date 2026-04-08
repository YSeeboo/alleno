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


def test_next_id_no_reuse_after_delete_max(db):
    """Deleting the highest ID should not cause reuse."""
    db.add(Part(id="PJ-0001", name="a"))
    db.add(Part(id="PJ-0002", name="b"))
    db.flush()
    # Generate next to initialize counter to 2
    assert _next_id(db, Part, "PJ") == "PJ-0003"
    # Simulate adding and deleting the record with max id
    db.add(Part(id="PJ-0003", name="c"))
    db.flush()
    db.query(Part).filter_by(id="PJ-0003").delete()
    db.flush()
    # Next ID should be 0004, not 0003
    assert _next_id(db, Part, "PJ") == "PJ-0004"


def test_next_id_no_reuse_after_delete_middle(db):
    """Deleting a middle ID leaves a gap — it is never filled."""
    db.add(Part(id="PJ-0001", name="a"))
    db.add(Part(id="PJ-0002", name="b"))
    db.flush()
    assert _next_id(db, Part, "PJ") == "PJ-0003"
    # Delete middle record
    db.query(Part).filter_by(id="PJ-0002").delete()
    db.flush()
    # Next should be 0004, not 0002
    assert _next_id(db, Part, "PJ") == "PJ-0004"


def test_next_id_init_from_existing_data(db):
    """First call with existing data initializes counter from max."""
    db.add(Part(id="PJ-0005", name="a"))
    db.add(Part(id="PJ-0002", name="b"))
    db.flush()
    # Counter doesn't exist yet; should initialize from max (5)
    assert _next_id(db, Part, "PJ") == "PJ-0006"
    assert _next_id(db, Part, "PJ") == "PJ-0007"
