import json
import math
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_app.models import GrowthHistoryRow, GrowthPeriod, PortfolioSnapshot, SnapshotSource
from portfolio_app.repositories import (
    GrowthCashflowRow,
    GrowthSnapshotRow,
    fetch_growth_cashflow_rows,
    fetch_growth_snapshot_by_date,
    fetch_growth_snapshots,
    upsert_portfolio_snapshot,
)
from portfolio_app.services.summary import build_summary

KST = ZoneInfo("Asia/Seoul")
EXTERNAL_CONTRIBUTION_TYPES = {"deposit", "debt_payment"}
EXTERNAL_WITHDRAWAL_TYPES = {"withdrawal"}
INCOME_TYPES = {"dividend", "interest"}
AUTO_REFRESH_SNAPSHOT_SOURCES = {"market_sync", "scheduled"}


@dataclass(frozen=True)
class GrowthSnapshotInput:
    snapshot_date: date
    net_worth_krw: float


@dataclass(frozen=True)
class GrowthCashflowInput:
    occurred_on: date
    type: str
    amount: float
    currency: str
    fx_rate_to_krw: float | None


def today_kst(now: datetime | None = None) -> date:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(KST).date()


def _snapshot_from_record(row: GrowthSnapshotRow) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        id=row.id,
        snapshot_date=row.snapshot_date,
        net_worth_krw=row.net_worth_krw,
        gross_assets_krw=row.gross_assets_krw,
        debt_krw=row.debt_krw,
        monthly_income_krw=row.monthly_income_krw,
        asset_mix=json.loads(row.asset_mix_json),
        source=row.source,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _fetch_snapshot_by_date(
    db: sqlite3.Connection,
    snapshot_date: date,
) -> PortfolioSnapshot | None:
    row = fetch_growth_snapshot_by_date(db, snapshot_date=snapshot_date)
    if row is None:
        return None
    return _snapshot_from_record(row)


def create_or_refresh_today_snapshot(
    db: sqlite3.Connection,
    *,
    source: SnapshotSource = "manual",
    today: date | None = None,
    refresh: bool = True,
) -> PortfolioSnapshot:
    snapshot_date = today or today_kst()
    existing = _fetch_snapshot_by_date(db, snapshot_date)
    if existing is not None and not refresh:
        return existing

    summary_result = build_summary(db, today=snapshot_date)
    asset_mix_json = json.dumps(summary_result.asset_mix, ensure_ascii=False, sort_keys=True)

    with db:
        upsert_portfolio_snapshot(
            db,
            snapshot_date=snapshot_date,
            net_worth_krw=summary_result.summary.net_worth_krw,
            gross_assets_krw=summary_result.summary.gross_assets_krw,
            debt_krw=summary_result.summary.debt_krw,
            monthly_income_krw=summary_result.summary.monthly_income_krw,
            asset_mix_json=asset_mix_json,
            source=source,
        )

    snapshot = _fetch_snapshot_by_date(db, snapshot_date)
    if snapshot is None:
        raise RuntimeError("오늘의 성장 기록 스냅샷을 찾을 수 없습니다.")
    return snapshot


def should_refresh_market_sync_snapshot(existing_source: SnapshotSource | None) -> bool:
    return existing_source is None or existing_source in AUTO_REFRESH_SNAPSHOT_SOURCES


def create_or_refresh_market_sync_snapshot(
    db: sqlite3.Connection,
    *,
    today: date | None = None,
) -> PortfolioSnapshot:
    snapshot_date = today or today_kst()
    existing = _fetch_snapshot_by_date(db, snapshot_date)
    refresh = should_refresh_market_sync_snapshot(existing.source if existing else None)
    return create_or_refresh_today_snapshot(
        db,
        source="market_sync",
        today=snapshot_date,
        refresh=refresh,
    )


def list_snapshots(
    db: sqlite3.Connection,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[PortfolioSnapshot]:
    rows = fetch_growth_snapshots(db, from_date=from_date, to_date=to_date)
    return [_snapshot_from_record(row) for row in rows]


def _parse_month(value: str) -> date:
    return date.fromisoformat(f"{value}-01")


def _parse_period_start(period: GrowthPeriod, value: str | None) -> date | None:
    if value is None:
        return None
    if period == "monthly":
        return _parse_month(value)
    return date(int(value), 1, 1)


def _parse_period_end(period: GrowthPeriod, value: str | None) -> date | None:
    if value is None:
        return None
    if period == "monthly":
        start = _parse_month(value)
        if start.month == 12:
            next_month = date(start.year + 1, 1, 1)
        else:
            next_month = date(start.year, start.month + 1, 1)
        return next_month - timedelta(days=1)
    return date(int(value), 12, 31)


def _period_key(snapshot_date: date, period: GrowthPeriod) -> str:
    if period == "monthly":
        return snapshot_date.strftime("%Y-%m")
    return snapshot_date.strftime("%Y")


def _amount_value_to_krw(
    *,
    amount: float,
    currency: str,
    fx_rate_to_krw: float | None,
) -> float:
    currency = currency.upper()
    if currency == "KRW" or amount == 0:
        return amount

    if (
        fx_rate_to_krw is None
        or not math.isfinite(float(fx_rate_to_krw))
        or float(fx_rate_to_krw) <= 0
    ):
        raise ValueError(f"{currency} 거래의 성장률 계산에 필요한 환율 정보가 없습니다.")
    return amount * float(fx_rate_to_krw)


def _cashflow_input_to_krw(cashflow: GrowthCashflowInput) -> float:
    return _amount_value_to_krw(
        amount=float(cashflow.amount or 0),
        currency=cashflow.currency,
        fx_rate_to_krw=cashflow.fx_rate_to_krw,
    )


def _period_cashflow_from_inputs(
    cashflows: Sequence[GrowthCashflowInput],
    *,
    start: date,
    end_exclusive: date,
) -> tuple[float, float]:
    external_cash_flow = 0.0
    dividend_interest = 0.0

    for cashflow in cashflows:
        if cashflow.occurred_on <= start or cashflow.occurred_on >= end_exclusive:
            continue

        amount_krw = _cashflow_input_to_krw(cashflow)
        if cashflow.type in EXTERNAL_CONTRIBUTION_TYPES:
            external_cash_flow += amount_krw
        elif cashflow.type in EXTERNAL_WITHDRAWAL_TYPES:
            external_cash_flow -= amount_krw
        elif cashflow.type in INCOME_TYPES:
            dividend_interest += amount_krw

    return external_cash_flow, dividend_interest


def _cashflow_row_to_input(row: GrowthCashflowRow) -> GrowthCashflowInput:
    return GrowthCashflowInput(
        occurred_on=row.occurred_on,
        type=row.type,
        amount=row.amount,
        currency=row.currency,
        fx_rate_to_krw=row.fx_rate_to_krw,
    )


def _assemble_growth_history_rows(
    *,
    snapshots: Sequence[GrowthSnapshotInput],
    cashflows: Sequence[GrowthCashflowInput],
    period: GrowthPeriod,
    from_value: str | None = None,
    to_value: str | None = None,
) -> list[GrowthHistoryRow]:
    from_date = _parse_period_start(period, from_value)
    to_date = _parse_period_end(period, to_value)
    filtered_snapshots = [
        snapshot
        for snapshot in sorted(snapshots, key=lambda item: item.snapshot_date)
        if (from_date is None or snapshot.snapshot_date >= from_date)
        and (to_date is None or snapshot.snapshot_date <= to_date)
    ]

    grouped: dict[str, list[GrowthSnapshotInput]] = defaultdict(list)
    for snapshot in filtered_snapshots:
        grouped[_period_key(snapshot.snapshot_date, period)].append(snapshot)

    rows: list[GrowthHistoryRow] = []
    cumulative_profit = 0.0
    first_baseline: float | None = None

    for key in sorted(grouped):
        period_snapshots = grouped[key]
        starting = period_snapshots[0]
        ending = period_snapshots[-1]
        external_cash_flow, dividend_interest = _period_cashflow_from_inputs(
            cashflows,
            start=starting.snapshot_date,
            end_exclusive=ending.snapshot_date + timedelta(days=1),
        )
        profit = ending.net_worth_krw - starting.net_worth_krw - external_cash_flow
        growth_rate = profit / starting.net_worth_krw if starting.net_worth_krw > 0 else None

        if not rows:
            first_baseline = starting.net_worth_krw if starting.net_worth_krw > 0 else None
        cumulative_profit += profit
        cumulative_growth_rate = (
            cumulative_profit / first_baseline
            if first_baseline is not None and first_baseline > 0
            else None
        )

        rows.append(
            GrowthHistoryRow(
                period=key,
                start_date=starting.snapshot_date,
                end_date=ending.snapshot_date,
                starting_net_worth_krw=starting.net_worth_krw,
                ending_net_worth_krw=ending.net_worth_krw,
                external_cash_flow_krw=external_cash_flow,
                dividend_interest_krw=dividend_interest,
                profit_krw=profit,
                growth_rate=growth_rate,
                cumulative_profit_krw=cumulative_profit,
                cumulative_growth_rate=cumulative_growth_rate,
            )
        )

    return rows


def _snapshot_to_input(snapshot: PortfolioSnapshot) -> GrowthSnapshotInput:
    return GrowthSnapshotInput(
        snapshot_date=snapshot.snapshot_date,
        net_worth_krw=snapshot.net_worth_krw,
    )


def _fetch_growth_cashflow_inputs(
    db: sqlite3.Connection,
    *,
    start: date,
    end_exclusive: date,
) -> list[GrowthCashflowInput]:
    rows = fetch_growth_cashflow_rows(db, start=start, end_exclusive=end_exclusive)
    return [_cashflow_row_to_input(row) for row in rows]


def build_growth_history(
    db: sqlite3.Connection,
    *,
    period: GrowthPeriod,
    from_value: str | None = None,
    to_value: str | None = None,
) -> list[GrowthHistoryRow]:
    from_date = _parse_period_start(period, from_value)
    to_date = _parse_period_end(period, to_value)
    snapshots = list_snapshots(db, from_date=from_date, to_date=to_date)
    snapshot_inputs = [_snapshot_to_input(snapshot) for snapshot in snapshots]
    if not snapshot_inputs:
        return []

    cashflow_inputs = _fetch_growth_cashflow_inputs(
        db,
        start=snapshot_inputs[0].snapshot_date,
        end_exclusive=snapshot_inputs[-1].snapshot_date + timedelta(days=1),
    )
    return _assemble_growth_history_rows(
        snapshots=snapshot_inputs,
        cashflows=cashflow_inputs,
        period=period,
        from_value=from_value,
        to_value=to_value,
    )


def build_growth_history_from_inputs(
    *,
    snapshots: Sequence[GrowthSnapshotInput],
    cashflows: Sequence[GrowthCashflowInput],
    period: GrowthPeriod,
    from_value: str | None = None,
    to_value: str | None = None,
) -> list[GrowthHistoryRow]:
    return _assemble_growth_history_rows(
        snapshots=snapshots,
        cashflows=cashflows,
        period=period,
        from_value=from_value,
        to_value=to_value,
    )
