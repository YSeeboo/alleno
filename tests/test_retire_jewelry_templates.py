import pytest
from sqlalchemy import text

from models.bom import Bom
from models.jewelry import Jewelry
from models.part import Part
from scripts.retire_jewelry_templates import apply_plan, build_plan, plan_digest, snapshot


@pytest.fixture
def legacy(db):
    # Transactional DDL disappears when this test session closes. These are
    # deliberately not ORM models registered in the new application.
    db.execute(text("CREATE TABLE jewelry_template (id integer PRIMARY KEY, name text NOT NULL)"))
    db.execute(text("CREATE TABLE jewelry_template_item (id integer PRIMARY KEY, "
                    "template_id integer REFERENCES jewelry_template(id), part_id text REFERENCES part(id), qty numeric)"))
    db.add(Part(id="keep-part", name="保留配件", unit="颗", unit_cost="1.125"))
    db.add(Jewelry(id="keep-jewelry", name="已有饰品", category="单对", unit="对", retail_price="29.99"))
    db.flush()
    db.add(Bom(id="keep-bom", jewelry_id="keep-jewelry", part_id="keep-part", qty_per_unit="2.125"))
    db.flush()
    db.execute(text("INSERT INTO jewelry_template VALUES (1, '可删除旧模板')"))
    db.execute(text("INSERT INTO jewelry_template_item VALUES (1, 1, 'keep-part', 8)"))
    return db


def test_preview_is_read_only_and_apply_preserves_business_rows(legacy):
    before = snapshot(legacy)
    plan = build_plan(legacy)
    assert snapshot(legacy) == before
    result = apply_plan(legacy, plan)
    assert result["deleted"] == {"jewelry_template": 1, "jewelry_template_item": 1}
    after = snapshot(legacy)
    for name in before.keys() - {"jewelry_template", "jewelry_template_item"}:
        assert after[name] == before[name]
    assert after["jewelry_template"]["count"] == after["jewelry_template_item"]["count"] == 0
    assert after["jewelry_structure"]["count"] == 0


def test_stale_or_tampered_plan_rejected(legacy):
    plan = build_plan(legacy)
    plan["tables"]["jewelry_template"]["count"] = 0
    with pytest.raises(ValueError, match="无效"):
        apply_plan(legacy, plan)
    plan = build_plan(legacy)
    legacy.execute(text("UPDATE part SET name = '预览后有业务修改' WHERE id = 'keep-part'"))
    with pytest.raises(ValueError, match="发生变化"):
        apply_plan(legacy, plan)
    assert legacy.execute(text("SELECT count(*) FROM jewelry_template")).scalar() == 1


def test_unexpected_cascade_fk_blocks_cleanup(legacy):
    legacy.execute(text("CREATE TABLE unexpected_template_ref (id integer, "
                        "template_id integer REFERENCES jewelry_template(id) ON DELETE CASCADE)"))
    with pytest.raises(ValueError, match="意外模板外键"):
        build_plan(legacy)


def test_dependency_added_after_preview_blocks_apply(legacy):
    plan = build_plan(legacy)
    legacy.execute(text("CREATE TABLE unexpected_template_ref (id integer, "
                        "template_id integer REFERENCES jewelry_template(id) ON DELETE CASCADE)"))
    with pytest.raises(ValueError, match="意外模板外键"):
        apply_plan(legacy, plan)


def test_wrong_database_plan_rejected(legacy):
    plan = build_plan(legacy)
    plan["database"] = "wrong-database"
    plan["digest"] = plan_digest(plan)
    with pytest.raises(ValueError, match="发生变化"):
        apply_plan(legacy, plan)


def test_explicit_migration_creates_empty_new_tables(legacy):
    for table in ("jewelry_structure_scheme", "jewelry_structure_batch", "jewelry_structure"):
        legacy.execute(text(f'DROP TABLE "{table}"'))
    plan = build_plan(legacy)
    apply_plan(legacy, plan)
    after = snapshot(legacy)
    for table in ("jewelry_structure_scheme", "jewelry_structure_batch", "jewelry_structure"):
        assert after[table]["count"] == 0


def test_custom_template_trigger_blocks_cleanup(legacy):
    legacy.execute(text("CREATE FUNCTION template_noop() RETURNS trigger LANGUAGE plpgsql "
                        "AS $$ BEGIN RETURN OLD; END $$"))
    legacy.execute(text("CREATE TRIGGER custom_delete BEFORE DELETE ON jewelry_template "
                        "FOR EACH ROW EXECUTE FUNCTION template_noop()"))
    with pytest.raises(ValueError, match="自定义触发器"):
        build_plan(legacy)
