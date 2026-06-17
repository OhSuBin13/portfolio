import json
import math
import sqlite3
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_app.api.summary import build_summary
from portfolio_app.models import GrowthHistoryRow, GrowthPeriod, PortfolioSnapshot, SnapshotSource

KST = ZoneInfo("Asia/Seoul")
EXTERNAL_CONTRIBUTION_TYPES = {"deposit", "debt_payment"}
EXTERNAL_WITHDRAWAL_TYPES = {"withdrawal"}
INCOME_TYPES = {"dividend", "interest"}


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

    summary, asset_mix, _asset_allocations = build_summary(db, today=snapshot_date)
    asset_mix_json = json.dumps(asset_mix, ensure_ascii=False, sort_keys=True)

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
                summary.net_worth_krw,
                summary.gross_assets_krw,
                summary.debt_krw,
                summary.monthly_income_krw,
                asset_mix_json,
                source,
            ),
        )

    snapshot = _fetch_snapshot_by_date(db, snapshot_date)
    if snapshot is None:
        raise RuntimeError("오늘의 성장 기록 스냅샷을 찾을 수 없습니다.")
    return snapshot


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


def _period_bounds(key: str, period: GrowthPeriod) -> tuple[str, str]:
    if period == "monthly":
        start = _parse_month(key)
        if start.month == 12:
            end = date(start.year + 1, 1, 1)
        else:
            end = date(start.year, start.month + 1, 1)
        return start.isoformat(), end.isoformat()

    year = int(key)
    return date(year, 1, 1).isoformat(), date(year + 1, 1, 1).isoformat()


def _amount_to_krw(row: sqlite3.Row) -> float:
    amount = float(row["amount"] or 0)
    currency = str(row["currency"]).upper()
    if currency == "KRW" or amount == 0:
        return amount

    rate = row["fx_rate_to_krw"]
    if rate is None or not math.isfinite(float(rate)) or float(rate) <= 0:
        raise ValueError(f"{currency} 거래의 성장률 계산에 필요한 환율 정보가 없습니다.")
    return amount * float(rate)


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
        start_bound, end_bound = _period_bounds(key, period)
        external_cash_flow, dividend_interest = _period_cashflow(
            db,
            start=start_bound,
            end=end_bound,
        )
        profit = ending.net_worth_krw - starting.net_worth_krw - external_cash_flow
        growth_rate = profit / starting.net_worth_krw if starting.net_worth_krw > 0 else None

        if first_baseline is None:
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
