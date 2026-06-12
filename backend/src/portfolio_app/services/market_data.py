import math
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class MarketQuote:
    symbol: str
    price: float
    currency: str
    source: str
    status: str = "ok"
    error_message: str = ""


@dataclass
class FxRate:
    base_currency: str
    quote_currency: str
    rate: float
    source: str


def _positive_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(message)
    return number


def keep_last_good_quote(*, previous: MarketQuote, error_message: str) -> MarketQuote:
    return MarketQuote(
        symbol=previous.symbol,
        price=previous.price,
        currency=previous.currency,
        source=previous.source,
        status="stale",
        error_message=error_message,
    )


class CoinGeckoProvider:
    source = "coingecko"

    async def fetch_crypto_quote(self, coin_id: str, *, vs_currency: str = "krw") -> MarketQuote:
        normalized_coin_id = coin_id.strip().lower()
        normalized_currency = vs_currency.strip().lower()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": normalized_coin_id, "vs_currencies": normalized_currency},
            )
            response.raise_for_status()
            payload = response.json()

        try:
            price = payload[normalized_coin_id][normalized_currency]
        except (KeyError, TypeError) as exc:
            raise ValueError("CoinGecko 응답에서 가격을 찾을 수 없습니다.") from exc

        return MarketQuote(
            symbol=normalized_coin_id,
            price=_positive_number(price, "CoinGecko 가격은 0보다 큰 숫자여야 합니다."),
            currency=normalized_currency.upper(),
            source=self.source,
        )


class FrankfurterProvider:
    source = "frankfurter"

    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        base = base_currency.strip().upper()
        quote = quote_currency.strip().upper()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"https://api.frankfurter.dev/v2/rate/{base}/{quote}")
            response.raise_for_status()
            payload = response.json()

        try:
            rate = payload["rate"]
        except (KeyError, TypeError) as exc:
            raise ValueError("Frankfurter 응답에서 환율을 찾을 수 없습니다.") from exc

        return FxRate(
            base_currency=base,
            quote_currency=quote,
            rate=_positive_number(rate, "Frankfurter 환율은 0보다 큰 숫자여야 합니다."),
            source=self.source,
        )


class AlphaVantageProvider:
    source = "alpha_vantage"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()

    async def fetch_equity_quote(self, symbol: str) -> MarketQuote:
        normalized_symbol = symbol.strip().upper()
        if not self.api_key:
            raise ValueError("Alpha Vantage API 키가 필요합니다.")

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": normalized_symbol,
                    "apikey": self.api_key,
                },
            )
            response.raise_for_status()
            payload = response.json()

        quote = payload.get("Global Quote")
        if not isinstance(quote, dict):
            raise ValueError("Alpha Vantage 응답에서 시세 정보를 찾을 수 없습니다.")

        price = quote.get("05. price")
        if price is None:
            raise ValueError("Alpha Vantage 응답에서 가격을 찾을 수 없습니다.")

        return MarketQuote(
            symbol=normalized_symbol,
            price=_positive_number(price, "Alpha Vantage 가격은 0보다 큰 숫자여야 합니다."),
            currency="USD",
            source=self.source,
        )
