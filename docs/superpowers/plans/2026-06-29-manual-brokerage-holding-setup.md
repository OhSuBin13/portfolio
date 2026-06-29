# Toss-Only Brokerage Portfolio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the local account/asset/holding/transaction ledger with a Toss-only brokerage portfolio surface backed directly by Toss accounts, Toss stock holdings, and Toss FX data.

**Architecture:** Toss becomes the brokerage source of truth for accounts and holdings. SQLite remains only for app settings, goals, backups, optional FX/cache/history records, and migration bookkeeping; it no longer owns `accounts`, `assets`, `holdings`, or `transactions`. Backend APIs expose Toss account, holding, and summary read models; frontend removes local manual account/asset/transaction workflows and shows read-only Toss brokerage data.

**Tech Stack:** FastAPI, SQLite migrations, Pydantic response models, httpx, pytest/pytest-httpx, React/Vite, source-inspection frontend tests.

---

## Product Decision

This is a breaking product change. The app stops being a full local personal-finance ledger and becomes a Toss brokerage stock/ETF portfolio viewer.

Toss `GET /api/v1/holdings` currently covers domestic KR and US stocks. It does not cover local cash/savings/debt tracking, manual adjustments, the app's local transaction ledger, or non-stock products such as overseas options and bonds. Those features must be removed or explicitly redesigned later from different Toss APIs.

## Current Context

- Current branch: `feature/manual-brokerage-holdings-setup`.
- Current schema version before this plan: `SCHEMA_VERSION = 9`.
- Existing local source tables to remove from the source-of-truth path: `accounts`, `assets`, `holdings`, `transactions`.
- Existing local tables that may remain: `schema_migrations`, `settings`, `fx_rates`, `goals`, `backups`.
- Existing Toss auth/provider boundary: `backend/src/portfolio_app/services/market_data.py::TossAuthClient`.
- Official Toss docs checked on 2026-06-29:
  - `GET /api/v1/accounts` returns Toss brokerage accounts and `accountSeq`.
  - `GET /api/v1/holdings` requires `X-Tossinvest-Account`.
  - `HoldingsItem` includes `symbol`, `name`, `marketCountry`, `currency`, `quantity`, `lastPrice`, `averagePurchasePrice`, and `marketValue`.
  - `Price` overview has `krw` and optional `usd`, so USD values still need USD/KRW conversion for a KRW net-worth view.

## Scope

Implement the Toss-only brokerage slice:

- Toss account list.
- Toss holding list for a selected Toss `accountSeq`.
- Toss-derived `/api/summary`.
- Read-only holdings UI.
- Dashboard using Toss-derived summary.
- Removal of local account/asset/transaction creation and local transaction history UI.

Out of scope for this plan:

- Toss order placement.
- Toss order-history import.
- Local manual onboarding or adjustment flows.
- Cash, savings, debt, and non-stock products.
- Growth/cashflow analytics based on local transactions.

## File Structure

- Create `backend/src/portfolio_app/services/toss_portfolio.py`: Toss account/holding provider and Toss summary assembler.
- Create `backend/src/portfolio_app/api/toss_portfolio.py`: `/api/toss/accounts` and `/api/toss/holdings`.
- Modify `backend/src/portfolio_app/api/summary.py`: use Toss summary instead of local DB summary.
- Modify `backend/src/portfolio_app/models.py`: replace local asset-allocation response shape with Toss-friendly allocation keys.
- Modify `backend/src/portfolio_app/schema.sql`: remove local ledger tables from fresh schema.
- Modify `backend/src/portfolio_app/migrations.py`: bump to v10 and drop local ledger tables on migration.
- Modify `backend/src/portfolio_app/main.py`: remove local account/asset/transaction/market-data routers, register Toss portfolio router.
- Delete `backend/src/portfolio_app/api/accounts.py`, `api/assets.py`, `api/transactions.py`, `api/market_data.py`, and `api/growth.py`.
- Delete `backend/src/portfolio_app/services/transactions.py`, `services/summary.py`, `services/growth.py`, and `services/market_sync_scheduler.py`.
- Create `backend/tests/test_toss_portfolio.py`: provider and summary-service tests.
- Create `backend/tests/test_toss_only_architecture.py`: route/schema/frontend removal guards.
- Modify `backend/tests/test_api.py`, `backend/tests/test_summary.py`, `backend/tests/test_db.py`: replace local-ledger expectations with Toss-only expectations.
- Delete `backend/tests/test_transactions.py` and local account/asset/market-data/growth tests that only cover removed behavior.
- Modify `frontend/src/types.ts`: Toss account/holding and Toss allocation types.
- Replace `frontend/src/components/HoldingsPage.tsx`: read-only Toss holdings view.
- Modify `frontend/src/components/Dashboard.tsx`: pass selected Toss account to `/api/summary`.
- Modify `frontend/src/components/SettingsPage.tsx`: remove local market-sync status polling and keep Toss credential/backups guidance.
- Modify `frontend/src/components/AppShell.tsx` and `frontend/src/App.tsx`: remove Transactions and Growth navigation for this Toss-only slice.
- Delete `frontend/src/components/TransactionsPage.tsx`, `frontend/src/components/GrowthHistoryPage.tsx`, `frontend/src/transactionPayload.ts`, and tests tied to local transaction entry/growth.
- Modify frontend source tests to assert no local ledger endpoints remain in UI.
- Modify `frontend/tests/settings-market-sync.test.mjs`: assert local market-sync status UI is gone.
- Modify `docs/toss-open-api-integration.md`: document the Toss-only product boundary.

## Task 1: Lock The Toss-Only Architecture Contract

**Files:**
- Create: `backend/tests/test_toss_only_architecture.py`
- Modify: `frontend/tests/holdings-page-form.test.mjs`
- Modify: `frontend/tests/transaction-payload-builder.test.mjs`
- Modify: `frontend/tests/growth-history-page.test.mjs`

- [ ] **Step 1: Add backend architecture guard tests**

Create `backend/tests/test_toss_only_architecture.py`:

```python
from pathlib import Path

ROOT = Path(__file__).parents[1]
BACKEND_SRC = ROOT / "src/portfolio_app"
FRONTEND_SRC = ROOT.parents[0] / "frontend/src"


def test_fresh_schema_no_longer_defines_local_ledger_tables():
    schema_sql = (BACKEND_SRC / "schema.sql").read_text(encoding="utf-8")

    removed_tables = ("accounts", "assets", "holdings", "transactions")
    for table_name in removed_tables:
        assert f"create table if not exists {table_name}" not in schema_sql


def test_main_registers_toss_portfolio_instead_of_local_ledger_routers():
    source = (BACKEND_SRC / "main.py").read_text(encoding="utf-8")

    assert "toss_portfolio" in source
    assert "app.include_router(toss_portfolio.router)" in source
    assert "app.include_router(accounts.router)" not in source
    assert "app.include_router(assets.router)" not in source
    assert "app.include_router(transactions.router)" not in source
    assert "app.include_router(market_data.router)" not in source


def test_frontend_no_longer_calls_local_ledger_endpoints():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in FRONTEND_SRC.glob("**/*")
        if path.suffix in {".ts", ".tsx"}
    )

    for endpoint in ("/api/accounts", "/api/assets", "/api/transactions", "/api/market-data/status"):
        assert endpoint not in combined
    assert "/api/toss/accounts" in combined
    assert "/api/toss/holdings" in combined
```

- [ ] **Step 2: Replace frontend local-ledger source tests**

Replace `frontend/tests/holdings-page-form.test.mjs` with:

```javascript
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/HoldingsPage.tsx", import.meta.url), "utf8")
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")

assert.ok(source.includes("/api/toss/accounts"), "Holdings page should load Toss brokerage accounts")
assert.ok(source.includes("/api/toss/holdings"), "Holdings page should load Toss holdings")
assert.ok(source.includes("Toss 보유자산"), "Holdings page should present Toss holdings")
assert.ok(source.includes("account_seq"), "Holdings page should use Toss account sequence identifiers")
assert.ok(source.includes("readOnly"), "Holdings page should not present manual ledger writes")

for (const removedEndpoint of ["/api/accounts", "/api/assets", "/api/transactions"]) {
  assert.ok(!source.includes(removedEndpoint), `${removedEndpoint} should not be used by Toss-only holdings`)
}

for (const removedText of ["계좌 만들기", "자산 만들기", "초기 잔액/보유 반영", "초기 거래 저장"]) {
  assert.ok(!source.includes(removedText), `${removedText} should be removed from Toss-only holdings`)
}

assert.ok(!appSource.includes("TransactionsPage"), "App should not mount the local transaction ledger page")
assert.ok(!shellSource.includes('id: "transactions"'), "Navigation should not expose local transactions")
assert.ok(!shellSource.includes('id: "growth"'), "Navigation should not expose transaction-derived growth")
```

Replace `frontend/tests/transaction-payload-builder.test.mjs` with:

```javascript
import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const payloadFile = new URL("../src/transactionPayload.ts", import.meta.url)

assert.ok(!appSource.includes("TransactionsPage"), "Toss-only app should remove transaction entry")
assert.ok(!existsSync(payloadFile), "Toss-only app should remove local transaction payload builder")
```

Replace `frontend/tests/growth-history-page.test.mjs` with:

```javascript
import assert from "node:assert/strict"
import { existsSync, readFileSync } from "node:fs"

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8")
const shellSource = readFileSync(new URL("../src/components/AppShell.tsx", import.meta.url), "utf8")
const growthPageFile = new URL("../src/components/GrowthHistoryPage.tsx", import.meta.url)

assert.ok(!appSource.includes("GrowthHistoryPage"), "Toss-only app should not mount transaction-derived growth history")
assert.ok(!shellSource.includes("성장기록"), "Toss-only app should remove growth navigation")
assert.ok(!existsSync(growthPageFile), "Toss-only app should delete the transaction-derived growth page")
```

- [ ] **Step 3: Run architecture tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_only_architecture.py -q
node frontend/tests/holdings-page-form.test.mjs
node frontend/tests/transaction-payload-builder.test.mjs
node frontend/tests/growth-history-page.test.mjs
```

Expected: FAIL because the local ledger routes, schema, and UI still exist.

## Task 2: Toss Provider And Summary Service

**Files:**
- Create: `backend/src/portfolio_app/services/toss_portfolio.py`
- Modify: `backend/src/portfolio_app/models.py`
- Create: `backend/tests/test_toss_portfolio.py`

- [ ] **Step 1: Add failing provider and summary tests**

Create `backend/tests/test_toss_portfolio.py`:

```python
import pytest

from portfolio_app.services.market_data import FxRate, TossAuthClient
from portfolio_app.services.toss_portfolio import (
    TossBrokerageProvider,
    build_toss_summary,
)


@pytest.mark.asyncio
async def test_toss_brokerage_provider_fetches_accounts(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        json={"result": [{"accountNo": "123-45-67890", "accountSeq": 12345, "accountType": "BROKERAGE"}]},
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    accounts = await provider.fetch_accounts()

    assert accounts[0].account_seq == "12345"
    assert accounts[0].account_no == "123-45-67890"
    assert accounts[0].account_type == "BROKERAGE"
    assert accounts[0].display_name == "토스증권 123-45-67890"


@pytest.mark.asyncio
async def test_toss_brokerage_provider_fetches_holdings(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={
            "result": {
                "items": [
                    {
                        "symbol": "005930",
                        "name": "삼성전자",
                        "marketCountry": "KR",
                        "currency": "KRW",
                        "quantity": "10",
                        "lastPrice": "75000",
                        "averagePurchasePrice": "70000",
                        "marketValue": {"purchaseAmount": "700000", "amount": "750000", "amountAfterCost": "749000"},
                    },
                    {
                        "symbol": "VOO",
                        "name": "Vanguard S&P 500 ETF",
                        "marketCountry": "US",
                        "currency": "USD",
                        "quantity": "3",
                        "lastPrice": "500",
                        "averagePurchasePrice": "450",
                        "marketValue": {"purchaseAmount": "1350", "amount": "1500", "amountAfterCost": "1499"},
                    },
                ]
            }
        },
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    holdings = await provider.fetch_holdings("12345")

    assert [holding.symbol for holding in holdings] == ["005930", "VOO"]
    assert holdings[0].market == "KR"
    assert holdings[0].market_value == 750000
    assert holdings[1].currency == "USD"
    assert holdings[1].market_value == 1500
    request = httpx_mock.get_requests()[1]
    assert request.headers["x-tossinvest-account"] == "12345"


class StubFxProvider:
    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        assert base_currency == "USD"
        assert quote_currency == "KRW"
        return FxRate(
            base_currency="USD",
            quote_currency="KRW",
            rate=1400,
            source="toss",
            fetched_at="2026-06-29T00:00:00+00:00",
        )


def test_build_toss_summary_uses_toss_holdings_and_fx_rate():
    from portfolio_app.services.toss_portfolio import TossHolding

    holdings = [
        TossHolding(
            symbol="005930",
            name="삼성전자",
            market="KR",
            currency="KRW",
            quantity=10,
            average_purchase_price=70000,
            last_price=75000,
            market_value=750000,
        ),
        TossHolding(
            symbol="VOO",
            name="Vanguard S&P 500 ETF",
            market="US",
            currency="USD",
            quantity=3,
            average_purchase_price=450,
            last_price=500,
            market_value=1500,
        ),
    ]

    result = build_toss_summary(holdings, usd_krw_rate=1400)

    assert result.summary.net_worth_krw == 2_850_000
    assert result.summary.gross_assets_krw == 2_850_000
    assert result.summary.debt_krw == 0
    assert result.summary.monthly_income_krw == 0
    assert result.summary.usd_krw_rate == 1400
    assert result.asset_mix == {"stock_etf": 100}
    assert [row["asset_key"] for row in result.asset_allocations] == ["KR:005930", "US:VOO"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py -q
```

Expected: FAIL because `services/toss_portfolio.py` and the `asset_key` allocation shape do not exist.

- [ ] **Step 3: Change allocation response model**

In `backend/src/portfolio_app/models.py`, replace `AssetAllocation` with:

```python
class AssetAllocation(BaseModel):
    model_config = ConfigDict(strict=True)

    asset_key: str
    asset_type: Literal["stock_etf"]
    symbol: str
    name: str
    label: str
    market: Literal["KR", "US"]
    currency: Currency
    value_krw: float = Field(ge=0, allow_inf_nan=False)
    percent: float = Field(ge=0, le=100, allow_inf_nan=False)
```

- [ ] **Step 4: Implement Toss portfolio service**

Create `backend/src/portfolio_app/services/toss_portfolio.py`:

```python
import math
from dataclasses import dataclass
from typing import Any

import httpx

from portfolio_app.models import PortfolioSummary
from portfolio_app.services.market_data import FxRateProvider, TossAuthClient, default_fx_rate_provider

TOSS_BASE_URL = "https://openapi.tossinvest.com"


@dataclass(frozen=True)
class TossAccount:
    account_seq: str
    account_no: str
    account_type: str
    display_name: str


@dataclass(frozen=True)
class TossHolding:
    symbol: str
    name: str
    market: str
    currency: str
    quantity: float
    average_purchase_price: float
    last_price: float | None
    market_value: float


@dataclass(frozen=True)
class TossSummaryResult:
    summary: PortfolioSummary
    asset_mix: dict[str, float]
    asset_allocations: list[dict[str, object]]


def _positive_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(message)
    return number


def _optional_positive_number(value: Any, message: str) -> float | None:
    if value is None or value == "":
        return None
    return _positive_number(value, message)


class TossBrokerageProvider:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = TOSS_BASE_URL,
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

    async def fetch_accounts(self) -> list[TossAccount]:
        token = await self._token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/accounts",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, list):
            raise ValueError("Toss 응답에서 계좌 목록을 찾을 수 없습니다.")

        accounts: list[TossAccount] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            account_seq = str(item.get("accountSeq", "")).strip()
            account_no = str(item.get("accountNo", "")).strip()
            account_type = str(item.get("accountType", "")).strip().upper()
            if not account_seq or not account_no:
                continue
            accounts.append(
                TossAccount(
                    account_seq=account_seq,
                    account_no=account_no,
                    account_type=account_type or "UNKNOWN",
                    display_name=f"토스증권 {account_no}",
                )
            )
        return accounts

    async def fetch_holdings(self, account_seq: str) -> list[TossHolding]:
        normalized_account_seq = account_seq.strip()
        if not normalized_account_seq:
            raise ValueError("Toss 계좌 식별값을 입력해 주세요.")

        token = await self._token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/holdings",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Tossinvest-Account": normalized_account_seq,
                },
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("result") if isinstance(payload, dict) else None
        items = result.get("items") if isinstance(result, dict) else None
        if not isinstance(items, list):
            raise ValueError("Toss 응답에서 보유 주식 목록을 찾을 수 없습니다.")

        holdings: list[TossHolding] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "")).strip().upper()
            name = str(item.get("name", "")).strip()
            market = str(item.get("marketCountry", "")).strip().upper()
            currency = str(item.get("currency", "")).strip().upper()
            market_value = item.get("marketValue")
            if not isinstance(market_value, dict):
                raise ValueError("Toss 응답에서 평가금액을 찾을 수 없습니다.")
            if market not in {"KR", "US"}:
                raise ValueError("Toss 보유자산 시장은 KR 또는 US여야 합니다.")
            if currency not in {"KRW", "USD"}:
                raise ValueError("Toss 보유자산 통화는 KRW 또는 USD여야 합니다.")
            holdings.append(
                TossHolding(
                    symbol=symbol,
                    name=name,
                    market=market,
                    currency=currency,
                    quantity=_positive_number(item.get("quantity"), "Toss 보유 수량은 0보다 커야 합니다."),
                    average_purchase_price=_positive_number(
                        item.get("averagePurchasePrice"),
                        "Toss 평균 매입가는 0보다 커야 합니다.",
                    ),
                    last_price=_optional_positive_number(item.get("lastPrice"), "Toss 현재가는 0보다 커야 합니다."),
                    market_value=_positive_number(
                        market_value.get("amount"),
                        "Toss 평가금액은 0보다 커야 합니다.",
                    ),
                )
            )
        return holdings


def build_toss_summary(
    holdings: list[TossHolding],
    *,
    usd_krw_rate: float | None,
) -> TossSummaryResult:
    values: list[tuple[TossHolding, float]] = []
    for holding in holdings:
        if holding.currency == "KRW":
            value_krw = holding.market_value
        elif holding.currency == "USD":
            if usd_krw_rate is None or usd_krw_rate <= 0:
                raise ValueError("USD 보유자산 평가에 필요한 USD/KRW 환율 정보가 없습니다.")
            value_krw = holding.market_value * usd_krw_rate
        else:
            raise ValueError("지원하지 않는 Toss 보유자산 통화입니다.")
        values.append((holding, value_krw))

    total = sum(value for _holding, value in values)
    allocations = [
        {
            "asset_key": f"{holding.market}:{holding.symbol}",
            "asset_type": "stock_etf",
            "symbol": holding.symbol,
            "name": holding.name,
            "label": holding.symbol,
            "market": holding.market,
            "currency": holding.currency,
            "value_krw": value_krw,
            "percent": round((value_krw / total) * 100, 2) if total > 0 else 0,
        }
        for holding, value_krw in values
        if value_krw > 0
    ]
    summary = PortfolioSummary(
        net_worth_krw=total,
        gross_assets_krw=total,
        debt_krw=0,
        monthly_income_krw=0,
        usd_krw_rate=usd_krw_rate,
        usd_krw_change_percent=None,
    )
    return TossSummaryResult(
        summary=summary,
        asset_mix={"stock_etf": 100} if total > 0 else {},
        asset_allocations=allocations,
    )


async def fetch_toss_summary(
    account_seq: str,
    *,
    provider: TossBrokerageProvider,
    fx_provider: FxRateProvider | None = None,
) -> TossSummaryResult:
    holdings = await provider.fetch_holdings(account_seq)
    has_usd = any(holding.currency == "USD" for holding in holdings)
    usd_krw_rate: float | None = None
    if has_usd:
        rate = await (fx_provider or default_fx_rate_provider()).fetch_rate("USD", "KRW")
        usd_krw_rate = rate.rate
    return build_toss_summary(holdings, usd_krw_rate=usd_krw_rate)
```

- [ ] **Step 5: Run service tests and verify they pass**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py -q
```

Expected: PASS.

## Task 3: Toss-Only Backend APIs

**Files:**
- Create: `backend/src/portfolio_app/api/toss_portfolio.py`
- Modify: `backend/src/portfolio_app/api/summary.py`
- Modify: `backend/src/portfolio_app/main.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_summary.py`

- [ ] **Step 1: Add failing API tests**

Replace or add these focused tests in `backend/tests/test_api.py`:

```python
def test_openapi_exposes_toss_only_portfolio_paths(tmp_path):
    client = create_test_client(tmp_path)
    schema = client.app.openapi()

    assert "/api/toss/accounts" in schema["paths"]
    assert "/api/toss/holdings" in schema["paths"]
    assert "/api/summary" in schema["paths"]
    assert "/api/accounts" not in schema["paths"]
    assert "/api/assets" not in schema["paths"]
    assert "/api/transactions" not in schema["paths"]


def test_toss_accounts_endpoint_returns_provider_accounts(tmp_path, monkeypatch):
    from portfolio_app.api import toss_portfolio
    from portfolio_app.services.toss_portfolio import TossAccount

    class StubProvider:
        def __init__(self, client_id, client_secret):
            pass

        async def fetch_accounts(self):
            return [
                TossAccount(
                    account_seq="12345",
                    account_no="123-45-67890",
                    account_type="BROKERAGE",
                    display_name="토스증권 123-45-67890",
                )
            ]

    monkeypatch.setattr(toss_portfolio, "TossBrokerageProvider", StubProvider)
    client = create_test_client(tmp_path)

    response = client.get("/api/toss/accounts")

    assert response.status_code == 200
    assert response.json() == [
        {
            "account_seq": "12345",
            "account_no": "123-45-67890",
            "account_type": "BROKERAGE",
            "display_name": "토스증권 123-45-67890",
        }
    ]


def test_toss_holdings_endpoint_returns_provider_holdings(tmp_path, monkeypatch):
    from portfolio_app.api import toss_portfolio
    from portfolio_app.services.toss_portfolio import TossHolding

    class StubProvider:
        def __init__(self, client_id, client_secret):
            pass

        async def fetch_holdings(self, account_seq):
            assert account_seq == "12345"
            return [
                TossHolding(
                    symbol="005930",
                    name="삼성전자",
                    market="KR",
                    currency="KRW",
                    quantity=10,
                    average_purchase_price=70000,
                    last_price=75000,
                    market_value=750000,
                )
            ]

    monkeypatch.setattr(toss_portfolio, "TossBrokerageProvider", StubProvider)
    client = create_test_client(tmp_path)

    response = client.get("/api/toss/holdings?account_seq=12345")

    assert response.status_code == 200
    assert response.json()[0]["symbol"] == "005930"
    assert response.json()[0]["market_value"] == 750000


def test_summary_endpoint_uses_toss_account_seq(tmp_path, monkeypatch):
    from portfolio_app.api import summary
    from portfolio_app.services.toss_portfolio import TossHolding

    class StubProvider:
        def __init__(self, client_id, client_secret):
            pass

        async def fetch_holdings(self, account_seq):
            assert account_seq == "12345"
            return [
                TossHolding(
                    symbol="005930",
                    name="삼성전자",
                    market="KR",
                    currency="KRW",
                    quantity=10,
                    average_purchase_price=70000,
                    last_price=75000,
                    market_value=750000,
                )
            ]

    monkeypatch.setattr(summary, "TossBrokerageProvider", StubProvider)
    client = create_test_client(tmp_path)

    response = client.get("/api/summary?account_seq=12345")

    assert response.status_code == 200
    assert response.json()["net_worth_krw"] == 750000
    assert response.json()["asset_allocations"][0]["asset_key"] == "KR:005930"
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_openapi_exposes_toss_only_portfolio_paths backend/tests/test_api.py::test_toss_accounts_endpoint_returns_provider_accounts backend/tests/test_api.py::test_toss_holdings_endpoint_returns_provider_holdings backend/tests/test_api.py::test_summary_endpoint_uses_toss_account_seq -q
```

Expected: FAIL because the Toss-only API routes are not implemented and local routes still exist.

- [ ] **Step 3: Create Toss portfolio router**

Create `backend/src/portfolio_app/api/toss_portfolio.py`:

```python
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from portfolio_app.services.toss_portfolio import TossBrokerageProvider

router = APIRouter(prefix="/api/toss", tags=["toss"])
AccountSeq = Annotated[str, Query(min_length=1)]


class TossAccountResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    account_seq: str
    account_no: str
    account_type: str
    display_name: str


class TossHoldingResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    symbol: str
    name: str
    market: str
    currency: str
    quantity: float
    average_purchase_price: float
    last_price: float | None
    market_value: float


def _provider(request: Request) -> TossBrokerageProvider:
    settings = request.app.state.settings
    return TossBrokerageProvider(settings.toss_api_key, settings.toss_secret_key)


def _provider_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        reason = response.reason_phrase or "Unknown"
        return f"Toss 요청 실패: HTTP {response.status_code} {reason}"
    return f"Toss 요청 실패: {exc.__class__.__name__}"


@router.get("/accounts", response_model=list[TossAccountResponse])
async def list_toss_accounts(request: Request) -> list[TossAccountResponse]:
    try:
        accounts = await _provider(request).fetch_accounts()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_provider_error_message(exc)) from exc

    return [
        TossAccountResponse(
            account_seq=account.account_seq,
            account_no=account.account_no,
            account_type=account.account_type,
            display_name=account.display_name,
        )
        for account in accounts
    ]


@router.get("/holdings", response_model=list[TossHoldingResponse])
async def list_toss_holdings(
    request: Request,
    account_seq: AccountSeq,
) -> list[TossHoldingResponse]:
    try:
        holdings = await _provider(request).fetch_holdings(account_seq)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_provider_error_message(exc)) from exc

    return [
        TossHoldingResponse(
            symbol=holding.symbol,
            name=holding.name,
            market=holding.market,
            currency=holding.currency,
            quantity=holding.quantity,
            average_purchase_price=holding.average_purchase_price,
            last_price=holding.last_price,
            market_value=holding.market_value,
        )
        for holding in holdings
    ]
```

- [ ] **Step 4: Replace summary API with Toss summary**

Replace `backend/src/portfolio_app/api/summary.py` with:

```python
import sqlite3
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from portfolio_app.api import get_db
from portfolio_app.models import SummaryResponse
from portfolio_app.services import goals as goal_service
from portfolio_app.services.market_data import default_fx_rate_provider
from portfolio_app.services.toss_portfolio import (
    TossBrokerageProvider,
    fetch_toss_summary,
)

router = APIRouter(prefix="/api/summary", tags=["summary"])
AccountSeq = Annotated[str, Query(min_length=1)]
Db = Annotated[sqlite3.Connection, Depends(get_db)]


def _provider_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        reason = response.reason_phrase or "Unknown"
        return f"Toss 요청 실패: HTTP {response.status_code} {reason}"
    return f"Toss 요청 실패: {exc.__class__.__name__}"


@router.get("", response_model=SummaryResponse)
async def get_summary(
    request: Request,
    db: Db,
    account_seq: AccountSeq,
) -> SummaryResponse:
    settings = request.app.state.settings
    provider = TossBrokerageProvider(settings.toss_api_key, settings.toss_secret_key)
    try:
        result = await fetch_toss_summary(
            account_seq,
            provider=provider,
            fx_provider=default_fx_rate_provider(settings),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_provider_error_message(exc)) from exc

    return SummaryResponse(
        **result.summary.model_dump(),
        asset_mix=result.asset_mix,
        asset_allocations=result.asset_allocations,
        goal_progress=goal_service.list_goal_progress_for_summary(db, result.summary),
    )
```

- [ ] **Step 5: Register only Toss-compatible routers**

In `backend/src/portfolio_app/main.py`, change the API imports to remove local ledger and market sync routers:

```python
from portfolio_app.api import (
    backups,
    goals,
    summary,
    toss_portfolio,
)
```

At router registration, keep:

```python
    app.include_router(summary.router)
    app.include_router(toss_portfolio.router)
    app.include_router(goals.router)
    app.include_router(backups.router)
```

Remove:

```python
    app.include_router(accounts.router)
    app.include_router(assets.router)
    app.include_router(transactions.router)
    app.include_router(growth.router)
    app.include_router(market_data.router)
```

Also remove `start_market_sync_task()` and `stop_market_sync_task()` from lifespan, because there are no local assets or `price_snapshots` to sync.

- [ ] **Step 6: Run API tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_openapi_exposes_toss_only_portfolio_paths backend/tests/test_api.py::test_toss_accounts_endpoint_returns_provider_accounts backend/tests/test_api.py::test_toss_holdings_endpoint_returns_provider_holdings backend/tests/test_api.py::test_summary_endpoint_uses_toss_account_seq -q
```

Expected: PASS.

## Task 4: Remove Local Ledger Schema And Migration Path

**Files:**
- Modify: `backend/src/portfolio_app/schema.sql`
- Modify: `backend/src/portfolio_app/migrations.py`
- Modify: `backend/tests/test_db.py`

- [ ] **Step 1: Replace DB tests for Toss-only schema**

In `backend/tests/test_db.py`, replace the core table test and schema version test with:

```python
def test_migrate_creates_toss_only_tables(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)

    assert {
        "schema_migrations",
        "settings",
        "fx_rates",
        "goals",
        "backups",
    }.issubset(table_names(db))
    assert {"accounts", "assets", "holdings", "transactions"}.isdisjoint(table_names(db))


def test_migrate_records_schema_version(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)

    assert migration_versions(db) == [10]
```

Add this migration test:

```python
def test_migrate_from_v9_drops_local_ledger_tables(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    db.executescript(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        );
        insert into schema_migrations(version) values (9);
        create table accounts (id integer primary key);
        create table assets (id integer primary key);
        create table holdings (id integer primary key);
        create table transactions (id integer primary key);
        create table price_snapshots (id integer primary key);
        create table settings (
          key text primary key,
          value text not null,
          updated_at text not null default current_timestamp
        );
        create table fx_rates (
          id integer primary key,
          base_currency text not null,
          quote_currency text not null default 'KRW',
          rate real not null,
          source text not null,
          fetched_at text not null,
          change_percent real
        );
        create table goals (
          id integer primary key,
          name text not null,
          type text not null check (type in ('net_worth','monthly_income')),
          target_amount_krw real not null check (target_amount_krw > 0),
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        create table backups (
          id integer primary key,
          path text not null,
          reason text not null,
          created_at text not null default current_timestamp
        );
        """
    )

    migrate(db)

    assert migration_versions(db)[-1] == 10
    assert {"accounts", "assets", "holdings", "transactions", "price_snapshots"}.isdisjoint(table_names(db))
```

- [ ] **Step 2: Run DB tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py::test_migrate_creates_toss_only_tables backend/tests/test_db.py::test_migrate_records_schema_version backend/tests/test_db.py::test_migrate_from_v9_drops_local_ledger_tables -q
```

Expected: FAIL because v10 and table drops are not implemented.

- [ ] **Step 3: Replace fresh schema**

In `backend/src/portfolio_app/schema.sql`, remove these tables and related indexes:

```sql
accounts
assets
holdings
transactions
price_snapshots
portfolio_snapshots
```

Keep only:

```sql
create table if not exists schema_migrations (
  version integer primary key,
  applied_at text not null default current_timestamp
);

create table if not exists fx_rates (
  id integer primary key,
  base_currency text not null check (base_currency in ('USD','KRW')),
  quote_currency text not null check (quote_currency in ('USD','KRW')) default 'KRW',
  rate real not null,
  source text not null,
  fetched_at text not null,
  change_percent real,
  unique(base_currency, quote_currency, fetched_at)
);

create index if not exists idx_fx_rates_summary_pair_latest
on fx_rates(base_currency, quote_currency, fetched_at desc, id desc);

create table if not exists goals (
  id integer primary key,
  name text not null,
  type text not null check (type in ('net_worth','monthly_income')),
  target_amount_krw real not null check (target_amount_krw > 0),
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists backups (
  id integer primary key,
  path text not null,
  reason text not null,
  created_at text not null default current_timestamp
);

create table if not exists settings (
  key text primary key,
  value text not null,
  updated_at text not null default current_timestamp
);
```

- [ ] **Step 4: Implement v10 migration**

In `backend/src/portfolio_app/migrations.py`, set:

```python
SCHEMA_VERSION = 10
```

Add:

```python
TOSS_ONLY_REMOVED_TABLES = (
    "portfolio_snapshots",
    "price_snapshots",
    "transactions",
    "holdings",
    "assets",
    "accounts",
)


def _migrate_from_9_to_10(db: sqlite3.Connection) -> None:
    db.execute("pragma foreign_keys = off")
    try:
        with db:
            for table_name in TOSS_ONLY_REMOVED_TABLES:
                db.execute(f"drop table if exists {table_name}")
            db.execute("insert or ignore into schema_migrations(version) values (10)")
    finally:
        db.execute("pragma foreign_keys = on")
```

In `migrate()`, after v9:

```python
    if version == 9:
        _migrate_from_9_to_10(db)
        version = 10
```

Remove `_seed_builtin_initial_assets()` calls from the fresh migration path. Old migration helper functions may stay as compatibility shims for databases below v9, but the final v10 step must always drop the local ledger tables listed in `TOSS_ONLY_REMOVED_TABLES`.

- [ ] **Step 5: Run DB tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py::test_migrate_creates_toss_only_tables backend/tests/test_db.py::test_migrate_records_schema_version backend/tests/test_db.py::test_migrate_from_v9_drops_local_ledger_tables -q
```

Expected: PASS.

## Task 5: Toss-Only Frontend

**Files:**
- Modify: `frontend/src/types.ts`
- Replace: `frontend/src/components/HoldingsPage.tsx`
- Modify: `frontend/src/components/Dashboard.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/components/TransactionsPage.tsx`
- Delete: `frontend/src/components/GrowthHistoryPage.tsx`
- Delete: `frontend/src/transactionPayload.ts`
- Modify: `frontend/tests/holdings-page-form.test.mjs`
- Modify: `frontend/tests/transaction-payload-builder.test.mjs`
- Modify: `frontend/tests/growth-history-page.test.mjs`

- [ ] **Step 1: Add frontend Toss types**

In `frontend/src/types.ts`, remove `Account`, `Asset`, and `Transaction`. Add:

```typescript
export type TossAccount = {
  account_seq: string
  account_no: string
  account_type: string
  display_name: string
}

export type TossHolding = {
  symbol: string
  name: string
  market: "KR" | "US"
  currency: "KRW" | "USD"
  quantity: number
  average_purchase_price: number
  last_price: number | null
  market_value: number
}
```

Change `AssetAllocation` to:

```typescript
export type AssetAllocation = {
  asset_key: string
  asset_type: "stock_etf"
  symbol: string
  name: string
  label: string
  market: "KR" | "US"
  currency: "KRW" | "USD"
  value_krw: number
  percent: number
}
```

- [ ] **Step 2: Replace holdings page**

Replace `frontend/src/components/HoldingsPage.tsx` with a read-only Toss view:

```tsx
import { useEffect, useState } from "react"
import { apiGet } from "../api"
import type { TossAccount, TossHolding } from "../types"

const getErrorMessage = (err: unknown) => (err instanceof Error ? err.message : String(err))
const formatNumber = (value: number) => value.toLocaleString("ko-KR", { maximumFractionDigits: 6 })
const formatMoney = (value: number, currency: string) =>
  `${value.toLocaleString(currency === "USD" ? "en-US" : "ko-KR", { maximumFractionDigits: 2 })} ${currency}`

export function HoldingsPage() {
  const [accounts, setAccounts] = useState<TossAccount[]>([])
  const [selectedAccountSeq, setSelectedAccountSeq] = useState("")
  const [holdings, setHoldings] = useState<TossHolding[]>([])
  const [error, setError] = useState("")
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    apiGet<TossAccount[]>("/api/toss/accounts")
      .then((data) => {
        setAccounts(data)
        setSelectedAccountSeq(data[0]?.account_seq ?? "")
        setError("")
      })
      .catch((err) => setError(getErrorMessage(err)))
  }, [])

  useEffect(() => {
    if (!selectedAccountSeq) {
      setHoldings([])
      return
    }

    setIsLoading(true)
    apiGet<TossHolding[]>(`/api/toss/holdings?account_seq=${encodeURIComponent(selectedAccountSeq)}`)
      .then((data) => {
        setHoldings(data)
        setError("")
      })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setIsLoading(false))
  }, [selectedAccountSeq])

  return (
    <section className="screen-stack">
      <header className="page-header">
        <h2>Toss 보유자산</h2>
        <p>토스증권 계좌의 국내/미국 주식 보유 현황을 조회합니다.</p>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="panel form-panel">
        <div className="section-heading">
          <h3>Toss 계좌</h3>
          <span>{accounts.length.toLocaleString("ko-KR")}개</span>
        </div>
        <label>
          조회 계좌
          <select
            value={selectedAccountSeq}
            onChange={(event) => setSelectedAccountSeq(event.target.value)}
          >
            <option value="">선택</option>
            {accounts.map((account) => (
              <option key={account.account_seq} value={account.account_seq}>
                {account.display_name}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="panel">
        <div className="section-heading">
          <h3>보유 주식</h3>
          <span>{isLoading ? "조회 중" : `${holdings.length.toLocaleString("ko-KR")}개`}</span>
        </div>
        {holdings.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>종목</th>
                  <th>시장</th>
                  <th>통화</th>
                  <th className="numeric-cell">수량</th>
                  <th className="numeric-cell">평균가</th>
                  <th className="numeric-cell">현재가</th>
                  <th className="numeric-cell">평가금액</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((holding) => (
                  <tr key={`${holding.market}:${holding.symbol}`}>
                    <td>{holding.name} ({holding.symbol})</td>
                    <td>{holding.market}</td>
                    <td>{holding.currency}</td>
                    <td className="numeric-cell">{formatNumber(holding.quantity)}</td>
                    <td className="numeric-cell">{formatMoney(holding.average_purchase_price, holding.currency)}</td>
                    <td className="numeric-cell">
                      {holding.last_price === null ? "-" : formatMoney(holding.last_price, holding.currency)}
                    </td>
                    <td className="numeric-cell">{formatMoney(holding.market_value, holding.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">조회된 Toss 보유자산이 없습니다.</p>
        )}
        <input readOnly hidden value={selectedAccountSeq} />
      </section>
    </section>
  )
}
```

- [ ] **Step 3: Update Dashboard account selection**

In `frontend/src/components/Dashboard.tsx`, load Toss accounts and request summary with `account_seq`:

```tsx
import type { AssetAllocation, PortfolioSummary, TossAccount } from "../types"
```

Add state:

```tsx
  const [accounts, setAccounts] = useState<TossAccount[]>([])
  const [selectedAccountSeq, setSelectedAccountSeq] = useState("")
```

Replace the existing summary `useEffect` with two effects:

```tsx
  useEffect(() => {
    apiGet<TossAccount[]>("/api/toss/accounts")
      .then((data) => {
        setAccounts(data)
        setSelectedAccountSeq(data[0]?.account_seq ?? "")
      })
      .catch((err) => setError(getErrorMessage(err)))
  }, [])

  useEffect(() => {
    if (!selectedAccountSeq) {
      return
    }

    apiGet<PortfolioSummary>(`/api/summary?account_seq=${encodeURIComponent(selectedAccountSeq)}`)
      .then((summaryData) => {
        setSummary(summaryData)
        setError("")
      })
      .catch((err) => setError(getErrorMessage(err)))
  }, [selectedAccountSeq])
```

In `getAllocationSegments()`, change:

```typescript
key: `stock_etf:${allocation.asset_id}`,
```

to:

```typescript
key: `stock_etf:${allocation.asset_key}`,
```

In the dashboard header controls, render a select for Toss accounts:

```tsx
          <select
            value={selectedAccountSeq}
            onChange={(event) => setSelectedAccountSeq(event.target.value)}
          >
            <option value="">Toss 계좌 선택</option>
            {accounts.map((account) => (
              <option key={account.account_seq} value={account.account_seq}>
                {account.display_name}
              </option>
            ))}
          </select>
```

- [ ] **Step 4: Remove local transaction and growth navigation**

In `frontend/src/components/AppShell.tsx`, remove `History` and `TrendingUp` imports and remove these nav items:

```typescript
{ id: "growth", label: "성장기록", icon: TrendingUp },
{ id: "transactions", label: "거래내역", icon: History },
```

In `frontend/src/App.tsx`, remove:

```typescript
import { GrowthHistoryPage } from "./components/GrowthHistoryPage"
import { TransactionsPage } from "./components/TransactionsPage"
```

and remove:

```tsx
{active === "growth" && <GrowthHistoryPage />}
{active === "transactions" && <TransactionsPage />}
```

Delete:

```bash
rm frontend/src/components/TransactionsPage.tsx frontend/src/components/GrowthHistoryPage.tsx frontend/src/transactionPayload.ts
```

- [ ] **Step 5: Run frontend tests**

Before running tests, replace `frontend/tests/settings-market-sync.test.mjs` with:

```javascript
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

const source = readFileSync(new URL("../src/components/SettingsPage.tsx", import.meta.url), "utf8")
const typesSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8")

assert.ok(source.includes("Toss API 인증 정보"), "Settings page should keep Toss credential guidance")
assert.ok(source.includes('"/api/backups"'), "Settings page should still show backup records")

assert.ok(!source.includes('"/api/market-data/status"'), "Toss-only settings should not poll local market-data status")
assert.ok(!source.includes("MARKET_STATUS_POLL_INTERVAL_MS"), "Toss-only settings should remove market status polling")
assert.ok(!source.includes("자동 시세 갱신"), "Toss-only settings should remove local market sync wording")
assert.ok(!source.includes("Alpha Vantage"), "Settings page should not show removed Alpha Vantage settings")
assert.ok(!typesSource.includes("MarketDataStatus"), "Toss-only frontend should remove local market data status types")
```

Update `frontend/src/components/SettingsPage.tsx` so it no longer imports or reads `MarketDataStatus`, no longer calls `/api/market-data/status`, and keeps only Toss credential guidance plus `/api/backups` history.

Run:

```bash
node frontend/tests/holdings-page-form.test.mjs
node frontend/tests/transaction-payload-builder.test.mjs
node frontend/tests/growth-history-page.test.mjs
node frontend/tests/settings-market-sync.test.mjs
npm --prefix frontend run build
```

Expected: PASS.

## Task 6: Remove Obsolete Backend Tests And Runtime Imports

**Files:**
- Delete: `backend/tests/test_transactions.py`
- Delete: `backend/tests/test_market_data.py`
- Delete: `backend/tests/test_market_data_service.py`
- Delete: `backend/tests/test_market_sync_scheduler.py`
- Delete: `backend/tests/test_growth.py`
- Delete: `backend/tests/test_growth_api.py`
- Modify: `backend/tests/test_summary.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/src/portfolio_app/main.py`
- Delete: `backend/src/portfolio_app/services/growth.py`
- Delete: `backend/src/portfolio_app/api/growth.py`

- [ ] **Step 1: Remove tests that assert deleted product behavior**

Delete these test files:

```bash
rm backend/tests/test_transactions.py backend/tests/test_market_data.py backend/tests/test_market_data_service.py backend/tests/test_market_sync_scheduler.py backend/tests/test_growth.py backend/tests/test_growth_api.py
```

- [ ] **Step 2: Rewrite summary tests around Toss-only service**

In `backend/tests/test_summary.py`, keep only tests that exercise:

```python
GET /api/summary?account_seq=...
SummaryResponse OpenAPI schema exposure
USD holding requires Toss USD/KRW rate
provider HTTP errors map to 502 without exposing secrets
```

Delete tests that insert into `accounts`, `assets`, `holdings`, or `transactions`.

- [ ] **Step 3: Remove growth runtime from router registration**

In `backend/src/portfolio_app/main.py`, ensure `growth` is not imported or included. Then delete the growth runtime files because transaction-derived growth history is not valid without local transactions:

```bash
rm backend/src/portfolio_app/api/growth.py backend/src/portfolio_app/services/growth.py
```

- [ ] **Step 4: Run backend architecture and focused tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_only_architecture.py backend/tests/test_toss_portfolio.py backend/tests/test_api.py backend/tests/test_summary.py backend/tests/test_db.py -q
.venv/bin/python -m ruff check backend/src backend/tests
```

Expected: PASS.

## Task 7: Documentation And Final Verification

**Files:**
- Modify: `docs/toss-open-api-integration.md`
- Modify: `docs/db_erd.md`

- [ ] **Step 1: Update Toss integration document**

In `docs/toss-open-api-integration.md`, replace the local-ledger source-of-truth recommendations with:

```markdown
Current product direction for the brokerage slice is Toss-only.

`accounts`, `assets`, `holdings`, and `transactions` are no longer the source of
truth for brokerage data. Toss `GET /api/v1/accounts` and `GET /api/v1/holdings`
own the displayed account and stock/ETF holding state. SQLite remains for app
settings, goals, backups, migration bookkeeping, and optional provider cache
data only.

Removed behavior:

- local account creation,
- local asset creation,
- local initial balance setup,
- local transaction entry,
- transaction-derived growth history.

Known limitation: Toss holdings currently cover KR/US stock holdings, not the
app's former cash, savings, debt, manual adjustment, or full personal-finance
ledger features.
```

- [ ] **Step 2: Update ERD**

In `docs/db_erd.md`, replace the old ERD with a Toss-only ERD containing:

```markdown
erDiagram
    schema_migrations {
      integer version PK
      text applied_at
    }
    settings {
      text key PK
      text value
      text updated_at
    }
    fx_rates {
      integer id PK
      text base_currency
      text quote_currency
      real rate
      text source
      text fetched_at
      real change_percent
    }
    goals {
      integer id PK
      text name
      text type
      real target_amount_krw
      text created_at
      text updated_at
    }
    backups {
      integer id PK
      text path
      text reason
      text created_at
    }
```

Add a note:

```markdown
Toss account and holding data is not represented as local relational source
tables. It is fetched from Toss APIs at read time.
```

- [ ] **Step 3: Run full verification**

Run:

```bash
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m ruff check backend/src backend/tests
npm --prefix frontend test
npm --prefix frontend run build
git status --short --branch
git diff --stat
git diff --cached --stat
```

Expected: PASS for test/build commands. Git diff should include only Toss-only portfolio files and documentation.

- [ ] **Step 4: Commit only after user approval**

If the user approves this scope, run:

```bash
git add backend/src/portfolio_app backend/tests frontend/src frontend/tests docs/toss-open-api-integration.md docs/db_erd.md
git commit -m "feat: switch brokerage portfolio to toss-only"
```

Expected: one focused breaking-change feature commit with no attribution trailers.

## Self-Review

- Spec coverage: The plan removes local `accounts`, `assets`, `holdings`, and `transactions` as the source of truth and replaces the brokerage flow with Toss accounts, Toss holdings, and Toss-derived summary.
- Placeholder scan: No task uses TBD, TODO, or unspecified implementation steps.
- Type consistency: Backend `asset_key` replaces local numeric `asset_id`; frontend `AssetAllocation` matches that response shape.
- Product honesty: The plan explicitly removes or hides local transaction entry and transaction-derived growth because Toss holdings alone cannot replace those semantics.
- Risk: This is a destructive migration. Before implementation, take a SQLite backup or rely on the existing startup backup path. Do not combine this with order-history or order-placement work.
