import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from portfolio_app.config import Settings, get_settings

TOSS_CANDLE_PAGE_LIMIT = 200
TOSS_CANDLE_LIMIT = 1000


@dataclass
class MarketCandle:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


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


TOSS_MAX_RETRIES = 1
TOSS_DEFAULT_RETRY_AFTER_SECONDS = 1.0
TOSS_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 60.0
TOSS_DEFAULT_TOKEN_EXPIRES_IN_SECONDS = 3600.0

Sleep = Callable[[float], Awaitable[None]]
Now = Callable[[], float]


def _retry_after_seconds(response: httpx.Response) -> float:
    header_value = response.headers.get("Retry-After") or response.headers.get(
        "X-RateLimit-Reset"
    )
    if header_value is None:
        return TOSS_DEFAULT_RETRY_AFTER_SECONDS

    try:
        delay = float(header_value)
    except ValueError:
        return TOSS_DEFAULT_RETRY_AFTER_SECONDS
    return max(delay, 0.0)


async def request_with_toss_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    sleep: Sleep = asyncio.sleep,
    max_retries: int = TOSS_MAX_RETRIES,
    **kwargs: object,
) -> httpx.Response:
    response = await client.request(method, url, **kwargs)
    for _attempt in range(max_retries):
        if response.status_code != 429:
            return response
        await sleep(_retry_after_seconds(response))
        response = await client.request(method, url, **kwargs)
    return response


class TossAuthClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = "https://openapi.tossinvest.com",
        sleep: Sleep = asyncio.sleep,
        now: Now = time.monotonic,
    ) -> None:
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._now = now
        self._token_lock = asyncio.Lock()
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0

    def _has_fresh_access_token(self) -> bool:
        return (
            self._access_token is not None
            and self._now() < self._access_token_expires_at
        )

    async def token(self) -> str:
        if self._has_fresh_access_token():
            assert self._access_token is not None
            return self._access_token

        async with self._token_lock:
            if self._has_fresh_access_token():
                assert self._access_token is not None
                return self._access_token

            if not self.client_id or not self.client_secret:
                raise ValueError("Toss API 인증 정보가 필요합니다.")

            async with httpx.AsyncClient(timeout=10) as client:
                response = await request_with_toss_retry(
                    client,
                    "POST",
                    f"{self.base_url}/oauth2/token",
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    sleep=self._sleep,
                )
                response.raise_for_status()
                payload = response.json()

            access_token = payload.get("access_token") if isinstance(payload, dict) else None
            if not isinstance(access_token, str) or not access_token.strip():
                raise ValueError("Toss 토큰 응답에서 access_token을 찾을 수 없습니다.")

            self._access_token = access_token.strip()
            self._access_token_expires_at = self._now() + max(
                _token_expires_in_seconds(payload)
                - TOSS_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS,
                0.0,
            )
            return self._access_token


def _token_expires_in_seconds(payload: dict[str, Any]) -> float:
    try:
        expires_in = float(payload.get("expires_in"))
    except (TypeError, ValueError):
        return TOSS_DEFAULT_TOKEN_EXPIRES_IN_SECONDS
    if not math.isfinite(expires_in) or expires_in < 0:
        return TOSS_DEFAULT_TOKEN_EXPIRES_IN_SECONDS
    return expires_in


def _positive_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(message)
    return number


def _required_text(value: Any, message: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(message)
    return text


def _non_negative_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(message)
    return number


def _first_present(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None


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
            rate=_positive_number(
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
                items, next_before = _candle_page(payload)
                if not items:
                    break

                candles.extend(_parse_candle(normalized_symbol, item) for item in items)
                remaining = limit - len(candles)
                if next_before is None or next_before == before:
                    break
                before = next_before

        return candles[:limit]


def _candle_page(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    result = payload.get("result") if isinstance(payload, dict) else None
    if isinstance(result, list):
        items = result
        next_before = None
    elif isinstance(result, dict):
        items = result.get("candles") or result.get("items") or result.get("data")
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


def _parse_candle(symbol: str, item: dict[str, Any]) -> MarketCandle:
    timestamp = _required_text(
        _first_present(item, "timestamp", "time", "date", "datetime", "dateTime"),
        "Toss 캔들 시간 값이 필요합니다.",
    )
    open_price = _positive_number(
        _first_present(item, "openPrice", "open"),
        "Toss 캔들 시가는 0보다 큰 숫자여야 합니다.",
    )
    high_price = _positive_number(
        _first_present(item, "highPrice", "high"),
        "Toss 캔들 고가는 0보다 큰 숫자여야 합니다.",
    )
    low_price = _positive_number(
        _first_present(item, "lowPrice", "low"),
        "Toss 캔들 저가는 0보다 큰 숫자여야 합니다.",
    )
    close_price = _positive_number(
        _first_present(item, "closePrice", "close"),
        "Toss 캔들 종가는 0보다 큰 숫자여야 합니다.",
    )
    volume = _non_negative_number(
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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_fetched_at_to_utc(value: str | None = None) -> str:
    if value is None or not value.strip():
        return _now_iso()

    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds")
