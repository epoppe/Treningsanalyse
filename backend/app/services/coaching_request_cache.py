"""Request-scoped coaching cache — keyed by as_of_date / treadmill / goal.

Historical as-of calls must never reuse a cache from a different as_of_date.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from typing import Any, Dict, Iterator, Optional

from .payload_hash import payload_hash

_cache_var: ContextVar[Optional[Dict[str, Any]]] = ContextVar("coaching_request_cache", default=None)


def cache_key(*, as_of_date: date, include_treadmill: bool = False, goal: Optional[Dict[str, Any]] = None) -> str:
    return f"{as_of_date.isoformat()}|tm={int(bool(include_treadmill))}|g={payload_hash(goal or {})}"


@contextmanager
def coaching_request_cache() -> Iterator[Dict[str, Any]]:
    store: Dict[str, Any] = {}
    token = _cache_var.set(store)
    try:
        yield store
    finally:
        _cache_var.reset(token)


def get_cache() -> Optional[Dict[str, Any]]:
    return _cache_var.get()


def cached_get(namespace: str, key: str) -> Any:
    store = get_cache()
    if store is None:
        return None
    return store.get(f"{namespace}:{key}")


def cached_set(namespace: str, key: str, value: Any) -> Any:
    store = get_cache()
    if store is not None:
        store[f"{namespace}:{key}"] = value
    return value


def get_or_set(namespace: str, key: str, factory):
    existing = cached_get(namespace, key)
    if existing is not None:
        return existing
    return cached_set(namespace, key, factory())
