import json
import math
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_app.models import GrowthHistoryRow, GrowthPeriod, PortfolioSnapshot, SnapshotSource
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


def _snapshot_from_row(row: sqlite3.Row) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        id=int(row["id"]),
        snapshot_date=date.fromisoformat(str(row["snapshot_date"])),
        net_worth_krw=float(row["net_worth_krw"]),
        gross_assets_krw=float(row["gross_assets_krw"]),
        debt_krw=float(row["debt_krw"]),
        monthly_income_krw=float(row["monthly_income_krw"]),
        asset_mix=json.loads(str(row["asset_mix_json"])),
        source=row["source"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _fetch_snapshot_by_date(
    db: sqlite3.Connection,
    snapshot_date: date,
) -> PortfolioSnapshot | None:
    row = db.execute(
        "select * from portfolio_snapshots where snapshot_date = ?",
        (snapshot_date.isoformat(),),
    ).fetchone()
    if row is None:
        return None
    return _snapshot_from_row(row)


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
        db.execute(
            """
            insert into portfolio_snapshots(
              snapshot_date, net_worth_krw, gross_assets_krw, debt_krw,
              monthly_income_krw, asset_mix_json, source
            )
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(snapshot_date)
            do update set net_worth_krw = excluded.net_worth_krw,
                          gross_assets_krw = excluded.gross_assets_krw,
                          debt_krw = excluded.debt_krw,
                          monthly_income_krw = excluded.monthly_income_krw,
                          asset_mix_json = excluded.asset_mix_json,
                          source = excluded.source,
                          updated_at = current_timestamp
            """,
            (
                snapshot_date.isoformat(),
                summary_result.summary.net_worth_krw,
                summary_result.summary.gross_assets_krw,
                summary_result.summary.debt_krw,
                summary_result.summary.monthly_income_krw,
                asset_mix_json,
                source,
            ),
        )

    snapshot = _fetch_snapshot_by_date(db, snapshot_date)
    if snapshot is None:
        raise RuntimeError("오늘의 성장 기록 스냅샷을 찾을 수 없습니다.")
    return snapshot


def create_or_refresh_market_sync_snapshot(
    db: sqlite3.Connection,
    *,
    today: date | None = None,
) -> PortfolioSnapshot:
    snapshot_date = today or today_kst()
    existing = _fetch_snapshot_by_date(db, snapshot_date)
    refresh = existing is None or existing.source in AUTO_REFRESH_SNAPSHOT_SOURCES
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
    clauses: list[str] = []
    params: list[str] = []
    if from_date is not None:
        clauses.append("snapshot_date >= ?")
        params.append(from_date.isoformat())
    if to_date is not None:
        clauses.append("snapshot_date <= ?")
        params.append(to_date.isoformat())

    where = f"where {' and '.join(clauses)}" if clauses else ""
    rows = db.execute(
        f"select * from portfolio_snapshots {where} order by snapshot_date, id",
        params,
    ).fetchall()
    return [_snapshot_from_row(row) for row in rows]


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


def _amount_to_krw(row: sqlite3.Row) -> float:
    return _amount_value_to_krw(
        amount=float(row["amount"] or 0),
        currency=str(row["currency"]),
        fx_rate_to_krw=row["fx_rate_to_krw"],
    )


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
        if cashflow.occurred_on < start or cashflow.occurred_on >= end_exclusive:
            continue

        amount_krw = _cashflow_input_to_krw(cashflow)
        if cashflow.type in EXTERNAL_CONTRIBUTION_TYPES:
            external_cash_flow += amount_krw
        elif cashflow.type in EXTERNAL_WITHDRAWAL_TYPES:
            external_cash_flow -= amount_krw
        elif cashflow.type in INCOME_TYPES:
            dividend_interest += amount_krw

    return external_cash_flow, dividend_interest


def _period_cashflow(db: sqlite3.Connection, *, start: str, end: str) -> tuple[float, float]:
    rows = db.execute(
        """
        select type, amount, currency, fx_rate_to_krw
        from transactions
        where occurred_on >= ?
          and occurred_on < ?
          and type in ('deposit', 'withdrawal', 'debt_payment', 'dividend', 'interest')
        order by occurred_on, id
        """,
        (start, end),
    ).fetchall()
    external_cash_flow = 0.0
    dividend_interest = 0.0

    for row in rows:
        amount_krw = _amount_to_krw(row)
        transaction_type = str(row["type"])
        if transaction_type in EXTERNAL_CONTRIBUTION_TYPES:
            external_cash_flow += amount_krw
        elif transaction_type in EXTERNAL_WITHDRAWAL_TYPES:
            external_cash_flow -= amount_krw
        elif transaction_type in INCOME_TYPES:
            dividend_interest += amount_krw

    return external_cash_flow, dividend_interest


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

    grouped: dict[str, list[PortfolioSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[_period_key(snapshot.snapshot_date, period)].append(snapshot)

    rows: list[GrowthHistoryRow] = []
    cumulative_profit = 0.0
    first_baseline: float | None = None

    for key in sorted(grouped):
        period_snapshots = grouped[key]
        starting = period_snapshots[0]
        ending = period_snapshots[-1]
        external_cash_flow, dividend_interest = _period_cashflow(
            db,
            start=starting.snapshot_date.isoformat(),
            end=(ending.snapshot_date + timedelta(days=1)).isoformat(),
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


def build_growth_history_from_inputs(
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
