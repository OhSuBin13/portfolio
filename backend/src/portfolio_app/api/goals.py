import sqlite3
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from portfolio_app.api.dependencies import Db
from portfolio_app.models import Goal, GoalType
from portfolio_app.services import goals as goal_service

router = APIRouter(prefix="/api/goals", tags=["goals"])


def _strip_string(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


GoalTypeInput = Annotated[GoalType, BeforeValidator(_strip_string)]
GoalTargetAmountKrw = Annotated[float, Field(gt=0, strict=True, allow_inf_nan=False)]


class GoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: GoalTypeInput
    target_amount_krw: GoalTargetAmountKrw


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Goal)
def create_goal_endpoint(payload: GoalCreate, db: Db) -> Goal:
    try:
        return goal_service.create_goal(
            db,
            name=payload.name,
            type=payload.type,
            target_amount_krw=payload.target_amount_krw,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="목표 정보를 저장할 수 없습니다.",
        ) from exc


@router.get("", response_model=list[Goal])
def list_goals(db: Db) -> list[Goal]:
    return goal_service.list_goals(db)
