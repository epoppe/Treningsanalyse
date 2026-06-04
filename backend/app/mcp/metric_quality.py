"""Kvalitetsrapport for alle MCP-metrikker — status, verdi og heuristikk."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from ..services.mcp_derived_metrics_service import DERIVED_METRIC_CATALOG
from .metric_glossary import get_glossary_entry


def build_metric_quality_report(
    *,
    catalog_metrics: List[Dict[str, Any]],
    query_timeseries_fn,
    reference_date: Optional[date] = None,
    lookback_days: int = 14,
) -> Dict[str, Any]:
    """
    Bygg rapport over alle katalog-metrikker.

    query_timeseries_fn(metric_key, start_date, end_date, limit) -> dict
    """
    ref = reference_date or date.today()
    start = ref - timedelta(days=max(lookback_days - 1, 0))

    entries: List[Dict[str, Any]] = []
    for meta in catalog_metrics:
        key = meta["key"]
        gloss = get_glossary_entry(key)
        entry: Dict[str, Any] = {
            "metric_key": key,
            "category": meta.get("category"),
            "unit": meta.get("unit"),
            "scope": meta.get("scope"),
            "source": meta.get("source"),
            "availability": meta.get("availability"),
            "availability_reason": meta.get("availability_reason"),
            "heuristic": bool(meta.get("heuristic", False)),
            "title": gloss.get("title"),
            "definition": gloss.get("definition"),
            "status": "unknown",
            "latest_value": None,
            "latest_date": None,
            "issue": None,
        }

        try:
            series = query_timeseries_fn(
                key,
                start_date=start.isoformat(),
                end_date=ref.isoformat(),
                limit=lookback_days,
            )
        except Exception as exc:
            entry["status"] = "bug"
            entry["issue"] = str(exc)
            entries.append(entry)
            continue

        status = series.get("status")
        if status == "error":
            entry["status"] = "bug"
            entry["issue"] = series.get("message")
        elif status == "unknown_metric":
            entry["status"] = "unknown"
            entry["issue"] = "Ikke i katalog"
        elif status != "ok":
            entry["status"] = "bug"
            entry["issue"] = str(status)
        else:
            points = series.get("points") or []
            if not points:
                availability = meta.get("availability")
                if availability in {"not_ingested", "empty_source", "unsupported"}:
                    entry["status"] = availability
                    entry["issue"] = meta.get("availability_reason")
                else:
                    entry["status"] = "no_data"
            else:
                last = points[-1]
                entry["status"] = "ok"
                entry["latest_value"] = last.get("value")
                entry["latest_date"] = last.get("date") or last.get("timestamp")
                if entry["heuristic"]:
                    entry["quality_note"] = "heuristikk — ikke Garmin-fasit"
                if meta.get("scope") == "activity":
                    entry["quality_note"] = (
                        (entry.get("quality_note") or "")
                        + " scope activity = siste økt med verdi"
                    ).strip()

        entries.append(entry)

    counts = Counter(e["status"] for e in entries)
    heuristic_ok = sum(
        1 for e in entries if e["status"] == "ok" and e.get("heuristic")
    )

    known_disambiguation = [
        {
            "topic": "Readiness",
            "keys": ["readiness.total_score", "readiness_score"],
            "note": "To ulike modeller — ikke sammenlign.",
        },
        {
            "topic": "Belastning",
            "keys": ["fitness.ctl", "fitness_score", "load.acwr"],
            "note": "CTL vs Banister fitness_score vs Garmin ACWR.",
        },
    ]

    return {
        "schema_version": "metric-quality-1",
        "reference_date": ref.isoformat(),
        "lookback_days": lookback_days,
        "summary": {
            "total": len(entries),
            "ok": counts.get("ok", 0),
            "no_data": counts.get("no_data", 0),
            "not_ingested": counts.get("not_ingested", 0),
            "empty_source": counts.get("empty_source", 0),
            "unsupported": counts.get("unsupported", 0),
            "bug": counts.get("bug", 0),
            "unknown": counts.get("unknown", 0),
            "heuristic_with_value": heuristic_ok,
        },
        "disambiguation": known_disambiguation,
        "entries": entries,
    }


def format_metric_quality_markdown(report: Dict[str, Any]) -> str:
    """Render rapport som markdown-tabell."""
    lines = [
        f"# Metric quality report — {report['reference_date']}",
        "",
        f"- OK: **{report['summary']['ok']}** / {report['summary']['total']}",
        f"- Uten data: **{report['summary']['no_data']}**",
        f"- Ikke ingestet: **{report['summary']['not_ingested']}**",
        f"- Tom kilde: **{report['summary']['empty_source']}**",
        f"- Unsupported: **{report['summary']['unsupported']}**",
        f"- Feil (bug): **{report['summary']['bug']}**",
        f"- Heuristiske med verdi: **{report['summary']['heuristic_with_value']}**",
        "",
        "| Metrikk | Status | Availability | Verdi | Dato | Heuristikk | Merknad |",
        "|---------|--------|--------------|-------|------|------------|---------|",
    ]
    for entry in report["entries"]:
        heuristic = "ja" if entry.get("heuristic") else "nei"
        value = entry.get("latest_value")
        value_text = "—" if value is None else f"`{value}`"
        note = entry.get("issue") or entry.get("quality_note") or ""
        if len(note) > 80:
            note = note[:77] + "…"
        lines.append(
            f"| `{entry['metric_key']}` | {entry['status']} | {entry.get('availability') or '—'} | {value_text} | "
            f"{entry.get('latest_date') or '—'} | {heuristic} | {note} |"
        )
    lines.append("")
    return "\n".join(lines)
