#!/usr/bin/env python3
"""Explicit release migration: backup → read-only preview → confirmed apply.

Deletes ONLY saved legacy template recipes, never parts or actual jewelry BOMs.
Run with all application writers stopped. Never imported by app startup.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text
from scripts.archive_production_orders import backup, database_identity, validate_backup, write_json

LEGACY = {"jewelry_template", "jewelry_template_item"}


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def plan_digest(plan):
    return sha256(json.dumps({k: v for k, v in plan.items() if k != "digest"},
                             ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def assert_safe_dependencies(db):
    # Check ALL schemas, not just public; an unexpected dependent table could
    # otherwise be modified by ON DELETE CASCADE without explicit permission.
    refs = db.execute(text("""
        SELECT ns.nspname, child.relname, con.conname
        FROM pg_constraint con
        JOIN pg_class parent ON parent.oid = con.confrelid
        JOIN pg_namespace pns ON pns.oid = parent.relnamespace
        JOIN pg_class child ON child.oid = con.conrelid
        JOIN pg_namespace ns ON ns.oid = child.relnamespace
        WHERE con.contype = 'f' AND pns.nspname = 'public'
          AND parent.relname IN ('jewelry_template', 'jewelry_template_item')
          AND NOT (ns.nspname = 'public' AND child.relname = 'jewelry_template_item'
                   AND parent.relname = 'jewelry_template')
    """)).all()
    if refs:
        raise ValueError(f"存在意外模板外键引用，拒绝清理：{refs}")
    custom = db.execute(text("""
        SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname IN ('jewelry_template', 'jewelry_template_item')
          AND NOT t.tgisinternal
        UNION
        SELECT c.relname FROM pg_rewrite r JOIN pg_class c ON c.oid = r.ev_class
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname IN ('jewelry_template', 'jewelry_template_item')
    """)).all()
    if custom:
        raise ValueError(f"模板表存在自定义触发器或规则，需人工审查：{custom}")


def snapshot(db):
    inspector = inspect(db.connection())
    result = {}
    for table in sorted(inspector.get_table_names(schema="public")):
        digest = sha256()
        count = 0
        # PostgreSQL serializes numeric/date/JSON values consistently. Order by
        # full row text also covers tables without an id or primary key.
        for row in db.execute(text(f'SELECT row_to_json(t)::text FROM public.{quote(table)} t '
                                   'ORDER BY row_to_json(t)::text COLLATE "C"')):
            digest.update(row[0].encode())
            digest.update(b"\n")
            count += 1
        result[table] = {"count": count, "sha256": digest.hexdigest()}
    return result


def build_plan(db):
    assert_safe_dependencies(db)
    _, identity = database_identity()
    plan = {"kind": "retire-jewelry-templates-v1", "database": identity, "tables": snapshot(db)}
    plan["digest"] = plan_digest(plan)
    return plan


def apply_plan(db, plan):
    if plan.get("kind") != "retire-jewelry-templates-v1" or plan.get("digest") != plan_digest(plan):
        raise ValueError("清理预览文件无效")
    db.execute(text("SET LOCAL lock_timeout = '10s'"))
    names = inspect(db.connection()).get_table_names(schema="public")
    if names:
        db.execute(text("LOCK TABLE " + ", ".join('public.' + quote(n) for n in sorted(names))
                        + " IN SHARE ROW EXCLUSIVE MODE"))
    if build_plan(db) != plan:
        raise ValueError("数据库数据或引用在预览后发生变化，请重新备份及预览")
    before = plan["tables"]
    # No TRUNCATE, CASCADE, part deletion, sequence reset, or schema drop.
    for table in ("jewelry_template_item", "jewelry_template"):
        if table in before:
            db.execute(text(f"DELETE FROM public.{quote(table)}"))
    after = snapshot(db)
    if any(after[name] != state for name, state in before.items() if name not in LEGACY):
        raise ValueError("非模板业务数据发生变化，拒绝提交")
    if any(after[name]["count"] for name in LEGACY & after.keys()):
        raise ValueError("旧模板未全部清理，拒绝提交")
    from models.jewelry_structure import JewelryStructure, JewelryStructureScheme, JewelryStructureBatch
    for model in (JewelryStructure, JewelryStructureScheme, JewelryStructureBatch):
        model.__table__.create(db.connection(), checkfirst=True)
    return {"deleted": {name: before[name]["count"] for name in LEGACY & before.keys()},
            "protected_tables_verified": len(before.keys() - LEGACY), "after": snapshot(db)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    b = commands.add_parser("backup")
    b.add_argument("--output", required=True, type=Path)
    p = commands.add_parser("preview")
    p.add_argument("--output", required=True, type=Path)
    a = commands.add_parser("apply")
    a.add_argument("--plan", required=True, type=Path)
    a.add_argument("--backup-file", required=True, type=Path)
    a.add_argument("--confirm", required=True, help="完整预览 digest")
    a.add_argument("--operator", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == "backup":
        backup(args.output)
        return
    from database import SessionLocal
    if args.command == "preview":
        with SessionLocal() as db:
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            plan = build_plan(db)
            write_json(args.output, plan)
        print(json.dumps({"legacy_rows": {n: s["count"] for n, s in plan["tables"].items() if n in LEGACY},
                          "digest": plan["digest"]}, ensure_ascii=False))
        return
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if args.confirm != plan.get("digest"):
        raise ValueError("确认摘要不匹配")
    validate_backup(args.backup_file)
    # Reserve audit path before writing; a failed run leaves a file for review.
    with Path(str(args.plan) + ".applied.json").open("x", encoding="utf-8") as audit:
        with SessionLocal() as db:
            result = apply_plan(db, plan)
            json.dump({"operator": args.operator, "plan_digest": plan["digest"],
                       "backup": str(args.backup_file.resolve()), **result}, audit,
                      ensure_ascii=False, indent=2)
            audit.flush()
            os.fsync(audit.fileno())
            db.commit()
    print("旧模板清理完成；其他业务表内容及记录数验证未变。请保留备份与审计文件。")


if __name__ == "__main__":
    main()
