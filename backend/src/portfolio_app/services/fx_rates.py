import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from portfolio_app.services.market_data import (
    FxRateProvider,
    default_fx_rate_provider,
    normalize_fetched_at_to_utc,
)

FX_REFRESH_TTL_SECONDS = 300


@dataclass
class FxRefreshResult:
    status: str
    rate: float | None
    fetched_at: str | None
    change_percent: float | None = None
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
        select rate, fetched_at, change_percent
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
    )
