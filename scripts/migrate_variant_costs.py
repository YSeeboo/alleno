"""
One-time migration: backfill purchase_cost and bead_cost on variant parts
from their parent parts.

Rules:
- Only processes parts with parent_part_id IS NOT NULL
- Only fills purchase_cost if variant's is NULL and parent's is NOT NULL
- Only fills bead_cost if variant's is NULL and parent's is NOT NULL
- Does NOT touch plating_cost
- Recalculates unit_cost after filling
- Idempotent: re-running does not change already-filled data

Usage:
    python scripts/migrate_variant_costs.py --dry-run   # preview changes
    python scripts/migrate_variant_costs.py              # apply changes
"""

import sys
import os
from decimal import Decimal

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from database import engine, SessionLocal
from models.part import Part


def _recalc_unit_cost(part: Part) -> None:
    purchase = Decimal(str(part.purchase_cost or 0))
    bead = Decimal(str(part.bead_cost or 0))
    plating = Decimal(str(part.plating_cost or 0))
    total = purchase + bead + plating
    part.unit_cost = total if total else None


def migrate(db: Session, dry_run: bool = True) -> dict:
    variants = db.query(Part).filter(Part.parent_part_id.isnot(None)).all()

    stats = {"total_variants": len(variants), "updated": 0, "skipped": 0, "details": []}

    for variant in variants:
        parent = db.get(Part, variant.parent_part_id)
        if parent is None:
            stats["skipped"] += 1
            continue

        changed = False
        detail = {"id": variant.id, "name": variant.name, "changes": []}

        if variant.purchase_cost is None and parent.purchase_cost is not None:
            detail["changes"].append(
                f"purchase_cost: NULL -> {parent.purchase_cost}"
            )
            if not dry_run:
                variant.purchase_cost = parent.purchase_cost
            changed = True

        if variant.bead_cost is None and parent.bead_cost is not None:
            detail["changes"].append(
                f"bead_cost: NULL -> {parent.bead_cost}"
            )
            if not dry_run:
                variant.bead_cost = parent.bead_cost
            changed = True

        if changed:
            if not dry_run:
                _recalc_unit_cost(variant)
            stats["updated"] += 1
            stats["details"].append(detail)
        else:
            stats["skipped"] += 1

    if not dry_run:
        db.commit()

    return stats


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"{'[DRY RUN] ' if dry_run else ''}Migrating variant costs...")
    print()

    db = SessionLocal()
    try:
        stats = migrate(db, dry_run=dry_run)
    finally:
        db.close()

    print(f"Total variants: {stats['total_variants']}")
    print(f"Would update:   {stats['updated']}" if dry_run else f"Updated:        {stats['updated']}")
    print(f"Skipped:        {stats['skipped']}")
    print()

    if stats["details"]:
        for d in stats["details"]:
            print(f"  {d['id']} ({d['name']})")
            for c in d["changes"]:
                print(f"    - {c}")
        print()

    if dry_run and stats["updated"] > 0:
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
