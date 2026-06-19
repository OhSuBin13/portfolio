import sqlite3
from collections.abc import Sequence

from portfolio_app import repositories
from portfolio_app.finance import calculate_goal_progress
from portfolio_app.models import Goal, GoalProgress, PortfolioSummary
from portfolio_app.services.summary import build_summary


def _goal_from_row(row: sqlite3.Row) -> Goal:
    return Goal(
        id=int(row["id"]),
        name=str(row["name"]),
        type=row["type"],
        target_amount_krw=float(row["target_amount_krw"]),
    )


def create_goal(
    db: sqlite3.Connection,
    *,
    name: str,
    type: str,
    target_amount_krw: float,
) -> Goal:
    row = repositories.create_goal_record(
        db,
        name=name,
        type=type,
        target_amount_krw=target_amount_krw,
    )
    return _goal_from_row(row)


def list_goals(db: sqlite3.Connection) -> list[Goal]:
    return [_goal_from_row(row) for row in repositories.fetch_goals(db)]


def build_goal_progress(summary: PortfolioSummary, goals: Sequence[Goal]) -> list[GoalProgress]:
    progress_rows = []
    for goal in goals:
        current_amount = (
            summary.net_worth_krw if goal.type == "net_worth" else summary.monthly_income_krw
        )
        progress_rows.append(calculate_goal_progress(goal, current_amount))
    return progress_rows


def list_goal_progress(db: sqlite3.Connection) -> list[GoalProgress]:
    result = build_summary(db)
    return build_goal_progress(result.summary, list_goals(db))
