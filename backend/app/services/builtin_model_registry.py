"""Canonical built-in coaching model versions — one source of truth."""

from __future__ import annotations

from typing import Dict, FrozenSet, Set


# Versions that are part of the application itself (not necessarily registered in DB).
BUILTIN_MODEL_VERSIONS: Dict[str, FrozenSet[str]] = {
    "ranker": frozenset({"default", "builtin_default"}),
    "calibration": frozenset({"default"}),
    "prescription": frozenset({"default"}),
}


class BuiltinModelRegistry:
    @staticmethod
    def known_versions(model_key: str) -> Set[str]:
        return set(BUILTIN_MODEL_VERSIONS.get(model_key, frozenset()))

    @staticmethod
    def is_known(model_key: str, version: str) -> bool:
        if version in BuiltinModelRegistry.known_versions(model_key):
            return True
        # Generic builtin marker used by CoachingModelRegistry.get_active fallback
        return version in {"default", "builtin_default"}

    @staticmethod
    def all_known() -> Set[str]:
        out: Set[str] = {"default", "builtin_default"}
        for versions in BUILTIN_MODEL_VERSIONS.values():
            out |= set(versions)
        return out
