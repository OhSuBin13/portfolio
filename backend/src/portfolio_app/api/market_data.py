import asyncio
import sqlite3
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from portfolio_app.api import get_db, require_non_empty, require_positive_number, row_to_dict
from portfolio_app.services.market_data import (
    AlphaVantageProvider,
    CoinGeckoProvider,
    FrankfurterProvider,
    MarketQuote,
    keep_last_good_quote,
)

router = APIRouter(prefix="/api/market-data", tags=["market-data"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]


class ManualPriceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: int
    price_krw: float
    source: str = "manual"
    error_message: str = ""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _insert_snapshot(
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="시세 스냅샷을 찾을 수 없습니다.",
        )
    return row


def _latest_snapshot(db: sqlite3.Connection, asset_id: int) -> sqlite3.Row | None:
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


def _snapshot_response(row: sqlite3.Row) -> dict[str, object]:
    return {
        "asset_id": row["asset_id"],
        "source": row["source"],
        "price_krw": row["price_krw"],
        "status": row["status"],
        "error_message": row["error_message"],
        "fetched_at": row["fetched_at"],
    }


async def _price_krw(
    quote: MarketQuote,
    *,
    db: sqlite3.Connection,
    fx_provider: FrankfurterProvider,
) -> float:
    if quote.currency.upper() == "KRW":
        return quote.price

    rate = await fx_provider.fetch_rate(quote.currency, "KRW")
    db.execute(
        """
        insert or ignore into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
        values (?, ?, ?, ?, ?)
        """,
        (rate.base_currency, rate.quote_currency, rate.rate, rate.source, _now_iso()),
    )
    return quote.price * rate.rate


async def _fetch_quote(
    asset: sqlite3.Row,
    *,
    alpha_provider: AlphaVantageProvider,
    coingecko_provider: CoinGeckoProvider,
) -> MarketQuote:
    asset_type = str(asset["type"])
    symbol = str(asset["symbol"])
    if asset_type == "crypto":
        return await coingecko_provider.fetch_crypto_quote(symbol.lower(), vs_currency="krw")
    return await alpha_provider.fetch_equity_quote(symbol)


@router.post("/manual-price", status_code=status.HTTP_201_CREATED)
def create_manual_price(payload: ManualPriceCreate, db: Db) -> dict[str, object]:
    price_krw = require_positive_number(payload.price_krw, "가격은 0보다 커야 합니다.")
    source = require_non_empty(payload.source, "시세 출처를 입력해 주세요.")
    asset = db.execute("select * from assets where id = ?", (payload.asset_id,)).fetchone()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="자산을 찾을 수 없습니다.",
        )

    with db:
        db.execute(
            "update assets set manual_price_krw = ?, updated_at = current_timestamp where id = ?",
            (price_krw, payload.asset_id),
        )
        row = _insert_snapshot(
            db,
            asset_id=payload.asset_id,
            source=source,
            price=price_krw,
            currency="KRW",
            price_krw=price_krw,
            status="manual",
            error_message=payload.error_message,
        )

    return row_to_dict(row)


@router.get("/status")
def list_market_data_status(db: Db) -> list[dict[str, object]]:
    rows = db.execute(
        """
        select ps.asset_id, ps.source, ps.price_krw, ps.status, ps.error_message, ps.fetched_at
        from price_snapshots ps
        where ps.id = (
            select latest.id
            from price_snapshots latest
            where latest.asset_id = ps.asset_id
            order by latest.fetched_at desc, latest.id desc
            limit 1
        )
        order by ps.asset_id
        """
    ).fetchall()
    return [_snapshot_response(row) for row in rows]


async def _sync_market_data(
    request: Request,
    db: sqlite3.Connection,
) -> dict[str, list[dict[str, object]]]:
    settings = request.app.state.settings
    assets = db.execute(
        """
        select *
        from assets
        where symbol is not null
          and trim(symbol) != ''
          and type in ('stock_etf', 'crypto')
        order by id
        """
    ).fetchall()
    alpha_provider = AlphaVantageProvider(settings.alpha_vantage_api_key)
    coingecko_provider = CoinGeckoProvider()
    fx_provider = FrankfurterProvider()
    results: list[dict[str, object]] = []

    for asset in assets:
        asset_id = int(asset["id"])
        symbol = str(asset["symbol"])
        try:
            quote = await _fetch_quote(
                asset,
                alpha_provider=alpha_provider,
                coingecko_provider=coingecko_provider,
            )
            price_krw = await _price_krw(quote, db=db, fx_provider=fx_provider)
            with db:
                _insert_snapshot(
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
        except (ValueError, sqlite3.Error) as exc:
            error_message = str(exc)
            previous = _latest_snapshot(db, asset_id)
            with db:
                if previous is None:
                    _insert_snapshot(
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
                    _insert_snapshot(
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

    return {"results": results}


@router.post("/sync")
def sync_market_data(request: Request, db: Db) -> dict[str, list[dict[str, object]]]:
    return asyncio.run(_sync_market_data(request, db))
