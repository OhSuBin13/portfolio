import sqlite3
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from portfolio_app.api import get_db
from portfolio_app.models import GrowthHistoryRow, GrowthPeriod, PortfolioSnapshot, SnapshotSource
from portfolio_app.services.growth import (
    build_growth_history,
    create_or_refresh_today_snapshot,
    list_snapshots,
)

router = APIRouter(prefix="/api/growth", tags=["growth"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]
FromDateQuery = Annotated[date | None, Query(alias="from")]
ToDateQuery = Annotated[date | None, Query(alias="to")]
FromValueQuery = Annotated[str | None, Query(alias="from")]
ToValueQuery = Annotated[str | None, Query(alias="to")]


class TodaySnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: SnapshotSource = "manual"


@router.post(
    "/snapshots/today",
    response_model=PortfolioSnapshot,
    status_code=status.HTTP_201_CREATED,
)
def create_today_snapshot(db: Db, payload: TodaySnapshotRequest | None = None) -> PortfolioSnapshot:
    snapshot_request = payload or TodaySnapshotRequest()
    try:
        return create_or_refresh_today_snapshot(db, source=snapshot_request.source)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/snapshots", response_model=list[PortfolioSnapshot])
def get_snapshots(
    db: Db,
    from_date: FromDateQuery = None,
    to_date: ToDateQuery = None,
) -> list[PortfolioSnapshot]:
    return list_snapshots(db, from_date=from_date, to_date=to_date)


@router.get("/history", response_model=list[GrowthHistoryRow])
def get_growth_history(
    db: Db,
    period: GrowthPeriod,
    from_value: FromValueQuery = None,
    to_value: ToValueQuery = None,
) -> list[GrowthHistoryRow]:
    try:
        return build_growth_history(
            db,
            period=period,
            from_value=from_value,
            to_value=to_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
