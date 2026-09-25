#!/usr/bin/env python3
"""Overwrite METRIC_QUALITY_REPORT.md from the current database.

Prefer `python -m app.tools.metric_quality` when you only want the summary.
This script still writes the markdown file, and only when asked:

    python scripts/generate_metric_quality_report.py --write-report
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.tools.metric_quality import main  # noqa: E402


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--write-report" not in argv:
        sys.stderr.write(
            "Refusing to overwrite METRIC_QUALITY_REPORT.md without --write-report.\n"
            "Print a summary with: python -m app.tools.metric_quality\n"
        )
        raise SystemExit(2)
    raise SystemExit(main(argv))
