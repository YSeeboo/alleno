"""In-memory draft and consumed-token tables for the Feishu purchase-order flow.

Drafts are short-lived (~1 hour). Process restart loses them — acceptable for an
interactive flow; the user can resend the message. Two tables:

- _drafts:   token -> (data, created_at, sender_open_id). Parsed-but-unconfirmed.
- _consumed: token -> (po_id, created_at, sender_open_id). Used so a second click
             of "confirm" can return a friendly "this PO is already created" reply.
"""
from __future__ import annotations

import secrets
import time
from threading import RLock
from typing import Any

_TTL_SECONDS = 3600
_lock = RLock()
_drafts: dict[str, tuple[Any, float, str]] = {}
_consumed: dict[str, tuple[str, float, str]] = {}


def _now() -> float:
    return time.monotonic()


def _gc_locked() -> None:
    """Caller must hold _lock."""
    cutoff = _now() - _TTL_SECONDS
    for tok in [t for t, (_, ts, _) in _drafts.items() if ts < cutoff]:
        _drafts.pop(tok, None)
    for tok in [t for t, (_, ts, _) in _consumed.items() if ts < cutoff]:
        _consumed.pop(tok, None)


def put(data: Any, sender_open_id: str) -> str:
    token = secrets.token_urlsafe(16)
    with _lock:
        _gc_locked()
        _drafts[token] = (data, _now(), sender_open_id)
    return token


def put_with_token(token: str, data: Any, sender_open_id: str) -> None:
    with _lock:
        _drafts[token] = (data, _now(), sender_open_id)


def pop_draft(token: str, sender_open_id: str) -> Any | None:
    with _lock:
        _gc_locked()
        entry = _drafts.get(token)
        if entry is None:
            return None
        data, ts, sender = entry
        if sender != sender_open_id:
            return None
        if _now() - ts > _TTL_SECONDS:
            _drafts.pop(token, None)
            return None
        _drafts.pop(token, None)
        return data


def get_draft(token: str, sender_open_id: str) -> Any | None:
    """Peek at a draft without removing it. Returns None on miss / expiry / sender mismatch."""
    with _lock:
        _gc_locked()
        entry = _drafts.get(token)
        if entry is None:
            return None
        data, ts, sender = entry
        if sender != sender_open_id:
            return None
        if _now() - ts > _TTL_SECONDS:
            _drafts.pop(token, None)
            return None
        return data


def mark_consumed(token: str, po_id: str, sender_open_id: str) -> None:
    with _lock:
        _gc_locked()
        _consumed[token] = (po_id, _now(), sender_open_id)


def get_consumed_po(token: str, sender_open_id: str) -> str | None:
    with _lock:
        _gc_locked()
        entry = _consumed.get(token)
        if entry is None:
            return None
        po_id, ts, sender = entry
        if sender != sender_open_id:
            return None
        if _now() - ts > _TTL_SECONDS:
            _consumed.pop(token, None)
            return None
        return po_id


# --- Test hooks ---

def _reset_for_test() -> None:
    with _lock:
        _drafts.clear()
        _consumed.clear()


def _set_ttl_for_test(seconds: int) -> None:
    global _TTL_SECONDS
    _TTL_SECONDS = seconds
