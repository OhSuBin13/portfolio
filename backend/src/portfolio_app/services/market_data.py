import asyncio
import math
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from portfolio_app.config import Settings, get_settings

TOSS_PRICE_SYMBOL_LIMIT = 200
TOSS_CANDLE_PAGE_LIMIT = 200
TOSS_CANDLE_LIMIT = 1000


@dataclass
class MarketQuote:
    symbol: str
    price: float
    currency: str
    source: str
    status: str = "ok"
    error_message: str = ""


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


class MarketDataProvider(Protocol):
    async def fetch_equity_quote(self, symbol: str) -> MarketQuote:
        pass

    async def fetch_equity_quotes(self, symbols: list[str]) -> list[MarketQuote]:
        pass

    async def fetch_candles(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        limit: int = TOSS_CANDLE_LIMIT,
    ) -> list[MarketCandle]:
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


class UnsupportedMarketDataProvider:
    def __init__(self, message: str) -> None:
        self.message = message

    async def fetch_equity_quote(self, _symbol: str) -> MarketQuote:
        raise ValueError(self.message)

    async def fetch_equity_quotes(self, _symbols: list[str]) -> list[MarketQuote]:
        raise ValueError(self.message)

    async def fetch_candles(
        self,
        _symbol: str,
        *,
        interval: str = "1d",
        limit: int = TOSS_CANDLE_LIMIT,
    ) -> list[MarketCandle]:
        raise ValueError(self.message)


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


def _normalized_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol or normalized_symbol in seen:
            continue
        normalized.append(normalized_symbol)
        seen.add(normalized_symbol)
    return normalized


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


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


def keep_last_good_quote(*, previous: MarketQuote, error_message: str) -> MarketQuote:
    return MarketQuote(
        symbol=previous.symbol,
        price=previous.price,
        currency=previous.currency,
        source=previous.source,
        status="stale",
        error_message=error_message,
    )


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

    async def fetch_equity_quote(self, symbol: str) -> MarketQuote:
        normalized_symbol = symbol.strip().upper()
        quotes = await self.fetch_equity_quotes([normalized_symbol])
        quote = next((quote for quote in quotes if quote.symbol == normalized_symbol), None)
        if quote is None:
            raise ValueError("Toss 응답에서 요청 종목의 시세 정보를 찾을 수 없습니다.")
        return quote

    async def fetch_equity_quotes(self, symbols: list[str]) -> list[MarketQuote]:
        normalized_symbols = _normalized_symbols(symbols)
        if not normalized_symbols:
            return []

        token = await self._token()
        quotes_by_symbol: dict[str, MarketQuote] = {}

        async with httpx.AsyncClient(timeout=10) as client:
            for chunk in _chunks(normalized_symbols, TOSS_PRICE_SYMBOL_LIMIT):
                response = await request_with_toss_retry(
                    client,
                    "GET",
                    f"{self.base_url}/api/v1/prices",
                    params={"symbols": ",".join(chunk)},
                    headers={"Authorization": f"Bearer {token}"},
                    sleep=self._sleep,
                )
                response.raise_for_status()
                payload = response.json()

                prices = payload.get("result") if isinstance(payload, dict) else None
                if not isinstance(prices, list):
                    raise ValueError("Toss 응답에서 시세 정보를 찾을 수 없습니다.")

                chunk_symbols = set(chunk)
                for item in prices:
                    if not isinstance(item, dict):
                        continue
                    symbol = str(item.get("symbol", "")).strip().upper()
                    if symbol not in chunk_symbols:
                        continue
                    currency = str(item.get("currency", "")).strip().upper()
                    if currency not in {"KRW", "USD"}:
                        raise ValueError("Toss 응답 통화는 KRW 또는 USD여야 합니다.")
                    quotes_by_symbol[symbol] = MarketQuote(
                        symbol=symbol,
                        price=_positive_number(
                            item.get("lastPrice"),
                            "Toss 가격은 0보다 큰 숫자여야 합니다.",
                        ),
                        currency=currency,
                        source=self.source,
                    )

        return [
            quotes_by_symbol[symbol]
            for symbol in normalized_symbols
            if symbol in quotes_by_symbol
        ]

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


def market_data_provider_for_asset(
    asset: Any,
    *,
    toss_provider: MarketDataProvider,
) -> MarketDataProvider:
    if _is_toss_supported_asset(asset):
        return toss_provider
    market = str(asset["market"]).upper()
    currency = str(asset["currency"]).upper()
    return UnsupportedMarketDataProvider(
        f"{market}/{currency} 시세 동기화는 아직 지원하지 않습니다."
    )


def _is_toss_supported_asset(asset: Any) -> bool:
    asset_type = str(asset["type"])
    market = str(asset["market"]).upper()
    currency = str(asset["currency"]).upper()

    return asset_type == "stock_etf" and (market, currency) in {("US", "USD"), ("KR", "KRW")}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_fetched_at_to_utc(value: str | None = None) -> str:
    if value is None or not value.strip():
        return _now_iso()

    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds")


def insert_price_snapshot(
    db: sqlite3.Connection,
    *,
    asset_id: int,
    source: str,
    price: float,
    currency: str,
    price_krw: float,
    status: str,
    error_message: str = "",
    fetched_at: str | None = None,
) -> sqlite3.Row:
    cursor = db.execute(
        """
        insert into price_snapshots(
            asset_id, source, price, currency, price_krw, fetched_at, status, error_message
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            source,
            price,
            currency,
            price_krw,
            fetched_at or _now_iso(),
            status,
            error_message,
        ),
    )
    row = db.execute("select * from price_snapshots where id = ?", (cursor.lastrowid,)).fetchone()
    if row is None:
        raise RuntimeError("시세 스냅샷을 찾을 수 없습니다.")
    return row


def latest_usable_price_snapshot(db: sqlite3.Connection, asset_id: int) -> sqlite3.Row | None:
    return db.execute(
        """
        select *
        from price_snapshots
        where asset_id = ?
          and status in ('ok', 'manual', 'stale')
        order by fetched_at desc, id desc
        limit 1
        """,
        (asset_id,),
    ).fetchone()


def _previous_quote(row: sqlite3.Row, symbol: str) -> MarketQuote:
    return MarketQuote(
        symbol=symbol,
        price=float(row["price"]),
        currency=str(row["currency"]),
        source=str(row["source"]),
    )


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        reason = response.reason_phrase or "Unknown"
        return f"시세 제공자 요청 실패: HTTP {response.status_code} {reason}"
    if isinstance(exc, httpx.HTTPError):
        return f"시세 제공자 요청 실패: {exc.__class__.__name__}"
    return str(exc)


async def _price_krw(
    quote: MarketQuote,
    *,
    db: sqlite3.Connection,
    fx_provider: FxRateProvider,
    fx_rate_cache: dict[tuple[str, str], FxRate] | None = None,
) -> float:
    base_currency = quote.currency.upper()
    quote_currency = "KRW"
    if base_currency == quote_currency:
        return quote.price

    cache_key = (base_currency, quote_currency)
    if fx_rate_cache is not None and cache_key in fx_rate_cache:
        rate = fx_rate_cache[cache_key]
        return quote.price * rate.rate

    rate = await fx_provider.fetch_rate(base_currency, quote_currency)
    if fx_rate_cache is not None:
        fx_rate_cache[cache_key] = rate
    db.execute(
        """
        insert or ignore into fx_rates(
          base_currency, quote_currency, rate, source, fetched_at, change_percent
        )
        values (?, ?, ?, ?, ?, ?)
        """,
        (
            rate.base_currency,
            rate.quote_currency,
            rate.rate,
            rate.source,
            normalize_fetched_at_to_utc(rate.fetched_at),
            rate.change_percent,
        ),
    )
    return quote.price * rate.rate


def _record_quote_failure(
    db: sqlite3.Connection,
    asset: sqlite3.Row,
    *,
    error_message: str,
) -> str:
    asset_id = int(asset["id"])
    symbol = str(asset["symbol"])
    previous = latest_usable_price_snapshot(db, asset_id)
    with db:
        if previous is None:
            insert_price_snapshot(
                db,
                asset_id=asset_id,
                source="market_data",
                price=0,
                currency=str(asset["currency"]),
                price_krw=0,
                status="failed",
                error_message=error_message,
            )
            return "failed"

        stale_quote = keep_last_good_quote(
            previous=_previous_quote(previous, symbol),
            error_message=error_message,
        )
        insert_price_snapshot(
            db,
            asset_id=asset_id,
            source=stale_quote.source,
            price=stale_quote.price,
            currency=stale_quote.currency,
            price_krw=float(previous["price_krw"]),
            status=stale_quote.status,
            error_message=stale_quote.error_message,
        )
        return stale_quote.status


async def _fetch_supported_toss_quotes(
    assets: list[sqlite3.Row],
    *,
    toss_provider: TossMarketDataProvider,
) -> tuple[dict[str, MarketQuote], str | None]:
    supported_symbols = [
        str(asset["symbol"])
        for asset in assets
        if _is_toss_supported_asset(asset)
    ]
    if not supported_symbols:
        return {}, None

    try:
        quotes = await toss_provider.fetch_equity_quotes(supported_symbols)
    except (ValueError, httpx.HTTPError) as exc:
        return {}, _safe_error_message(exc)

    return {quote.symbol: quote for quote in quotes}, None


async def _quote_for_asset(
    asset: sqlite3.Row,
    *,
    toss_provider: TossMarketDataProvider,
    toss_quotes: dict[str, MarketQuote],
    toss_error_message: str | None,
) -> MarketQuote:
    if _is_toss_supported_asset(asset):
        if toss_error_message is not None:
            raise ValueError(toss_error_message)
        normalized_symbol = str(asset["symbol"]).strip().upper()
        quote = toss_quotes.get(normalized_symbol)
        if quote is None:
            raise ValueError("Toss 응답에서 요청 종목의 시세 정보를 찾을 수 없습니다.")
        return quote

    provider = market_data_provider_for_asset(
        asset,
        toss_provider=toss_provider,
    )
    return await provider.fetch_equity_quote(str(asset["symbol"]))


async def sync_market_data_for_settings(
    settings: Settings,
    db: sqlite3.Connection,
) -> dict[str, object]:
    assets = db.execute(
        """
        select *
        from assets
        where symbol is not null
          and trim(symbol) != ''
          and type in ('stock_etf')
        order by id
        """
    ).fetchall()
    toss_auth_client = TossAuthClient(settings.toss_api_key, settings.toss_secret_key)
    toss_provider = TossMarketDataProvider(
        settings.toss_api_key,
        settings.toss_secret_key,
        auth_client=toss_auth_client,
    )
    fx_provider = default_fx_rate_provider(settings, auth_client=toss_auth_client)
    fx_rate_cache: dict[tuple[str, str], FxRate] = {}
    toss_quotes, toss_error_message = await _fetch_supported_toss_quotes(
        assets,
        toss_provider=toss_provider,
    )
    results: list[dict[str, object]] = []

    for asset in assets:
        asset_id = int(asset["id"])
        symbol = str(asset["symbol"])
        try:
            quote = await _quote_for_asset(
                asset,
                toss_provider=toss_provider,
                toss_quotes=toss_quotes,
                toss_error_message=toss_error_message,
            )
            price_krw = await _price_krw(
                quote,
                db=db,
                fx_provider=fx_provider,
                fx_rate_cache=fx_rate_cache,
            )
            with db:
                insert_price_snapshot(
                    db,
                    asset_id=asset_id,
                    source=quote.source,
                    price=quote.price,
                    currency=quote.currency,
                    price_krw=price_krw,
                    status=quote.status,
                    error_message=quote.error_message,
                )
            results.append(
                {
                    "asset_id": asset_id,
                    "symbol": symbol,
                    "status": quote.status,
                    "error_message": quote.error_message,
                }
            )
        except (ValueError, sqlite3.Error, httpx.HTTPError) as exc:
            error_message = _safe_error_message(exc)
            result_status = _record_quote_failure(
                db,
                asset,
                error_message=error_message,
            )
            results.append(
                {
                    "asset_id": asset_id,
                    "symbol": symbol,
                    "status": result_status,
                    "error_message": error_message,
                }
            )

    return {"results": results}
