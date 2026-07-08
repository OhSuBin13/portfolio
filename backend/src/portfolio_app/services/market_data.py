import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx

from portfolio_app.config import Settings, get_settings
from portfolio_app.services.market_candles import MarketCandle, candle_page, parse_candle
from portfolio_app.services.toss_http import (
    TOSS_DEFAULT_RETRY_AFTER_SECONDS as TOSS_DEFAULT_RETRY_AFTER_SECONDS,
)
from portfolio_app.services.toss_http import (
    Sleep,
    TossAuthClient,
    request_with_toss_retry,
)
from portfolio_app.services.toss_http import (
    _retry_after_seconds as _retry_after_seconds,
)
from portfolio_app.services.toss_payloads import (
    positive_number,
)

TOSS_CANDLE_PAGE_LIMIT = 200
TOSS_CANDLE_LIMIT = 1000


@dataclass
class FxRate:
    base_currency: str
    quote_currency: str
    rate: float
    source: str
    change_percent: float | None = None
    fetched_at: str | None = None


class FxRateProvider(Protocol):
    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        pass


class TossFxRateProvider:
    source = "toss"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = "https://openapi.tossinvest.com",
        auth_client: TossAuthClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._auth_client = auth_client or TossAuthClient(
            client_id,
            client_secret,
            base_url=self.base_url,
            sleep=sleep,
        )

    async def _token(self) -> str:
        return await self._auth_client.token()

    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        base = base_currency.strip().upper()
        quote = quote_currency.strip().upper()
        if base == quote or {base, quote} != {"USD", "KRW"}:
            raise ValueError("Toss 환율은 USD/KRW 또는 KRW/USD만 지원합니다.")

        token = await self._token()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/exchange-rate",
                params={"baseCurrency": base, "quoteCurrency": quote},
                headers={"Authorization": f"Bearer {token}"},
                sleep=self._sleep,
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ValueError("Toss 응답에서 환율 정보를 찾을 수 없습니다.")

        response_base = str(result.get("baseCurrency", "")).strip().upper()
        response_quote = str(result.get("quoteCurrency", "")).strip().upper()
        if (response_base, response_quote) != (base, quote):
            raise ValueError("Toss 응답 환율 통화가 요청과 일치하지 않습니다.")
        fetched_at = result.get("validFrom")

        return FxRate(
            base_currency=response_base,
            quote_currency=response_quote,
            rate=positive_number(
                result.get("rate"),
                "Toss 환율은 0보다 큰 숫자여야 합니다.",
            ),
            source=self.source,
            fetched_at=(
                fetched_at.strip()
                if isinstance(fetched_at, str) and fetched_at.strip()
                else None
            ),
        )


def default_fx_rate_provider(
    settings: Settings | None = None,
    *,
    auth_client: TossAuthClient | None = None,
) -> FxRateProvider:
    resolved_settings = settings or get_settings()
    return TossFxRateProvider(
        resolved_settings.toss_api_key,
        resolved_settings.toss_secret_key,
        auth_client=auth_client,
    )


class TossMarketDataProvider:
    source = "toss"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = "https://openapi.tossinvest.com",
        auth_client: TossAuthClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._auth_client = auth_client or TossAuthClient(
            client_id,
            client_secret,
            base_url=self.base_url,
            sleep=sleep,
        )

    async def _token(self) -> str:
        return await self._auth_client.token()

    async def fetch_candles(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        limit: int = TOSS_CANDLE_LIMIT,
    ) -> list[MarketCandle]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("Toss 캔들 조회 종목 심볼을 입력해 주세요.")

        normalized_interval = interval.strip()
        if normalized_interval not in {"1m", "1d"}:
            raise ValueError("Toss 캔들 주기는 1m 또는 1d만 지원합니다.")
        if limit < 1 or limit > TOSS_CANDLE_LIMIT:
            raise ValueError("Toss 캔들 조회 개수는 1개 이상 1000개 이하이어야 합니다.")

        token = await self._token()
        candles: list[MarketCandle] = []
        before: str | None = None
        remaining = limit

        async with httpx.AsyncClient(timeout=10) as client:
            while remaining > 0:
                count = min(remaining, TOSS_CANDLE_PAGE_LIMIT)
                params: dict[str, object] = {
                    "symbol": normalized_symbol,
                    "interval": normalized_interval,
                    "count": count,
                    "adjusted": "true",
                }
                if before is not None:
                    params["before"] = before

                response = await request_with_toss_retry(
                    client,
                    "GET",
                    f"{self.base_url}/api/v1/candles",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                    sleep=self._sleep,
                )
                response.raise_for_status()
                payload = response.json()
                items, next_before = candle_page(payload)
                if not items:
                    break

                candles.extend(parse_candle(normalized_symbol, item) for item in items)
                remaining = limit - len(candles)
                if next_before is None or next_before == before:
                    break
                before = next_before

        return candles[:limit]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_fetched_at_to_utc(value: str | None = None) -> str:
    if value is None or not value.strip():
        return _now_iso()

    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds")
