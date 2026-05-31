#!/usr/bin/env python3
"""Skriv METRIC_QUALITY_REPORT.md fra metric_quality_report()."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.mcp.training_tools import metric_quality_report  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[2] / "METRIC_QUALITY_REPORT.md"


def main() -> None:
    report = metric_quality_report(markdown=True)
    OUTPUT.write_text(report["markdown"], encoding="utf-8")
    summary = report["summary"]
    print(
        f"Wrote {OUTPUT} — ok={summary['ok']}/{summary['total']}, "
        f"no_data={summary['no_data']}, bug={summary['bug']}"
    )


if __name__ == "__main__":
    main()
