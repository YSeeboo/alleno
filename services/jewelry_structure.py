"""Resolve once on the server; persist concrete BOMs, never live inheritance.

All mutations flush only. The request's get_db dependency owns commit/rollback.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json

import jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from models.jewelry_structure import JewelryStructure, JewelryStructureBatch, JewelryStructureScheme
from models.part import Part
from schemas.jewelry_structure import BatchInput, StructureWrite
from services.bom import set_bom
from services.jewelry import create_jewelry
from time_utils import now_beijing


class StructureConflict(ValueError):
    pass


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def get_structure(db, structure_id, lock=False):
    q = db.query(JewelryStructure).filter_by(id=structure_id).populate_existing()
    if lock:
        q = q.with_for_update()
    obj = q.first()
    if obj is None:
        raise LookupError("结构不存在或已删除")
    return obj


def check_revision(obj, revision):
    if obj.revision != revision:
        raise StructureConflict("结构或方案已被修改，请重新加载并预览，避免覆盖其他人的设置")


def _check_parts(db, ids, lock=False):
    ids = {i for i in ids if i}
    q = db.query(Part).filter(Part.id.in_(ids))
    if lock:
        q = q.with_for_update(read=True)
    found = {p.id: p for p in q.populate_existing().all()}
    missing = ids - found.keys()
    if missing:
        raise ValueError("配件不存在：" + "、".join(sorted(missing)))
    return found


def serialize(obj):
    keys = {s["key"] for s in obj.slots}
    return {
        "id": obj.id, "name": obj.name, "note": obj.note, "category": obj.category,
        "unit": obj.unit, "revision": obj.revision, "slots": obj.slots,
        "created_at": obj.created_at.isoformat(),
        "schemes": [{"id": s.id, "name": s.name, "revision": s.revision,
                     "overrides": s.overrides, "invalid_keys": sorted(set(s.overrides) - keys)}
                    for s in obj.schemes],
    }


def save_structure(db, body, structure_id=None):
    obj = get_structure(db, structure_id, lock=True) if structure_id else None
    if obj:
        check_revision(obj, body.revision)
    data = StructureWrite.model_validate(body.model_dump(exclude={"revision"})).model_dump(mode="json")
    _check_parts(db, [s["part_id"] for s in data["slots"]])
    if obj:
        for key, value in data.items():
            setattr(obj, key, value)
        obj.revision += 1
    else:
        obj = JewelryStructure(**data)
        db.add(obj)
    db.flush()
    return serialize(obj)


def delete_structure(db, structure_id, revision):
    obj = get_structure(db, structure_id, lock=True)
    check_revision(obj, revision)
    db.delete(obj)
    db.flush()


def save_scheme(db, structure_id, body, scheme_id=None):
    obj = get_structure(db, structure_id, lock=True)
    check_revision(obj, body.structure_revision)
    slots = {s["key"]: s for s in obj.slots}
    overrides = {k: v.model_dump(mode="json", exclude_unset=True) for k, v in body.overrides.items()}
    if set(overrides) - slots.keys():
        raise ValueError("方案引用了已删除或不属于本结构的位置，请显式移除失效设置")
    for key, value in overrides.items():
        if slots[key]["selectable"] and "part_id" in value:
            raise ValueError("逐件选配位置的配件请在创建饰品时选择，不绑定到搭配方案")
    _check_parts(db, [v.get("part_id") for v in overrides.values()])
    if scheme_id:
        s = next((s for s in obj.schemes if s.id == scheme_id), None)
        if s is None:
            raise LookupError("搭配方案不属于本结构或已删除")
        s.name, s.overrides, s.revision = body.name, overrides, s.revision + 1
    else:
        obj.schemes.append(JewelryStructureScheme(name=body.name, overrides=overrides))
    obj.revision += 1
    db.flush()
    return serialize(obj)


def delete_scheme(db, structure_id, scheme_id, revision):
    obj = get_structure(db, structure_id, lock=True)
    check_revision(obj, revision)
    s = next((s for s in obj.schemes if s.id == scheme_id), None)
    if s is None:
        raise LookupError("搭配方案不存在")
    obj.schemes.remove(s)
    obj.revision += 1
    db.flush()
    return serialize(obj)


def resolve_batch(db: Session, body: BatchInput, lock=False):
    obj = get_structure(db, body.structure_id, lock=lock)
    check_revision(obj, body.structure_revision)
    config = body.draft.model_dump(mode="json") if body.draft else {
        "name": obj.name, "note": obj.note, "category": obj.category, "unit": obj.unit, "slots": obj.slots,
    }
    slots = config["slots"]
    keys = {s["key"] for s in slots}
    schemes = {s.id: s for s in obj.schemes}
    # Validate even an unused default; a foreign ID must never be silently ignored.
    if body.default_scheme_id is not None and body.default_scheme_id not in schemes:
        raise ValueError("默认搭配方案不属于当前结构或已删除")
    results = []
    for row in body.rows:
        scheme_id = row.scheme_id if row.scheme_id is not None else body.default_scheme_id
        selected = schemes.get(scheme_id)
        if scheme_id is not None and selected is None:
            raise ValueError(f"{row.name}：搭配方案不属于当前结构或已删除")
        changes = selected.overrides if selected else {}
        if set(changes) - keys:
            raise ValueError(f"{row.name}：方案引用已删除的位置，请修复方案或换用其他方案")
        touched = set(row.selections) | set(row.overrides) | set(row.removed_keys)
        if touched - keys:
            raise ValueError(f"{row.name}：单件调整引用了不存在的位置，请重新检查")
        if any(not s["selectable"] and s["key"] in row.selections for s in slots):
            raise ValueError(f"{row.name}：只能对逐件选配位置填写选配值")
        extra_keys = [s.key for s in row.extras]
        if len(set(extra_keys)) != len(extra_keys) or set(extra_keys) & keys:
            raise ValueError(f"{row.name}：新增位置标识不能重复或覆盖原位置")
        resolved = []
        for slot in slots:
            key = slot["key"]
            if key in row.removed_keys:
                continue
            item = {**slot, **changes.get(key, {})}
            source = "搭配方案" if key in changes else "结构默认"
            if key in row.selections:
                item["part_id"] = row.selections[key]
                source = "逐件选择"
            if key in row.overrides:
                item.update(row.overrides[key].model_dump(mode="json", exclude_unset=True))
                source = "单件调整"
            resolved.append({**item, "source": source})
        resolved += [{**s.model_dump(mode="json"), "source": "单件新增"} for s in row.extras]
        if not resolved:
            raise ValueError(f"{row.name}：至少保留一个配件")
        if any(not i["part_id"] for i in resolved):
            raise ValueError(f"{row.name}：仍有配件待选择")
        results.append({"key": row.key, "name": row.name, "scheme_name": selected.name if selected else "结构默认",
                        "scheme_revision": selected.revision if selected else None, "positions": resolved})
    # Lock referenced parts during confirmation, preventing deletion / unit edits
    # between token validation and the concrete BOM write.
    parts = _check_parts(db, [i["part_id"] for r in results for i in r["positions"]], lock=lock)
    for row in results:
        combined = {}
        for item in row["positions"]:
            p = parts[item["part_id"]]
            if not p.unit or not p.unit.strip():
                raise ValueError(f"{row['name']}：配件 {p.name} 未设置库存单位，请先补全")
            item.update(part_name=p.name, unit=p.unit)
            item["qty"] = str(Decimal(item["qty"]).quantize(Decimal("0.0001")))
            if p.id not in combined:
                combined[p.id] = {"part_id": p.id, "part_name": p.name, "unit": p.unit,
                                  "qty": Decimal(0), "positions": []}
            combined[p.id]["qty"] += Decimal(item["qty"])
            combined[p.id]["positions"].append(item["name"])
        for item in combined.values():
            if item["qty"] >= Decimal("1000000"):
                raise ValueError(f"{row['name']}：合并后用量超出 BOM 数量范围")
            item["qty"] = str(item["qty"])
        row["bom"] = list(combined.values())
    return {"structure_id": obj.id, "structure_name": config["name"], "structure_revision": obj.revision,
            "from_draft": body.draft is not None, "category": config["category"], "unit": config["unit"], "rows": results}


def preview_batch(db, body, user_id):
    result = resolve_batch(db, body)
    token = jwt.encode({"kind": "jewelry-structure-preview", "user_id": user_id,
                        "digest": digest({"batch": body.model_dump(mode="json"), "result": result}),
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=20)},
                       settings.JWT_SECRET_KEY, algorithm="HS256")
    return {**result, "preview_token": token}


def confirm_batch(db, body, user_id):
    # Serialize retries for the same key. PostgreSQL transaction locks are
    # released on commit / rollback, including a lost-response retry.
    lock_key = int.from_bytes(sha256(f"structure:{user_id}:{body.request_key}".encode()).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    payload = digest(body.batch.model_dump(mode="json"))
    existing = db.query(JewelryStructureBatch).filter_by(user_id=user_id, request_key=body.request_key).first()
    if existing:
        if existing.payload_digest != payload:
            raise StructureConflict("同一个请求标识不能用于不同批次，请重新预览")
        return existing.result
    result = resolve_batch(db, body.batch, lock=True)
    try:
        token = jwt.decode(body.preview_token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        if (token.get("kind") != "jewelry-structure-preview" or token.get("user_id") != user_id
                or token.get("digest") != digest({"batch": body.batch.model_dump(mode="json"), "result": result})):
            raise ValueError("预览与当前配置不一致")
    except (jwt.PyJWTError, ValueError) as e:
        raise StructureConflict("预览已过期或配置发生变化，请重新预览后确认") from e
    # The savepoint also makes service-level failures atomic when called by
    # scripts or tests rather than the normal request transaction wrapper.
    with db.begin_nested():
        for source, row in zip(body.batch.rows, result["rows"]):
            jewelry = create_jewelry(db, {
                **source.model_dump(include={"name", "color", "image", "retail_price", "wholesale_price", "handcraft_cost"}),
                "category": result["category"], "unit": result["unit"], "status": "active",
            })
            for item in row["bom"]:
                set_bom(db, jewelry.id, item["part_id"], Decimal(item["qty"]))
            row["jewelry_id"] = jewelry.id
        result["created_at"] = now_beijing().isoformat()
        db.add(JewelryStructureBatch(user_id=user_id, request_key=body.request_key, payload_digest=payload, result=result))
        db.flush()
    return result
