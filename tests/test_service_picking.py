"""Tests for services/picking.py — picking simulation aggregation and state."""

from decimal import Decimal
from typing import Optional
from sqlalchemy import inspect

from models.order import Order, OrderPickingRecord
from models.part import Part


def test_order_picking_record_table_exists(db):
    """The OrderPickingRecord table is registered with SQLAlchemy and create_all()
    made it. Basic smoke test for the model wiring."""
    insp = inspect(db.get_bind())
    assert "order_picking_record" in insp.get_table_names()


def test_order_picking_record_insert_and_read(db):
    """Insert a picking record and read it back. Verifies columns exist,
    defaults work, and unique key isn't fighting normal inserts."""
    part = Part(id="PJ-X-00001", name="Test Part")
    db.add(part)
    db.flush()

    order = Order(id="OR-PICK-1", customer_name="Test")
    db.add(order)
    db.flush()

    rec = OrderPickingRecord(
        order_id="OR-PICK-1",
        part_id="PJ-X-00001",
        qty_per_unit=Decimal("2.0000"),
    )
    db.add(rec)
    db.flush()

    row = db.query(OrderPickingRecord).filter_by(order_id="OR-PICK-1").one()
    assert row.part_id == "PJ-X-00001"
    assert float(row.qty_per_unit) == 2.0
    assert row.picked_at is not None  # default populated


# --- Schema smoke tests ---

def test_picking_simulation_response_schema():
    from schemas.order import (
        PickingVariant, PickingPartRow, PickingProgress,
        PickingSimulationResponse,
    )
    resp = PickingSimulationResponse(
        order_id="OR-1",
        customer_name="客户 A",
        rows=[
            PickingPartRow(
                part_id="PJ-X-001",
                part_name="小珠子",
                part_image="https://example/x.png",
                current_stock=45.0,
                is_composite_child=False,
                variants=[
                    PickingVariant(qty_per_unit=2.0, units_count=10,
                                   subtotal=20.0, picked=False),
                ],
                total_required=20.0,
            ),
        ],
        progress=PickingProgress(total=1, picked=0),
    )
    assert resp.rows[0].variants[0].qty_per_unit == 2.0


def test_picking_mark_request_schema():
    from schemas.order import PickingMarkRequest
    req = PickingMarkRequest(part_id="PJ-X-001", qty_per_unit=3.0)
    assert req.qty_per_unit == 3.0


def test_picking_pdf_request_defaults_include_picked_false():
    from schemas.order import PickingPdfRequest
    req = PickingPdfRequest()
    assert req.include_picked is False


# --- Aggregation: core ---


def _make_part(db, pid: str, name: str, image: Optional[str] = None, is_composite: bool = False):
    from models.part import Part
    p = Part(id=pid, name=name, category="吊坠", image=image, is_composite=is_composite)
    db.add(p)
    db.flush()
    return p


def _make_jewelry(db, jid: str, name: str):
    from models.jewelry import Jewelry
    j = Jewelry(id=jid, name=name, category="戒指")
    db.add(j)
    db.flush()
    return j


def _make_bom(db, jewelry_id: str, part_id: str, qty_per_unit: float):
    from decimal import Decimal
    from models.bom import Bom
    from services._helpers import _next_id
    b = Bom(
        id=_next_id(db, Bom, "BM"),
        jewelry_id=jewelry_id,
        part_id=part_id,
        qty_per_unit=Decimal(str(qty_per_unit)),
    )
    db.add(b)
    db.flush()
    return b


def _make_order(db, oid: str, items: list):
    """items: list of (jewelry_id, quantity)."""
    from models.order import Order, OrderItem
    from decimal import Decimal
    order = Order(id=oid, customer_name="客户测试")
    db.add(order)
    db.flush()
    for jid, qty in items:
        db.add(OrderItem(order_id=oid, jewelry_id=jid, quantity=qty,
                         unit_price=Decimal("1.0")))
    db.flush()
    return order


def test_picking_simulation_single_jewelry_single_part(db):
    """Order with 1 jewelry (quantity=10) → 1 part at qty_per_unit=2 → subtotal=20."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "小珠子")
    _make_jewelry(db, "SP-0001", "项链 A")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_order(db, "OR-0001", [("SP-0001", 10)])

    result = get_picking_simulation(db, "OR-0001")

    assert result.order_id == "OR-0001"
    assert result.customer_name == "客户测试"
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.part_id == "PJ-X-00001"
    assert row.part_name == "小珠子"
    assert row.is_composite_child is False
    assert len(row.variants) == 1
    v = row.variants[0]
    assert v.qty_per_unit == 2.0
    assert v.units_count == 10
    assert v.subtotal == 20.0
    assert v.picked is False
    assert row.total_required == 20.0
    assert result.progress.total == 1
    assert result.progress.picked == 0


def test_picking_simulation_empty_order(db):
    """Order with no items → empty rows, progress 0/0."""
    from services.picking import get_picking_simulation

    _make_order(db, "OR-EMPTY", [])
    result = get_picking_simulation(db, "OR-EMPTY")
    assert result.rows == []
    assert result.progress.total == 0
    assert result.progress.picked == 0


def test_picking_simulation_order_not_found(db):
    """Unknown order id → ValueError."""
    from services.picking import get_picking_simulation
    import pytest
    with pytest.raises(ValueError, match="OR-NOPE"):
        get_picking_simulation(db, "OR-NOPE")


def test_picking_simulation_two_parts_same_jewelry(db):
    """Jewelry with 2 parts in BOM → 2 rows sorted by part_id."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "珠子")
    _make_part(db, "PJ-X-00002", "扣子")
    _make_jewelry(db, "SP-0001", "项链")
    _make_bom(db, "SP-0001", "PJ-X-00002", 1.0)  # insert out of order
    _make_bom(db, "SP-0001", "PJ-X-00001", 3.0)
    _make_order(db, "OR-0001", [("SP-0001", 5)])

    result = get_picking_simulation(db, "OR-0001")
    assert [r.part_id for r in result.rows] == ["PJ-X-00001", "PJ-X-00002"]
    assert result.rows[0].variants[0].subtotal == 15.0  # 3 × 5
    assert result.rows[1].variants[0].subtotal == 5.0   # 1 × 5


def test_picking_simulation_same_part_two_jewelries_same_qty(db):
    """Two jewelries using the same part at the same qty_per_unit →
    one row, one variant, units_count summed."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "项链 A")
    _make_jewelry(db, "SP-0002", "项链 B")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_bom(db, "SP-0002", "PJ-X-00001", 2.0)
    _make_order(db, "OR-0001", [("SP-0001", 10), ("SP-0002", 5)])

    result = get_picking_simulation(db, "OR-0001")
    assert len(result.rows) == 1
    row = result.rows[0]
    assert len(row.variants) == 1
    assert row.variants[0].units_count == 15  # 10 + 5
    assert row.variants[0].subtotal == 30.0   # 2 × 15


def test_picking_simulation_same_part_two_jewelries_different_qty(db):
    """Same part used at two distinct qty_per_unit → 1 row, 2 variants."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "A")
    _make_jewelry(db, "SP-0002", "B")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_bom(db, "SP-0002", "PJ-X-00001", 3.0)
    _make_order(db, "OR-0001", [("SP-0001", 10), ("SP-0002", 5)])

    result = get_picking_simulation(db, "OR-0001")
    assert len(result.rows) == 1
    row = result.rows[0]
    variants_by_qty = {v.qty_per_unit: v for v in row.variants}
    assert 2.0 in variants_by_qty
    assert 3.0 in variants_by_qty
    assert variants_by_qty[2.0].units_count == 10
    assert variants_by_qty[2.0].subtotal == 20.0
    assert variants_by_qty[3.0].units_count == 5
    assert variants_by_qty[3.0].subtotal == 15.0
    assert row.total_required == 35.0  # 20 + 15
    assert result.progress.total == 2  # 2 variants


# --- Aggregation: composite expansion ---


def _make_part_bom(db, parent_part_id: str, child_part_id: str, qty_per_unit: float):
    from models.part_bom import PartBom
    from services._helpers import _next_id
    from decimal import Decimal
    pb = PartBom(
        id=_next_id(db, PartBom, "PB"),
        parent_part_id=parent_part_id,
        child_part_id=child_part_id,
        qty_per_unit=Decimal(str(qty_per_unit)),
    )
    db.add(pb)
    db.flush()
    return pb


def test_picking_simulation_composite_expanded_to_atoms(db):
    """Jewelry BOM references a composite part → output contains atomic
    children only, with is_composite_child=True; composite itself is absent."""
    from services.picking import get_picking_simulation

    # Composite "金属底托" has 2 atomic children: 焊接片 × 2, 链扣 × 1
    composite = _make_part(db, "PJ-X-00010", "金属底托", is_composite=True)
    atom_a = _make_part(db, "PJ-X-00011", "焊接片")
    atom_b = _make_part(db, "PJ-X-00012", "链扣")
    _make_part_bom(db, "PJ-X-00010", "PJ-X-00011", 2.0)
    _make_part_bom(db, "PJ-X-00010", "PJ-X-00012", 1.0)

    _make_jewelry(db, "SP-0001", "戒指")
    _make_bom(db, "SP-0001", "PJ-X-00010", 1.0)  # 1 composite per unit
    _make_order(db, "OR-0001", [("SP-0001", 5)])  # 5 units

    result = get_picking_simulation(db, "OR-0001")
    part_ids = [r.part_id for r in result.rows]
    assert "PJ-X-00010" not in part_ids  # composite itself absent
    assert "PJ-X-00011" in part_ids
    assert "PJ-X-00012" in part_ids

    row_a = next(r for r in result.rows if r.part_id == "PJ-X-00011")
    assert row_a.is_composite_child is True
    # Each unit → 1 composite → 2 焊接片. 5 units → 10 焊接片.
    # qty_per_unit at leaf = jewelry.qty_per_unit × composite_qty_per_unit = 1 × 2 = 2
    assert len(row_a.variants) == 1
    v = row_a.variants[0]
    assert v.qty_per_unit == 2.0
    assert v.units_count == 5
    assert v.subtotal == 10.0


def test_picking_simulation_nested_composite(db):
    """Composite A → composite B → atom C. Output contains only C with
    is_composite_child=True."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00020", "外组合 A", is_composite=True)
    _make_part(db, "PJ-X-00021", "内组合 B", is_composite=True)
    _make_part(db, "PJ-X-00022", "原子 C")
    _make_part_bom(db, "PJ-X-00020", "PJ-X-00021", 2.0)
    _make_part_bom(db, "PJ-X-00021", "PJ-X-00022", 3.0)

    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00020", 1.0)
    _make_order(db, "OR-0001", [("SP-0001", 4)])

    result = get_picking_simulation(db, "OR-0001")
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.part_id == "PJ-X-00022"
    assert row.is_composite_child is True
    # 1 A = 2 B = 6 C per jewelry unit. qty_per_unit=6, units=4, subtotal=24.
    v = row.variants[0]
    assert v.qty_per_unit == 6.0
    assert v.units_count == 4
    assert v.subtotal == 24.0


def test_picking_simulation_atom_appears_both_direct_and_via_composite(db):
    """An atom used both directly in a jewelry BOM and indirectly via a
    composite → single row; is_composite_child=True (because at least one
    occurrence came from composite expansion)."""
    from services.picking import get_picking_simulation

    # Composite "支架" expands to atom "螺丝" × 2.
    _make_part(db, "PJ-X-00030", "支架", is_composite=True)
    _make_part(db, "PJ-X-00031", "螺丝")
    _make_part_bom(db, "PJ-X-00030", "PJ-X-00031", 2.0)

    # Jewelry uses BOTH the composite (1 per unit) AND the atom directly (1 per unit).
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00030", 1.0)  # via composite → 螺丝 × 2
    _make_bom(db, "SP-0001", "PJ-X-00031", 1.0)  # direct → 螺丝 × 1
    _make_order(db, "OR-0001", [("SP-0001", 10)])

    result = get_picking_simulation(db, "OR-0001")
    row = next(r for r in result.rows if r.part_id == "PJ-X-00031")
    assert row.is_composite_child is True  # set because of the composite path
    # Two variants expected: qty_per_unit 1.0 (direct) and qty_per_unit 2.0 (via composite).
    qtys = sorted(v.qty_per_unit for v in row.variants)
    assert qtys == [1.0, 2.0]


def test_picking_simulation_composite_cycle_guarded(db):
    """A cyclic part BOM (A → B → A) does not cause infinite recursion.
    _expand_to_atoms's path-based _ancestors guard must terminate when it
    revisits any node on the current path. The cycle short-circuits,
    producing no output for the cyclic sub-tree."""
    from services.picking import get_picking_simulation

    # Cycle: A expands to B; B expands back to A. Neither has atomic leaves.
    _make_part(db, "PJ-X-00040", "环 A", is_composite=True)
    _make_part(db, "PJ-X-00041", "环 B", is_composite=True)
    _make_part_bom(db, "PJ-X-00040", "PJ-X-00041", 1.0)
    _make_part_bom(db, "PJ-X-00041", "PJ-X-00040", 1.0)

    # Jewelry uses the composite A and an unrelated atom.
    _make_part(db, "PJ-X-00042", "独立原子")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00040", 1.0)
    _make_bom(db, "SP-0001", "PJ-X-00042", 2.0)
    _make_order(db, "OR-0001", [("SP-0001", 3)])

    # Must terminate (not hang). Cycle contributes no atoms, so the
    # unrelated atom is the only row in the output.
    result = get_picking_simulation(db, "OR-0001")
    assert [r.part_id for r in result.rows] == ["PJ-X-00042"]


def test_picking_simulation_empty_composite_contributes_nothing(db):
    """A composite part with no part_bom children is a no-op — the
    jewelry BOM row referencing it expands to zero atoms, and the
    composite itself is never emitted (since composites are always hidden).
    Pins behavior so a future change doesn't silently leak the composite."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00050", "空组合", is_composite=True)
    # No PartBom rows for PJ-X-00050.
    _make_part(db, "PJ-X-00051", "正常原子")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00050", 1.0)
    _make_bom(db, "SP-0001", "PJ-X-00051", 1.0)
    _make_order(db, "OR-0001", [("SP-0001", 5)])

    result = get_picking_simulation(db, "OR-0001")
    part_ids = [r.part_id for r in result.rows]
    assert "PJ-X-00050" not in part_ids  # composite itself is hidden
    assert part_ids == ["PJ-X-00051"]    # only the real atom remains


def test_picking_simulation_diamond_dag_counts_both_paths(db):
    """Diamond DAG: composite A has two composite children B and C, both of
    which expand to the same atom D. The path-based _ancestors guard only
    skips the CURRENT path, so D must be reached via both B and C and the
    quantities accumulate. This is the specific invariant that justifies
    path-based (not global-visited) cycle detection."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00060", "顶 A", is_composite=True)
    _make_part(db, "PJ-X-00061", "中 B", is_composite=True)
    _make_part(db, "PJ-X-00062", "中 C", is_composite=True)
    _make_part(db, "PJ-X-00063", "底 D")  # atomic

    # A → B (× 2) and A → C (× 3); both B and C → D but with different qtys.
    _make_part_bom(db, "PJ-X-00060", "PJ-X-00061", 2.0)
    _make_part_bom(db, "PJ-X-00060", "PJ-X-00062", 3.0)
    _make_part_bom(db, "PJ-X-00061", "PJ-X-00063", 5.0)   # via B: 2×5 = 10 per A
    _make_part_bom(db, "PJ-X-00062", "PJ-X-00063", 7.0)   # via C: 3×7 = 21 per A

    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00060", 1.0)
    _make_order(db, "OR-0001", [("SP-0001", 1)])  # 1 unit for easy math

    result = get_picking_simulation(db, "OR-0001")
    # D should appear via both paths, producing two distinct variants
    # (qty_per_unit 10 and qty_per_unit 21) — NOT merged into one row.
    rows = [r for r in result.rows if r.part_id == "PJ-X-00063"]
    assert len(rows) == 1
    variants = sorted(v.qty_per_unit for v in rows[0].variants)
    assert variants == [10.0, 21.0]
    assert rows[0].total_required == 31.0  # 10×1 + 21×1


# --- Aggregation: stock and picked state ---


def _add_stock(db, part_id: str, qty: float, reason: str = "入库"):
    from models.inventory_log import InventoryLog
    from decimal import Decimal
    db.add(InventoryLog(
        item_type="part", item_id=part_id,
        change_qty=Decimal(str(qty)), reason=reason,
    ))
    db.flush()


def test_picking_simulation_current_stock(db):
    """current_stock is computed from inventory_log SUM for each part."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00001", 1.0)
    _make_order(db, "OR-0001", [("SP-0001", 3)])

    _add_stock(db, "PJ-X-00001", 20.0)
    _add_stock(db, "PJ-X-00001", -5.0, reason="出库")

    result = get_picking_simulation(db, "OR-0001")
    assert result.rows[0].current_stock == 15.0


def test_picking_simulation_no_stock_is_zero(db):
    """Part with no inventory_log entries → current_stock = 0."""
    from services.picking import get_picking_simulation

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00001", 1.0)
    _make_order(db, "OR-0001", [("SP-0001", 1)])

    result = get_picking_simulation(db, "OR-0001")
    assert result.rows[0].current_stock == 0.0


def test_picking_simulation_picked_state_reflected(db):
    """An OrderPickingRecord sets the matching variant's picked=True and
    bumps progress.picked."""
    from services.picking import get_picking_simulation
    from models.order import OrderPickingRecord
    from decimal import Decimal

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "A")
    _make_jewelry(db, "SP-0002", "B")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_bom(db, "SP-0002", "PJ-X-00001", 3.0)
    _make_order(db, "OR-0001", [("SP-0001", 10), ("SP-0002", 5)])

    # Mark only the qty=2 variant.
    db.add(OrderPickingRecord(
        order_id="OR-0001", part_id="PJ-X-00001",
        qty_per_unit=Decimal("2.0"),
    ))
    db.flush()

    result = get_picking_simulation(db, "OR-0001")
    row = result.rows[0]
    picked = {v.qty_per_unit: v.picked for v in row.variants}
    assert picked[2.0] is True
    assert picked[3.0] is False
    assert result.progress.total == 2
    assert result.progress.picked == 1


# --- State mutations: mark / unmark / reset ---


def _setup_single_variant_order(db):
    """Common setup: order with one part/one variant."""
    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_order(db, "OR-0001", [("SP-0001", 3)])


def test_mark_picked_creates_record(db):
    from services.picking import mark_picked, get_picking_simulation
    _setup_single_variant_order(db)

    result = mark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    assert result.picked is True
    assert result.picked_at is not None

    sim = get_picking_simulation(db, "OR-0001")
    assert sim.rows[0].variants[0].picked is True


def test_mark_picked_idempotent(db):
    """Calling mark_picked twice is a no-op on the second call."""
    from services.picking import mark_picked
    from models.order import OrderPickingRecord
    _setup_single_variant_order(db)

    mark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    mark_picked(db, "OR-0001", "PJ-X-00001", 2.0)  # second call must not raise

    count = db.query(OrderPickingRecord).filter_by(order_id="OR-0001").count()
    assert count == 1


def test_mark_picked_rejects_unknown_variant(db):
    """Variant not in the order's aggregation → ValueError."""
    from services.picking import mark_picked
    import pytest
    _setup_single_variant_order(db)

    with pytest.raises(ValueError, match="配货范围"):
        mark_picked(db, "OR-0001", "PJ-X-00001", 999.0)  # wrong qty_per_unit
    with pytest.raises(ValueError, match="配货范围"):
        mark_picked(db, "OR-0001", "PJ-NOPE", 2.0)        # wrong part_id


def test_mark_picked_order_not_found(db):
    from services.picking import mark_picked
    import pytest
    with pytest.raises(ValueError, match="OR-NOPE"):
        mark_picked(db, "OR-NOPE", "PJ-X-00001", 2.0)


def test_unmark_picked_removes_record(db):
    from services.picking import mark_picked, unmark_picked
    from models.order import OrderPickingRecord
    _setup_single_variant_order(db)

    mark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    result = unmark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    assert result.picked is False

    count = db.query(OrderPickingRecord).filter_by(order_id="OR-0001").count()
    assert count == 0


def test_unmark_picked_idempotent(db):
    """Unmark when no record exists is silent."""
    from services.picking import unmark_picked
    _setup_single_variant_order(db)

    result = unmark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    assert result.picked is False  # not raised


def test_reset_picking_clears_all(db):
    from services.picking import mark_picked, reset_picking, get_picking_simulation
    _make_part(db, "PJ-X-00001", "A")
    _make_part(db, "PJ-X-00002", "B")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00001", 1.0)
    _make_bom(db, "SP-0001", "PJ-X-00002", 1.0)
    _make_order(db, "OR-0001", [("SP-0001", 5)])

    mark_picked(db, "OR-0001", "PJ-X-00001", 1.0)
    mark_picked(db, "OR-0001", "PJ-X-00002", 1.0)

    deleted = reset_picking(db, "OR-0001")
    assert deleted == 2

    sim = get_picking_simulation(db, "OR-0001")
    assert all(not v.picked for r in sim.rows for v in r.variants)


def test_reset_picking_unknown_order(db):
    from services.picking import reset_picking
    import pytest
    with pytest.raises(ValueError, match="OR-NOPE"):
        reset_picking(db, "OR-NOPE")


def test_reset_picking_no_records_returns_zero(db):
    from services.picking import reset_picking
    _setup_single_variant_order(db)
    assert reset_picking(db, "OR-0001") == 0


def test_unmark_picked_after_order_edit_clears_orphan(db):
    """After marking a variant picked, if the order is edited so the variant
    is no longer in the aggregation, unmark_picked still removes the orphan row.
    This is intentional — deleting a 'should not exist' row is strictly corrective."""
    from services.picking import mark_picked, unmark_picked, get_picking_simulation
    from models.order import OrderPickingRecord, OrderItem

    _make_part(db, "PJ-X-00001", "珠子")
    _make_jewelry(db, "SP-0001", "J")
    _make_bom(db, "SP-0001", "PJ-X-00001", 2.0)
    _make_order(db, "OR-0001", [("SP-0001", 3)])

    # Mark, then delete the order's only OrderItem so the variant orphans.
    mark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    db.query(OrderItem).filter_by(order_id="OR-0001").delete()
    db.flush()

    # Variant now absent from the aggregation.
    sim = get_picking_simulation(db, "OR-0001")
    assert sim.rows == []

    # Orphan row still in DB.
    assert db.query(OrderPickingRecord).filter_by(order_id="OR-0001").count() == 1

    # Permissive unmark clears it.
    result = unmark_picked(db, "OR-0001", "PJ-X-00001", 2.0)
    assert result.picked is False
    assert db.query(OrderPickingRecord).filter_by(order_id="OR-0001").count() == 0


def test_unmark_picked_order_not_found(db):
    from services.picking import unmark_picked
    import pytest
    with pytest.raises(ValueError, match="OR-NOPE"):
        unmark_picked(db, "OR-NOPE", "PJ-X-00001", 2.0)
