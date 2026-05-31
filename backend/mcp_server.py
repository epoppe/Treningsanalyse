"""MCP stdio server for Treningsanalyse.

Run from backend:
    python mcp_server.py

Cursor/Claude-style config example:
    {
      "mcpServers": {
        "treningsanalyse": {
          "command": "/path/to/backend/.venv/bin/python",
          "args": ["/path/to/backend/mcp_server.py"]
        }
      }
    }
"""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised only when dependency missing
    raise SystemExit(
        "MCP SDK mangler. Installer backend requirements først: "
        "cd backend && .venv/bin/pip install -r requirements.txt"
    ) from exc

from app.mcp import training_tools


mcp = FastMCP("treningsanalyse")


def _call_tool(fn, *args, **kwargs):
    # Data loading and cache fallbacks can print diagnostics. MCP stdio reserves
    # stdout for JSON-RPC, so route incidental output to stderr during tool calls.
    with redirect_stdout(sys.stderr):
        return fn(*args, **kwargs)


@mcp.resource("treningsanalyse://athlete-profile")
def athlete_profile_resource() -> str:
    """Stable athlete profile, thresholds, latest performance metrics and data inventory."""
    return json.dumps(_call_tool(training_tools.athlete_profile), ensure_ascii=False, indent=2)


@mcp.resource("treningsanalyse://coaching-snapshot")
def coaching_snapshot_resource() -> str:
    """Latest persisted coaching snapshot, if one has been calculated."""
    return json.dumps(_call_tool(training_tools.coaching_snapshot), ensure_ascii=False, indent=2)


@mcp.resource("treningsanalyse://metric-glossary")
def metric_glossary_resource() -> str:
    """Coaching glossary: how to interpret every MCP metric."""
    return json.dumps(_call_tool(training_tools.metric_glossary), ensure_ascii=False, indent=2)


@mcp.tool()
def athlete_profile() -> dict:
    """Return stable athlete context: units, latest thresholds, VO2max, HRV and data inventory."""
    return _call_tool(training_tools.athlete_profile)


@mcp.tool()
def analyze_recent_training(days: int = 90, include_treadmill: bool = False) -> dict:
    """Analyze recent training with Banister fitness/fatigue, polarized distribution, thresholds and HRV guidance."""
    return _call_tool(training_tools.analyze_recent_training, days=days, include_treadmill=include_treadmill)


@mcp.tool()
def training_readiness_check(target_date: Optional[str] = None) -> dict:
    """Check if hard training is sensible on target_date (YYYY-MM-DD) using load, HRV, sleep and fatigue flags."""
    return _call_tool(training_tools.training_readiness_check, target_date=target_date)


@mcp.tool()
def list_recent_activities(limit: int = 10, activity_type: Optional[str] = None) -> dict:
    """List compact recent activities with explicit dates, day-of-week, pace, HR and load."""
    return _call_tool(training_tools.list_recent_activities, limit=limit, activity_type=activity_type)


@mcp.tool()
def activity_deep_dive(activity_id: Optional[str] = None) -> dict:
    """Deep dive into one activity, defaulting to latest activity, with physiology and kilometer splits."""
    return _call_tool(training_tools.activity_deep_dive, activity_id=activity_id)


@mcp.tool()
def route_comparison(activity_id: Optional[str] = None, limit: int = 10) -> dict:
    """Compare an activity, defaulting to latest run, with historical same-route matches."""
    return _call_tool(training_tools.route_comparison, activity_id=activity_id, limit=limit)


@mcp.tool()
def compare_recent_runs(limit: int = 5, same_route_as_latest: bool = False) -> dict:
    """Compare recent runs, optionally restricted to same route as the latest run."""
    return _call_tool(training_tools.compare_recent_runs, limit=limit, same_route_as_latest=same_route_as_latest)


@mcp.tool()
def metric_catalog() -> dict:
    """List whitelisted metrics that can be queried through MCP timeseries."""
    return _call_tool(training_tools.metric_catalog)


@mcp.tool()
def metric_glossary(
    metric_key: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> dict:
    """Return how to interpret metrics for precise coaching."""
    return _call_tool(
        training_tools.metric_glossary,
        metric_key=metric_key,
        category=category,
        search=search,
    )


@mcp.tool()
def coaching_decision_snapshot(target_date: Optional[str] = None) -> dict:
    """Training decision metrics: consistency, event readiness, limiters, recommended workout."""
    return _call_tool(training_tools.coaching_decision_snapshot, target_date=target_date)


@mcp.tool()
def query_metric_timeseries(
    metric_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 365,
) -> dict:
    """Query one whitelisted metric as a compact dated time series. Dates use YYYY-MM-DD."""
    return _call_tool(
        training_tools.query_metric_timeseries,
        metric_key=metric_key,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@mcp.tool()
def metric_quality_report(
    target_date: Optional[str] = None,
    lookback_days: int = 14,
    markdown: bool = False,
) -> dict:
    """Quality report for all catalog metrics: ok / no_data / bug, latest value, date, heuristic flag."""
    return _call_tool(
        training_tools.metric_quality_report,
        target_date=target_date,
        lookback_days=lookback_days,
        markdown=markdown,
    )


@mcp.prompt()
def training_readiness_prompt(target_date: Optional[str] = None) -> str:
    return (
        "Use treningsanalyse tools to assess whether Erik should train hard today. "
        f"Target date: {target_date or 'today'}. "
        "Call training_readiness_check first, then athlete_profile if threshold context is needed. "
        "Answer in Norwegian with a concrete recommendation: hard / moderate / easy / rest, and why."
    )


@mcp.prompt()
def recent_training_prompt(days: int = 90) -> str:
    return (
        f"Analyze Erik's last {days} days of training. "
        "Call analyze_recent_training and athlete_profile. Focus on Banister fitness/fatigue, "
        "80/20 intensity distribution, threshold density, HRV readiness and the next practical adjustment. "
        "Answer in Norwegian."
    )


@mcp.prompt()
def same_route_comparison_prompt(activity_id: Optional[str] = None) -> str:
    return (
        "Compare a run with historical runs on the same route. "
        f"Activity id: {activity_id or 'latest run'}. "
        "Call route_comparison, then activity_deep_dive if split detail is needed. "
        "Answer in Norwegian with pace, HR and performance context."
    )


if __name__ == "__main__":
    try:
        mcp.run()
    except BrokenPipeError:  # pragma: no cover - common when an MCP client disconnects
        sys.exit(0)
