import pytest

from portfolio_app.services.market_candles import (
    MarketCandle,
    candle_page,
    parse_candle,
)


def test_candle_page_reads_supported_result_shapes():
    items, next_before = candle_page(
        {
            "result": {
                "items": [{"timestamp": "2026-01-01"}],
                "next_before": " cursor-1 ",
            }
        }
    )

    assert items == [{"timestamp": "2026-01-01"}]
    assert next_before == "cursor-1"
    assert candle_page({"result": [{"timestamp": "2026-01-02"}]}) == (
        [{"timestamp": "2026-01-02"}],
        None,
    )


def test_candle_page_rejects_missing_or_non_object_items():
    with pytest.raises(ValueError, match="Toss 응답에서 캔들 정보를 찾을 수 없습니다."):
        candle_page({"result": {"candles": None}})

    with pytest.raises(ValueError, match="Toss 캔들 항목은 객체여야 합니다."):
        candle_page({"result": {"candles": ["bad"]}})


def test_parse_candle_coerces_alias_payload_to_market_candle():
    assert parse_candle(
        "AAPL",
        {
            "dateTime": "2026-01-01T00:00:00Z",
            "openPrice": "170",
            "highPrice": "181",
            "lowPrice": "169",
            "closePrice": "180",
            "tradeVolume": "1234",
        },
    ) == MarketCandle(
        symbol="AAPL",
        timestamp="2026-01-01T00:00:00Z",
        open=170,
        high=181,
        low=169,
        close=180,
        volume=1234,
    )


def test_parse_candle_rejects_inverted_high_low():
    with pytest.raises(ValueError, match="Toss 캔들 고가는 저가보다 작을 수 없습니다."):
        parse_candle(
            "AAPL",
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "open": "170",
                "high": "168",
                "low": "169",
                "close": "170",
                "volume": "1234",
            },
        )
