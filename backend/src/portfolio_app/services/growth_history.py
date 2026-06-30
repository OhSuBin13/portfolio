from collections.abc import Iterable
from dataclasses import dataclass
from itertools import groupby
from operator import attrgetter

from portfolio_app.models import GrowthAnnualHistoryRow, GrowthMonthHistoryRow


@dataclass(frozen=True)
class GrowthMonthInput:
    account_seq: str
    year: int
    month: int
    net_worth_krw: float
    monthly_dividend_krw: float
    created_at: str = ""
    updated_at: str = ""


def build_month_history(rows: Iterable[GrowthMonthInput]) -> list[GrowthMonthHistoryRow]:
    sorted_rows = _normalized_rows(rows)
    history: list[GrowthMonthHistoryRow] = []

    for account_seq, account_rows in groupby(sorted_rows, key=attrgetter("account_seq")):
        previous: GrowthMonthInput | None = None
        cumulative_dividend = 0.0
        return_sum = 0.0
        return_count = 0

        for row in account_rows:
            monthly_return_ratio = _return_ratio_for_adjacent_month(row, previous)
            if monthly_return_ratio is not None:
                return_sum += monthly_return_ratio
                return_count += 1
            cumulative_dividend += row.monthly_dividend_krw

            history.append(
                GrowthMonthHistoryRow(
                    account_seq=account_seq,
                    year=row.year,
                    month=row.month,
                    net_worth_krw=float(row.net_worth_krw),
                    monthly_dividend_krw=float(row.monthly_dividend_krw),
                    monthly_return_ratio=monthly_return_ratio,
                    average_return_ratio=_average(return_sum, return_count),
                    cumulative_dividend_krw=cumulative_dividend,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
            previous = row

    return history


def build_annual_history(
    rows: Iterable[GrowthMonthInput],
    *,
    sp500_annual_return_ratios: dict[int, float] | None = None,
    current_year: int | None = None,
) -> list[GrowthAnnualHistoryRow]:
    latest_months = _latest_months_by_year(_normalized_rows(rows))
    history: list[GrowthAnnualHistoryRow] = []
    proxy_ratios = sp500_annual_return_ratios or {}

    for account_seq, account_rows in groupby(latest_months, key=attrgetter("account_seq")):
        previous: GrowthMonthInput | None = None
        return_sum = 0.0
        return_count = 0

        for row in account_rows:
            annual_return_ratio = _return_ratio_for_adjacent_year(row, previous)
            sp500_annual_return_ratio = (
                None
                if current_year is not None and row.year >= current_year
                else proxy_ratios.get(row.year)
            )
            if annual_return_ratio is not None:
                return_sum += annual_return_ratio
                return_count += 1

            history.append(
                GrowthAnnualHistoryRow(
                    account_seq=account_seq,
                    year=row.year,
                    display_year=f"{row.year % 100:02d}",
                    source_month=row.month,
                    net_worth_krw=float(row.net_worth_krw),
                    annual_return_ratio=annual_return_ratio,
                    average_return_ratio=_average(return_sum, return_count),
                    sp500_annual_return_ratio=sp500_annual_return_ratio,
                )
            )
            previous = row

    return history


def _normalized_rows(rows: Iterable[GrowthMonthInput]) -> list[GrowthMonthInput]:
    sorted_rows = sorted(rows, key=attrgetter("account_seq", "year", "month"))
    previous_key: tuple[str, int, int] | None = None
    for row in sorted_rows:
        key = (row.account_seq, row.year, row.month)
        if key == previous_key:
            raise ValueError(
                f"Duplicate growth month input: {row.account_seq} {row.year}-{row.month:02d}"
            )
        previous_key = key
    return sorted_rows


def _latest_months_by_year(rows: Iterable[GrowthMonthInput]) -> list[GrowthMonthInput]:
    latest: dict[tuple[str, int], GrowthMonthInput] = {}
    for row in rows:
        key = (row.account_seq, row.year)
        current = latest.get(key)
        if current is None or row.month >= current.month:
            latest[key] = row
    return sorted(latest.values(), key=attrgetter("account_seq", "year"))


def _return_ratio_for_adjacent_month(
    current: GrowthMonthInput,
    previous: GrowthMonthInput | None,
) -> float | None:
    if previous is None or previous.net_worth_krw == 0:
        return None
    if (previous.year, previous.month) != _previous_calendar_month(current):
        return None
    return current.net_worth_krw / previous.net_worth_krw


def _return_ratio_for_adjacent_year(
    current: GrowthMonthInput,
    previous: GrowthMonthInput | None,
) -> float | None:
    if previous is None or previous.net_worth_krw == 0:
        return None
    if previous.year != current.year - 1:
        return None
    return current.net_worth_krw / previous.net_worth_krw


def _previous_calendar_month(row: GrowthMonthInput) -> tuple[int, int]:
    if row.month == 1:
        return row.year - 1, 12
    return row.year, row.month - 1


def _average(total: float, count: int) -> float | None:
    if count == 0:
        return None
    return total / count
