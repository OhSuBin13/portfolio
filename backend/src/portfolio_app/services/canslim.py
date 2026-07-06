import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx

FMP_BASE_URL = "https://financialmodelingprep.com"
FMP_TOP_HOLDER_LIMIT = 10
FMP_MARKET_RANGE_DAYS = {
    "3m": 90,
    "6m": 182,
    "1y": 365,
}


@dataclass
class FmpCompanyProfile:
    symbol: str
    company_name: str | None
    exchange: str | None
    sector: str | None
    industry: str | None
    description: str | None
    currency: str | None
    is_etf: bool | None


@dataclass
class FmpIncomeRow:
    date: str | None
    period: str | None
    calendar_year: int | None
    eps_diluted: float | None


@dataclass
class FmpPriceRow:
    symbol: str
    date: str | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    vwap: float | None
    traded_value_usd: float | None


@dataclass
class FmpFloatData:
    symbol: str
    float_shares: float | None
    outstanding_shares: float | None


@dataclass
class FmpPositionsSummary:
    symbol: str
    year: int | None
    quarter: int | None
    holders_count: int | None
    holders_count_change: float | None
    shares_count: float | None
    shares_count_change: float | None
    ownership_percent: float | None
    market_value_change: float | None


@dataclass
class FmpTopHolder:
    holder: str | None
    cik: str | None
    shares: float | None
    market_value: float | None
    change: float | None
    weight: float | None
    performance_1y_percent: float | None
    performance_3y_percent: float | None
    performance_5y_percent: float | None
    performance_relative_to_sp500_percent: float | None


@dataclass
class FmpCanslimBundle:
    symbol: str
    profile: FmpCompanyProfile
    quarterly_income: list[FmpIncomeRow]
    annual_income: list[FmpIncomeRow]
    prices: list[FmpPriceRow]
    spy_prices: list[FmpPriceRow]
    float_data: FmpFloatData
    peers: list[str]
    positions_summary: FmpPositionsSummary | None
    top_holders: list[FmpTopHolder]


@dataclass(frozen=True)
class Fmp13fPeriod:
    year: int
    quarter: int
    date: str


class FmpProviderError(RuntimeError):
    pass


Today = Callable[[], date | str]


def normalize_symbol(symbol: str) -> str:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("종목 심볼을 입력해 주세요.")
    return normalized_symbol


class FmpCanslimProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = FMP_BASE_URL,
        today: Today = date.today,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self._today = today

    async def fetch_bundle(self, symbol: str, *, market_range: str = "6m") -> FmpCanslimBundle:
        if not self.api_key:
            raise ValueError("FMP API 키를 설정해 주세요.")

        normalized_symbol = normalize_symbol(symbol)
        today = _today_date(self._today())
        stock_from = (today - timedelta(days=365)).isoformat()
        market_from = (today - timedelta(days=_market_range_days(market_range) - 1)).isoformat()
        to_date = today.isoformat()
        period_13f = _latest_filed_13f_period(today)

        async with httpx.AsyncClient(timeout=10.0) as client:
            profile_payload = await self._get_json(
                client,
                "/stable/profile",
                {"symbol": normalized_symbol, "apikey": self.api_key},
            )
            quarterly_income_payload = await self._get_json(
                client,
                "/stable/income-statement",
                {
                    "symbol": normalized_symbol,
                    "period": "quarter",
                    "limit": 8,
                    "apikey": self.api_key,
                },
            )
            annual_income_payload = await self._get_json(
                client,
                "/stable/income-statement",
                {
                    "symbol": normalized_symbol,
                    "period": "annual",
                    "limit": 5,
                    "apikey": self.api_key,
                },
            )
            prices_payload = await self._get_json(
                client,
                "/stable/historical-price-eod/full",
                {
                    "symbol": normalized_symbol,
                    "from": stock_from,
                    "to": to_date,
                    "apikey": self.api_key,
                },
            )
            spy_prices_payload = await self._get_json(
                client,
                "/stable/historical-price-eod/full",
                {
                    "symbol": "SPY",
                    "from": market_from,
                    "to": to_date,
                    "apikey": self.api_key,
                },
            )
            float_payload = await self._get_json(
                client,
                "/stable/shares-float",
                {"symbol": normalized_symbol, "apikey": self.api_key},
            )
            peers_payload = await self._get_json(
                client,
                "/stable/stock-peers",
                {"symbol": normalized_symbol, "apikey": self.api_key},
            )
            positions_payload = await self._optional_get_json(
                client,
                "/stable/institutional-ownership/symbol-positions-summary",
                {
                    "symbol": normalized_symbol,
                    "year": period_13f.year,
                    "quarter": period_13f.quarter,
                    "apikey": self.api_key,
                },
            )
            positions_summary = None
            top_holders: list[FmpTopHolder] = []
            if positions_payload is not None:
                positions_summary = _parse_positions_summary(
                    _first_item(positions_payload),
                    normalized_symbol,
                )
                holders_payload = await self._optional_get_json(
                    client,
                    "/api/v4/institutional-ownership/institutional-holders/symbol-ownership",
                    {
                        "page": 0,
                        "date": period_13f.date,
                        "symbol": normalized_symbol,
                        "apikey": self.api_key,
                    },
                )
                if holders_payload is not None:
                    top_holders = await self._parse_top_holders(client, holders_payload)

        profile = _parse_profile(_first_item(profile_payload), normalized_symbol)
        return FmpCanslimBundle(
            symbol=normalized_symbol,
            profile=profile,
            quarterly_income=_parse_income_rows(quarterly_income_payload),
            annual_income=_parse_income_rows(annual_income_payload),
            prices=_parse_price_rows(prices_payload, normalized_symbol),
            spy_prices=_parse_price_rows(spy_prices_payload, "SPY"),
            float_data=_parse_float_data(_first_item(float_payload), normalized_symbol),
            peers=_parse_peers(peers_payload),
            positions_summary=positions_summary,
            top_holders=top_holders,
        )

    async def _parse_top_holders(
        self,
        client: httpx.AsyncClient,
        payload: Any,
    ) -> list[FmpTopHolder]:
        top_holders: list[FmpTopHolder] = []
        for item in _items(payload)[:FMP_TOP_HOLDER_LIMIT]:
            cik = _optional_text(item.get("cik"))
            performance_payload = None
            if cik is not None:
                performance_payload = await self._optional_get_json(
                    client,
                    "/stable/institutional-ownership/holder-performance-summary",
                    {"cik": cik, "page": 0, "apikey": self.api_key},
                )
            top_holders.append(_parse_top_holder(item, _first_item(performance_payload)))
        return top_holders

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, object],
    ) -> Any:
        try:
            response = await client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise FmpProviderError(_safe_http_error_message(exc)) from exc
        except ValueError as exc:
            raise FmpProviderError("FMP 응답을 해석할 수 없습니다.") from exc

    async def _optional_get_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, object],
    ) -> Any | None:
        try:
            return await self._get_json(client, path, params)
        except FmpProviderError:
            return None


def _today_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _market_range_days(market_range: str) -> int:
    normalized_range = market_range.strip().lower()
    try:
        return FMP_MARKET_RANGE_DAYS[normalized_range]
    except KeyError as exc:
        raise ValueError("지원하지 않는 시장 범위입니다.") from exc


def _latest_filed_13f_period(today: date) -> Fmp13fPeriod:
    filed_as_of = today - timedelta(days=45)
    quarter_ends = [
        (1, date(filed_as_of.year, 3, 31)),
        (2, date(filed_as_of.year, 6, 30)),
        (3, date(filed_as_of.year, 9, 30)),
        (4, date(filed_as_of.year, 12, 31)),
    ]
    for quarter, quarter_end in reversed(quarter_ends):
        if filed_as_of >= quarter_end:
            return Fmp13fPeriod(
                year=quarter_end.year,
                quarter=quarter,
                date=quarter_end.isoformat(),
            )

    previous_year_end = date(filed_as_of.year - 1, 12, 31)
    return Fmp13fPeriod(
        year=previous_year_end.year,
        quarter=4,
        date=previous_year_end.isoformat(),
    )


def _safe_http_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        reason = response.reason_phrase or "Unknown"
        return f"FMP 요청 실패: HTTP {response.status_code} {reason}"
    return f"FMP 요청 실패: {exc.__class__.__name__}"


def _items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _first_item(payload: Any) -> dict[str, Any] | None:
    items = _items(payload)
    return items[0] if items else None


def _parse_profile(item: dict[str, Any] | None, fallback_symbol: str) -> FmpCompanyProfile:
    item = item or {}
    symbol = _optional_text(item.get("symbol")) or fallback_symbol
    return FmpCompanyProfile(
        symbol=symbol.upper(),
        company_name=_optional_text(item.get("companyName")),
        exchange=_optional_text(item.get("exchangeShortName")),
        sector=_optional_text(item.get("sector")),
        industry=_optional_text(item.get("industry")),
        description=_optional_text(item.get("description")),
        currency=_optional_text(item.get("currency")),
        is_etf=_optional_bool(item.get("isEtf")),
    )


def _parse_income_rows(payload: Any) -> list[FmpIncomeRow]:
    return [
        FmpIncomeRow(
            date=_optional_text(item.get("date")),
            period=_optional_text(item.get("period")),
            calendar_year=_optional_int(item.get("calendarYear")),
            eps_diluted=_optional_float(item.get("epsdiluted")),
        )
        for item in _items(payload)
    ]


def _parse_price_rows(payload: Any, fallback_symbol: str) -> list[FmpPriceRow]:
    rows: list[FmpPriceRow] = []
    for item in _items(payload):
        symbol = (_optional_text(item.get("symbol")) or fallback_symbol).upper()
        close = _optional_float(item.get("close"))
        volume = _optional_float(item.get("volume"))
        vwap = _optional_float(item.get("vwap"))
        rows.append(
            FmpPriceRow(
                symbol=symbol,
                date=_optional_text(item.get("date")),
                open=_optional_float(item.get("open")),
                high=_optional_float(item.get("high")),
                low=_optional_float(item.get("low")),
                close=close,
                volume=volume,
                vwap=vwap,
                traded_value_usd=_traded_value_usd(close=close, volume=volume, vwap=vwap),
            )
        )
    return rows


def _parse_float_data(item: dict[str, Any] | None, fallback_symbol: str) -> FmpFloatData:
    item = item or {}
    symbol = (_optional_text(item.get("symbol")) or fallback_symbol).upper()
    return FmpFloatData(
        symbol=symbol,
        float_shares=_optional_float(item.get("floatShares")),
        outstanding_shares=_optional_float(item.get("outstandingShares")),
    )


def _parse_peers(payload: Any) -> list[str]:
    peers: list[str] = []
    if not isinstance(payload, list):
        return peers

    for item in payload:
        if isinstance(item, dict):
            peer = _optional_text(item.get("symbol"))
        elif isinstance(item, str):
            peer = _optional_text(item)
        else:
            peer = None
        if peer is not None:
            peers.append(peer.upper())
    return peers


def _parse_positions_summary(
    item: dict[str, Any] | None,
    fallback_symbol: str,
) -> FmpPositionsSummary:
    item = item or {}
    symbol = (_optional_text(item.get("symbol")) or fallback_symbol).upper()
    return FmpPositionsSummary(
        symbol=symbol,
        year=_optional_int(item.get("year")),
        quarter=_optional_int(item.get("quarter")),
        holders_count=_optional_int(item.get("investorsHolding")),
        holders_count_change=_optional_float(item.get("investorsHoldingChange")),
        shares_count=_optional_float(item.get("numberOfShares")),
        shares_count_change=_optional_float(item.get("numberOfSharesChange")),
        ownership_percent=_optional_float(item.get("ownershipPercent")),
        market_value_change=_optional_float(item.get("marketValueChange")),
    )


def _parse_top_holder(
    item: dict[str, Any],
    performance_item: dict[str, Any] | None,
) -> FmpTopHolder:
    performance_item = performance_item or {}
    return FmpTopHolder(
        holder=_optional_text(item.get("holder")),
        cik=_optional_text(item.get("cik")),
        shares=_optional_float(item.get("shares")),
        market_value=_optional_float(item.get("marketValue")),
        change=_optional_float(item.get("change")),
        weight=_optional_float(item.get("weight")),
        performance_1y_percent=_ratio_to_percent(performance_item.get("performance1year")),
        performance_3y_percent=_ratio_to_percent(performance_item.get("performance3year")),
        performance_5y_percent=_ratio_to_percent(performance_item.get("performance5year")),
        performance_relative_to_sp500_percent=_ratio_to_percent(
            performance_item.get("performanceRelativeToSP500")
        ),
    )


def _traded_value_usd(
    *,
    close: float | None,
    volume: float | None,
    vwap: float | None,
) -> float | None:
    if volume is None:
        return None
    price = vwap if vwap is not None and vwap > 0 else close
    if price is None:
        return None
    return price * volume


def _ratio_to_percent(value: Any) -> float | None:
    number = _optional_float(value)
    if number is None:
        return None
    return number * 100


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _optional_int(value: Any) -> int | None:
    number = _optional_float(value)
    if number is None:
        return None
    return int(number)


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized_value = value.strip().lower()
        if normalized_value in {"true", "1", "yes"}:
            return True
        if normalized_value in {"false", "0", "no"}:
            return False
    return None
