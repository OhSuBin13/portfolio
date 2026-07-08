import asyncio

import httpx

from portfolio_app.services.fx_rates import (
    FxRate as FxRate,
)
from portfolio_app.services.fx_rates import (
    FxRateProvider as FxRateProvider,
)
from portfolio_app.services.fx_rates import (
    TossFxRateProvider as TossFxRateProvider,
)
from portfolio_app.services.fx_rates import (
    default_fx_rate_provider as default_fx_rate_provider,
)
from portfolio_app.services.fx_rates import (
    normalize_fetched_at_to_utc as normalize_fetched_at_to_utc,
)
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

TOSS_CANDLE_PAGE_LIMIT = 200
TOSS_CANDLE_LIMIT = 1000


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
