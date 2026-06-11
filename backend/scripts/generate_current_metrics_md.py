#!/usr/bin/env python3
"""Generer MCP_CURRENT_METRICS.md med nåværende verdier + ordbok fra MCP."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy.orm import selectinload  # noqa: E402

from app.mcp.metric_glossary import (  # noqa: E402
    COACHING_DISAMBIGUATION,
    CATEGORY_GLOSSARY,
    METRIC_GLOSSARY,
    SCOPE_DESCRIPTIONS,
    get_glossary_entry,
)
from app.mcp import training_tools  # noqa: E402
from app.database.models.activity import Activity  # noqa: E402
from app.services.mcp_derived_metrics_service import (  # noqa: E402
    DERIVED_METRIC_CATALOG,
    McpDerivedMetricsService,
)
from app.utils.activity_filters import is_running_activity  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[2] / "MCP_CURRENT_METRICS.md"

EXTRA_DERIVED_KEYS = sorted(
    key for key in METRIC_GLOSSARY if key not in DERIVED_METRIC_CATALOG
)


def _format_value(value: Any, unit: Optional[str]) -> str:
    if value is None:
        return "*(ingen verdi)*"
    if isinstance(value, float):
        text = f"{value:.4g}" if value != 0 else "0"
    elif isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    if unit and unit not in {"value", "label", "class", "code", "zone"}:
        return f"`{text}` ({unit})"
    return f"`{text}`"


def _stored_latest_values() -> Dict[str, Tuple[Any, Optional[str]]]:
    """Hent siste lagrede verdi per metrikk (effektivt, én DB-sesjon)."""
    out: Dict[str, Tuple[Any, Optional[str]]] = {}
    by_model: Dict[Any, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)

    for key, definition in training_tools.METRIC_CATALOG.items():
        by_model[(definition["model"], definition["date_field"])].append((key, definition))

    with training_tools.training_context() as (db, _storage):
        for (model, date_field), items in by_model.items():
            date_col = getattr(model, date_field)
            rows = db.query(model).order_by(date_col.desc()).limit(80).all()
            if not rows:
                for key, _defn in items:
                    out[key] = (None, None)
                continue

            for key, definition in items:
                value = None
                as_of = None
                column = definition.get("column")
                for row in rows:
                    if definition.get("derived") == "activity_pace":
                        val = training_tools._activity_pace(row)
                    elif column:
                        val = getattr(row, column, None)
                    else:
                        val = None
                    if val is None:
                        continue
                    value = round(float(val), 3) if isinstance(val, (int, float)) else val
                    dv = getattr(row, date_field)
                    if isinstance(dv, datetime):
                        as_of = dv.date().isoformat()
                    elif isinstance(dv, int):
                        as_of = str(dv)
                    elif dv:
                        as_of = dv.isoformat()
                    break
                out[key] = (value, as_of)
    return out


def _derived_latest_values() -> Dict[str, Tuple[Any, Optional[str]]]:
    today = date.today()
    out: Dict[str, Tuple[Any, Optional[str]]] = {}
    with training_tools.training_context() as (db, storage):
        service = McpDerivedMetricsService(db, storage)
        latest_run: Optional[Activity] = (
            db.query(Activity)
            .options(selectinload(Activity.activity_type))
            .order_by(Activity.start_time.desc())
            .limit(50)
            .all()
        )
        latest_run = next((a for a in latest_run if is_running_activity(a)), None)

        for key, definition in DERIVED_METRIC_CATALOG.items():
            scope = definition["scope"]
            try:
                if scope == "activity" and latest_run:
                    value = service._activity_metric_value(key, latest_run)  # noqa: SLF001
                    as_of = latest_run.start_time.date().isoformat() if latest_run.start_time else None
                elif scope == "snapshot":
                    value = service._daily_metric_value(key, today)  # noqa: SLF001
                    as_of = today.isoformat()
                else:
                    value = None
                    as_of = None
                    for offset in range(0, 14):
                        day = today - timedelta(days=offset)
                        value = service._daily_metric_value(key, day)  # noqa: SLF001
                        if value is not None:
                            as_of = day.isoformat()
                            break
            except Exception:
                value, as_of = None, None
            out[key] = (value, as_of)

        for key in EXTRA_DERIVED_KEYS:
            try:
                value = service._daily_metric_value(key, today)  # noqa: SLF001
            except Exception:
                value = None
            out[key] = (value, today.isoformat() if value is not None else None)
    return out


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as exc:
        return {"error": str(exc)} if default is None else default


def _data_quality_warnings(
    athlete: Dict[str, Any],
    coaching: Dict[str, Any],
    readiness: Dict[str, Any],
    *,
    with_values: int,
    total: int,
) -> List[str]:
    """Flagg mønstre som ofte oppleves som «feil» uten at beregningen er bug."""
    warnings: List[str] = []
    inv = athlete.get("data_inventory") or {}
    activities = int(inv.get("activities") or 0)

    if activities == 0 and with_values > 0:
        warnings.append(
            f"**{with_values}** metrikker har verdi uten aktiviteter i databasen — "
            "sannsynligvis standardverdier/heuristikk, ikke målt data."
        )

    if isinstance(coaching, dict) and not coaching.get("error"):
        cons = (coaching.get("consistency") or {}).get("score")
        limiters = coaching.get("limiting_factors") or {}
        if cons is not None and float(cons) < 10 and limiters.get("consistency", 0) > 50:
            warnings.append(
                f"Consistency score er **{cons}** (0 treningsdager), men limiter "
                f"`consistency` er **{limiters['consistency']}** — høy limiter-score betyr "
                "«sterk begrensning», ikke god konsistens."
            )
        readiness_ev = coaching.get("readiness_by_event") or {}
        if activities == 0 and any(v is not None for v in readiness_ev.values()):
            warnings.append(
                "Event readiness (5k/10k/HM/maraton) har tall uten treningsdata — "
                "`get_event_readiness` faller tilbake til `total_score=50` når Garmin-readiness mangler."
            )
        if coaching.get("training_block") == "peak" and activities == 0:
            warnings.append(
                "Training block er **peak** med CTL/ATL/TSB ≈ 0 — "
                "`get_training_block` tolker null-belastning som «peak»-grensetilfelle."
            )

    if isinstance(readiness, dict) and not readiness.get("error"):
        hrv = readiness.get("hrv_guidance") or {}
        if hrv.get("rmssd_baseline") is None and readiness.get("recommendation") == "normal_training":
            warnings.append(
                "Training readiness anbefaler **normal_training** uten HRV-baseline — "
                "manglende data gir ofte «grønt lys» i stedet for «ukjent»."
            )
        banister = readiness.get("banister") or {}
        if banister.get("fitness") == 0 and banister.get("status") == "productive_load":
            warnings.append(
                "Banister-status er **productive_load** med fitness/fatigue 0 — "
                "status-tekst kan være misvisende ved tom historikk."
            )

    if total and with_values < total * 0.1:
        warnings.append(
            f"Bare **{with_values}/{total}** metrikker har verdi — forvent mange "
            "«ingen verdi»-felt; sjekk sync og at metrics er precomputet."
        )

    return warnings


def _metric_row(
    key: str,
    meta: Dict[str, Any],
    value: Any,
    as_of: Optional[str],
) -> List[str]:
    gloss = get_glossary_entry(key)
    lines = [f"### `{key}`"]
    title = gloss.get("title")
    if title and title != key:
        lines.append(f"**{title}**")
    lines.append("")
    meta_bits = []
    if meta.get("unit"):
        meta_bits.append(f"enhet: `{meta['unit']}`")
    if meta.get("scope"):
        meta_bits.append(f"scope: `{meta['scope']}`")
    if meta.get("source"):
        meta_bits.append(f"kilde: `{meta['source']}`")
    if meta.get("availability"):
        meta_bits.append(f"availability: `{meta['availability']}`")
    if meta.get("heuristic"):
        meta_bits.append("**heuristikk**")
    if meta_bits:
        lines.append("*" + " · ".join(meta_bits) + "*")
        lines.append("")
    lines.append(f"- **Nåværende verdi:** {_format_value(value, meta.get('unit'))}")
    if as_of:
        lines.append(f"- **Per dato:** `{as_of}`")
    if meta.get("availability_reason"):
        lines.append(f"- **Availability:** {meta['availability_reason']}")
    for label, gkey in (
        ("Definisjon", "definition"),
        ("Tolkning", "interpretation"),
        ("Coaching", "coaching_use"),
        ("Merk", "caveats"),
        ("Datakilde (ordbok)", "source"),
    ):
        text = gloss.get(gkey)
        if text:
            lines.append(f"- **{label}:** {text}")
    lines.append("")
    return lines


def main() -> None:
    reference_date = date.today().isoformat()
    catalog = training_tools.metric_catalog()
    stored = _stored_latest_values()
    derived = _derived_latest_values()
    athlete = _safe(training_tools.athlete_profile)
    coaching = _safe(lambda: training_tools.coaching_decision_snapshot())
    readiness = _safe(training_tools.training_readiness_check)

    lines: List[str] = [
        "# MCP — nåværende metrikker og ordbok",
        "",
        f"Referansedato: **{reference_date}**. Generert fra MCP-verktøyene "
        "(`metric_catalog`, `metric_glossary`, `athlete_profile`, "
        "`coaching_decision_snapshot`, `training_readiness_check`) og intern "
        "snapshot-henting som speiler `query_metric_timeseries`.",
        "",
        "> Kjør på nytt med din lokale database: "
        "`cd backend && python3 scripts/generate_current_metrics_md.py` "
        "og `python3 scripts/generate_mcp_fresh_export.py`",
        "",
        "---",
        "",
        "## Sammendrag",
        "",
        f"- **Metrikker i katalog:** {catalog['count']}",
        f"- **Kategorier:** {', '.join(f'`{c}`' for c in catalog.get('categories', []))}",
        f"- **Availability states:** {', '.join(f'`{s}`' for s in catalog.get('availability_states', []))}",
    ]

    if athlete.get("error"):
        lines.append(f"- **Athlete profile:** feilet ({athlete['error']})")
    else:
        inv = athlete.get("data_inventory", {})
        lines.append(
            f"- **Data:** {inv.get('activities', 0)} aktiviteter, "
            f"{inv.get('runs', 0)} løp, {inv.get('route_groups', 0)} rutegrupper"
        )

    # Pre-count for warnings (quick pass)
    pre_missing = 0
    pre_total = len(catalog["metrics"])
    for metric in catalog["metrics"]:
        key = metric["key"]
        if metric.get("source") == "derived":
            val = derived.get(key, (None,))[0]
        else:
            val = stored.get(key, (None,))[0]
        if val is None:
            pre_missing += 1
    quality_warnings = _data_quality_warnings(
        athlete,
        coaching,
        readiness,
        with_values=pre_total - pre_missing,
        total=pre_total,
    )

    if quality_warnings:
        lines.extend(["", "### Observasjoner for denne kjøringen", ""])
        for warning in quality_warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.extend(["", "---", "", "## Viktig: ikke forveksle disse", "", "| Tema | Metrikker | Regel |", "|------|-----------|-------|"])
    for item in COACHING_DISAMBIGUATION:
        rule = item["rule"].replace("\n", " ")
        lines.append(f"| {item['topic']} | `{item['metrics']}` | {rule} |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Kjente fallgruver (kan virke feil eller misvisende)",
            "",
            "| Fenomen | Hva skjer | Anbefaling |",
            "|---------|-----------|------------|",
            "| `readiness_score` vs `readiness.total_score` | To ulike modeller (intern heuristikk vs Garmin 15/15/70) | Bruk én konsekvent |",
            "| `fitness.tsb` og `fitness.form` | Samme beregning (alias) | Ikke tolke som to uavhengige signaler |",
            "| `load.acwr` | Garmin ACWR hvis finnes, ellers 7d/28d TSS-ratio | Sjekk kilde før sammenligning med CTL/ATL |",
            "| `fitness_score` / `fatigue_score` | Banister delt på 1,5, klippet 0–100 | Ikke sammenlign med rå CTL/ATL |",
            "| `performance_score` | `50 + Banister performance` | Relativ trend, ikke absolutt skala |",
            "| `predicted_*_time` | Critical Speed-modell | Kan avvike fra faktisk konkurranseform |",
            "| Heuristikk (`heuristic: true`) | Modellerte coaching-score | Hint, ikke fasit |",
            "| Ordbok uten katalog | F.eks. `consistency.score` | Se coaching snapshot nedenfor |",
            "| `scope: activity` | Siste økt med verdi | «Per dato» = øktdato |",
            "| `scope: snapshot` | Ofte all-time / siste beregning | Verifiser dato |",
            "",
            "---",
            "",
            "## Athlete profile",
            "",
            "```json",
            json.dumps(athlete, ensure_ascii=False, indent=2),
            "```",
            "",
            "---",
            "",
            "## Coaching decision snapshot",
            "",
            "```json",
            json.dumps(coaching, ensure_ascii=False, indent=2),
            "```",
            "",
            "---",
            "",
            "## Training readiness",
            "",
            "```json",
            json.dumps(readiness, ensure_ascii=False, indent=2),
            "```",
            "",
            "---",
            "",
            "## Scope",
            "",
            "| Scope | Betydning |",
            "|-------|-----------|",
        ]
    )
    for scope, desc in sorted(SCOPE_DESCRIPTIONS.items()):
        lines.append(f"| `{scope}` | {desc} |")

    lines.extend(["", "---", "", "## Kategorier", ""])
    for cat, info in sorted(CATEGORY_GLOSSARY.items()):
        lines.append(f"### `{cat}`")
        lines.append(f"- {info.get('definition', '')}")
        lines.append(f"- *Coaching:* {info.get('coaching_use', '')}")
        lines.append("")

    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for metric in catalog["metrics"]:
        by_cat[metric["category"]].append(metric)

    lines.extend(["---", "", "## Alle metrikker med nåværende verdi", ""])
    missing = 0
    total = 0

    for cat in sorted(by_cat):
        lines.append(f"## Kategori: `{cat}`")
        lines.append("")
        for metric in sorted(by_cat[cat], key=lambda m: m["key"]):
            key = metric["key"]
            total += 1
            if metric.get("source") == "derived":
                value, as_of = derived.get(key, (None, None))
            else:
                value, as_of = stored.get(key, (None, None))
            if value is None:
                missing += 1
            meta = {
                "unit": metric.get("unit"),
                "scope": metric.get("scope"),
                "source": metric.get("source"),
                "heuristic": metric.get("heuristic", False),
                "availability": metric.get("availability"),
                "availability_reason": metric.get("availability_reason"),
            }
            lines.extend(_metric_row(key, meta, value, as_of))

    extra_with_value = sum(1 for k in EXTRA_DERIVED_KEYS if derived.get(k, (None,))[0] is not None)
    if EXTRA_DERIVED_KEYS:
        lines.extend(
            [
                "---",
                "",
                "## Ordbok uten katalogoppføring",
                "",
                f"{len(EXTRA_DERIVED_KEYS)} nøkler i ordbok som ikke er i `metric_catalog`. "
                f"{extra_with_value} har beregnet verdi i dag.",
                "",
            ]
        )
        for key in EXTRA_DERIVED_KEYS:
            value, as_of = derived.get(key, (None, None))
            gloss = get_glossary_entry(key)
            meta = {"unit": None, "scope": "daily", "source": "derived", "heuristic": True}
            lines.extend(_metric_row(key, meta, value, as_of))

    lines.extend(
        [
            "---",
            "",
            "## Statistikk",
            "",
            f"- Med verdi: **{total - missing}** / {total}",
            f"- Uten verdi: **{missing}**",
            "",
        ]
    )

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(lines)} lines, {total - missing}/{total} with values)")


if __name__ == "__main__":
    main()
