#!/usr/bin/env python3
"""Generer docs/METRIC_GLOSSARY.md fra app.mcp.metric_glossary."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.mcp.metric_glossary import (  # noqa: E402
    CATEGORY_GLOSSARY,
    COACHING_DISAMBIGUATION,
    SCOPE_DESCRIPTIONS,
    STORED_PREFIX_GLOSSARY,
    get_glossary_entry,
)
from app.mcp.training_tools import METRIC_CATALOG  # noqa: E402
from app.services.mcp_derived_metrics_service import DERIVED_METRIC_CATALOG  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[2] / "METRIC_GLOSSARY.md"


def _fmt_entry(entry: dict, meta: dict | None = None) -> list[str]:
    lines = [f"### `{entry['metric_key']}`"]
    if entry.get("title") and entry["title"] != entry["metric_key"]:
        lines.append(f"**{entry['title']}**")
    lines.append("")
    if meta:
        parts = []
        if meta.get("unit"):
            parts.append(f"enhet: `{meta['unit']}`")
        if meta.get("scope"):
            parts.append(f"scope: `{meta['scope']}`")
        if meta.get("heuristic"):
            parts.append("heuristikk: ja")
        if meta.get("source"):
            parts.append(f"kilde i katalog: `{meta['source']}`")
        if parts:
            lines.append("*" + " · ".join(parts) + "*")
            lines.append("")
    for label, key in (
        ("Definisjon", "definition"),
        ("Tolkning", "interpretation"),
        ("Coaching", "coaching_use"),
        ("Merk", "caveats"),
        ("Datakilde", "source"),
    ):
        value = entry.get(key)
        if value:
            lines.append(f"- **{label}:** {value}")
    lines.append("")
    return lines


def main() -> None:
    lines: list[str] = [
        "# Metric glossary (MCP / PPAP)",
        "",
        "Ordbok for alle metrikker som kan spørres via MCP (`metric_catalog`, ",
        "`query_metric_timeseries`, `metric_glossary`). Bruk denne når du coacher ",
        "eller skriver prompts — **ikke** bland metrikker som ser like ut.",
        "",
        "> Generert fra `backend/app/mcp/metric_glossary.py`. Kjør på nytt: ",
        "`cd backend && python3 scripts/generate_metric_glossary_md.py`",
        "",
        "---",
        "",
        "## Viktig: ikke forveksle disse",
        "",
        "| Tema | Metrikker | Regel |",
        "|------|-----------|-------|",
    ]

    for item in COACHING_DISAMBIGUATION:
        rule = item["rule"].replace("\n", " ")
        lines.append(f"| {item['topic']} | `{item['metrics']}` | {rule} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Scope (tidsoppløsning)",
            "",
            "| Scope | Betydning |",
            "|-------|-----------|",
        ]
    )
    for scope, desc in sorted(SCOPE_DESCRIPTIONS.items()):
        lines.append(f"| `{scope}` | {desc} |")

    lines.extend(["", "---", "", "## Kategorier (oversikt)", ""])
    for cat, info in sorted(CATEGORY_GLOSSARY.items()):
        lines.append(f"### `{cat}`")
        lines.append(f"- **Definisjon:** {info.get('definition', '')}")
        lines.append(f"- **Coaching:** {info.get('coaching_use', '')}")
        lines.append("")

    lines.extend(["---", "", "## Beregnete metrikker (derived)", ""])
    by_cat: dict[str, list[str]] = defaultdict(list)
    for key in sorted(DERIVED_METRIC_CATALOG):
        by_cat[DERIVED_METRIC_CATALOG[key]["category"]].append(key)

    for cat in sorted(by_cat):
        lines.append(f"## Kategori: `{cat}`")
        lines.append("")
        for key in by_cat[cat]:
            entry = get_glossary_entry(key)
            lines.extend(_fmt_entry(entry, DERIVED_METRIC_CATALOG[key]))

    lines.extend(["---", "", "## Lagrede metrikker (Garmin/sync)", ""])
    lines.append(
        "Disse hentes fra databasekolonner. De fleste har generisk forklaring via "
        "prefiks nedenfor; viktige felt har egne oppføringer i koden."
    )
    lines.append("")
    lines.append("### Prefiks-mønstre")
    lines.append("")
    for prefix, info in STORED_PREFIX_GLOSSARY.items():
        lines.append(f"#### `{prefix}*`")
        lines.append(f"- **Definisjon:** {info['definition']}")
        lines.append(f"- **Tolkning:** {info['interpretation']}")
        lines.append(f"- **Coaching:** {info['coaching_use']}")
        lines.append(f"- **Kilde:** {info['source']}")
        lines.append("")

    stored_by_cat: dict[str, list[str]] = defaultdict(list)
    for key, defn in METRIC_CATALOG.items():
        stored_by_cat[defn["category"]].append(key)

    lines.append("### Full liste lagrede nøkler (alfabetisk per kategori)")
    lines.append("")
    for cat in sorted(stored_by_cat):
        lines.append(f"#### `{cat}` ({len(stored_by_cat[cat])} nøkler)")
        lines.append("")
        for key in sorted(stored_by_cat[cat]):
            defn = METRIC_CATALOG[key]
            gloss = get_glossary_entry(key)
            summary = gloss.get("definition", "")
            if len(summary) > 120:
                summary = summary[:117] + "…"
            lines.append(
                f"- `{key}` — {summary} *(enhet: {defn.get('unit', '?')}, "
                f"scope: stored)*"
            )
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## MCP-oppslag",
            "",
            "| Kanal | Bruk |",
            "|-------|------|",
            "| Ressurs `treningsanalyse://metric-glossary` | Full JSON-ordbok |",
            "| Verktøy `metric_glossary(metric_key=...)` | Én metrikk eller søk |",
            "| Verktøy `metric_catalog()` | Alle nøkler + kort `summary` |",
            "| Verktøy `query_metric_timeseries(...)` | Verdidata |",
            "",
        ]
    )

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
