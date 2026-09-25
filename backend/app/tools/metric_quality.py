"""Print the existing metric-quality report without rewriting the committed snapshot.

Run from backend/:

    python -m app.tools.metric_quality
    python -m app.tools.metric_quality --previous snapshot.json
    python -m app.tools.metric_quality --write-report

The default prints a summary. It does not overwrite METRIC_QUALITY_REPORT.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from app.mcp.metric_quality import CAPABILITY_NOTE, summary_delta

REPORT_PATH = Path(__file__).resolve().parents[3] / "METRIC_QUALITY_REPORT.md"


def build_payload(report: Dict[str, Any], previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = {
        "schema_version": report.get("schema_version"),
        "reference_date": report.get("reference_date"),
        "lookback_days": report.get("lookback_days"),
        "summary": report.get("summary") or {},
        "capability_vs_availability": CAPABILITY_NOTE,
    }
    if previous is not None:
        previous_summary = previous.get("summary") if "summary" in previous else previous
        payload["summary_delta"] = summary_delta(payload["summary"], previous_summary or {})
    return payload


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Metric quality summary from the existing catalog generator.")
    parser.add_argument("--target-date", default=None)
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--previous", type=Path, default=None, help="Earlier JSON summary to diff against.")
    parser.add_argument("--json-out", type=Path, default=None, help="Write the summary JSON here.")
    parser.add_argument("--markdown", action="store_true", help="Print markdown to stdout.")
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Overwrite METRIC_QUALITY_REPORT.md. Off unless this flag is set.",
    )
    args = parser.parse_args(argv)

    from app.mcp.training_tools import metric_quality_report

    report = metric_quality_report(
        target_date=args.target_date,
        lookback_days=args.lookback_days,
        markdown=args.markdown or args.write_report,
    )
    previous = None
    if args.previous is not None:
        previous = json.loads(args.previous.read_text(encoding="utf-8"))
    payload = build_payload(report, previous)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json_out is not None:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    if args.markdown:
        sys.stdout.write(report.get("markdown") or "")
        if not str(report.get("markdown") or "").endswith("\n"):
            sys.stdout.write("\n")
    else:
        sys.stdout.write(text + "\n")
    if args.write_report:
        REPORT_PATH.write_text(report.get("markdown") or "", encoding="utf-8")
        sys.stderr.write(f"Wrote {REPORT_PATH}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
