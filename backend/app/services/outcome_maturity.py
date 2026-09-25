"""Maturity windows for prospective coaching outcomes.

Pending windows are not failures. Missing markers inside a closed window are
incomplete data, not negative physiology.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

# Execution can be judged once the recommendation's calendar day has ended.
EXECUTION_LAG_DAYS = 1
# Next-day HRV/RHR needs the following day to have occurred (24–48h).
SHORT_TERM_LAG_DAYS = 2
# Medium-term utility reads markers out to +21 days.
MEDIUM_TERM_LAG_DAYS = 21

PENDING = "pending"
MATURE = "mature"
INCOMPLETE_DATA = "incomplete_data"
EVALUATED = "evaluated"


def window_closed(as_of: date, today: date, lag_days: int) -> bool:
    return today >= as_of + timedelta(days=lag_days)


def maturity_for_window(
    as_of: date,
    today: date,
    lag_days: int,
    *,
    has_value: bool,
) -> str:
    """pending while the window is open; evaluated or incomplete once it closes."""
    if not window_closed(as_of, today, lag_days):
        return PENDING
    if has_value:
        return EVALUATED
    return INCOMPLETE_DATA


def execution_maturity(as_of: date, today: date, *, has_outcome: bool) -> str:
    return maturity_for_window(as_of, today, EXECUTION_LAG_DAYS, has_value=has_outcome)


def short_term_maturity(as_of: date, today: date, *, has_value: bool) -> str:
    return maturity_for_window(as_of, today, SHORT_TERM_LAG_DAYS, has_value=has_value)


def medium_term_maturity(as_of: date, today: date, *, has_value: bool) -> str:
    return maturity_for_window(as_of, today, MEDIUM_TERM_LAG_DAYS, has_value=has_value)


def is_usable_status(status: Optional[str]) -> bool:
    """Only evaluated observations belong in a metric denominator."""
    return status == EVALUATED
