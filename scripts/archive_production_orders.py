#!/usr/bin/env python3
"""Explicit backup → preview → apply/restore; never run on app startup."""
import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def write_json(path: Path, data):
    # Exclusive creation prevents accidentally replacing a preview / audit file.
    with path.open("x", encoding="utf-8") as f:
        os.chmod(path, 0o600)
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def file_digest(path: Path):
    digest = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def database_identity():
    from sqlalchemy.engine import make_url, URL
    from config import settings
    url = make_url(settings.DATABASE_URL).set(drivername="postgresql")
    # URL.set(password=None) leaves the original password intact in SQLAlchemy.
    public_url = URL.create(
        "postgresql", username=url.username, host=url.host, port=url.port,
        database=url.database, query=url.query,
    )
    identity = public_url.render_as_string(hide_password=False)
    return url, sha256(identity.encode()).hexdigest()


def backup(path: Path):
    from sqlalchemy.engine import URL
    from time_utils import now_beijing
    url, identity = database_identity()
    metadata = Path(str(path) + ".json")
    if metadata.exists():
        raise ValueError("备份元数据文件已存在，请换一个文件名")
    with path.open("xb") as f:
        os.chmod(path, 0o600)
    env = os.environ.copy()
    if url.password is not None:
        env["PGPASSWORD"] = url.password
    connection = URL.create(
        "postgresql", username=url.username, host=url.host, port=url.port,
        database=url.database, query=url.query,
    ).render_as_string(hide_password=False)
    # Password stays in the environment, never argv, shell history or output.
    subprocess.run(
        ["pg_dump", "--format=custom", "--file", str(path), "--dbname", connection],
        env=env, check=True,
    )
    subprocess.run(["pg_restore", "--list", str(path)], check=True, stdout=subprocess.DEVNULL)
    write_json(metadata, {
        "database": identity,
        "created_at": now_beijing().isoformat(),
        "sha256": file_digest(path),
    })
    print(f"完整数据库备份成功：{path}（请同时保留 {metadata.name}）")


def validate_backup(path: Path):
    _, identity = database_identity()
    metadata = json.loads(Path(str(path) + ".json").read_text(encoding="utf-8"))
    if metadata["database"] != identity or metadata["sha256"] != file_digest(path):
        raise ValueError("备份数据库不匹配或备份文件校验失败")
    subprocess.run(["pg_restore", "--list", str(path)], check=True, stdout=subprocess.DEVNULL)


def lock_business_tables(db):
    from sqlalchemy import text
    # Excludes concurrent receipt / stock writes until commit. A timeout avoids
    # hanging a busy shop. Stop writers for the maintenance window as documented.
    db.execute(text("SET LOCAL lock_timeout = '10s'"))
    tables = (
        "plating_order", "handcraft_order", "plating_order_item",
        "handcraft_part_item", "handcraft_jewelry_item", "plating_receipt",
        "handcraft_receipt", "plating_receipt_item", "handcraft_receipt_item",
        "handcraft_picking_record", "handcraft_picking_weight", "vendor_receipt",
        "inventory_log",
    )
    db.execute(text("LOCK TABLE " + ", ".join(tables) + " IN SHARE ROW EXCLUSIVE MODE"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    backup_parser = commands.add_parser("backup", help="完整 pg_dump 备份，不改数据库")
    backup_parser.add_argument("--output", type=Path, required=True)
    preview = commands.add_parser("preview", help="只读预览，不会归档")
    preview.add_argument("--before", type=date.fromisoformat, required=True, help="北京时间、不含当天，如 2026-10-29")
    preview.add_argument("--output", type=Path, required=True)
    for command in ("apply", "restore"):
        p = commands.add_parser(command)
        p.add_argument("--plan", type=Path, required=True)
        p.add_argument("--backup-file", type=Path, required=True)
        p.add_argument("--confirm", required=True, help="预览文件完整 digest")
        if command == "apply":
            p.add_argument("--operator", required=True)
            p.add_argument("--reason", required=True)
    args = parser.parse_args()
    # Resolve user paths before changing directory for .env loading.
    for name in ("output", "plan", "backup_file"):
        if hasattr(args, name):
            setattr(args, name, getattr(args, name).resolve())
    os.chdir(ROOT)
    os.umask(0o077)
    if args.command == "backup":
        backup(args.output)
        return

    from database import SessionLocal
    from services.production_archive import (
        build_archive_plan, apply_archive_plan, restore_archive_plan, validate_plan,
    )
    if args.command == "preview":
        with SessionLocal() as db:
            from sqlalchemy import text
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            plan = build_archive_plan(db, args.before)
            _, identity = database_identity()
            plan["database"] = identity
            from services.production_archive import plan_digest
            plan["digest"] = plan_digest(plan)
            write_json(args.output, plan)
        print(f"只读预览：北京时间 {args.before} 00:00 之前，不含当天；含待发出和进行中。")
        for kind, label in (("plating", "电镀"), ("handcraft", "手工")):
            rows = plan["snapshot"][kind]
            print(f"{label}：{len(rows)} 单，状态统计：{dict(Counter(r['status'] for r in rows))}")
            for row in rows:
                print(f"  {row['id']}  {row['created_at']}  {row['status']}")
        print(f"归档批次：{plan['batch_id']}\n确认摘要：{plan['digest']}\n预览文件：{args.output}")
        print("未修改数据库。预览文件含明细数量和回收/付款快照，请妥善保管，不要公开。")
        return

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    validate_plan(plan)
    _, identity = database_identity()
    if plan.get("database") != identity or args.confirm != plan["digest"]:
        raise ValueError("目标数据库或确认摘要不匹配，拒绝执行")
    validate_backup(args.backup_file)
    # Reserve the audit output before making any database changes.
    audit_path = Path(str(args.plan) + f".{args.command}.json")
    with audit_path.open("x", encoding="utf-8") as audit:
        with SessionLocal() as db:
            lock_business_tables(db)
            if args.command == "apply":
                count = apply_archive_plan(db, plan, operator=args.operator, reason=args.reason)
            else:
                count = restore_archive_plan(db, plan)
            from time_utils import now_beijing
            json.dump({
                "command": args.command, "batch_id": plan["batch_id"],
                "count": count, "at": now_beijing().isoformat(),
                "operator": getattr(args, "operator", None),
                "reason": getattr(args, "reason", None),
                "backup_file": str(args.backup_file),
            }, audit, ensure_ascii=False, indent=2)
            audit.flush()
            os.fsync(audit.fileno())
            db.commit()
    print(f"成功：{args.command} 共 {count} 单。库存、实收数量和付款信息未修改。")
    print(f"操作记录：{audit_path}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"操作未完成：{exc}。请保留输出并检查；不要反复执行写入命令。")
