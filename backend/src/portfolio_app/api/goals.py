import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from portfolio_app.api import (
    created_row,
    get_db,
    require_allowed,
    require_non_empty,
    require_positive_number,
    row_to_dict,
)
from portfolio_app.api.summary import build_summary
from portfolio_app.finance import calculate_goal_progress
from portfolio_app.models import Goal

GOAL_TYPES = {"net_worth", "monthly_income"}

router = APIRouter(prefix="/api/goals", tags=["goals"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


@router.post("", status_code=status.HTTP_201_CREATED)
def create_goal_endpoint(payload: GoalCreate, db: Db) -> dict[str, object]:
    name = require_non_empty(payload.name, "목표 이름을 입력해 주세요.")
    goal_type = require_allowed(payload.type, GOAL_TYPES, "지원하지 않는 목표 유형입니다.")
    target_amount_krw = require_positive_number(
        payload.target_amount_krw,
        "목표 금액은 0보다 커야 합니다.",
    )

    try:
        cursor = db.execute(
            "insert into goals(name, type, target_amount_krw) values (?, ?, ?)",
            (name, goal_type, target_amount_krw),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="목표 정보를 저장할 수 없습니다.",
        ) from exc

    return created_row(db, "goals", int(cursor.lastrowid))


@router.get("")
def list_goals(db: Db) -> list[dict[str, object]]:
    rows = db.execute("select * from goals order by id").fetchall()
    return [row_to_dict(row) for row in rows]


@router.get("/progress")
def list_goal_progress(db: Db) -> list[dict[str, object]]:
    summary, _asset_mix, _asset_allocations = build_summary(db)
    rows = db.execute("select * from goals order by id").fetchall()
    progress_rows = []
    for row in rows:
        goal = _goal_from_row(row)
        current_amount = (
            summary.net_worth_krw if goal.type == "net_worth" else summary.monthly_income_krw
        )
        progress_rows.append(calculate_goal_progress(goal, current_amount).model_dump())
    return progress_rows
