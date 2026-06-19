import sqlite3
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from portfolio_app.api import (
    get_db,
    require_allowed,
    require_non_empty,
    require_positive_number,
)
from portfolio_app.models import GOAL_TYPES, Goal, GoalProgress
from portfolio_app.services import goals as goal_service

router = APIRouter(prefix="/api/goals", tags=["goals"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    target_amount_krw: float


@dataclass(frozen=True)
class ValidatedGoalPayload:
    name: str
    type: str
    target_amount_krw: float


def validate_goal_payload(payload: GoalCreate) -> ValidatedGoalPayload:
    name = require_non_empty(payload.name, "목표 이름을 입력해 주세요.")
    goal_type = require_allowed(payload.type, GOAL_TYPES, "지원하지 않는 목표 유형입니다.")
    target_amount_krw = require_positive_number(
        payload.target_amount_krw,
        "목표 금액은 0보다 커야 합니다.",
    )
    return ValidatedGoalPayload(
        name=name,
        type=goal_type,
        target_amount_krw=target_amount_krw,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Goal)
def create_goal_endpoint(payload: GoalCreate, db: Db) -> Goal:
    goal = validate_goal_payload(payload)

    try:
        return goal_service.create_goal(
            db,
            name=goal.name,
            type=goal.type,
            target_amount_krw=goal.target_amount_krw,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="목표 정보를 저장할 수 없습니다.",
        ) from exc


@router.get("", response_model=list[Goal])
def list_goals(db: Db) -> list[Goal]:
    return goal_service.list_goals(db)


@router.get("/progress", response_model=list[GoalProgress])
def list_goal_progress(db: Db) -> list[GoalProgress]:
    try:
        return goal_service.list_goal_progress(db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
