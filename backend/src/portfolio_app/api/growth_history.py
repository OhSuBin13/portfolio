import sqlite3
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field

from portfolio_app.api.dependencies import Db
from portfolio_app.api.validation import normalize_account_seq
from portfolio_app.models import (
    GrowthAnnualHistoryRow,
    GrowthMonthHistoryRow,
    Sp500ProxyPriceRow,
)
from portfolio_app.repositories import (
    delete_growth_month_history,
    fetch_growth_month_history_rows,
    fetch_sp500_proxy_annual_return_ratios,
    fetch_sp500_proxy_prices,
    upsert_growth_month_history,
    upsert_sp500_proxy_price,
)
from portfolio_app.services.growth_history import (
    GrowthMonthInput,
    build_annual_history,
    build_month_history,
)

router = APIRouter(prefix="/api/growth", tags=["growth"])
AccountSeq = Annotated[str, Query(min_length=1)]
YearPath = Annotated[int, Path(ge=2000, le=2099)]
MonthPath = Annotated[int, Path(ge=1, le=12)]


class GrowthMonthHistoryUpsert(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    net_worth_krw: float = Field(ge=0, allow_inf_nan=False)
    monthly_dividend_krw: float = Field(ge=0, allow_inf_nan=False)


class Sp500ProxyPriceUpsert(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    price: float = Field(gt=0, allow_inf_nan=False)


def _month_input_from_row(row: sqlite3.Row) -> GrowthMonthInput:
    return GrowthMonthInput(
        account_seq=str(row["account_seq"]),
        year=int(row["year"]),
        month=int(row["month"]),
        net_worth_krw=float(row["net_worth_krw"]),
        monthly_dividend_krw=float(row["monthly_dividend_krw"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _month_inputs_for_account(
    db: sqlite3.Connection,
    *,
    account_seq: str,
) -> list[GrowthMonthInput]:
    rows = fetch_growth_month_history_rows(db, account_seq=account_seq)
    return [_month_input_from_row(row) for row in rows]


def _build_month_history(
    rows: list[GrowthMonthInput],
) -> list[GrowthMonthHistoryRow]:
    try:
        return build_month_history(rows)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def _build_annual_history(
    rows: list[GrowthMonthInput],
    *,
    sp500_annual_return_ratios: dict[int, float] | None = None,
    current_year: int | None = None,
) -> list[GrowthAnnualHistoryRow]:
    try:
        return build_annual_history(
            rows,
            sp500_annual_return_ratios=sp500_annual_return_ratios,
            current_year=current_year,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def _sp500_proxy_price_from_row(row: sqlite3.Row) -> Sp500ProxyPriceRow:
    return Sp500ProxyPriceRow(
        year=int(row["year"]),
        proxy_symbol=str(row["proxy_symbol"]),
        price=float(row["price"]),
        currency=str(row["currency"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


@router.put("/month-history/{year}/{month}", response_model=GrowthMonthHistoryRow)
def upsert_growth_month_history_endpoint(
    payload: GrowthMonthHistoryUpsert,
    db: Db,
    year: YearPath,
    month: MonthPath,
    account_seq: AccountSeq,
) -> GrowthMonthHistoryRow:
    normalized_account_seq = normalize_account_seq(account_seq)
    upsert_growth_month_history(
        db,
        account_seq=normalized_account_seq,
        year=year,
        month=month,
        net_worth_krw=payload.net_worth_krw,
        monthly_dividend_krw=payload.monthly_dividend_krw,
    )
    history = _build_month_history(
        _month_inputs_for_account(db, account_seq=normalized_account_seq)
    )
    for row in history:
        if row.year == year and row.month == month:
            return row
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="저장된 월간 성장 기록을 찾을 수 없습니다.",
    )


@router.delete(
    "/month-history/{year}/{month}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_growth_month_history_endpoint(
    db: Db,
    year: YearPath,
    month: MonthPath,
    account_seq: AccountSeq,
) -> None:
    normalized_account_seq = normalize_account_seq(account_seq)
    deleted = delete_growth_month_history(
        db,
        account_seq=normalized_account_seq,
        year=year,
        month=month,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="삭제할 월간 성장 기록을 찾을 수 없습니다.",
        )


@router.get("/month-history", response_model=list[GrowthMonthHistoryRow])
def list_growth_month_history(
    db: Db,
    account_seq: AccountSeq,
) -> list[GrowthMonthHistoryRow]:
    normalized_account_seq = normalize_account_seq(account_seq)
    return _build_month_history(
        _month_inputs_for_account(db, account_seq=normalized_account_seq)
    )


@router.get("/sp500-proxy-prices", response_model=list[Sp500ProxyPriceRow])
def list_sp500_proxy_prices(db: Db) -> list[Sp500ProxyPriceRow]:
    return [_sp500_proxy_price_from_row(row) for row in fetch_sp500_proxy_prices(db)]


@router.put("/sp500-proxy-prices/{year}", response_model=Sp500ProxyPriceRow)
def upsert_sp500_proxy_price_endpoint(
    payload: Sp500ProxyPriceUpsert,
    db: Db,
    year: YearPath,
) -> Sp500ProxyPriceRow:
    row = upsert_sp500_proxy_price(db, year=year, price=payload.price)
    return _sp500_proxy_price_from_row(row)


@router.get("/annual-history", response_model=list[GrowthAnnualHistoryRow])
def list_growth_annual_history(
    db: Db,
    account_seq: AccountSeq,
) -> list[GrowthAnnualHistoryRow]:
    normalized_account_seq = normalize_account_seq(account_seq)
    month_inputs = _month_inputs_for_account(db, account_seq=normalized_account_seq)
    current_year = date.today().year
    sp500_annual_return_ratios = fetch_sp500_proxy_annual_return_ratios(
        db,
        years=[row.year for row in month_inputs],
        current_year=current_year,
    )
    return _build_annual_history(
        month_inputs,
        sp500_annual_return_ratios=sp500_annual_return_ratios,
        current_year=current_year,
    )
