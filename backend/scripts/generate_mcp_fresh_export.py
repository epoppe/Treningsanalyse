#!/usr/bin/env python3
"""Generer MCP_FRESH_VALUES.json/.csv fra live DB + metric_catalog (ingen stale snapshots)."""

from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.mcp import training_tools  # noqa: E402
from app.mcp.speed_metric_format import mcp_export_display_value  # noqa: E402
from app.services.mcp_derived_metrics_service import (  # noqa: E402
    DERIVED_METRIC_CATALOG,
    McpDerivedMetricsService,
)

_DAILY_DERIVED_LOOKBACK_DAYS = 14
JSON_OUTPUT = ROOT / "MCP_FRESH_VALUES.json"
CSV_OUTPUT = ROOT / "MCP_FRESH_VALUES.csv"

CSV_FIELDS = [
    "key",
    "value",
    "date",
    "unit",
    "category",
    "source",
    "scope",
    "availability",
    "availability_reason",
    "heuristic",
    "summary",
    "canonical_key",
]


def _serialize_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, (dict, list, str, int, bool)) or value is None:
        return value
    return str(value)


def _metric_definition(key: str, source: str) -> Dict[str, Any]:
    if source == "derived":
        return DERIVED_METRIC_CATALOG.get(key, {})
    return training_tools.METRIC_CATALOG.get(key, {})


def _metric_entry(
    key: str,
    meta: Dict[str, Any],
    value: Any,
    as_of: Optional[str],
    *,
    canonical_key: Optional[str] = None,
    preformatted: bool = False,
) -> Dict[str, Any]:
    if preformatted:
        display_value = value
        display_unit = meta.get("unit")
    else:
        source = "derived" if meta.get("source") == "derived" else "stored"
        lookup_key = canonical_key or key
        definition = _metric_definition(lookup_key, source)
        display_value, display_unit = mcp_export_display_value(
            key,
            value,
            source=source,
            definition=definition,
        )
    return {
        "key": key,
        "value": _serialize_value(display_value),
        "date": as_of,
        "unit": display_unit if display_unit is not None else meta.get("unit"),
        "category": meta.get("category"),
        "source": meta.get("source"),
        "scope": meta.get("scope"),
        "availability": meta.get("availability"),
        "availability_reason": meta.get("availability_reason"),
        "heuristic": meta.get("heuristic"),
        "summary": meta.get("summary"),
        "canonical_key": canonical_key,
    }


def _catalog_by_key(catalog: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {metric["key"]: metric for metric in catalog["metrics"]}


def _latest_daily_derived_value(
    derived: McpDerivedMetricsService,
    metric_key: str,
    *,
    rolling_daily: bool = False,
) -> tuple[Any, Optional[str], Optional[str]]:
    """Finn siste ikke-null daglig avledet verdi uten full timeseries (raskere export)."""
    today = date.today()
    for offset in range(_DAILY_DERIVED_LOOKBACK_DAYS):
        day = today - timedelta(days=offset)
        if rolling_daily:
            value = derived._ppap.get_rolling_duration_curve_value(metric_key, day)
        else:
            value = derived._daily_metric_value(metric_key, day)
        if value is not None:
            display_unit = training_tools.mcp_display_unit(metric_key) or DERIVED_METRIC_CATALOG.get(
                metric_key, {}
            ).get("unit")
            return value, day.isoformat(), display_unit
    return None, None, None


def _latest_metric_value(
    metric_key: str,
    *,
    derived: Optional[McpDerivedMetricsService] = None,
) -> tuple[Any, Optional[str], Optional[str]]:
    """Fetch latest user-facing MCP value using the same display logic as query_metric_timeseries."""
    canonical_key, _ = training_tools._resolve_metric_key(metric_key)
    definition = DERIVED_METRIC_CATALOG.get(canonical_key, {})
    scope = definition.get("scope")

    if derived is not None and scope in {"daily", "rolling_daily"}:
        return _latest_daily_derived_value(
            derived,
            canonical_key,
            rolling_daily=scope == "rolling_daily",
        )

    query_limit = 365 if scope == "activity" else 1
    result = training_tools.query_metric_timeseries(metric_key=metric_key, limit=query_limit)
    if result.get("status") != "ok":
        return None, None, None

    points = result.get("points") or []
    if not points:
        return None, None, result.get("display_unit") or result.get("unit")

    point = points[-1]
    return (
        point.get("value"),
        point.get("date"),
        result.get("display_unit") or result.get("unit"),
    )


def _build_export_rows(
    catalog: Dict[str, Any],
) -> List[Dict[str, Any]]:
    by_key = _catalog_by_key(catalog)
    rows: List[Dict[str, Any]] = []

    with training_tools.training_context() as (db, storage):
        derived = McpDerivedMetricsService(db, storage)

        for index, metric in enumerate(catalog["metrics"], start=1):
            key = metric["key"]
            value, as_of, display_unit = _latest_metric_value(key, derived=derived)
            metric_meta = {**metric}
            if display_unit:
                metric_meta["unit"] = display_unit
            rows.append(
                _metric_entry(
                    key,
                    metric_meta,
                    value,
                    as_of,
                    canonical_key=metric.get("canonical_key"),
                    preformatted=True,
                )
            )
            if index % 50 == 0:
                print(f"  [{index}/{catalog['count']}] export...", flush=True)

        for alias, canonical in sorted(training_tools.METRIC_KEY_ALIASES.items()):
            canonical_meta = by_key.get(canonical)
            if canonical_meta is None:
                continue
            value, as_of, display_unit = _latest_metric_value(alias, derived=derived)
            alias_meta = {
                **canonical_meta,
                "key": alias,
            }
            if display_unit:
                alias_meta["unit"] = display_unit
            rows.append(
                _metric_entry(
                    alias,
                    alias_meta,
                    value,
                    as_of,
                    canonical_key=canonical,
                    preformatted=True,
                )
            )

    rows.sort(key=lambda row: row["key"])
    return rows


def _write_csv(rows: List[Dict[str, Any]]) -> None:
    with CSV_OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def main() -> None:
    reference_date = date.today().isoformat()
    catalog = training_tools.metric_catalog()
    rows = _build_export_rows(catalog)

    with_values = sum(1 for row in rows if row["value"] is not None)
    payload = {
        "reference_date": reference_date,
        "count": len(rows),
        "catalog_metric_count": catalog["count"],
        "with_values": with_values,
        "without_values": len(rows) - with_values,
        "metrics": rows,
    }

    JSON_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(rows)
    print(
        f"Wrote {JSON_OUTPUT} and {CSV_OUTPUT} "
        f"({with_values}/{len(rows)} with values, ref={reference_date})"
    )


if __name__ == "__main__":
    main()
