import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from portfolio_app.config import Settings, get_settings
from portfolio_app.services.toss_http import Sleep, TossAuthClient, request_with_toss_retry
from portfolio_app.services.toss_payloads import positive_number

FX_REFRESH_TTL_SECONDS = 300


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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_fetched_at_to_utc(value: str | None = None) -> str:
    if value is None or not value.strip():
        return _now_iso()

    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds")


@dataclass
class FxRefreshResult:
    status: str
    rate: float | None
    fetched_at: str | None
    change_percent: float | None = None
    source: str = ""
    error_message: str = ""


def _parse_fetched_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def latest_fx_rate(
    db: sqlite3.Connection,
    *,
    base_currency: str,
    quote_currency: str,
) -> sqlite3.Row | None:
    return db.execute(
        """
        select rate, source, fetched_at, change_percent
        from fx_rates
        where base_currency = ?
          and quote_currency = ?
        order by fetched_at desc, id desc
        limit 1
        """,
        (base_currency.upper(), quote_currency.upper()),
    ).fetchone()


def is_fx_rate_fresh(row: sqlite3.Row | None, *, ttl_seconds: int) -> bool:
    if row is None:
        return False

    fetched_at = _parse_fetched_at(str(row["fetched_at"]))
    return datetime.now(UTC) < fetched_at + timedelta(seconds=ttl_seconds)


def insert_fx_rate(
    db: sqlite3.Connection,
    *,
    base_currency: str,
    quote_currency: str,
    rate: float,
    source: str,
    change_percent: float | None = None,
    fetched_at: str | None = None,
) -> None:
    db.execute(
        """
        insert or ignore into fx_rates(
          base_currency, quote_currency, rate, source, fetched_at, change_percent
        )
        values (?, ?, ?, ?, ?, ?)
        """,
        (
            base_currency.upper(),
            quote_currency.upper(),
            rate,
            source,
            normalize_fetched_at_to_utc(fetched_at),
            change_percent,
        ),
    )


async def refresh_fx_rate_if_stale(
    db: sqlite3.Connection,
    *,
    base_currency: str = "USD",
    quote_currency: str = "KRW",
    ttl_seconds: int = FX_REFRESH_TTL_SECONDS,
    provider: FxRateProvider | None = None,
) -> FxRefreshResult:
    base = base_currency.upper()
    quote = quote_currency.upper()
    latest = latest_fx_rate(db, base_currency=base, quote_currency=quote)

    if is_fx_rate_fresh(latest, ttl_seconds=ttl_seconds):
        return FxRefreshResult(
            status="fresh",
            rate=float(latest["rate"]),
            fetched_at=str(latest["fetched_at"]),
            change_percent=latest["change_percent"],
            source=str(latest["source"]),
        )

    try:
        fetched = await (provider or default_fx_rate_provider()).fetch_rate(base, quote)
    except Exception as exc:
        if latest is None:
            return FxRefreshResult(
                status="missing",
                rate=None,
                fetched_at=None,
                error_message=str(exc),
            )
        return FxRefreshResult(
            status="stale",
            rate=float(latest["rate"]),
            fetched_at=str(latest["fetched_at"]),
            change_percent=latest["change_percent"],
            source=str(latest["source"]),
            error_message=str(exc),
        )

    fetched_at = normalize_fetched_at_to_utc(fetched.fetched_at)
    with db:
        insert_fx_rate(
            db,
            base_currency=fetched.base_currency,
            quote_currency=fetched.quote_currency,
            rate=fetched.rate,
            source=fetched.source,
            change_percent=fetched.change_percent,
            fetched_at=fetched_at,
        )
    return FxRefreshResult(
        status="refreshed",
        rate=fetched.rate,
        fetched_at=fetched_at,
        change_percent=fetched.change_percent,
        source=fetched.source,
    )


class CachedFxRateProvider:
    def __init__(
        self,
        db: sqlite3.Connection,
        *,
        ttl_seconds: int = FX_REFRESH_TTL_SECONDS,
        provider: FxRateProvider | None = None,
    ) -> None:
        self.db = db
        self.ttl_seconds = ttl_seconds
        self.provider = provider

    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        base = base_currency.strip().upper()
        quote = quote_currency.strip().upper()
        result = await refresh_fx_rate_if_stale(
            self.db,
            base_currency=base,
            quote_currency=quote,
            ttl_seconds=self.ttl_seconds,
            provider=self.provider,
        )
        if result.rate is None:
            raise ValueError(result.error_message or "환율 정보를 가져올 수 없습니다.")
        return FxRate(
            base_currency=base,
            quote_currency=quote,
            rate=result.rate,
            source=result.source or "cache",
            change_percent=result.change_percent,
            fetched_at=result.fetched_at,
        )
