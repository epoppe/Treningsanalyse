"""SQLAlchemy query-count budget for coaching hot paths."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, List, Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


class QueryBudgetExceeded(AssertionError):
    pass


@contextmanager
def assert_query_budget(
    db: Session,
    *,
    max_queries: int,
    label: str = "coaching",
) -> Iterator[List[str]]:
    """Count SQL statements executed on this session's bind during the block."""
    bind = db.get_bind()
    if not isinstance(bind, Engine):
        bind = bind.engine  # type: ignore[attr-defined]
    statements: List[str] = []

    def _before_cursor(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(str(statement))

    event.listen(bind, "before_cursor_execute", _before_cursor)
    try:
        yield statements
        if len(statements) > max_queries:
            raise QueryBudgetExceeded(
                f"{label}: {len(statements)} queries exceeded budget {max_queries}. "
                f"Sample: {statements[:5]}"
            )
    finally:
        event.remove(bind, "before_cursor_execute", _before_cursor)


def count_queries(db: Session) -> contextmanager:
    """Alias factory for profiling without assertion."""

    @contextmanager
    def _cm() -> Iterator[List[str]]:
        with assert_query_budget(db, max_queries=10_000, label="profile") as stmts:
            yield stmts

    return _cm()
