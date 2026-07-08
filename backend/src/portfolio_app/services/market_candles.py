from dataclasses import dataclass
from typing import Any

from portfolio_app.services.toss_payloads import (
    non_negative_number,
    positive_number,
    required_text,
)


@dataclass
class MarketCandle:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def candle_page(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    result = payload.get("result") if isinstance(payload, dict) else None
    if isinstance(result, list):
        items = result
        next_before = None
    elif isinstance(result, dict):
        items = next(
            (result[key] for key in ("candles", "items", "data") if key in result),
            None,
        )
        next_before_value = result.get("nextBefore") or result.get("next_before")
        next_before = (
            next_before_value.strip()
            if isinstance(next_before_value, str) and next_before_value.strip()
            else None
        )
    else:
        items = None
        next_before = None

    if not isinstance(items, list):
        raise ValueError("Toss 응답에서 캔들 정보를 찾을 수 없습니다.")
    if any(not isinstance(item, dict) for item in items):
        raise ValueError("Toss 캔들 항목은 객체여야 합니다.")
    return items, next_before


def parse_candle(symbol: str, item: dict[str, Any]) -> MarketCandle:
    timestamp = required_text(
        _first_present(item, "timestamp", "time", "date", "datetime", "dateTime"),
        "Toss 캔들 시간 값이 필요합니다.",
    )
    open_price = positive_number(
        _first_present(item, "openPrice", "open"),
        "Toss 캔들 시가는 0보다 큰 숫자여야 합니다.",
    )
    high_price = positive_number(
        _first_present(item, "highPrice", "high"),
        "Toss 캔들 고가는 0보다 큰 숫자여야 합니다.",
    )
    low_price = positive_number(
        _first_present(item, "lowPrice", "low"),
        "Toss 캔들 저가는 0보다 큰 숫자여야 합니다.",
    )
    close_price = positive_number(
        _first_present(item, "closePrice", "close"),
        "Toss 캔들 종가는 0보다 큰 숫자여야 합니다.",
    )
    volume = non_negative_number(
        _first_present(item, "volume", "tradeVolume"),
        "Toss 캔들 거래량은 0 이상의 숫자여야 합니다.",
    )
    if high_price < low_price:
        raise ValueError("Toss 캔들 고가는 저가보다 작을 수 없습니다.")

    return MarketCandle(
        symbol=symbol,
        timestamp=timestamp,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
    )


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None
