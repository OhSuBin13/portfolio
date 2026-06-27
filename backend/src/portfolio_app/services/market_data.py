import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Protocol

import httpx

from portfolio_app.config import Settings

NAVER_USD_KRW_URL = (
    "https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW"
)
NUMBER_PATTERN = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?")


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


class FxRateProvider(Protocol):
    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        pass


class MarketDataProvider(Protocol):
    async def fetch_equity_quote(self, symbol: str) -> MarketQuote:
        pass


class UnsupportedMarketDataProvider:
    def __init__(self, message: str) -> None:
        self.message = message

    async def fetch_equity_quote(self, _symbol: str) -> MarketQuote:
        raise ValueError(self.message)


def _positive_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(message)
    return number


def _finite_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number):
        raise ValueError(message)
    return number


def _number_from_text(text: str, message: str) -> float:
    compact_text = "".join(text.replace("\xa0", " ").split())
    match = NUMBER_PATTERN.search(compact_text)
    if match is None:
        raise ValueError(message)
    return _finite_number(match.group(0).replace(",", ""), message)


class _NaverExchangeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.today_text_parts: list[str] = []
        self.exday_text_parts: list[str] = []
        self.exday_em_groups: list[tuple[set[str], str]] = []
        self._section: str | None = None
        self._em_depth = 0
        self._active_em_classes: set[str] = set()
        self._active_em_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        classes = set((attr_map.get("class") or "").split())

        if tag == "p":
            if "no_today" in classes:
                self._section = "today"
            elif "no_exday" in classes:
                self._section = "exday"

        if (
            self._section == "exday"
            and tag == "em"
            and classes.intersection({"no_up", "no_down", "no_change"})
        ):
            if self._em_depth == 0:
                self._active_em_classes = classes
                self._active_em_text_parts = []
            self._em_depth += 1

    def handle_data(self, data: str) -> None:
        if self._section == "today":
            self.today_text_parts.append(data)
            return

        if self._section == "exday":
            self.exday_text_parts.append(data)
            if self._em_depth > 0:
                self._active_em_text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._section == "exday" and tag == "em" and self._em_depth > 0:
            self._em_depth -= 1
            if self._em_depth == 0:
                self.exday_em_groups.append(
                    (set(self._active_em_classes), "".join(self._active_em_text_parts))
                )
                self._active_em_classes = set()
                self._active_em_text_parts = []

        if tag == "p" and self._section in {"today", "exday"}:
            self._section = None
            self._em_depth = 0
            self._active_em_classes = set()
            self._active_em_text_parts = []


def _parse_naver_change_percent(parser: _NaverExchangeParser) -> float | None:
    for classes, text in parser.exday_em_groups:
        if "%" not in text:
            continue

        value = _number_from_text(
            text,
            "Naver Finance 응답에서 전일대비 변경율을 찾을 수 없습니다.",
        )
        compact_text = "".join(text.split())
        if "-" in compact_text:
            return -abs(value)
        if "+" in compact_text:
            return abs(value)
        if "no_down" in classes:
            return -abs(value)
        return abs(value)

    if "%" not in "".join(parser.exday_text_parts):
        return None

    return _number_from_text(
        "".join(parser.exday_text_parts),
        "Naver Finance 응답에서 전일대비 변경율을 찾을 수 없습니다.",
    )


def keep_last_good_quote(*, previous: MarketQuote, error_message: str) -> MarketQuote:
    return MarketQuote(
        symbol=previous.symbol,
        price=previous.price,
        currency=previous.currency,
        source=previous.source,
        status="stale",
        error_message=error_message,
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


class NaverFinanceProvider:
    source = "naver_finance"

    def __init__(self, url: str = NAVER_USD_KRW_URL) -> None:
        self.url = url

    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        base = base_currency.strip().upper()
        quote = quote_currency.strip().upper()
        if (base, quote) != ("USD", "KRW"):
            raise ValueError("Naver Finance는 USD/KRW 환율만 지원합니다.")

        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            response = await client.get(self.url)
            response.raise_for_status()

        parser = _NaverExchangeParser()
        parser.feed(response.text)

        rate = _number_from_text(
            "".join(parser.today_text_parts),
            "Naver Finance 응답에서 USD/KRW 환율을 찾을 수 없습니다.",
        )
        return FxRate(
            base_currency=base,
            quote_currency=quote,
            rate=_positive_number(rate, "Naver Finance 환율은 0보다 큰 숫자여야 합니다."),
            source=self.source,
            change_percent=_parse_naver_change_percent(parser),
        )


class FallbackFxRateProvider:
    def __init__(self, *providers: FxRateProvider) -> None:
        self.providers = providers

    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return await provider.fetch_rate(base_currency, quote_currency)
            except Exception as exc:
                errors.append(str(exc))

        raise ValueError(f"환율 제공자 요청이 모두 실패했습니다: {'; '.join(errors)}")


def default_fx_rate_provider() -> FxRateProvider:
    return FallbackFxRateProvider(NaverFinanceProvider(), FrankfurterProvider())


class TossMarketDataProvider:
    source = "toss"

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

    async def _token(self) -> str:
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

    async def fetch_equity_quote(self, symbol: str) -> MarketQuote:
        normalized_symbol = symbol.strip().upper()
        token = await self._token()

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/prices",
                params={"symbols": normalized_symbol},
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload = response.json()

        prices = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(prices, list):
            raise ValueError("Toss 응답에서 시세 정보를 찾을 수 없습니다.")

        quote = next(
            (
                item
                for item in prices
                if isinstance(item, dict)
                and str(item.get("symbol", "")).strip().upper() == normalized_symbol
            ),
            None,
        )
        if quote is None:
            raise ValueError("Toss 응답에서 요청 종목의 시세 정보를 찾을 수 없습니다.")

        currency = str(quote.get("currency", "")).strip().upper()
        if currency not in {"KRW", "USD"}:
            raise ValueError("Toss 응답 통화는 KRW 또는 USD여야 합니다.")

        return MarketQuote(
            symbol=normalized_symbol,
            price=_positive_number(quote.get("lastPrice"), "Toss 가격은 0보다 큰 숫자여야 합니다."),
            currency=currency,
            source=self.source,
        )


def market_data_provider_for_asset(
    asset: Any,
    *,
    toss_provider: MarketDataProvider,
) -> MarketDataProvider:
    asset_type = str(asset["type"])
    market = str(asset["market"]).upper()
    currency = str(asset["currency"]).upper()

    if asset_type == "stock_etf" and (market, currency) in {("US", "USD"), ("KR", "KRW")}:
        return toss_provider
    return UnsupportedMarketDataProvider(
        f"{market}/{currency} 시세 동기화는 아직 지원하지 않습니다."
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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
) -> float:
    if quote.currency.upper() == "KRW":
        return quote.price

    rate = await fx_provider.fetch_rate(quote.currency, "KRW")
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
            _now_iso(),
            rate.change_percent,
        ),
    )
    return quote.price * rate.rate


async def _fetch_quote(
    asset: sqlite3.Row,
    *,
    toss_provider: TossMarketDataProvider,
) -> MarketQuote:
    symbol = str(asset["symbol"])
    provider = market_data_provider_for_asset(
        asset,
        toss_provider=toss_provider,
    )
    return await provider.fetch_equity_quote(symbol)


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
    toss_provider = TossMarketDataProvider(settings.toss_api_key, settings.toss_secret_key)
    fx_provider = default_fx_rate_provider()
    results: list[dict[str, object]] = []

    for asset in assets:
        asset_id = int(asset["id"])
        symbol = str(asset["symbol"])
        try:
            quote = await _fetch_quote(
                asset,
                toss_provider=toss_provider,
            )
            price_krw = await _price_krw(quote, db=db, fx_provider=fx_provider)
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
                    result_status = "failed"
                else:
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
                    result_status = stale_quote.status
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
