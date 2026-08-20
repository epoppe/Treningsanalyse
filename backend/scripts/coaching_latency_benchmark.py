#!/usr/bin/env python3
"""Latency / query-count baseline for coaching hot paths (local DB).

Usage:
  PYTHONPATH=. python scripts/coaching_latency_benchmark.py
"""

from __future__ import annotations

import statistics
import tempfile
import time
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base
from app.database.models.activity import ActivityType
from app.services.coaching_orchestrator import CoachingOrchestrator


def _percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((p / 100.0) * (len(ordered) - 1)))
    return ordered[idx]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{Path(tmp) / 'bench.db'}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        db.add(ActivityType(type_key="running", type_name="Running"))
        db.commit()

        statements = []

        def before_cursor(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", before_cursor)
        orch = CoachingOrchestrator(db, None)
        latencies = []
        query_counts = []
        for _ in range(8):
            statements.clear()
            t0 = time.perf_counter()
            orch.preview_decision(date(2026, 5, 19), detail="concise")
            latencies.append((time.perf_counter() - t0) * 1000.0)
            query_counts.append(len(statements))
        event.remove(engine, "before_cursor_execute", before_cursor)
        print(
            {
                "endpoint": "preview_decision/concise",
                "p50_ms": round(_percentile(latencies, 50), 2),
                "p95_ms": round(_percentile(latencies, 95), 2),
                "mean_ms": round(statistics.mean(latencies), 2),
                "query_count_p50": _percentile(query_counts, 50),
                "query_count_p95": _percentile(query_counts, 95),
                "note": "Baseline only — optimize after profiling.",
            }
        )
        db.close()


if __name__ == "__main__":
    main()
