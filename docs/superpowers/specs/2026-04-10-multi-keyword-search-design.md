# Multi-Keyword Search — Design

**Date:** 2026-04-10
**Status:** Draft
**Area:** `services/` search filters

## Problem

All list/search endpoints currently use a single `ILIKE '%keyword%'` substring
match against one or two columns. This means a query like `"背镂空 桃心"`
cannot find a part named `"背镂空满钻桃心"`, because the literal substring
`"背镂空 桃心"` (with a space) does not appear in the record — even though
both tokens do.

Users naturally express refinement by adding keywords separated by spaces,
and expect **AND** semantics across tokens. The current behavior is
counter-intuitive and limits how they can narrow results.

## Goal

Support whitespace-delimited multi-keyword search across all existing list
endpoints, with AND semantics between tokens and OR semantics across the
searchable columns of each endpoint. Single-keyword behavior must remain
functionally equivalent.

## Non-Goals (YAGNI)

Explicitly excluded from this change:

- Pinyin search
- Fuzzy / typo-tolerant matching (pg_trgm, similarity)
- Relevance ranking (results continue to order by `id DESC`)
- Full-text search extensions (`pg_trgm`, `zhparser`, `tsvector`)
- Frontend debounce or loading-state tweaks
- Configurable AND/OR toggles on the helper
- Token count limits
- Any unrelated refactoring

These are all viable future improvements and can be layered on without
changing the helper's public interface.

## Design

### New helper

Add `keyword_filter` to `services/_helpers.py`:

```python
from typing import Optional
from sqlalchemy import and_, or_

def keyword_filter(keyword: Optional[str], *columns):
    """
    Build a multi-keyword search filter.

    Splits `keyword` on any Unicode whitespace (including U+3000 全角空格).
    Each token must match at least one of `columns` (OR); all tokens must
    match (AND). Uses ILIKE for case-insensitive substring matching.

    Returns a SQLAlchemy clause, or None if keyword is empty / whitespace-only.
    Callers should check for None and skip adding the filter in that case.

    Example:
        clause = keyword_filter("背镂空 桃心", Part.name, Part.id)
        if clause is not None:
            q = q.filter(clause)
    """
    if not keyword:
        return None
    tokens = keyword.split()  # no-arg split handles any Unicode whitespace
    if not tokens:
        return None
    return and_(*[
        or_(*[col.ilike(f"%{tok}%") for col in columns])
        for tok in tokens
    ])
```

### Key design decisions

- **Returns `None` on empty input** rather than a tautology clause. This
  forces callers to be explicit and avoids polluting the query with no-op
  predicates. The call-site pattern is a two-line check.
- **Variadic columns** (`*columns`) supports the existing heterogeneity across
  call sites: some search 1 column (supplier name), some 2 (id + name), some
  4 (joined tables in plating / handcraft).
- **Encapsulates tokenization, matching operator, and wildcard format.**
  Future upgrades (e.g., switching to pg_trgm `%` operator or adding a
  normalization step) change only the helper body — no call-site edits.
- **`str.split()` without arguments** splits on any Unicode whitespace per
  the Python data model, which includes half-width space, full-width space
  (U+3000), tab, and newline. No manual normalization needed.

### Call-site migration

All 9 existing `ILIKE`-based search points are migrated to the helper. The
pattern is identical at every site: delete the `or_(...)` chain, call
`keyword_filter`, guard on `None`.

| # | File:Line | Columns |
|---|---|---|
| 1 | `services/part.py:65` | `Part.name`, `Part.id` |
| 2 | `services/jewelry.py:46` | `Jewelry.name`, `Jewelry.id` |
| 3 | `services/inventory.py:109` | `Part.name`, `Part.id` |
| 4 | `services/inventory.py:130` | `Jewelry.name`, `Jewelry.id` |
| 5 | `services/plating.py:369-372` | `SendPart.id`, `SendPart.name`, `ReceivePart.id`, `ReceivePart.name` |
| 6 | `services/handcraft.py:539` | `Part.id`, `Part.name` |
| 7 | `services/handcraft.py:593-594` | `Jewelry.id`, `Jewelry.name`, `Part.id`, `Part.name` |
| 8 | `services/kanban.py:1254` | `PlatingOrder.supplier_name` |
| 9 | `services/kanban.py:1261` | `HandcraftOrder.supplier_name` |

Example migration (`services/part.py`):

```python
# Before
if name is not None:
    q = q.filter(or_(Part.name.ilike(f"%{name}%"), Part.id.ilike(f"%{name}%")))

# After
clause = keyword_filter(name, Part.name, Part.id)
if clause is not None:
    q = q.filter(clause)
```

### Mixed ID + name queries

For call sites where one column is an ID (ASCII, e.g. `PJ-DZ-00001`) and
another is a Chinese name, per-token `OR(name, id)` looks redundant — a
Chinese token can never match an ID column, and vice versa. This redundancy
is intentional:

1. **Enables mixed queries.** `"PJ-DZ 桃心"` becomes
   `(name~PJ-DZ OR id~PJ-DZ) AND (name~桃心 OR id~桃心)`, which correctly
   filters to records whose ID contains `PJ-DZ` **and** whose name contains
   `桃心`. Splitting behavior by token type (heuristic: "is it ASCII?") would
   add brittle logic and break if ID formats ever include non-ASCII.
2. **Consistent rule.** The single-token case already uses `OR(name, id)`;
   keeping the same rule per-token avoids behavior divergence between
   one-token and multi-token queries.
3. **Negligible cost.** The extra `ILIKE` comparisons are on indexed-or-
   small tables with simple string ops; performance difference is
   unmeasurable at current data volume.

## Tokenization rules

- **Split on any Unicode whitespace** (Python `str.split()` default behavior,
  which includes U+3000 full-width space).
- **Case-insensitive** via `ILIKE` (PostgreSQL built-in). No Python-side
  lower-casing needed.
- **Empty / whitespace-only input** → return `None`, no filter added.
- **Empty tokens from consecutive whitespace** → implicitly filtered by
  `str.split()`'s default behavior.
- **No token count limit.** Internal tool, no public exposure, no DoS
  concern at current scale.

## Behavior change analysis

The change is **non-breaking in practice**. The only possible regression
would be if code or users relied on matching a literal substring that
contained whitespace as one atomic piece. We analyzed this:

- **Records containing whitespace in name/ID**: if a record is
  `"ABC DEF"` and the user searches `"ABC DEF"`, the old behavior matches
  on the full substring. The new behavior splits into `["ABC", "DEF"]` and
  still matches, because both tokens occur in the same row (AND holds).
  **No regression.**
- **Word-order-sensitive queries**: a search for `"DEF ABC"` against
  `"ABC DEF"` used to miss (substring order matters) but will now hit.
  **This is an improvement, not a regression.**
- **Pathological case**: searching for literal multi-space sequences like
  `"  "` used to depend on whether the record's column contained two
  consecutive spaces. No real business workflow depends on this.

## Security

ILIKE patterns are passed via SQLAlchemy parameter binding
(`col.ilike(f"%{tok}%")`), so `tok` is a bound parameter, not concatenated
into SQL. No SQL injection risk.

The `%` and `_` characters in user input are still interpreted as LIKE
wildcards — this is unchanged from current behavior and not addressed
here (non-goal).

## Testing

### New: helper unit tests

`tests/test_helpers_keyword_filter.py` — uses the `db` fixture with a small
fixture dataset to verify actual SQL behavior (not just AST shape). Cases:

- `None` → returns `None`
- `""` → returns `None`
- `"   "` (whitespace-only) → returns `None`
- `"桃心"` (single token) → finds `"背镂空满钻桃心"`
- `"背镂空 桃心"` (multi-token, half-width space) → finds `"背镂空满钻桃心"`
  **(primary regression case)**
- `"背镂空　桃心"` (full-width space U+3000) → same as above
- `"桃心 不存在的词"` → empty result (verifies AND semantics)
- Case-insensitive: `"TAOXIN"` matches record named `"taoxin"` (ASCII case)
- `"PJ-DZ 桃心"` against fixture with a record named `"桃心吊坠"` and
  id `PJ-DZ-00001` → hit (verifies mixed-column query)
- Single-column call `keyword_filter("老王 北京", PlatingOrder.supplier_name)`
  → AND semantics hold when only one column is passed (covers the kanban
  supplier-name case)

### Updated: existing search tests

Run `pytest` after migration. For each of the 9 call sites, check whether
its tests exercise search with a keyword containing spaces. If so, evaluate:

- **If the test is just verifying "search finds the record"** → update the
  keyword to something without spaces, or adapt to the new AND semantics.
- **If the test is specifically verifying literal-substring-including-space
  behavior** → discuss with the user; this is an unlikely but possible
  explicit dependency.

### New: API-level regression test

Add a test in `tests/test_api_parts.py`, e.g. `test_list_parts_multi_keyword_and`:

1. Create a part named `"背镂空满钻桃心"`.
2. `GET /parts?name=背镂空 桃心` (URL-encoded space).
3. Assert the part appears in results.

This pins the end-to-end behavior that originally motivated the change and
protects against future regressions at the API boundary.

## Files touched

### New
- `tests/test_helpers_keyword_filter.py`

### Modified
- `services/_helpers.py` — add `keyword_filter`, add `and_` / `or_` imports, add `Optional` import
- `services/part.py` — line 65
- `services/jewelry.py` — line 46
- `services/inventory.py` — lines 109, 130
- `services/plating.py` — lines 369-372
- `services/handcraft.py` — lines 539, 593-594
- `services/kanban.py` — lines 1254, 1261
- `tests/test_api_parts.py` — add multi-keyword regression test; update existing search tests if affected
- `tests/test_api_jewelries.py`, `tests/test_api_inventory.py`, `tests/test_api_plating.py`, `tests/test_api_handcraft.py`, `tests/test_api_kanban.py` — only if existing search cases are affected by the behavior change
