"""Grensekontroll for lag 3 (avledede metrikker).

Moduler i DERIVED_MODULES skal ikke lese Garmin JSON direkte
(detailed_metrics, summaryDTO, camelCase Garmin-nøkler).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

# Filstier relative til backend/app/
DERIVED_MODULES = (
    "services/analysis_service.py",
    "services/power_service.py",
    "services/performance_metrics_service.py",
    "services/sync_modules/metrics_service.py",
    "services/mcp_derived_metrics_service.py",
    "services/coaching_analysis_service.py",
    "services/training_stress_service.py",
)

# Mønstre som ikke skal forekomme i lag 3-kilde
FORBIDDEN_PATTERNS = (
    "activity.detailed_metrics",
    "detailed_metrics.get(",
    "summaryDTO",
    'act_data.get("averageHR")',
    'act_data.get("vO2MaxValue")',
    'record.get("enhanced_speed")',
    'record.get("enhancedSpeed")',
)


def scan_derived_layer_violations(
    app_root: Path,
    *,
    modules: Iterable[str] = DERIVED_MODULES,
    patterns: Iterable[str] = FORBIDDEN_PATTERNS,
) -> List[Tuple[str, int, str]]:
    """Returner liste av (rel_path, line_no, pattern) for brudd."""
    violations: List[Tuple[str, int, str]] = []
    for rel in modules:
        path = app_root / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            # Tillat kommentarer som beskriver forbudet
            stripped = line.lstrip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            for pattern in patterns:
                if pattern in line:
                    violations.append((rel, i, pattern))
    return violations
