import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from portfolio_app import repositories
from portfolio_app.finance import calculate_goal_progress
from portfolio_app.models import GOAL_TYPES, Goal, GoalProgress, PortfolioSummary


@dataclass(frozen=True)
class GoalInput:
    name: str
    type: str
    target_amount_krw: float


def _goal_from_row(row: sqlite3.Row) -> Goal:
    return Goal(
        id=int(row["id"]),
        name=str(row["name"]),
        type=row["type"],
        target_amount_krw=float(row["target_amount_krw"]),
    )


def validate_goal_input(
    *,
    name: str,
    type: str,
    target_amount_krw: float,
) -> GoalInput:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("목표 이름을 입력해 주세요.")

    normalized_type = type.strip()
    if normalized_type not in GOAL_TYPES:
        raise ValueError("지원하지 않는 목표 유형입니다.")

    if not math.isfinite(target_amount_krw) or target_amount_krw <= 0:
        raise ValueError("목표 금액은 0보다 커야 합니다.")

    return GoalInput(
        name=normalized_name,
        type=normalized_type,
        target_amount_krw=target_amount_krw,
    )


def create_goal(
    db: sqlite3.Connection,
    *,
    name: str,
    type: str,
    target_amount_krw: float,
) -> Goal:
    goal = validate_goal_input(
        name=name,
        type=type,
        target_amount_krw=target_amount_krw,
    )
    row = repositories.create_goal_record(
        db,
        name=goal.name,
        type=goal.type,
        target_amount_krw=goal.target_amount_krw,
    )
    return _goal_from_row(row)


def list_goals(db: sqlite3.Connection) -> list[Goal]:
    return [_goal_from_row(row) for row in repositories.fetch_goals(db)]


def _current_amount_for_goal(summary: PortfolioSummary, goal: Goal) -> float:
    match goal.type:
        case "net_worth":
            return summary.net_worth_krw
        case "monthly_income":
            return summary.monthly_income_krw
        case _:
            raise ValueError(f"지원하지 않는 목표 유형입니다: {goal.type}")


def build_goal_progress(summary: PortfolioSummary, goals: Sequence[Goal]) -> list[GoalProgress]:
    progress_rows = []
    for goal in goals:
        current_amount = _current_amount_for_goal(summary, goal)
        progress_rows.append(calculate_goal_progress(goal, current_amount))
    return progress_rows


def list_goal_progress_for_summary(
    db: sqlite3.Connection,
    summary: PortfolioSummary,
) -> list[GoalProgress]:
    return build_goal_progress(summary, list_goals(db))
