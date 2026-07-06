# CAN SLIM Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a US-stock CAN SLIM analysis screen backed by a backend-owned FMP provider.

**Architecture:** Add a new backend `canslim` service/provider boundary that fetches normalized FMP data, calculates C/A/N/S/L/I evidence, returns SPY market context for M, and caches provider payloads in SQLite. Expose it through `GET /api/canslim/analysis`, then add a dedicated React page that searches arbitrary US stock symbols without calling FMP from the browser.

**Tech Stack:** FastAPI, Pydantic v2, httpx, SQLite migrations/repositories, pytest/pytest-httpx, React/Vite/TypeScript, source-inspection frontend tests.

---

## References

- Approved spec: `docs/superpowers/specs/2026-07-06-canslim-analysis-design.md`
- FMP docs: `https://site.financialmodelingprep.com/developer/docs`
- FMP profile endpoint: `https://site.financialmodelingprep.com/developer/docs/stable/profile-symbol`
- FMP income statement endpoint: `https://site.financialmodelingprep.com/developer/docs/stable/income-statement`
- FMP price/volume endpoint: `https://site.financialmodelingprep.com/developer/docs/stable/historical-price-eod-full`
- FMP peers endpoint: `https://site.financialmodelingprep.com/developer/docs/stable/peers`
- FMP shares float endpoint: `https://site.financialmodelingprep.com/developer/docs/stable/shares-float`
- FMP positions summary endpoint: `https://site.financialmodelingprep.com/developer/docs/stable/positions-summary`
- FMP holder performance endpoint: `https://site.financialmodelingprep.com/developer/docs/stable/holder-performance-summary`

## File Structure

Backend files:

- Create `backend/src/portfolio_app/services/canslim.py`
  - FMP provider, normalized dataclasses, rule calculations, SPY traded-value conversion, cache orchestration.
- Create `backend/src/portfolio_app/api/canslim.py`
  - FastAPI route, request validation, provider/cache wiring, safe error translation.
- Modify `backend/src/portfolio_app/config.py`
  - Add `fmp_api_key`.
- Modify `backend/src/portfolio_app/models.py`
  - Add Pydantic response models for the CAN SLIM API.
- Modify `backend/src/portfolio_app/schema.sql`
  - Add `canslim_cache_entries`.
- Modify `backend/src/portfolio_app/migrations.py`
  - Bump schema version from 15 to 16 and add v15->v16 migration.
- Modify `backend/src/portfolio_app/repositories.py`
  - Add cache fetch/upsert/delete helpers.
- Modify `backend/src/portfolio_app/main.py`
  - Register the `canslim` router.
- Create `backend/tests/test_canslim.py`
  - Provider parser, rule, and cache orchestration tests.
- Modify `backend/tests/test_api.py`
  - OpenAPI and HTTP route behavior tests.
- Modify `backend/tests/test_db.py`
  - Fresh schema and v15 migration tests.

Frontend files:

- Modify `frontend/src/types.ts`
  - Add `CanslimAnalysis` and nested types.
- Create `frontend/src/components/CanslimPage.tsx`
  - Search UI, status tiles, institutional section, SPY context chart.
- Modify `frontend/src/components/AppShell.tsx`
  - Add `CAN SLIM` nav item.
- Modify `frontend/src/App.tsx`
  - Mount `CanslimPage`.
- Modify `frontend/src/styles.css`
  - Add compact analysis screen, status tiles, holder table, and SPY chart styles.
- Create `frontend/tests/canslim-page.test.mjs`
  - Source-inspection coverage for the new page.
- Modify `frontend/package.json`
  - Add the new test to `npm test`.

Docs:

- Modify `README.md`
  - Document `PORTFOLIO_FMP_API_KEY` and the US-only CAN SLIM flow.

---

### Task 1: FMP Settings And Provider Parser

**Files:**
- Modify: `backend/src/portfolio_app/config.py`
- Create: `backend/src/portfolio_app/services/canslim.py`
- Test: `backend/tests/test_canslim.py`

- [ ] **Step 1: Write failing provider tests**

Create `backend/tests/test_canslim.py` with these tests:

```python
import pytest

from portfolio_app.config import Settings
from portfolio_app.services.canslim import (
    FmpCanslimProvider,
    FmpProviderError,
    normalize_symbol,
)


@pytest.mark.asyncio
async def test_fmp_provider_requires_api_key():
    provider = FmpCanslimProvider("")

    with pytest.raises(ValueError, match="FMP API 키를 설정해 주세요."):
        await provider.fetch_bundle("NVDA", market_range="6m")


def test_normalize_symbol_trims_and_uppercases():
    assert normalize_symbol(" nvda ") == "NVDA"


@pytest.mark.parametrize("symbol", ["", "   "])
def test_normalize_symbol_rejects_blank(symbol):
    with pytest.raises(ValueError, match="종목 심볼을 입력해 주세요."):
        normalize_symbol(symbol)


@pytest.mark.asyncio
async def test_fmp_provider_fetches_and_normalizes_bundle(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/profile?symbol=NVDA&apikey=fmp-key",
        json=[
            {
                "symbol": "NVDA",
                "companyName": "NVIDIA Corporation",
                "exchangeShortName": "NASDAQ",
                "sector": "Technology",
                "industry": "Semiconductors",
                "description": "NVIDIA designs accelerated computing products.",
                "currency": "USD",
                "isEtf": False,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/income-statement"
            "?symbol=NVDA&period=quarter&limit=8&apikey=fmp-key"
        ),
        json=[
            {"date": "2026-04-30", "period": "Q1", "epsdiluted": 1.20},
            {"date": "2025-04-30", "period": "Q1", "epsdiluted": 0.60},
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/income-statement"
            "?symbol=NVDA&period=annual&limit=5&apikey=fmp-key"
        ),
        json=[
            {"date": "2026-01-31", "calendarYear": "2026", "epsdiluted": 4.00},
            {"date": "2025-01-31", "calendarYear": "2025", "epsdiluted": 2.50},
            {"date": "2024-01-31", "calendarYear": "2024", "epsdiluted": 1.50},
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/historical-price-eod/full"
            "?symbol=NVDA&from=2025-07-06&to=2026-07-06&apikey=fmp-key"
        ),
        json=[
            {
                "symbol": "NVDA",
                "date": "2026-07-02",
                "open": 150,
                "high": 156,
                "low": 149,
                "close": 155,
                "volume": 150_000_000,
                "vwap": 153.5,
            },
            {
                "symbol": "NVDA",
                "date": "2026-07-01",
                "open": 148,
                "high": 151,
                "low": 147,
                "close": 150,
                "volume": 100_000_000,
                "vwap": 149.5,
            },
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/historical-price-eod/full"
            "?symbol=SPY&from=2026-01-06&to=2026-07-06&apikey=fmp-key"
        ),
        json=[
            {
                "symbol": "SPY",
                "date": "2026-07-02",
                "open": 620,
                "high": 625,
                "low": 618,
                "close": 624,
                "volume": 60_000_000,
                "vwap": 622.5,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/shares-float?symbol=NVDA&apikey=fmp-key",
        json=[{"symbol": "NVDA", "floatShares": 22_000_000_000, "outstandingShares": 24_000_000_000}],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/peers?symbol=NVDA&apikey=fmp-key",
        json=[{"symbol": "AMD"}, {"symbol": "AVGO"}],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/institutional-ownership/"
            "symbol-positions-summary?symbol=NVDA&apikey=fmp-key"
        ),
        json=[
            {
                "symbol": "NVDA",
                "year": 2026,
                "quarter": 1,
                "investorsHolding": 4100,
                "investorsHoldingChange": 120,
                "numberOfShares": 14_000_000_000,
                "numberOfSharesChange": 0.08,
                "ownershipPercent": 0.57,
                "marketValueChange": 0.11,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/api/v4/institutional-ownership/"
            "institutional-holders/symbol-ownership?page=0&symbol=NVDA&apikey=fmp-key"
        ),
        json=[
            {
                "holder": "High Quality Capital",
                "cik": "0000000001",
                "shares": 10_000_000,
                "marketValue": 1_550_000_000,
                "change": 0.2,
                "weight": 0.04,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/institutional-ownership/"
            "holder-performance-summary?cik=0000000001&page=0&apikey=fmp-key"
        ),
        json=[
            {
                "cik": "0000000001",
                "holder": "High Quality Capital",
                "performance1year": 0.32,
                "performance3year": 0.85,
                "performance5year": 1.6,
                "performanceRelativeToSP500": 0.21,
            }
        ],
    )

    provider = FmpCanslimProvider(
        "fmp-key",
        today=lambda: "2026-07-06",
    )

    bundle = await provider.fetch_bundle(" nvda ", market_range="6m")

    assert bundle.profile.symbol == "NVDA"
    assert bundle.profile.company_name == "NVIDIA Corporation"
    assert bundle.profile.exchange == "NASDAQ"
    assert bundle.profile.currency == "USD"
    assert bundle.quarterly_income[0].eps_diluted == 1.20
    assert bundle.annual_income[0].calendar_year == 2026
    assert bundle.prices[0].date == "2026-07-02"
    assert bundle.spy_prices[0].traded_value_usd == 37_350_000_000.0
    assert bundle.float_data.float_shares == 22_000_000_000
    assert bundle.peers == ["AMD", "AVGO"]
    assert bundle.positions_summary.holders_count_change == 120
    assert bundle.top_holders[0].performance_1y_percent == 32.0


@pytest.mark.asyncio
async def test_fmp_provider_raises_safe_error_for_http_failure(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/profile?symbol=NVDA&apikey=fmp-key",
        status_code=403,
        json={"Error Message": "secret provider detail"},
    )
    provider = FmpCanslimProvider("fmp-key")

    with pytest.raises(FmpProviderError) as exc_info:
        await provider.fetch_bundle("NVDA", market_range="6m")

    assert str(exc_info.value) == "FMP 요청 실패: HTTP 403 Forbidden"
    assert "secret provider detail" not in str(exc_info.value)
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_canslim.py::test_fmp_provider_requires_api_key backend/tests/test_canslim.py::test_normalize_symbol_trims_and_uppercases backend/tests/test_canslim.py::test_fmp_provider_fetches_and_normalizes_bundle -q
```

Expected: FAIL with import errors for `portfolio_app.services.canslim`.

- [ ] **Step 3: Implement settings and minimal provider parser**

Modify `backend/src/portfolio_app/config.py`:

```python
class Settings(BaseSettings):
    data_dir: Path = Path("data")
    database_path: Path = Path("data/portfolio.sqlite")
    backup_dir: Path = Path("data/backups")
    market_sync_enabled: bool = True
    market_sync_interval_seconds: int = Field(default=300, gt=0)
    toss_api_key: str = ""
    toss_secret_key: str = ""
    fmp_api_key: str = ""
    backup_enabled: bool = True
    backup_interval_seconds: int = Field(default=3600, gt=0)
```

Create `backend/src/portfolio_app/services/canslim.py` with this initial content:

```python
import asyncio
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

import httpx

FMP_BASE_URL = "https://financialmodelingprep.com"
SUPPORTED_MARKET_RANGES = {"3m": 90, "6m": 182, "1y": 365}
TOP_HOLDER_LIMIT = 10

CanslimStatus = Literal["pass", "watch", "fail", "unknown", "info"]


class FmpProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class FmpCompanyProfile:
    symbol: str
    company_name: str
    exchange: str
    sector: str | None
    industry: str | None
    description: str
    currency: str
    is_etf: bool


@dataclass(frozen=True)
class FmpIncomeRow:
    date: str
    period: str
    calendar_year: int | None
    eps_diluted: float | None


@dataclass(frozen=True)
class FmpPriceRow:
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None

    @property
    def traded_value_usd(self) -> float:
        basis = self.vwap if self.vwap is not None and self.vwap > 0 else self.close
        return basis * self.volume


@dataclass(frozen=True)
class FmpFloatData:
    float_shares: float | None
    outstanding_shares: float | None


@dataclass(frozen=True)
class FmpPositionsSummary:
    holders_count_change: float | None
    shares_change_percent: float | None
    ownership_percent: float | None
    market_value_change_percent: float | None


@dataclass(frozen=True)
class FmpTopHolder:
    holder_name: str
    cik: str
    shares: float
    market_value: float
    position_change_percent: float | None
    portfolio_weight_percent: float | None
    performance_1y_percent: float | None
    performance_3y_percent: float | None
    performance_5y_percent: float | None
    excess_vs_sp500_percent: float | None


@dataclass(frozen=True)
class FmpCanslimBundle:
    profile: FmpCompanyProfile
    quarterly_income: list[FmpIncomeRow]
    annual_income: list[FmpIncomeRow]
    prices: list[FmpPriceRow]
    spy_prices: list[FmpPriceRow]
    float_data: FmpFloatData
    peers: list[str]
    positions_summary: FmpPositionsSummary | None
    top_holders: list[FmpTopHolder]


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("종목 심볼을 입력해 주세요.")
    return normalized


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _required_float(value: Any, message: str) -> float:
    number = _optional_float(value)
    if number is None:
        raise ValueError(message)
    return number


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _safe_http_error(exc: httpx.HTTPError) -> FmpProviderError:
    if isinstance(exc, httpx.HTTPStatusError):
        return FmpProviderError(
            f"FMP 요청 실패: HTTP {exc.response.status_code} {exc.response.reason_phrase}"
        )
    return FmpProviderError(f"FMP 요청 실패: {exc.__class__.__name__}")


class FmpCanslimProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = FMP_BASE_URL,
        today: Callable[[], str] | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self._today = today or (lambda: date.today().isoformat())

    async def fetch_bundle(
        self,
        symbol: str,
        *,
        market_range: str = "6m",
    ) -> FmpCanslimBundle:
        if not self.api_key:
            raise ValueError("FMP API 키를 설정해 주세요.")
        normalized_symbol = normalize_symbol(symbol)
        if market_range not in SUPPORTED_MARKET_RANGES:
            raise ValueError("시장 컨텍스트 기간은 3m, 6m, 1y 중 하나여야 합니다.")

        today = date.fromisoformat(self._today())
        price_from = today - timedelta(days=365)
        spy_from = today - timedelta(days=SUPPORTED_MARKET_RANGES[market_range])

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                (
                    profile_payload,
                    quarterly_payload,
                    annual_payload,
                    prices_payload,
                    spy_payload,
                    float_payload,
                    peers_payload,
                    positions_payload,
                    holders_payload,
                ) = await asyncio.gather(
                    self._get(client, "/stable/profile", symbol=normalized_symbol),
                    self._get(
                        client,
                        "/stable/income-statement",
                        symbol=normalized_symbol,
                        period="quarter",
                        limit=8,
                    ),
                    self._get(
                        client,
                        "/stable/income-statement",
                        symbol=normalized_symbol,
                        period="annual",
                        limit=5,
                    ),
                    self._get(
                        client,
                        "/stable/historical-price-eod/full",
                        symbol=normalized_symbol,
                        **{"from": price_from.isoformat(), "to": today.isoformat()},
                    ),
                    self._get(
                        client,
                        "/stable/historical-price-eod/full",
                        symbol="SPY",
                        **{"from": spy_from.isoformat(), "to": today.isoformat()},
                    ),
                    self._get(client, "/stable/shares-float", symbol=normalized_symbol),
                    self._get(client, "/stable/peers", symbol=normalized_symbol),
                    self._get(
                        client,
                        "/stable/institutional-ownership/symbol-positions-summary",
                        symbol=normalized_symbol,
                    ),
                    self._get(
                        client,
                        "/api/v4/institutional-ownership/"
                        "institutional-holders/symbol-ownership",
                        page=0,
                        symbol=normalized_symbol,
                    ),
                )
            except httpx.HTTPError as exc:
                raise _safe_http_error(exc) from exc

            top_holders = await self._top_holders_with_performance(
                client,
                _parse_holder_seed_rows(holders_payload),
            )

        return FmpCanslimBundle(
            profile=_parse_profile(profile_payload),
            quarterly_income=_parse_income_rows(quarterly_payload),
            annual_income=_parse_income_rows(annual_payload),
            prices=_parse_price_rows(prices_payload),
            spy_prices=_parse_price_rows(spy_payload),
            float_data=_parse_float_data(float_payload),
            peers=_parse_peers(peers_payload),
            positions_summary=_parse_positions_summary(positions_payload),
            top_holders=top_holders,
        )

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        **params: object,
    ) -> object:
        response = await client.get(
            f"{self.base_url}{path}",
            params={**params, "apikey": self.api_key},
        )
        response.raise_for_status()
        return response.json()

    async def _top_holders_with_performance(
        self,
        client: httpx.AsyncClient,
        seeds: list[dict[str, object]],
    ) -> list[FmpTopHolder]:
        holders: list[FmpTopHolder] = []
        for seed in seeds[:TOP_HOLDER_LIMIT]:
            cik = _text(seed.get("cik"))
            performance = {}
            if cik:
                try:
                    payload = await self._get(
                        client,
                        "/stable/institutional-ownership/holder-performance-summary",
                        cik=cik,
                        page=0,
                    )
                    performance = _first_dict(payload)
                except httpx.HTTPError as exc:
                    raise _safe_http_error(exc) from exc
            holders.append(_parse_top_holder(seed, performance))
        return holders


def _first_dict(payload: object) -> dict[str, object]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if isinstance(payload, dict):
        return payload
    return {}


def _parse_profile(payload: object) -> FmpCompanyProfile:
    item = _first_dict(payload)
    return FmpCompanyProfile(
        symbol=_text(item.get("symbol")).upper(),
        company_name=_text(item.get("companyName") or item.get("company_name")),
        exchange=_text(item.get("exchangeShortName") or item.get("exchange")),
        sector=_text(item.get("sector")) or None,
        industry=_text(item.get("industry")) or None,
        description=_text(item.get("description")),
        currency=_text(item.get("currency")).upper(),
        is_etf=bool(item.get("isEtf") or item.get("is_etf")),
    )


def _parse_income_rows(payload: object) -> list[FmpIncomeRow]:
    if not isinstance(payload, list):
        return []
    rows: list[FmpIncomeRow] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        calendar_year_text = _text(item.get("calendarYear") or item.get("calendar_year"))
        rows.append(
            FmpIncomeRow(
                date=_text(item.get("date")),
                period=_text(item.get("period")),
                calendar_year=int(calendar_year_text) if calendar_year_text.isdigit() else None,
                eps_diluted=_optional_float(item.get("epsdiluted") or item.get("epsDiluted")),
            )
        )
    return rows


def _parse_price_rows(payload: object) -> list[FmpPriceRow]:
    if not isinstance(payload, list):
        return []
    rows: list[FmpPriceRow] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        rows.append(
            FmpPriceRow(
                symbol=_text(item.get("symbol")).upper(),
                date=_text(item.get("date")),
                open=_required_float(item.get("open"), "FMP 가격 시가가 필요합니다."),
                high=_required_float(item.get("high"), "FMP 가격 고가가 필요합니다."),
                low=_required_float(item.get("low"), "FMP 가격 저가가 필요합니다."),
                close=_required_float(item.get("close"), "FMP 가격 종가가 필요합니다."),
                volume=_required_float(item.get("volume"), "FMP 거래량이 필요합니다."),
                vwap=_optional_float(item.get("vwap")),
            )
        )
    return rows


def _parse_float_data(payload: object) -> FmpFloatData:
    item = _first_dict(payload)
    return FmpFloatData(
        float_shares=_optional_float(item.get("floatShares") or item.get("float_shares")),
        outstanding_shares=_optional_float(
            item.get("outstandingShares") or item.get("outstanding_shares")
        ),
    )


def _parse_peers(payload: object) -> list[str]:
    if not isinstance(payload, list):
        return []
    peers: list[str] = []
    for item in payload:
        if isinstance(item, str):
            symbol = item
        elif isinstance(item, dict):
            symbol = _text(item.get("symbol"))
        else:
            symbol = ""
        if symbol:
            peers.append(symbol.upper())
    return peers


def _parse_positions_summary(payload: object) -> FmpPositionsSummary | None:
    item = _first_dict(payload)
    if not item:
        return None
    return FmpPositionsSummary(
        holders_count_change=_optional_float(
            item.get("investorsHoldingChange") or item.get("holdersCountChange")
        ),
        shares_change_percent=_optional_float(
            item.get("numberOfSharesChange") or item.get("sharesChangePercent")
        ),
        ownership_percent=_optional_float(item.get("ownershipPercent")),
        market_value_change_percent=_optional_float(
            item.get("marketValueChange") or item.get("marketValueChangePercent")
        ),
    )


def _parse_holder_seed_rows(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _parse_top_holder(seed: dict[str, object], performance: dict[str, object]) -> FmpTopHolder:
    return FmpTopHolder(
        holder_name=_text(seed.get("holder") or seed.get("holderName")),
        cik=_text(seed.get("cik")),
        shares=_optional_float(seed.get("shares")) or 0.0,
        market_value=_optional_float(seed.get("marketValue") or seed.get("market_value")) or 0.0,
        position_change_percent=_optional_float(seed.get("change") or seed.get("changePercent")),
        portfolio_weight_percent=_optional_float(seed.get("weight") or seed.get("weightPercent")),
        performance_1y_percent=_percent(
            performance.get("performance1year") or performance.get("performance_1y")
        ),
        performance_3y_percent=_percent(
            performance.get("performance3year") or performance.get("performance_3y")
        ),
        performance_5y_percent=_percent(
            performance.get("performance5year") or performance.get("performance_5y")
        ),
        excess_vs_sp500_percent=_percent(
            performance.get("performanceRelativeToSP500")
            or performance.get("excess_vs_sp500")
        ),
    )


def _percent(value: object) -> float | None:
    number = _optional_float(value)
    return number * 100 if number is not None and abs(number) <= 10 else number
```

- [ ] **Step 4: Run provider tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_canslim.py -q
.venv/bin/python -m ruff check backend/src/portfolio_app/config.py backend/src/portfolio_app/services/canslim.py backend/tests/test_canslim.py
```

Expected: PASS.

- [ ] **Step 5: Commit provider boundary**

```bash
git add backend/src/portfolio_app/config.py backend/src/portfolio_app/services/canslim.py backend/tests/test_canslim.py
git commit -m "feat: add FMP CAN SLIM provider"
```

---

### Task 2: CAN SLIM Rule Calculations

**Files:**
- Modify: `backend/src/portfolio_app/services/canslim.py`
- Test: `backend/tests/test_canslim.py`

- [ ] **Step 1: Write failing rule tests**

Append these tests to `backend/tests/test_canslim.py`:

```python
from portfolio_app.services.canslim import (
    FmpCanslimBundle,
    FmpCompanyProfile,
    FmpFloatData,
    FmpIncomeRow,
    FmpPositionsSummary,
    FmpPriceRow,
    FmpTopHolder,
    build_canslim_analysis,
)


def profile(**overrides):
    values = {
        "symbol": "NVDA",
        "company_name": "NVIDIA Corporation",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "industry": "Semiconductors",
        "description": "NVIDIA designs accelerated computing products.",
        "currency": "USD",
        "is_etf": False,
    }
    values.update(overrides)
    return FmpCompanyProfile(**values)


def price(date, close, volume, open_price=None):
    open_value = open_price if open_price is not None else close - 1
    return FmpPriceRow(
        symbol="NVDA",
        date=date,
        open=open_value,
        high=max(open_value, close) + 1,
        low=min(open_value, close) - 1,
        close=close,
        volume=volume,
        vwap=None,
    )


def bundle(**overrides):
    prices = [
        price("2026-07-02", 155, 180_000_000, 150),
        price("2026-07-01", 150, 100_000_000, 149),
        *[
            price(f"2026-05-{day:02d}", 140 + day / 100, 100_000_000, 139)
            for day in range(1, 51)
        ],
    ]
    values = {
        "profile": profile(),
        "quarterly_income": [
            FmpIncomeRow("2026-04-30", "Q1", None, 1.25),
            FmpIncomeRow("2025-04-30", "Q1", None, 0.50),
        ],
        "annual_income": [
            FmpIncomeRow("2026-01-31", "FY", 2026, 4.00),
            FmpIncomeRow("2025-01-31", "FY", 2025, 2.50),
            FmpIncomeRow("2024-01-31", "FY", 2024, 1.25),
        ],
        "prices": prices,
        "spy_prices": [
            FmpPriceRow("SPY", "2026-07-02", 620, 625, 618, 624, 60_000_000, 622.5)
        ],
        "float_data": FmpFloatData(2_000_000_000, 2_400_000_000),
        "peers": ["AMD", "AVGO"],
        "positions_summary": FmpPositionsSummary(100, 0.08, 0.57, 0.11),
        "top_holders": [
            FmpTopHolder(
                "High Quality Capital",
                "0000000001",
                10_000_000,
                1_550_000_000,
                0.20,
                0.04,
                32.0,
                85.0,
                160.0,
                21.0,
            )
        ],
    }
    values.update(overrides)
    return FmpCanslimBundle(**values)


def test_build_canslim_analysis_classifies_strong_stock():
    analysis = build_canslim_analysis(bundle(), market_range="6m", cached=False)

    assert analysis["symbol"] == "NVDA"
    assert analysis["letters"]["c"]["status"] == "pass"
    assert analysis["letters"]["c"]["metrics"]["quarterly_eps_growth_percent"] == 150.0
    assert analysis["letters"]["a"]["status"] == "pass"
    assert analysis["letters"]["n"]["status"] == "info"
    assert analysis["letters"]["s"]["status"] == "pass"
    assert analysis["letters"]["l"]["status"] in {"pass", "watch", "unknown"}
    assert analysis["letters"]["i"]["status"] == "pass"
    assert analysis["letters"]["i"]["top_performing_holders"][0]["holder_name"] == "High Quality Capital"
    assert analysis["letters"]["m"]["status"] == "info"
    assert analysis["letters"]["m"]["symbol"] == "SPY"
    assert analysis["letters"]["m"]["range"] == "6m"
    assert analysis["letters"]["m"]["candles"][0]["traded_value_usd"] == 37_350_000_000.0


def test_build_canslim_analysis_marks_missing_eps_unknown():
    analysis = build_canslim_analysis(
        bundle(quarterly_income=[], annual_income=[]),
        market_range="6m",
        cached=False,
    )

    assert analysis["letters"]["c"]["status"] == "unknown"
    assert analysis["letters"]["a"]["status"] == "unknown"


def test_build_canslim_analysis_rejects_non_us_or_etf_targets():
    for target_profile in [
        profile(exchange="KOSPI", currency="KRW"),
        profile(symbol="SPY", is_etf=True),
    ]:
        with pytest.raises(ValueError, match="CAN SLIM v1은 미국 상장 보통주만 지원합니다."):
            build_canslim_analysis(
                bundle(profile=target_profile),
                market_range="6m",
                cached=False,
            )


def test_build_canslim_analysis_keeps_i_unknown_when_13f_missing():
    analysis = build_canslim_analysis(
        bundle(positions_summary=None, top_holders=[]),
        market_range="6m",
        cached=False,
    )

    assert analysis["letters"]["i"]["status"] == "unknown"
    assert analysis["letters"]["i"]["institutional_flow"] == {
        "holders_count_change": None,
        "shares_change_percent": None,
        "ownership_percent": None,
        "market_value_change_percent": None,
    }
    assert analysis["letters"]["i"]["top_performing_holders"] == []
```

- [ ] **Step 2: Run rule tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_canslim.py::test_build_canslim_analysis_classifies_strong_stock backend/tests/test_canslim.py::test_build_canslim_analysis_rejects_non_us_or_etf_targets -q
```

Expected: FAIL with missing `build_canslim_analysis`.

- [ ] **Step 3: Implement rule calculations**

Append these functions to `backend/src/portfolio_app/services/canslim.py`:

```python
US_EXCHANGES = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}


def build_canslim_analysis(
    bundle: FmpCanslimBundle,
    *,
    market_range: str,
    cached: bool,
) -> dict[str, object]:
    _validate_us_common_stock(bundle.profile)
    return {
        "symbol": bundle.profile.symbol,
        "company_name": bundle.profile.company_name,
        "exchange": bundle.profile.exchange,
        "sector": bundle.profile.sector,
        "industry": bundle.profile.industry,
        "description": bundle.profile.description,
        "currency": "USD",
        "provider": "fmp",
        "generated_at": date.today().isoformat(),
        "cached": cached,
        "letters": {
            "c": _letter_c(bundle.quarterly_income),
            "a": _letter_a(bundle.annual_income),
            "n": _letter_n(bundle.profile),
            "s": _letter_s(bundle.prices, bundle.float_data),
            "l": _letter_l(bundle.prices, bundle.spy_prices, bundle.peers),
            "i": _letter_i(bundle.positions_summary, bundle.top_holders),
            "m": _letter_m(bundle.spy_prices, market_range=market_range),
        },
    }


def _validate_us_common_stock(profile: FmpCompanyProfile) -> None:
    if profile.currency != "USD" or profile.exchange.upper() not in US_EXCHANGES or profile.is_etf:
        raise ValueError("CAN SLIM v1은 미국 상장 보통주만 지원합니다.")


def _letter(
    status: CanslimStatus,
    headline: str,
    *,
    details: list[str] | None = None,
    metrics: dict[str, object] | None = None,
    source: str = "fmp",
    as_of: str | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "headline": headline,
        "details": details or [],
        "metrics": metrics or {},
        "source": source,
        "as_of": as_of,
    }


def _letter_c(rows: list[FmpIncomeRow]) -> dict[str, object]:
    if len(rows) < 2 or rows[0].eps_diluted is None or rows[1].eps_diluted in {None, 0}:
        return _letter("unknown", "최근 분기 EPS 비교 데이터가 부족합니다.", source="fmp income-statement")
    growth = ((rows[0].eps_diluted - rows[1].eps_diluted) / abs(rows[1].eps_diluted)) * 100
    status: CanslimStatus = "pass" if growth >= 25 else "watch" if growth >= 0 else "fail"
    return _letter(
        status,
        f"최근 분기 EPS 성장률 {growth:.1f}%",
        metrics={"quarterly_eps_growth_percent": round(growth, 2)},
        source="fmp income-statement",
        as_of=rows[0].date,
    )


def _letter_a(rows: list[FmpIncomeRow]) -> dict[str, object]:
    usable = [row for row in rows if row.eps_diluted is not None]
    if len(usable) < 3:
        return _letter("unknown", "최근 3개 연간 EPS 데이터가 부족합니다.", source="fmp income-statement")
    latest, middle, oldest = usable[:3]
    assert latest.eps_diluted is not None
    assert middle.eps_diluted is not None
    assert oldest.eps_diluted is not None
    if oldest.eps_diluted <= 0 or middle.eps_diluted <= 0 or latest.eps_diluted <= 0:
        return _letter("fail", "연간 EPS가 양수 흐름을 유지하지 못했습니다.", source="fmp income-statement")
    cagr = ((latest.eps_diluted / oldest.eps_diluted) ** (1 / 2) - 1) * 100
    sequential = latest.eps_diluted > middle.eps_diluted > oldest.eps_diluted
    status: CanslimStatus = "pass" if sequential and cagr >= 25 else "watch" if cagr > 0 else "fail"
    return _letter(
        status,
        f"최근 3개 연간 EPS CAGR {cagr:.1f}%",
        metrics={"annual_eps_cagr_percent": round(cagr, 2), "annual_eps_sequential_growth": sequential},
        source="fmp income-statement",
        as_of=latest.date,
    )


def _letter_n(profile: FmpCompanyProfile) -> dict[str, object]:
    return _letter(
        "info",
        f"{profile.company_name} 사업 개요",
        details=[profile.description],
        metrics={"sector": profile.sector, "industry": profile.industry, "exchange": profile.exchange},
        source="fmp profile",
    )


def _letter_s(prices: list[FmpPriceRow], float_data: FmpFloatData) -> dict[str, object]:
    if len(prices) < 51:
        return _letter("unknown", "거래량 평균 계산에 필요한 가격 데이터가 부족합니다.", source="fmp historical-price-eod")
    latest, previous = prices[0], prices[1]
    avg_volume = sum(row.volume for row in prices[1:51]) / 50
    ratio = latest.volume / avg_volume if avg_volume > 0 else 0
    rose = latest.close > previous.close
    if rose and ratio >= 1.5:
        status: CanslimStatus = "pass"
    elif rose and ratio >= 1.2:
        status = "watch"
    else:
        status = "fail"
    return _letter(
        status,
        f"최근 거래량은 50일 평균의 {ratio:.2f}배입니다.",
        metrics={
            "latest_close": latest.close,
            "latest_volume": latest.volume,
            "average_volume_50d": round(avg_volume, 2),
            "volume_ratio": round(ratio, 2),
            "float_shares": float_data.float_shares,
            "outstanding_shares": float_data.outstanding_shares,
        },
        source="fmp historical-price-eod, fmp shares-float",
        as_of=latest.date,
    )


def _letter_l(
    prices: list[FmpPriceRow],
    spy_prices: list[FmpPriceRow],
    peers: list[str],
) -> dict[str, object]:
    stock_return = _period_return_percent(prices)
    spy_return = _period_return_percent(spy_prices)
    if stock_return is None or spy_return is None:
        return _letter("unknown", "상대강도 계산에 필요한 가격 데이터가 부족합니다.", source="fmp historical-price-eod")
    excess = stock_return - spy_return
    status: CanslimStatus = "pass" if excess >= 20 else "watch" if excess >= 0 else "fail"
    return _letter(
        status,
        f"SPY 대비 기간 초과수익률 {excess:.1f}%",
        metrics={
            "stock_return_percent": round(stock_return, 2),
            "spy_return_percent": round(spy_return, 2),
            "excess_return_percent": round(excess, 2),
            "peer_count": len(peers),
            "peer_rank_percentile": None,
        },
        source="fmp historical-price-eod, fmp peers",
    )


def _period_return_percent(rows: list[FmpPriceRow]) -> float | None:
    if len(rows) < 2 or rows[-1].close <= 0:
        return None
    return ((rows[0].close / rows[-1].close) - 1) * 100


def _letter_i(
    summary: FmpPositionsSummary | None,
    top_holders: list[FmpTopHolder],
) -> dict[str, object]:
    flow = {
        "holders_count_change": None,
        "shares_change_percent": None,
        "ownership_percent": None,
        "market_value_change_percent": None,
    }
    if summary is None:
        result = _letter("unknown", "기관 보유 데이터가 없거나 접근할 수 없습니다.", source="fmp 13f")
        result["institutional_flow"] = flow
        result["top_performing_holders"] = []
        return result
    flow = {
        "holders_count_change": summary.holders_count_change,
        "shares_change_percent": summary.shares_change_percent,
        "ownership_percent": summary.ownership_percent,
        "market_value_change_percent": summary.market_value_change_percent,
    }
    has_top_support = any((holder.performance_1y_percent or 0) > 0 for holder in top_holders)
    positive_flow = (summary.holders_count_change or 0) > 0 and (summary.shares_change_percent or 0) > 0
    if positive_flow and has_top_support:
        status: CanslimStatus = "pass"
    elif positive_flow or has_top_support:
        status = "watch"
    else:
        status = "fail"
    result = _letter(
        status,
        "기관 보유 흐름과 상위 성과 기관 보유를 확인했습니다.",
        source="fmp 13f",
        metrics=flow,
    )
    result["institutional_flow"] = flow
    result["top_performing_holders"] = [
        {
            "holder_name": holder.holder_name,
            "cik": holder.cik,
            "shares": holder.shares,
            "market_value": holder.market_value,
            "position_change_percent": holder.position_change_percent,
            "portfolio_weight_percent": holder.portfolio_weight_percent,
            "performance_1y_percent": holder.performance_1y_percent,
            "performance_3y_percent": holder.performance_3y_percent,
            "performance_5y_percent": holder.performance_5y_percent,
            "excess_vs_sp500_percent": holder.excess_vs_sp500_percent,
        }
        for holder in top_holders
    ]
    return result


def _letter_m(spy_prices: list[FmpPriceRow], *, market_range: str) -> dict[str, object]:
    return {
        "status": "info",
        "symbol": "SPY",
        "range": market_range,
        "candles": [
            {
                "date": row.date,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
                "traded_value_usd": row.traded_value_usd,
            }
            for row in spy_prices
        ],
        "source": "fmp",
        "as_of": spy_prices[0].date if spy_prices else None,
    }
```

- [ ] **Step 4: Run rule tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_canslim.py -q
.venv/bin/python -m ruff check backend/src/portfolio_app/services/canslim.py backend/tests/test_canslim.py
```

Expected: PASS.

- [ ] **Step 5: Commit calculation service**

```bash
git add backend/src/portfolio_app/services/canslim.py backend/tests/test_canslim.py
git commit -m "feat: calculate CAN SLIM analysis"
```

---

### Task 3: CAN SLIM Cache Schema And Repository

**Files:**
- Modify: `backend/src/portfolio_app/schema.sql`
- Modify: `backend/src/portfolio_app/migrations.py`
- Modify: `backend/src/portfolio_app/repositories.py`
- Modify: `backend/tests/test_db.py`
- Modify: `backend/tests/test_canslim.py`

- [ ] **Step 1: Write failing DB and cache tests**

Modify `backend/tests/test_db.py`:

```python
TOSS_ONLY_TABLES = {
    "schema_migrations",
    "fx_rates",
    "goals",
    "backups",
    "settings",
    "toss_order_import_runs",
    "toss_orders",
    "chart_marker_memos",
    "growth_month_history",
    "sp500_proxy_prices",
    "canslim_cache_entries",
}
```

Add:

```python
def assert_canslim_cache_contract(db: sqlite3.Connection) -> None:
    assert "canslim_cache_entries" in table_names(db)
    assert column_names(db, "canslim_cache_entries") == {
        "cache_key",
        "provider",
        "payload_json",
        "fetched_at",
        "expires_at",
    }


def test_canslim_cache_contract_in_fresh_schema(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    assert migration_versions(db) == [16]
    assert_canslim_cache_contract(db)


def test_migrate_from_v15_adds_canslim_cache_entries(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    create_schema_migrations(db, 15)
    create_toss_only_survivor_tables(db)
    db.execute(
        """
        create table growth_month_history (
          id integer primary key,
          account_seq text not null,
          year integer not null check (year >= 2000 and year <= 2099),
          month integer not null check (month >= 1 and month <= 12),
          net_worth_krw real not null check (net_worth_krw >= 0),
          monthly_dividend_krw real not null default 0 check (monthly_dividend_krw >= 0),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          unique(account_seq, year, month)
        )
        """
    )
    db.execute(
        """
        create table sp500_proxy_prices (
          id integer primary key,
          year integer not null check (year >= 2000 and year <= 2099),
          proxy_symbol text not null default 'VOO' check (proxy_symbol = 'VOO'),
          price real not null check (price > 0),
          currency text not null default 'USD' check (currency = 'USD'),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          unique(proxy_symbol, year)
        )
        """
    )
    db.execute(
        """
        create table chart_marker_memos (
          id integer primary key,
          account_seq text not null,
          symbol text not null,
          marker_key text not null,
          memo text not null default '',
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp,
          unique(account_seq, symbol, marker_key)
        )
        """
    )
    db.commit()

    migrate(db)

    assert migration_versions(db) == [15, 16]
    assert_canslim_cache_contract(db)
```

Append to `backend/tests/test_canslim.py`:

```python
from portfolio_app import repositories
from portfolio_app.db import connect
from portfolio_app.migrations import migrate


def test_canslim_cache_repository_round_trips_payload(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    repositories.upsert_canslim_cache_entry(
        db,
        cache_key="fmp:analysis:NVDA:6m",
        provider="fmp",
        payload_json='{"symbol":"NVDA"}',
        fetched_at="2026-07-06T00:00:00+00:00",
        expires_at="2026-07-07T00:00:00+00:00",
    )

    row = repositories.fetch_canslim_cache_entry(db, cache_key="fmp:analysis:NVDA:6m")

    assert row is not None
    assert row["provider"] == "fmp"
    assert row["payload_json"] == '{"symbol":"NVDA"}'


def test_canslim_cache_repository_refresh_replaces_payload(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    repositories.upsert_canslim_cache_entry(
        db,
        cache_key="fmp:analysis:NVDA:6m",
        provider="fmp",
        payload_json='{"old":true}',
        fetched_at="2026-07-06T00:00:00+00:00",
        expires_at="2026-07-07T00:00:00+00:00",
    )
    repositories.upsert_canslim_cache_entry(
        db,
        cache_key="fmp:analysis:NVDA:6m",
        provider="fmp",
        payload_json='{"old":false}',
        fetched_at="2026-07-06T01:00:00+00:00",
        expires_at="2026-07-07T01:00:00+00:00",
    )

    row = repositories.fetch_canslim_cache_entry(db, cache_key="fmp:analysis:NVDA:6m")

    assert row["payload_json"] == '{"old":false}'
    assert row["fetched_at"] == "2026-07-06T01:00:00+00:00"
```

- [ ] **Step 2: Run DB/cache tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py::test_canslim_cache_contract_in_fresh_schema backend/tests/test_canslim.py::test_canslim_cache_repository_round_trips_payload -q
```

Expected: FAIL because schema version is 15 and cache helpers do not exist.

- [ ] **Step 3: Implement schema, migration, and repository helpers**

Modify `backend/src/portfolio_app/schema.sql` before the seed insert:

```sql
create table if not exists canslim_cache_entries (
  cache_key text primary key,
  provider text not null,
  payload_json text not null,
  fetched_at text not null,
  expires_at text not null
);
```

Modify `backend/src/portfolio_app/migrations.py`:

```python
SCHEMA_VERSION = 16
```

Add after `_migrate_from_14_to_15`:

```python
def _migrate_from_15_to_16(db: sqlite3.Connection) -> None:
    with db:
        db.execute("begin")
        for statement in _schema_statements(SCHEMA_PATH.read_text(encoding="utf-8")):
            db.execute(statement)
        db.execute("insert or ignore into schema_migrations(version) values (16)")
```

Add in `migrate()` after the version 14 block:

```python
    if version == 15:
        _migrate_from_15_to_16(db)
        version = 16
```

Append to `backend/src/portfolio_app/repositories.py`:

```python
def fetch_canslim_cache_entry(
    db: sqlite3.Connection,
    *,
    cache_key: str,
) -> sqlite3.Row | None:
    return db.execute(
        """
        select *
        from canslim_cache_entries
        where cache_key = ?
        """,
        (cache_key,),
    ).fetchone()


def upsert_canslim_cache_entry(
    db: sqlite3.Connection,
    *,
    cache_key: str,
    provider: str,
    payload_json: str,
    fetched_at: str,
    expires_at: str,
    commit: bool = True,
) -> sqlite3.Row:
    db.execute(
        """
        insert into canslim_cache_entries(
            cache_key, provider, payload_json, fetched_at, expires_at
        )
        values (?, ?, ?, ?, ?)
        on conflict(cache_key)
        do update set provider = excluded.provider,
                      payload_json = excluded.payload_json,
                      fetched_at = excluded.fetched_at,
                      expires_at = excluded.expires_at
        """,
        (cache_key, provider, payload_json, fetched_at, expires_at),
    )
    if commit:
        db.commit()
    row = fetch_canslim_cache_entry(db, cache_key=cache_key)
    if row is None:
        raise RuntimeError("저장된 CAN SLIM 캐시를 찾을 수 없습니다.")
    return row
```

- [ ] **Step 4: Run DB/cache tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py::test_canslim_cache_contract_in_fresh_schema backend/tests/test_db.py::test_migrate_from_v15_adds_canslim_cache_entries backend/tests/test_canslim.py::test_canslim_cache_repository_round_trips_payload backend/tests/test_canslim.py::test_canslim_cache_repository_refresh_replaces_payload -q
.venv/bin/python -m ruff check backend/src/portfolio_app/migrations.py backend/src/portfolio_app/repositories.py backend/tests/test_db.py backend/tests/test_canslim.py
```

Expected: PASS.

- [ ] **Step 5: Commit cache persistence**

```bash
git add backend/src/portfolio_app/schema.sql backend/src/portfolio_app/migrations.py backend/src/portfolio_app/repositories.py backend/tests/test_db.py backend/tests/test_canslim.py
git commit -m "feat: cache CAN SLIM provider data"
```

---

### Task 4: CAN SLIM API Route

**Files:**
- Create: `backend/src/portfolio_app/api/canslim.py`
- Modify: `backend/src/portfolio_app/main.py`
- Modify: `backend/src/portfolio_app/models.py`
- Modify: `backend/src/portfolio_app/services/canslim.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_canslim.py`

- [ ] **Step 1: Write failing API tests**

Add to `backend/tests/test_api.py`:

```python
def test_openapi_exposes_canslim_analysis_path(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "/api/canslim/analysis" in schema["paths"]
    parameters = schema["paths"]["/api/canslim/analysis"]["get"]["parameters"]
    assert {
        "name": "symbol",
        "in": "query",
        "required": True,
        "schema": {"type": "string", "minLength": 1, "title": "Symbol"},
    } in parameters


def test_canslim_analysis_requires_fmp_key(tmp_path):
    client = create_test_client(tmp_path)

    response = client.get("/api/canslim/analysis?symbol=NVDA")

    assert response.status_code == 400
    assert response.json()["detail"] == "FMP API 키를 설정해 주세요."


def test_canslim_analysis_rejects_blank_symbol(tmp_path):
    client = create_test_client(tmp_path, fmp_api_key="fmp-key")

    response = client.get("/api/canslim/analysis?symbol=%20%20")

    assert response.status_code == 400
    assert response.json()["detail"] == "종목 심볼을 입력해 주세요."


def test_canslim_analysis_rejects_bad_market_range(tmp_path):
    client = create_test_client(tmp_path, fmp_api_key="fmp-key")

    response = client.get("/api/canslim/analysis?symbol=NVDA&market_range=2y")

    assert response.status_code == 400
    assert response.json()["detail"] == "시장 컨텍스트 기간은 3m, 6m, 1y 중 하나여야 합니다."
```

Add a route success test after the parser tests can be reused. Keep the HTTP mocks focused by using compact payloads:

```python
def mock_canslim_fmp_success(httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/profile?symbol=NVDA&apikey=fmp-key",
        json=[
            {
                "symbol": "NVDA",
                "companyName": "NVIDIA Corporation",
                "exchangeShortName": "NASDAQ",
                "sector": "Technology",
                "industry": "Semiconductors",
                "description": "NVIDIA designs accelerated computing products.",
                "currency": "USD",
                "isEtf": False,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/income-statement"
            "?symbol=NVDA&period=quarter&limit=8&apikey=fmp-key"
        ),
        json=[
            {"date": "2026-04-30", "period": "Q1", "epsdiluted": 1.20},
            {"date": "2025-04-30", "period": "Q1", "epsdiluted": 0.60},
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/income-statement"
            "?symbol=NVDA&period=annual&limit=5&apikey=fmp-key"
        ),
        json=[
            {"date": "2026-01-31", "calendarYear": "2026", "epsdiluted": 4.00},
            {"date": "2025-01-31", "calendarYear": "2025", "epsdiluted": 2.50},
            {"date": "2024-01-31", "calendarYear": "2024", "epsdiluted": 1.25},
        ],
    )
    price_rows = [
        {
            "symbol": "NVDA",
            "date": "2026-07-02",
            "open": 150,
            "high": 156,
            "low": 149,
            "close": 155,
            "volume": 180_000_000,
            "vwap": 153.5,
        },
        {
            "symbol": "NVDA",
            "date": "2026-07-01",
            "open": 149,
            "high": 151,
            "low": 147,
            "close": 150,
            "volume": 100_000_000,
            "vwap": 149.5,
        },
        *[
            {
                "symbol": "NVDA",
                "date": f"2026-05-{day:02d}",
                "open": 140,
                "high": 142,
                "low": 139,
                "close": 141,
                "volume": 100_000_000,
                "vwap": 141,
            }
            for day in range(1, 51)
        ],
    ]
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/historical-price-eod/full"
            "?symbol=NVDA&from=2025-07-06&to=2026-07-06&apikey=fmp-key"
        ),
        json=price_rows,
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/historical-price-eod/full"
            "?symbol=SPY&from=2026-01-05&to=2026-07-06&apikey=fmp-key"
        ),
        json=[
            {
                "symbol": "SPY",
                "date": "2026-07-02",
                "open": 620,
                "high": 625,
                "low": 618,
                "close": 624,
                "volume": 60_000_000,
                "vwap": 622.5,
            }
        ],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/shares-float?symbol=NVDA&apikey=fmp-key",
        json=[{"floatShares": 2_000_000_000, "outstandingShares": 2_400_000_000}],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://financialmodelingprep.com/stable/peers?symbol=NVDA&apikey=fmp-key",
        json=[{"symbol": "AMD"}],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/institutional-ownership/"
            "symbol-positions-summary?symbol=NVDA&apikey=fmp-key"
        ),
        json=[{"investorsHoldingChange": 100, "numberOfSharesChange": 0.08, "ownershipPercent": 0.57, "marketValueChange": 0.11}],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/api/v4/institutional-ownership/"
            "institutional-holders/symbol-ownership?page=0&symbol=NVDA&apikey=fmp-key"
        ),
        json=[{"holder": "High Quality Capital", "cik": "0000000001", "shares": 1000, "marketValue": 155000, "change": 0.2, "weight": 0.04}],
    )
    httpx_mock.add_response(
        method="GET",
        url=(
            "https://financialmodelingprep.com/stable/institutional-ownership/"
            "holder-performance-summary?cik=0000000001&page=0&apikey=fmp-key"
        ),
        json=[{"performance1year": 0.32, "performance3year": 0.85, "performance5year": 1.6, "performanceRelativeToSP500": 0.21}],
    )


def test_canslim_analysis_returns_us_stock_analysis(tmp_path, httpx_mock):
    client = create_test_client(tmp_path, fmp_api_key="fmp-key")
    mock_canslim_fmp_success(httpx_mock)

    response = client.get("/api/canslim/analysis?symbol=%20nvda%20&market_range=6m")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "NVDA"
    assert body["company_name"] == "NVIDIA Corporation"
    assert body["currency"] == "USD"
    assert body["provider"] == "fmp"
    assert body["letters"]["c"]["status"] == "pass"
    assert body["letters"]["i"]["top_performing_holders"][0]["holder_name"] == "High Quality Capital"
    assert body["letters"]["m"]["status"] == "info"
    assert body["letters"]["m"]["symbol"] == "SPY"
    assert body["letters"]["m"]["range"] == "6m"
```

Modify `backend/tests/test_api.py::create_test_client` settings defaults:

```python
"fmp_api_key": "",
```

- [ ] **Step 2: Run API tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_openapi_exposes_canslim_analysis_path backend/tests/test_api.py::test_canslim_analysis_requires_fmp_key -q
```

Expected: FAIL because the route is not registered.

- [ ] **Step 3: Add response models and route**

Append to `backend/src/portfolio_app/models.py`:

```python
CanslimLetterStatus = Literal["pass", "watch", "fail", "unknown", "info"]
CanslimMarketRange = Literal["3m", "6m", "1y"]


class CanslimLetterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CanslimLetterStatus
    headline: str
    details: list[str]
    metrics: dict[str, float | str | bool | None]
    source: str
    as_of: str | None


class CanslimInstitutionalFlow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    holders_count_change: float | None
    shares_change_percent: float | None
    ownership_percent: float | None
    market_value_change_percent: float | None


class CanslimTopPerformingHolder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    holder_name: str
    cik: str
    shares: float = Field(ge=0, allow_inf_nan=False)
    market_value: float = Field(ge=0, allow_inf_nan=False)
    position_change_percent: float | None = Field(default=None, allow_inf_nan=False)
    portfolio_weight_percent: float | None = Field(default=None, allow_inf_nan=False)
    performance_1y_percent: float | None = Field(default=None, allow_inf_nan=False)
    performance_3y_percent: float | None = Field(default=None, allow_inf_nan=False)
    performance_5y_percent: float | None = Field(default=None, allow_inf_nan=False)
    excess_vs_sp500_percent: float | None = Field(default=None, allow_inf_nan=False)


class CanslimInstitutionalLetterResponse(CanslimLetterResponse):
    institutional_flow: CanslimInstitutionalFlow
    top_performing_holders: list[CanslimTopPerformingHolder]


class CanslimMarketCandle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: float = Field(ge=0, allow_inf_nan=False)
    traded_value_usd: float = Field(ge=0, allow_inf_nan=False)


class CanslimMarketContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["info"]
    symbol: Literal["SPY"]
    range: CanslimMarketRange
    candles: list[CanslimMarketCandle]
    source: Literal["fmp"]
    as_of: str | None


class CanslimLettersResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    c: CanslimLetterResponse
    a: CanslimLetterResponse
    n: CanslimLetterResponse
    s: CanslimLetterResponse
    l: CanslimLetterResponse
    i: CanslimInstitutionalLetterResponse
    m: CanslimMarketContextResponse


class CanslimAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    company_name: str
    exchange: str
    sector: str | None
    industry: str | None
    description: str
    currency: Literal["USD"]
    provider: Literal["fmp"]
    generated_at: str
    cached: bool
    letters: CanslimLettersResponse
```

Create `backend/src/portfolio_app/api/canslim.py`:

```python
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from portfolio_app.api import get_db
from portfolio_app.models import CanslimAnalysisResponse
from portfolio_app.services.canslim import (
    FmpCanslimProvider,
    FmpProviderError,
    build_canslim_analysis,
    normalize_symbol,
)

router = APIRouter(prefix="/api/canslim", tags=["canslim"])
MarketRange = Literal["3m", "6m", "1y"]


@router.get("/analysis", response_model=CanslimAnalysisResponse)
async def get_canslim_analysis(
    request: Request,
    _db=Depends(get_db),
    symbol: Annotated[str, Query(min_length=1)],
    market_range: MarketRange = "6m",
    refresh: bool = False,
) -> dict[str, object]:
    del _db, refresh
    try:
        normalized_symbol = normalize_symbol(symbol)
        settings = request.app.state.settings
        provider = FmpCanslimProvider(settings.fmp_api_key)
        bundle = await provider.fetch_bundle(normalized_symbol, market_range=market_range)
        return build_canslim_analysis(bundle, market_range=market_range, cached=False)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (FmpProviderError, httpx.HTTPError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
```

Modify `backend/src/portfolio_app/main.py` imports:

```python
from portfolio_app.api import (
    backups,
    canslim,
    goals,
    growth_history,
    summary,
    toss_portfolio,
)
```

Register the router before goals/backups:

```python
    app.include_router(canslim.router)
```

- [ ] **Step 4: Run API tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_openapi_exposes_canslim_analysis_path backend/tests/test_api.py::test_canslim_analysis_requires_fmp_key backend/tests/test_api.py::test_canslim_analysis_rejects_blank_symbol backend/tests/test_api.py::test_canslim_analysis_rejects_bad_market_range backend/tests/test_api.py::test_canslim_analysis_returns_us_stock_analysis -q
.venv/bin/python -m ruff check backend/src/portfolio_app/api/canslim.py backend/src/portfolio_app/main.py backend/src/portfolio_app/models.py backend/tests/test_api.py
```

Expected: PASS. If the SPY date range in the mocked URL differs by one day because `date.today()` is used during test execution, inject `today=lambda: "2026-07-06"` into the route through app state before widening test expectations.

- [ ] **Step 5: Commit API route**

```bash
git add backend/src/portfolio_app/api/canslim.py backend/src/portfolio_app/main.py backend/src/portfolio_app/models.py backend/src/portfolio_app/services/canslim.py backend/tests/test_api.py backend/tests/test_canslim.py
git commit -m "feat: expose CAN SLIM analysis API"
```

---

### Task 5: Backend Cache Orchestration In API

**Files:**
- Modify: `backend/src/portfolio_app/api/canslim.py`
- Modify: `backend/src/portfolio_app/services/canslim.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing cache behavior tests**

Add to `backend/tests/test_api.py`:

```python
def test_canslim_analysis_uses_cached_payload(tmp_path):
    client = create_test_client(tmp_path, fmp_api_key="fmp-key")
    db_path = tmp_path / "portfolio.sqlite"
    import sqlite3

    db = sqlite3.connect(db_path)
    db.execute(
        """
        insert into canslim_cache_entries(cache_key, provider, payload_json, fetched_at, expires_at)
        values (?, ?, ?, ?, ?)
        """,
        (
            "fmp:analysis:NVDA:6m",
            "fmp",
            '{"symbol":"NVDA","company_name":"Cached NVIDIA","exchange":"NASDAQ","sector":null,"industry":null,"description":"","currency":"USD","provider":"fmp","generated_at":"2026-07-06","cached":true,"letters":{"c":{"status":"unknown","headline":"cached","details":[],"metrics":{},"source":"fmp","as_of":null},"a":{"status":"unknown","headline":"cached","details":[],"metrics":{},"source":"fmp","as_of":null},"n":{"status":"info","headline":"cached","details":[],"metrics":{},"source":"fmp","as_of":null},"s":{"status":"unknown","headline":"cached","details":[],"metrics":{},"source":"fmp","as_of":null},"l":{"status":"unknown","headline":"cached","details":[],"metrics":{},"source":"fmp","as_of":null},"i":{"status":"unknown","headline":"cached","details":[],"metrics":{},"source":"fmp","as_of":null,"institutional_flow":{"holders_count_change":null,"shares_change_percent":null,"ownership_percent":null,"market_value_change_percent":null},"top_performing_holders":[]},"m":{"status":"info","symbol":"SPY","range":"6m","candles":[],"source":"fmp","as_of":null}}}',
            "2026-07-06T00:00:00+00:00",
            "2099-01-01T00:00:00+00:00",
        ),
    )
    db.commit()
    db.close()

    response = client.get("/api/canslim/analysis?symbol=NVDA")

    assert response.status_code == 200
    assert response.json()["company_name"] == "Cached NVIDIA"
    assert response.json()["cached"] is True


def test_canslim_analysis_refresh_bypasses_cache(tmp_path, httpx_mock):
    client = create_test_client(tmp_path, fmp_api_key="fmp-key")
    mock_canslim_fmp_success(httpx_mock)

    response = client.get("/api/canslim/analysis?symbol=NVDA&refresh=true")

    assert response.status_code == 200
    assert response.json()["company_name"] == "NVIDIA Corporation"
    assert response.json()["cached"] is False
```

- [ ] **Step 2: Run cache behavior tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_canslim_analysis_uses_cached_payload backend/tests/test_api.py::test_canslim_analysis_refresh_bypasses_cache -q
```

Expected: first test FAILS because the API ignores cache.

- [ ] **Step 3: Implement cache orchestration**

Append to `backend/src/portfolio_app/services/canslim.py`:

```python
import json
from datetime import UTC, datetime


def canslim_analysis_cache_key(symbol: str, market_range: str) -> str:
    return f"fmp:analysis:{normalize_symbol(symbol)}:{market_range}"


def cache_expiry_iso(hours: int) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat(timespec="seconds")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def cached_payload_is_fresh(row: Any) -> bool:
    expires_at = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
    return datetime.now(UTC) < expires_at


def dumps_analysis_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads_analysis_payload(payload_json: str) -> dict[str, object]:
    payload = json.loads(payload_json)
    if not isinstance(payload, dict):
        raise ValueError("CAN SLIM 캐시 payload가 객체가 아닙니다.")
    payload["cached"] = True
    return payload
```

Modify `backend/src/portfolio_app/api/canslim.py`:

```python
from portfolio_app import repositories
from portfolio_app.services.canslim import (
    FmpCanslimProvider,
    FmpProviderError,
    build_canslim_analysis,
    cached_payload_is_fresh,
    cache_expiry_iso,
    canslim_analysis_cache_key,
    dumps_analysis_payload,
    loads_analysis_payload,
    normalize_symbol,
    now_iso,
)
```

Use the DB dependency and cache:

```python
async def get_canslim_analysis(
    request: Request,
    db=Depends(get_db),
    symbol: Annotated[str, Query(min_length=1)],
    market_range: MarketRange = "6m",
    refresh: bool = False,
) -> dict[str, object]:
    try:
        normalized_symbol = normalize_symbol(symbol)
        cache_key = canslim_analysis_cache_key(normalized_symbol, market_range)
        cached_row = repositories.fetch_canslim_cache_entry(db, cache_key=cache_key)
        if not refresh and cached_row is not None and cached_payload_is_fresh(cached_row):
            return loads_analysis_payload(str(cached_row["payload_json"]))

        settings = request.app.state.settings
        provider = FmpCanslimProvider(settings.fmp_api_key)
        bundle = await provider.fetch_bundle(normalized_symbol, market_range=market_range)
        payload = build_canslim_analysis(bundle, market_range=market_range, cached=False)
        repositories.upsert_canslim_cache_entry(
            db,
            cache_key=cache_key,
            provider="fmp",
            payload_json=dumps_analysis_payload(payload),
            fetched_at=now_iso(),
            expires_at=cache_expiry_iso(1),
        )
        return payload
```

- [ ] **Step 4: Run cache API tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_canslim_analysis_uses_cached_payload backend/tests/test_api.py::test_canslim_analysis_refresh_bypasses_cache -q
.venv/bin/python -m ruff check backend/src/portfolio_app/api/canslim.py backend/src/portfolio_app/services/canslim.py backend/tests/test_api.py
```

Expected: PASS.

- [ ] **Step 5: Commit API cache orchestration**

```bash
git add backend/src/portfolio_app/api/canslim.py backend/src/portfolio_app/services/canslim.py backend/tests/test_api.py
git commit -m "feat: serve CAN SLIM analysis from cache"
```

---

### Task 6: Frontend CAN SLIM Page

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/components/CanslimPage.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/tests/canslim-page.test.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: Write failing frontend source test**

Create `frontend/tests/canslim-page.test.mjs`:

```js
import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")
const typesSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")
const stylesSource = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8")
const pageFile = new URL("../src/components/CanslimPage.tsx", import.meta.url)

assert.ok(existsSync(pageFile), "CAN SLIM page should exist")
assert.ok(appSource.includes("CanslimPage"), "App should import the CAN SLIM page")
assert.ok(appSource.includes('active === "canslim"'), "App should mount the CAN SLIM screen")
assert.ok(shellSource.includes('id: "canslim"'), "AppShell should expose CAN SLIM navigation")
assert.ok(shellSource.includes("CAN SLIM"), "AppShell should label the CAN SLIM screen")
assert.ok(typesSource.includes("CanslimAnalysis"), "Types should define CanslimAnalysis")
assert.ok(typesSource.includes("CanslimTopPerformingHolder"), "Types should define holder rows")

const pageSource = readFileSync(pageFile, "utf8")

for (const expected of [
  "/api/canslim/analysis",
  "refresh=true",
  "market_range",
  "C/A/N/S/L/I/M",
  "top_performing_holders",
  "institutional_flow",
  "traded_value_usd",
  "SPY",
  "FMP API 키를 설정해 주세요.",
  "CAN SLIM v1은 미국 상장 보통주만 지원합니다.",
  "상위 성과 기관",
  "거래대금",
  "시장 컨텍스트",
]) {
  assert.ok(pageSource.includes(expected), `CAN SLIM page should include ${expected}`)
}

for (const letter of ["c", "a", "n", "s", "l", "i", "m"]) {
  assert.ok(pageSource.includes(`letters.${letter}`), `Page should render ${letter.toUpperCase()}`)
}

assert.ok(stylesSource.includes(".canslim-grid"), "Styles should include CAN SLIM grid")
assert.ok(stylesSource.includes(".canslim-status-pass"), "Styles should include pass state")
assert.ok(stylesSource.includes(".canslim-status-unknown"), "Styles should include unknown state")
assert.ok(
  !pageSource.includes("매수 추천") && !pageSource.includes("매도 추천"),
  "CAN SLIM page should not render buy/sell recommendation copy",
)
```

Modify `frontend/package.json`:

```json
"test": "node tests/holdings-page-form.test.mjs && node tests/dashboard-currency-toggle.test.mjs && node tests/settings-market-sync.test.mjs && node tests/growth-history-page.test.mjs && node tests/transactions-nullable-relations.test.mjs && node tests/transaction-payload-builder.test.mjs && node tests/toss-order-history-page.test.mjs && node tests/chart-markers.test.mjs && node tests/charts-page.test.mjs && node tests/canslim-page.test.mjs"
```

- [ ] **Step 2: Run frontend test to verify RED**

Run:

```bash
cd frontend && npm test
```

Expected: FAIL because `CanslimPage.tsx` does not exist.

- [ ] **Step 3: Add frontend types**

Append to `frontend/src/types.ts`:

```ts
export type CanslimLetterStatus = "pass" | "watch" | "fail" | "unknown" | "info"
export type CanslimMarketRange = "3m" | "6m" | "1y"

export type CanslimLetter = {
  status: CanslimLetterStatus
  headline: string
  details: string[]
  metrics: Record<string, number | string | boolean | null>
  source: string
  as_of: string | null
}

export type CanslimInstitutionalFlow = {
  holders_count_change: number | null
  shares_change_percent: number | null
  ownership_percent: number | null
  market_value_change_percent: number | null
}

export type CanslimTopPerformingHolder = {
  holder_name: string
  cik: string
  shares: number
  market_value: number
  position_change_percent: number | null
  portfolio_weight_percent: number | null
  performance_1y_percent: number | null
  performance_3y_percent: number | null
  performance_5y_percent: number | null
  excess_vs_sp500_percent: number | null
}

export type CanslimInstitutionalLetter = CanslimLetter & {
  institutional_flow: CanslimInstitutionalFlow
  top_performing_holders: CanslimTopPerformingHolder[]
}

export type CanslimMarketCandle = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  traded_value_usd: number
}

export type CanslimMarketContext = {
  status: "info"
  symbol: "SPY"
  range: CanslimMarketRange
  candles: CanslimMarketCandle[]
  source: "fmp"
  as_of: string | null
}

export type CanslimAnalysis = {
  symbol: string
  company_name: string
  exchange: string
  sector: string | null
  industry: string | null
  description: string
  currency: "USD"
  provider: "fmp"
  generated_at: string
  cached: boolean
  letters: {
    c: CanslimLetter
    a: CanslimLetter
    n: CanslimLetter
    s: CanslimLetter
    l: CanslimLetter
    i: CanslimInstitutionalLetter
    m: CanslimMarketContext
  }
}
```

- [ ] **Step 4: Add `CanslimPage.tsx`**

Create `frontend/src/components/CanslimPage.tsx`:

```tsx
import { RefreshCw, Search } from "lucide-react"
import { type FormEvent, useMemo, useState } from "react"
import { apiGet } from "../api"
import type {
  CanslimAnalysis,
  CanslimLetter,
  CanslimLetterStatus,
  CanslimMarketCandle,
  CanslimMarketRange,
} from "../types"

const statusLabels: Record<CanslimLetterStatus, string> = {
  pass: "통과",
  watch: "관찰",
  fail: "미달",
  unknown: "데이터 없음",
  info: "정보",
}

const letters = [
  ["c", "C", "분기 EPS"],
  ["a", "A", "연간 EPS"],
  ["n", "N", "회사/사업"],
  ["s", "S", "수급"],
  ["l", "L", "주도주"],
  ["i", "I", "기관"],
  ["m", "M", "시장 컨텍스트"],
] as const

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))

const formatNumber = (value: number | null | undefined, maximumFractionDigits = 2) =>
  typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("ko-KR", { maximumFractionDigits })
    : "-"

const formatPercent = (value: number | null | undefined) =>
  typeof value === "number" && Number.isFinite(value) ? `${formatNumber(value)}%` : "-"

const formatUsd = (value: number | null | undefined) =>
  typeof value === "number" && Number.isFinite(value)
    ? `$${value.toLocaleString("ko-KR", { maximumFractionDigits: 0 })}`
    : "-"

function Sparkline({ candles }: { candles: CanslimMarketCandle[] }) {
  const points = useMemo(() => {
    if (candles.length === 0) {
      return ""
    }
    const closes = candles.map((candle) => candle.close)
    const min = Math.min(...closes)
    const max = Math.max(...closes)
    const range = max - min || 1
    return candles
      .map((candle, index) => {
        const x = (index / Math.max(candles.length - 1, 1)) * 100
        const y = 40 - ((candle.close - min) / range) * 36
        return `${x.toFixed(2)},${y.toFixed(2)}`
      })
      .join(" ")
  }, [candles])
  const maxTradedValue = Math.max(...candles.map((candle) => candle.traded_value_usd), 1)

  return (
    <svg className="canslim-market-chart" role="img" viewBox="0 0 100 64">
      <polyline className="canslim-market-line" fill="none" points={points} />
      {candles.slice(-18).map((candle, index) => {
        const height = Math.max((candle.traded_value_usd / maxTradedValue) * 16, 1)
        return (
          <rect
            className="canslim-market-volume"
            height={height}
            key={`${candle.date}:${index}`}
            width={3}
            x={index * 5.4}
            y={62 - height}
          />
        )
      })}
    </svg>
  )
}

function LetterTile({ letter, label, name, value }: { letter: string; label: string; name: string; value: CanslimLetter }) {
  return (
    <div className={`canslim-tile canslim-status-${value.status}`}>
      <span>{letter}</span>
      <strong>{label}</strong>
      <small>{name}</small>
      <p>{value.headline}</p>
    </div>
  )
}

export function CanslimPage() {
  const [symbol, setSymbol] = useState("")
  const [marketRange, setMarketRange] = useState<CanslimMarketRange>("6m")
  const [analysis, setAnalysis] = useState<CanslimAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const loadAnalysis = async (refresh = false) => {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) {
      setError("종목 심볼을 입력해 주세요.")
      return
    }
    const params = new URLSearchParams({ symbol: normalized, market_range: marketRange })
    if (refresh) {
      params.set("refresh", "true")
    }
    setLoading(true)
    setError("")
    try {
      const result = await apiGet<CanslimAnalysis>(`/api/canslim/analysis?${params.toString()}`)
      setAnalysis(result)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    void loadAnalysis(false)
  }

  return (
    <div className="screen-stack canslim-screen">
      <section className="page-header canslim-header">
        <div>
          <h2>CAN SLIM</h2>
          <p>C/A/N/S/L/I/M 근거를 확인하는 미국 상장 보통주 리서치 도구입니다.</p>
        </div>
      </section>

      <form className="panel canslim-search-panel" onSubmit={handleSubmit}>
        <label>
          종목 심볼
          <input
            onChange={(event) => setSymbol(event.target.value)}
            placeholder="NVDA"
            value={symbol}
          />
        </label>
        <label>
          시장 컨텍스트
          <select
            onChange={(event) => setMarketRange(event.target.value as CanslimMarketRange)}
            value={marketRange}
          >
            <option value="3m">3개월</option>
            <option value="6m">6개월</option>
            <option value="1y">1년</option>
          </select>
        </label>
        <button disabled={loading} type="submit">
          <Search size={16} />
          분석
        </button>
        <button disabled={loading || !analysis} onClick={() => void loadAnalysis(true)} type="button">
          <RefreshCw size={16} />
          새로고침
        </button>
      </form>

      {error && <div className="error">{error}</div>}
      {!analysis && !error && (
        <div className="panel empty-state">
          FMP API 키를 설정해 주세요. CAN SLIM v1은 미국 상장 보통주만 지원합니다.
        </div>
      )}

      {analysis && (
        <>
          <section className="panel canslim-company-panel">
            <div>
              <span>{analysis.exchange} · {analysis.currency} · {analysis.cached ? "캐시" : "신규 조회"}</span>
              <h3>{analysis.symbol} · {analysis.company_name}</h3>
              <p>{analysis.sector ?? "-"} · {analysis.industry ?? "-"}</p>
            </div>
            <p>{analysis.description}</p>
          </section>

          <section className="canslim-grid">
            {letters.map(([key, letter, name]) => (
              <LetterTile
                key={key}
                label={statusLabels[analysis.letters[key].status]}
                letter={letter}
                name={name}
                value={analysis.letters[key]}
              />
            ))}
          </section>

          <section className="panel">
            <div className="section-heading">
              <h3>C/A/N/S/L/I/M 근거</h3>
              <span>{analysis.provider.toUpperCase()} · {analysis.generated_at}</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>항목</th>
                    <th>상태</th>
                    <th>근거</th>
                    <th>출처</th>
                  </tr>
                </thead>
                <tbody>
                  {letters.map(([key, letter]) => (
                    <tr key={key}>
                      <td>{letter}</td>
                      <td>{statusLabels[analysis.letters[key].status]}</td>
                      <td>{analysis.letters[key].headline}</td>
                      <td>{analysis.letters[key].source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <h3>상위 성과 기관</h3>
              <span>institutional_flow · top_performing_holders</span>
            </div>
            <div className="metric-strip">
              <span>기관 수 변화 {formatNumber(analysis.letters.i.institutional_flow.holders_count_change)}</span>
              <span>보유 주식 변화 {formatPercent(analysis.letters.i.institutional_flow.shares_change_percent)}</span>
              <span>보유 비중 {formatPercent(analysis.letters.i.institutional_flow.ownership_percent)}</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>기관</th>
                    <th>보유 가치</th>
                    <th>비중</th>
                    <th>1년</th>
                    <th>3년</th>
                    <th>5년</th>
                    <th>S&P 500 대비</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.letters.i.top_performing_holders.map((holder) => (
                    <tr key={holder.cik}>
                      <td>{holder.holder_name}</td>
                      <td>{formatUsd(holder.market_value)}</td>
                      <td>{formatPercent(holder.portfolio_weight_percent)}</td>
                      <td>{formatPercent(holder.performance_1y_percent)}</td>
                      <td>{formatPercent(holder.performance_3y_percent)}</td>
                      <td>{formatPercent(holder.performance_5y_percent)}</td>
                      <td>{formatPercent(holder.excess_vs_sp500_percent)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <h3>시장 컨텍스트 · SPY</h3>
              <span>거래량 · 거래대금</span>
            </div>
            <Sparkline candles={analysis.letters.m.candles} />
            <div className="metric-strip">
              <span>최근 종가 {formatUsd(analysis.letters.m.candles[0]?.close)}</span>
              <span>최근 거래량 {formatNumber(analysis.letters.m.candles[0]?.volume, 0)}</span>
              <span>최근 거래대금 {formatUsd(analysis.letters.m.candles[0]?.traded_value_usd)}</span>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Mount page and nav**

Modify `frontend/src/App.tsx`:

```tsx
import { CanslimPage } from "./components/CanslimPage"
```

Add before settings:

```tsx
{active === "canslim" && <CanslimPage />}
```

Modify `frontend/src/components/AppShell.tsx` import:

```tsx
import { BarChart3, Database, Flag, LineChart, ReceiptText, SearchCheck, Settings, TrendingUp } from "lucide-react"
```

Add nav item before settings:

```tsx
{ id: "canslim", label: "CAN SLIM", icon: SearchCheck },
```

- [ ] **Step 6: Add styles**

Append to `frontend/src/styles.css`:

```css
.canslim-header {
  align-items: end;
  grid-template-columns: minmax(0, 1fr);
}

.canslim-search-panel {
  align-items: end;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(160px, 1fr) 160px auto auto;
}

.canslim-search-panel label {
  display: grid;
  gap: 6px;
}

.canslim-search-panel button {
  align-items: center;
  display: inline-flex;
  gap: 8px;
  justify-content: center;
  min-height: 38px;
}

.canslim-company-panel {
  display: grid;
  gap: 12px;
}

.canslim-company-panel h3 {
  font-size: 20px;
  margin: 4px 0;
}

.canslim-company-panel p {
  margin: 0;
}

.canslim-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(7, minmax(110px, 1fr));
}

.canslim-tile {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  display: grid;
  gap: 4px;
  min-height: 138px;
  padding: 12px;
}

.canslim-tile span {
  color: #111827;
  font-size: 22px;
  font-weight: 800;
}

.canslim-tile strong {
  font-size: 13px;
}

.canslim-tile small,
.canslim-tile p {
  color: #475569;
  font-size: 12px;
  margin: 0;
}

.canslim-status-pass {
  border-color: #86efac;
  background: #f0fdf4;
}

.canslim-status-watch,
.canslim-status-info {
  border-color: #fde047;
  background: #fefce8;
}

.canslim-status-fail {
  border-color: #fca5a5;
  background: #fef2f2;
}

.canslim-status-unknown {
  border-color: #cbd5e1;
  background: #f8fafc;
}

.metric-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 10px 0;
}

.metric-strip span {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  color: #334155;
  padding: 6px 8px;
}

.canslim-market-chart {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  height: 220px;
  width: 100%;
}

.canslim-market-line {
  stroke: #2563eb;
  stroke-width: 2;
}

.canslim-market-volume {
  fill: #94a3b8;
}
```

- [ ] **Step 7: Run frontend tests to verify GREEN**

Run:

```bash
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm run lint
```

Expected: PASS. If TypeScript reports the `letters[key]` lookup as too broad, introduce `type CanslimLetterKey = "c" | "a" | "n" | "s" | "l" | "i" | "m"` and type the `letters` constant with that key.

- [ ] **Step 8: Commit frontend page**

```bash
git add frontend/src/types.ts frontend/src/components/CanslimPage.tsx frontend/src/components/AppShell.tsx frontend/src/App.tsx frontend/src/styles.css frontend/tests/canslim-page.test.mjs frontend/package.json
git commit -m "feat: add CAN SLIM analysis page"
```

---

### Task 7: README And Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Modify `README.md` backend setup section:

````markdown
For CAN SLIM analysis of US-listed common stocks, configure an FMP API key on
the backend:

```bash
PORTFOLIO_FMP_API_KEY=...
```

The CAN SLIM screen calls the local backend route `/api/canslim/analysis`.
FMP credentials are never sent to the frontend.
````

Modify current flow:

```markdown
9. Open `CAN SLIM`, enter a US stock symbol such as `NVDA`, and review the
   C/A/N/S/L/I evidence plus SPY market context.
```

- [ ] **Step 2: Run full verification**

Run:

```bash
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m ruff check backend
cd frontend && npm test
cd frontend && npm run build
cd frontend && npm run lint
git diff --check
```

Expected: all commands pass.

- [ ] **Step 3: Commit README**

```bash
git add README.md
git commit -m "docs: document CAN SLIM setup"
```

---

## Self-Review

Spec coverage:

- US-only symbol search is covered in Tasks 1, 2, 4, and 6.
- FMP backend-only provider and safe error handling are covered in Tasks 1 and 4.
- C/A/N/S/L/I calculations are covered in Task 2.
- Top-performing institutional holders are covered in Tasks 1, 2, and 6.
- M as SPY chart, volume, and traded value without verdict text is covered in Tasks 2 and 6.
- Cache table, TTL-ready cache keys, and refresh behavior are covered in Tasks 3 and 5.
- Frontend navigation, status tiles, institutional table, and SPY context are covered in Task 6.
- README setup is covered in Task 7.

Vague-instruction scan:

- No unfinished markers or vague implementation instructions are intentionally left.

Type consistency:

- Backend uses `CanslimAnalysisResponse`, `CanslimLetterResponse`, `CanslimInstitutionalLetterResponse`, and `CanslimMarketContextResponse`.
- Frontend uses matching `CanslimAnalysis`, `CanslimLetter`, `CanslimInstitutionalLetter`, and `CanslimMarketContext` names.
- The API path is consistently `/api/canslim/analysis`.
- The market range field is consistently `market_range` in the query and `range` in the M response.

Residual risk:

- The route success test may need a fixed date injection because the provider date window depends on `date.today()`.
- FMP's 13F endpoint access depends on plan tier. Keep failures isolated to I rather than failing the whole analysis.
