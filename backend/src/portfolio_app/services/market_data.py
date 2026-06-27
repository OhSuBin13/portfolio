import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from portfolio_app.config import Settings, get_settings

TOSS_PRICE_SYMBOL_LIMIT = 200


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


class UnsupportedMarketDataProvider:
    def __init__(self, message: str) -> None:
        self.message = message

    async def fetch_equity_quote(self, _symbol: str) -> MarketQuote:
        raise ValueError(self.message)

    async def fetch_equity_quotes(self, _symbols: list[str]) -> list[MarketQuote]:
        raise ValueError(self.message)


class TossAuthClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = "https://openapi.tossinvest.com",
    ) -> None:
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.base_url = base_url.rstrip("/")
        self._access_token: str | None = None

    async def token(self) -> str:
        if self._access_token:
            return self._access_token

        if not self.client_id or not self.client_secret:
            raise ValueError("Toss API 인증 정보가 필요합니다.")

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.base_url}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            response.raise_for_status()
            payload = response.json()

        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("Toss 토큰 응답에서 access_token을 찾을 수 없습니다.")

        self._access_token = access_token.strip()
        return self._access_token


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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._auth_client = auth_client or TossAuthClient(
            client_id,
            client_secret,
            base_url=self.base_url,
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
            response = await client.get(
                f"{self.base_url}/api/v1/exchange-rate",
                params={"baseCurrency": base, "quoteCurrency": quote},
                headers={"Authorization": f"Bearer {token}"},
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._auth_client = auth_client or TossAuthClient(
            client_id,
            client_secret,
            base_url=self.base_url,
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
                response = await client.get(
                    f"{self.base_url}/api/v1/prices",
                    params={"symbols": ",".join(chunk)},
                    headers={"Authorization": f"Bearer {token}"},
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

    response: dict[str, object] = {"results": results}
    try:
        from portfolio_app.services.growth import create_or_refresh_market_sync_snapshot

        response["snapshot"] = create_or_refresh_market_sync_snapshot(db)
    except (ValueError, sqlite3.Error) as exc:
        response["snapshot_error"] = str(exc)

    return response
