import csv
import io
import math
import re
from dataclasses import dataclass

ASSET_TYPE_MAP = {
    "현금": "cash",
    "적금": "savings",
    "주식": "stock_etf",
    "ETF": "stock_etf",
    "부채": "debt",
}

FORMULA_ERRORS = {"#DIV/0!", "#REF!", "#N/A", "#VALUE!", "#NAME?", "#NUM!", "#NULL!"}
SYMBOL_COLUMNS = ("티커", "심볼", "symbol")


@dataclass
class ImportRow:
    row_number: int
    asset_type: str
    name: str
    symbol: str | None
    quantity: float
    price: float | None
    average_cost: float | None
    fx_rate_to_krw: float | None
    value_krw: float
    message: str = ""


@dataclass
class IgnoredRow:
    row_number: int
    message: str


@dataclass
class ImportPreview:
    mapped_rows: list[ImportRow]
    ignored_rows: list[IgnoredRow]


def parse_number(value: str) -> float | None:
    cleaned = value.strip()
    cleaned = re.sub(r"[₩$€¥원,\s%]", "", cleaned)
    if cleaned.upper() in {"", "-", *FORMULA_ERRORS}:
        return None
    number = float(cleaned)
    if not math.isfinite(number):
        raise ValueError("숫자 값을 읽을 수 없습니다.")
    return number


def _parse_required_number(row: dict[str, str], column: str) -> float | None:
    return parse_number(row.get(column) or "")


def _parse_optional_number(row: dict[str, str], column: str) -> float | None:
    return parse_number(row.get(column) or "")


def _parse_symbol(row: dict[str, str]) -> str | None:
    for column in SYMBOL_COLUMNS:
        symbol = (row.get(column) or "").strip().upper()
        if symbol:
            return symbol
    return None


def parse_portfolio_csv(csv_text: str) -> ImportPreview:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    mapped: list[ImportRow] = []
    ignored: list[IgnoredRow] = []

    for row_number, row in enumerate(reader, start=2):
        raw_type = (row.get("종류") or "").strip()
        name = (row.get("이름") or "").strip()
        asset_type = ASSET_TYPE_MAP.get(raw_type)

        if not asset_type or not name:
            ignored.append(
                IgnoredRow(row_number=row_number, message="종류 또는 이름을 읽을 수 없습니다.")
            )
            continue

        try:
            value_krw = _parse_required_number(row, "평가액")
            quantity = _parse_optional_number(row, "개수") or 0
            price = _parse_optional_number(row, "개당 가격")
            average_cost = _parse_optional_number(row, "평단가")
            fx_rate_to_krw = _parse_optional_number(row, "환율")
        except ValueError:
            ignored.append(IgnoredRow(row_number=row_number, message="숫자 값을 읽을 수 없습니다."))
            continue

        if value_krw is None:
            ignored.append(IgnoredRow(row_number=row_number, message="평가액을 읽을 수 없습니다."))
            continue

        mapped.append(
            ImportRow(
                row_number=row_number,
                asset_type=asset_type,
                name=name,
                symbol=_parse_symbol(row),
                quantity=quantity,
                price=price,
                average_cost=average_cost,
                fx_rate_to_krw=fx_rate_to_krw,
                value_krw=value_krw,
            )
        )

    return ImportPreview(mapped_rows=mapped, ignored_rows=ignored)
