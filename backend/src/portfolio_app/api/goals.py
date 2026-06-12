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

GOAL_TYPES = {"net_worth", "monthly_income"}

router = APIRouter(prefix="/api/goals", tags=["goals"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    target_amount_krw: float


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
