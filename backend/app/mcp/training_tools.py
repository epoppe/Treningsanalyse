"""MCP training tools — backwards-compatible facade over app.mcp.tools."""

from __future__ import annotations

from .tools.shared import *  # noqa: F403
from .tools.shared import (  # noqa: F401 — private helpers used by tests/scripts
    _activity_pace,
    _infer_metric_unit,
    _latest_derived_metric_value,
    _parse_date,
    _resolve_activity,
    _resolve_metric_key,
    _run_query_metric_timeseries,
    coaching_backtest_summary,
    training_context,
)
