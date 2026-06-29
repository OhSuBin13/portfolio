# Manual Stock Metadata Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual stock/ETF metadata input flow that can also prefill metadata from Toss stock-info lookup without changing the existing local ledger semantics.

**Architecture:** Keep `/api/assets` as the asset persistence boundary, add stock-only metadata columns to `assets`, and expose a read-only local lookup endpoint for Toss stock metadata. The holdings UI remains the first entry point: the user can type metadata manually, or enter a symbol and prefill name, market, currency, listed status, and instrument type.

**Tech Stack:** FastAPI, Pydantic v2, SQLite migrations, httpx, React/Vite, source-inspection frontend tests, pytest, ruff.

---

## Scope Decisions

- Preserve the existing contract that built-in `cash`, `savings`, and `debt` assets are seeded and listed automatically.
- Keep manual asset creation on the holdings page limited to `stock_etf`.
- Do not import holdings, orders, or brokerage account data in this feature.
- Do not make automatic reconciliation decisions. This feature only stores asset metadata and offers lookup-assisted form filling.
- Verify the latest Toss stock-info response shape against official Toss Open API docs before implementing the provider parser. The local design document currently identifies `GET /api/v1/stocks` as the target endpoint.

## File Structure

- Modify `backend/src/portfolio_app/schema.sql`: add persisted stock metadata columns to `assets`.
- Modify `backend/src/portfolio_app/migrations.py`: bump schema to v9 and migrate existing DBs.
- Modify `backend/src/portfolio_app/api/assets.py`: add request/response models, metadata validation, and a read-only stock metadata lookup route.
- Modify `backend/src/portfolio_app/repositories.py`: thread metadata through `create_asset()` and `create_asset_record()`.
- Create `backend/src/portfolio_app/services/stock_metadata.py`: Toss stock-info provider and normalization into the local response model.
- Modify `backend/tests/test_db.py`: cover fresh schema and v8-to-v9 migration.
- Modify `backend/tests/test_api.py`: cover asset payload metadata validation and `/api/assets` persistence.
- Create `backend/tests/test_stock_metadata.py`: cover Toss stock metadata parsing and provider failures.
- Modify `frontend/src/types.ts`: add asset metadata and lookup response types.
- Modify `frontend/src/components/HoldingsPage.tsx`: add lookup button and manual metadata controls.
- Modify `frontend/tests/holdings-page-form.test.mjs`: lock down KR/US market controls, metadata controls, and lookup call.
- Modify `docs/toss-open-api-integration.md`: mark Phase 2 implementation status after the feature is complete.

## Task 1: Persist Stock Metadata On Assets

**Files:**
- Modify: `backend/src/portfolio_app/schema.sql`
- Modify: `backend/src/portfolio_app/migrations.py`
- Modify: `backend/tests/test_db.py`

- [ ] **Step 1: Write failing schema tests**

Add these tests to `backend/tests/test_db.py`:

```python
def test_assets_table_has_stock_metadata_columns(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    migrate(db)

    columns = {row["name"]: row for row in db.execute("pragma table_info(assets)").fetchall()}

    assert "is_listed" in columns
    assert "instrument_type" in columns
    assert "metadata_source" in columns
    assert columns["metadata_source"]["dflt_value"] == "'manual'"


def test_migrate_from_v8_adds_stock_metadata_columns(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)
    db.executescript(
        """
        create table schema_migrations (
          version integer primary key,
          applied_at text not null default current_timestamp
        );
        insert into schema_migrations(version) values (8);

        create table assets (
          id integer primary key,
          symbol text,
          name text not null,
          type text not null check (type in ('cash','savings','stock_etf','debt')),
          currency text not null check (currency in ('USD','KRW')) default 'KRW',
          market text,
          manual_price_krw real,
          created_at text not null default current_timestamp,
          updated_at text not null default current_timestamp
        );
        create unique index idx_assets_symbol_market
        on assets(symbol, market)
        where symbol is not null;
        insert into assets(symbol, name, type, currency, market)
        values ('VOO', 'Vanguard S&P 500 ETF', 'stock_etf', 'USD', 'US');
        """
    )

    migrate(db)

    version = db.execute("select max(version) from schema_migrations").fetchone()[0]
    row = db.execute(
        """
        select symbol, name, type, currency, market, is_listed, instrument_type, metadata_source
        from assets
        where symbol = 'VOO'
        """
    ).fetchone()
    assert version == 9
    assert dict(row) == {
        "symbol": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "type": "stock_etf",
        "currency": "USD",
        "market": "US",
        "is_listed": 1,
        "instrument_type": None,
        "metadata_source": "manual",
    }
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py::test_assets_table_has_stock_metadata_columns backend/tests/test_db.py::test_migrate_from_v8_adds_stock_metadata_columns -q
```

Expected: both tests fail because `is_listed`, `instrument_type`, `metadata_source`, and schema version 9 do not exist yet.

- [ ] **Step 3: Add schema columns**

In `backend/src/portfolio_app/schema.sql`, change the `assets` table to include these columns after `manual_price_krw`:

```sql
  is_listed integer check (is_listed in (0,1)),
  instrument_type text,
  metadata_source text not null default 'manual' check (metadata_source in ('manual','toss')),
```

- [ ] **Step 4: Add migration v9**

In `backend/src/portfolio_app/migrations.py`, change:

```python
SCHEMA_VERSION = 8
```

to:

```python
SCHEMA_VERSION = 9
```

Update `_create_assets_table_sql()` to include the same three columns:

```python
          is_listed integer check (is_listed in (0,1)),
          instrument_type text,
          metadata_source text not null default 'manual' check (metadata_source in ('manual','toss')),
```

Add this migration after `_migrate_from_7_to_8()`:

```python
def _migrate_from_8_to_9(db: sqlite3.Connection) -> None:
    columns = _pragma_column_names(db.execute("pragma table_info(assets)").fetchall())
    with db:
        if "is_listed" not in columns:
            db.execute("alter table assets add column is_listed integer check (is_listed in (0,1))")
        if "instrument_type" not in columns:
            db.execute("alter table assets add column instrument_type text")
        if "metadata_source" not in columns:
            db.execute(
                """
                alter table assets
                add column metadata_source text not null default 'manual'
                check (metadata_source in ('manual','toss'))
                """
            )
        db.execute(
            """
            update assets
            set is_listed = 1
            where type = 'stock_etf'
              and is_listed is null
            """
        )
        db.execute(
            """
            update assets
            set is_listed = null,
                instrument_type = null
            where type in ('cash', 'savings', 'debt')
            """
        )
        db.execute("insert or ignore into schema_migrations(version) values (9)")
```

Then call it in `migrate()`:

```python
    if version == 8:
        _migrate_from_8_to_9(db)
        version = 9
```

- [ ] **Step 5: Run schema tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py::test_assets_table_has_stock_metadata_columns backend/tests/test_db.py::test_migrate_from_v8_adds_stock_metadata_columns -q
```

Expected: PASS.

## Task 2: Validate And Persist Asset Metadata Through `/api/assets`

**Files:**
- Modify: `backend/src/portfolio_app/api/assets.py`
- Modify: `backend/src/portfolio_app/repositories.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_repositories.py`

- [ ] **Step 1: Write failing API validation tests**

Add these tests to `backend/tests/test_api.py`:

```python
def test_asset_payload_validation_normalizes_stock_metadata():
    from portfolio_app.api import assets

    payload = assets.AssetCreate(
        symbol=" 005930 ",
        name=" 삼성전자 ",
        type="stock_etf",
        currency=" krw ",
        market=" kr ",
        is_listed=True,
        instrument_type=" stock ",
        metadata_source="toss",
    )

    validated = assets.validate_asset_payload(payload)

    assert validated.symbol == "005930"
    assert validated.name == "삼성전자"
    assert validated.type == "stock_etf"
    assert validated.currency == "KRW"
    assert validated.market == "KR"
    assert validated.is_listed is True
    assert validated.instrument_type == "STOCK"
    assert validated.metadata_source == "toss"


def test_asset_payload_validation_clears_metadata_for_builtin_asset():
    from portfolio_app.api import assets

    payload = assets.AssetCreate(
        symbol="KRW",
        name="원화 현금",
        type="cash",
        currency="KRW",
        market="KR",
        is_listed=True,
        instrument_type="stock",
        metadata_source="toss",
    )

    validated = assets.validate_asset_payload(payload)

    assert validated.symbol is None
    assert validated.market is None
    assert validated.is_listed is None
    assert validated.instrument_type is None
    assert validated.metadata_source == "manual"


def test_can_create_stock_asset_with_manual_metadata(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/assets",
        json={
            "symbol": "005930",
            "name": "삼성전자",
            "type": "stock_etf",
            "currency": "KRW",
            "market": "KR",
            "is_listed": True,
            "instrument_type": "stock",
            "metadata_source": "manual",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["symbol"] == "005930"
    assert created["name"] == "삼성전자"
    assert created["type"] == "stock_etf"
    assert created["currency"] == "KRW"
    assert created["market"] == "KR"
    assert created["is_listed"] == 1
    assert created["instrument_type"] == "STOCK"
    assert created["metadata_source"] == "manual"
```

- [ ] **Step 2: Write failing repository test**

Add this to `backend/tests/test_repositories.py`:

```python
def test_create_asset_record_persists_stock_metadata(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)

    row = repositories.create_asset_record(
        db,
        symbol="005930",
        name="삼성전자",
        type="stock_etf",
        currency="KRW",
        market="KR",
        is_listed=True,
        instrument_type="STOCK",
        metadata_source="manual",
    )

    assert row["symbol"] == "005930"
    assert row["is_listed"] == 1
    assert row["instrument_type"] == "STOCK"
    assert row["metadata_source"] == "manual"
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_asset_payload_validation_normalizes_stock_metadata backend/tests/test_api.py::test_asset_payload_validation_clears_metadata_for_builtin_asset backend/tests/test_api.py::test_can_create_stock_asset_with_manual_metadata backend/tests/test_repositories.py::test_create_asset_record_persists_stock_metadata -q
```

Expected: FAIL because `AssetCreate`, `ValidatedAssetPayload`, and repository functions do not accept metadata fields yet.

- [ ] **Step 4: Update API model and validation**

In `backend/src/portfolio_app/api/assets.py`, extend `AssetCreate`:

```python
    is_listed: bool | None = None
    instrument_type: str | None = None
    metadata_source: str = "manual"
```

Extend `ValidatedAssetPayload`:

```python
    is_listed: bool | None
    instrument_type: str | None
    metadata_source: str
```

Add near `ASSET_TYPES`:

```python
METADATA_SOURCES = {"manual", "toss"}
```

In `validate_asset_payload()`, after `market` is calculated:

```python
    metadata_source = require_allowed(
        payload.metadata_source,
        METADATA_SOURCES,
        "지원하지 않는 메타데이터 출처입니다.",
    )
    instrument_type = payload.instrument_type.strip().upper() if payload.instrument_type else None
    is_listed = payload.is_listed
```

Inside the existing type branch:

```python
    if asset_type == "stock_etf":
        market = require_non_empty(payload.market or "", "시장을 입력해 주세요.").upper()
        if is_listed is None:
            is_listed = True
    elif asset_type in {"cash", "savings", "debt"}:
        symbol = None
        market = None
        is_listed = None
        instrument_type = None
        metadata_source = "manual"
```

Return the new fields:

```python
        is_listed=is_listed,
        instrument_type=instrument_type,
        metadata_source=metadata_source,
```

- [ ] **Step 5: Thread metadata through repositories**

In `backend/src/portfolio_app/repositories.py`, update `create_asset()` signature:

```python
    is_listed: bool | None = None,
    instrument_type: str | None = None,
    metadata_source: str = "manual",
```

Change its insert:

```python
        """
        insert into assets(
          symbol, name, type, currency, market, is_listed, instrument_type, metadata_source
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            symbol,
            name,
            type,
            currency,
            market,
            None if is_listed is None else int(is_listed),
            instrument_type,
            metadata_source,
        ),
```

Update `create_asset_record()` with the same parameters and pass them through to `create_asset()`.

In `backend/src/portfolio_app/api/assets.py`, pass the validated fields into `repositories.create_asset_record()`:

```python
            is_listed=asset.is_listed,
            instrument_type=asset.instrument_type,
            metadata_source=asset.metadata_source,
```

- [ ] **Step 6: Run API and repository tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_asset_payload_validation_normalizes_stock_metadata backend/tests/test_api.py::test_asset_payload_validation_clears_metadata_for_builtin_asset backend/tests/test_api.py::test_can_create_stock_asset_with_manual_metadata backend/tests/test_repositories.py::test_create_asset_record_persists_stock_metadata -q
```

Expected: PASS.

## Task 3: Add Toss Stock Metadata Lookup Service And Endpoint

**Files:**
- Create: `backend/src/portfolio_app/services/stock_metadata.py`
- Modify: `backend/src/portfolio_app/api/assets.py`
- Create: `backend/tests/test_stock_metadata.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing provider tests**

Create `backend/tests/test_stock_metadata.py`:

```python
import pytest

from portfolio_app.services.market_data import TossAuthClient
from portfolio_app.services.stock_metadata import TossStockMetadataProvider


@pytest.mark.asyncio
async def test_toss_stock_metadata_provider_parses_stock_info(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/stocks?symbols=005930",
        json={
            "result": [
                {
                    "symbol": "005930",
                    "name": "삼성전자",
                    "market": "KR",
                    "currency": "KRW",
                    "isListed": True,
                    "instrumentType": "stock",
                }
            ]
        },
    )
    auth_client = TossAuthClient("toss-client", "toss-secret")
    provider = TossStockMetadataProvider("toss-client", "toss-secret", auth_client=auth_client)

    metadata = await provider.fetch_stock_metadata(" 005930 ")

    assert metadata.symbol == "005930"
    assert metadata.name == "삼성전자"
    assert metadata.market == "KR"
    assert metadata.currency == "KRW"
    assert metadata.is_listed is True
    assert metadata.instrument_type == "STOCK"
    assert metadata.metadata_source == "toss"


@pytest.mark.asyncio
async def test_toss_stock_metadata_provider_rejects_missing_symbol():
    provider = TossStockMetadataProvider("toss-client", "toss-secret")

    with pytest.raises(ValueError, match="종목 심볼을 입력해 주세요."):
        await provider.fetch_stock_metadata(" ")
```

- [ ] **Step 2: Write failing endpoint test**

Add this to `backend/tests/test_api.py`:

```python
def test_stock_metadata_lookup_endpoint_is_documented(tmp_path):
    client = create_test_client(tmp_path)

    schema = client.get("/openapi.json").json()

    assert "/api/assets/stock-metadata" in schema["paths"]
    response_schema = schema["paths"]["/api/assets/stock-metadata"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert response_schema == {"$ref": "#/components/schemas/StockMetadataResponse"}
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_stock_metadata.py backend/tests/test_api.py::test_stock_metadata_lookup_endpoint_is_documented -q
```

Expected: FAIL because the service module and route do not exist.

- [ ] **Step 4: Create stock metadata service**

Create `backend/src/portfolio_app/services/stock_metadata.py`:

```python
from dataclasses import dataclass
from typing import Any

import httpx

from portfolio_app.services.market_data import TossAuthClient

TOSS_STOCKS_URL = "https://openapi.tossinvest.com/api/v1/stocks"


@dataclass(frozen=True)
class StockMetadata:
    symbol: str
    name: str
    market: str
    currency: str
    is_listed: bool
    instrument_type: str | None
    metadata_source: str = "toss"


def _require_text(value: object, message: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(message)
    return text


def _normalize_stock_item(item: dict[str, Any], requested_symbol: str) -> StockMetadata:
    symbol = _require_text(item.get("symbol"), "Toss 응답에서 종목 심볼을 찾을 수 없습니다.").upper()
    if symbol != requested_symbol:
        raise ValueError("Toss 응답 종목 심볼이 요청과 일치하지 않습니다.")

    name = _require_text(item.get("name"), "Toss 응답에서 종목 이름을 찾을 수 없습니다.")
    market = _require_text(item.get("market"), "Toss 응답에서 시장 정보를 찾을 수 없습니다.").upper()
    currency = _require_text(item.get("currency"), "Toss 응답에서 통화 정보를 찾을 수 없습니다.").upper()
    if currency not in {"KRW", "USD"}:
        raise ValueError("Toss 응답 통화는 KRW 또는 USD여야 합니다.")
    if market not in {"KR", "US"}:
        raise ValueError("Toss 응답 시장은 KR 또는 US여야 합니다.")

    is_listed = item.get("isListed", True)
    instrument_type = item.get("instrumentType")

    return StockMetadata(
        symbol=symbol,
        name=name,
        market=market,
        currency=currency,
        is_listed=bool(is_listed),
        instrument_type=str(instrument_type).strip().upper() if instrument_type else None,
    )


class TossStockMetadataProvider:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        auth_client: TossAuthClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._auth_client = auth_client or TossAuthClient(client_id, client_secret, timeout=timeout)
        self._timeout = timeout

    async def fetch_stock_metadata(self, symbol: str) -> StockMetadata:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("종목 심볼을 입력해 주세요.")

        token = await self._auth_client.access_token()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                TOSS_STOCKS_URL,
                params={"symbols": normalized_symbol},
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("result")
        if not isinstance(result, list) or not result:
            raise ValueError("Toss 응답에서 요청 종목의 정보를 찾을 수 없습니다.")
        first = result[0]
        if not isinstance(first, dict):
            raise ValueError("Toss 응답 종목 정보가 올바르지 않습니다.")
        return _normalize_stock_item(first, normalized_symbol)
```

- [ ] **Step 5: Add endpoint model and route**

In `backend/src/portfolio_app/api/assets.py`, add imports:

```python
from fastapi import APIRouter, Depends, HTTPException, Request, status
from portfolio_app.services.stock_metadata import TossStockMetadataProvider
```

Add response model:

```python
class StockMetadataResponse(BaseModel):
    symbol: str
    name: str
    market: str
    currency: str
    is_listed: bool
    instrument_type: str | None
    metadata_source: str
```

Add the route before `@router.post("")` so it is not interpreted as an asset id route in future:

```python
@router.get("/stock-metadata", response_model=StockMetadataResponse)
async def lookup_stock_metadata(symbol: str, request: Request) -> StockMetadataResponse:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="종목 심볼을 입력해 주세요.",
        )

    settings = request.app.state.settings
    provider = TossStockMetadataProvider(settings.toss_api_key, settings.toss_secret_key)
    try:
        metadata = await provider.fetch_stock_metadata(normalized_symbol)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return StockMetadataResponse(
        symbol=metadata.symbol,
        name=metadata.name,
        market=metadata.market,
        currency=metadata.currency,
        is_listed=metadata.is_listed,
        instrument_type=metadata.instrument_type,
        metadata_source=metadata.metadata_source,
    )
```

- [ ] **Step 6: Run provider and OpenAPI tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_stock_metadata.py backend/tests/test_api.py::test_stock_metadata_lookup_endpoint_is_documented -q
```

Expected: PASS.

## Task 4: Add Holdings UI Manual Metadata Controls And Lookup Prefill

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/HoldingsPage.tsx`
- Modify: `frontend/tests/holdings-page-form.test.mjs`

- [ ] **Step 1: Write failing frontend source tests**

In `frontend/tests/holdings-page-form.test.mjs`, change the market assertion to expect KR and US:

```js
assert.deepEqual(optionValues(marketBlocks[0]), ["US", "KR"], "market select should offer US and KR")
```

Add these assertions near the asset form tests:

```js
assert.ok(source.includes("종목 정보 불러오기"), "asset form should expose a stock metadata lookup action")
assert.ok(source.includes("/api/assets/stock-metadata"), "asset form should call the stock metadata lookup API")
assert.ok(source.includes("상장 상태"), "asset form should expose listed status")
assert.ok(source.includes("상품 유형"), "asset form should expose instrument type")
assert.ok(source.includes("metadataSource"), "asset form should track metadata source")
```

- [ ] **Step 2: Run frontend test and verify it fails**

Run:

```bash
npm --prefix frontend test
```

Expected: FAIL because the UI does not yet expose metadata lookup or controls and the market select only has `US`.

- [ ] **Step 3: Update frontend types**

In `frontend/src/types.ts`, extend `Asset`:

```ts
  is_listed: number | null
  instrument_type: string | null
  metadata_source: "manual" | "toss"
```

Add:

```ts
export type StockMetadata = {
  symbol: string
  name: string
  market: "US" | "KR"
  currency: "USD" | "KRW"
  is_listed: boolean
  instrument_type: string | null
  metadata_source: "toss"
}
```

- [ ] **Step 4: Update `HoldingsPage` form state**

In `frontend/src/components/HoldingsPage.tsx`, update imports:

```ts
import type { Account, Asset, StockMetadata, Transaction } from "../types"
```

Extend `AssetForm`:

```ts
  isListed: boolean
  instrumentType: string
  metadataSource: "manual" | "toss"
```

Update the initial `assetForm`:

```ts
    isListed: true,
    instrumentType: "STOCK",
    metadataSource: "manual",
```

Add lookup state near asset messages:

```ts
  const [assetLookupLoading, setAssetLookupLoading] = useState(false)
```

Add this handler before `handleAssetSubmit`:

```ts
  const handleStockMetadataLookup = async () => {
    setAssetMessage("")
    setAssetError("")

    const symbol = assetForm.symbol.trim().toUpperCase()
    if (!symbol) {
      setAssetError("종목 심볼을 입력하세요.")
      return
    }

    setAssetLookupLoading(true)
    try {
      const metadata = await apiGet<StockMetadata>(
        `/api/assets/stock-metadata?symbol=${encodeURIComponent(symbol)}`,
      )
      setAssetForm((prev) => ({
        ...prev,
        symbol: metadata.symbol,
        name: metadata.name,
        currency: metadata.currency,
        market: metadata.market,
        isListed: metadata.is_listed,
        instrumentType: metadata.instrument_type ?? prev.instrumentType,
        metadataSource: metadata.metadata_source,
      }))
      setAssetMessage("종목 정보를 불러왔습니다.")
    } catch (err) {
      setAssetError(getErrorMessage(err))
    } finally {
      setAssetLookupLoading(false)
    }
  }
```

Update `handleAssetSubmit()` payload:

```ts
        is_listed: assetForm.isListed,
        instrument_type: assetForm.instrumentType.trim() || null,
        metadata_source: assetForm.metadataSource,
```

Update the reset:

```ts
      setAssetForm((prev) => ({
        ...prev,
        symbol: "",
        name: "",
        isListed: true,
        instrumentType: "STOCK",
        metadataSource: "manual",
      }))
```

- [ ] **Step 5: Update asset form JSX**

In the symbol label, add a lookup button after the input:

```tsx
              <button
                className="secondary-button compact-button"
                type="button"
                onClick={handleStockMetadataLookup}
                disabled={assetLookupLoading}
              >
                종목 정보 불러오기
              </button>
```

Change market options:

```tsx
                <option value="US">US</option>
                <option value="KR">KR</option>
```

Add metadata controls before the submit button:

```tsx
          <div className="field-row">
            <label>
              상품 유형
              <select
                value={assetForm.instrumentType}
                onChange={(event) =>
                  setAssetForm((prev) => ({
                    ...prev,
                    instrumentType: event.target.value,
                    metadataSource: "manual",
                  }))
                }
              >
                <option value="STOCK">STOCK</option>
                <option value="ETF">ETF</option>
                <option value="ETN">ETN</option>
                <option value="REIT">REIT</option>
                <option value="OTHER">OTHER</option>
              </select>
            </label>
            <label>
              상장 상태
              <select
                value={assetForm.isListed ? "listed" : "unlisted"}
                onChange={(event) =>
                  setAssetForm((prev) => ({
                    ...prev,
                    isListed: event.target.value === "listed",
                    metadataSource: "manual",
                  }))
                }
              >
                <option value="listed">상장</option>
                <option value="unlisted">상장폐지/비상장</option>
              </select>
            </label>
          </div>
```

- [ ] **Step 6: Run frontend test**

Run:

```bash
npm --prefix frontend test
```

Expected: PASS.

## Task 5: Document Completion And Run Full Verification

**Files:**
- Modify: `docs/toss-open-api-integration.md`

- [ ] **Step 1: Update Toss integration document**

In `docs/toss-open-api-integration.md`, update the Priority 2 row from:

```markdown
| 2 | Manual stock asset metadata input | `GET /api/v1/stocks` | Good augmentation. Can auto-fill name, market, currency, listed status, and instrument metadata. |
```

to:

```markdown
| 2 | Manual stock asset metadata input | `GET /api/v1/stocks` | Implemented for holdings-page stock/ETF asset creation. The user can enter metadata manually or prefill name, market, currency, listed status, and instrument type from Toss stock info. |
```

Under `### Phase 2: Stock Metadata Validation`, change:

```markdown
Use Toss stock info during stock/ETF asset creation.
```

to:

```markdown
Implemented behavior uses Toss stock info during stock/ETF asset creation while keeping manual metadata entry available.
```

- [ ] **Step 2: Run focused backend verification**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py::test_assets_table_has_stock_metadata_columns backend/tests/test_db.py::test_migrate_from_v8_adds_stock_metadata_columns backend/tests/test_api.py::test_asset_payload_validation_normalizes_stock_metadata backend/tests/test_api.py::test_asset_payload_validation_clears_metadata_for_builtin_asset backend/tests/test_api.py::test_can_create_stock_asset_with_manual_metadata backend/tests/test_api.py::test_stock_metadata_lookup_endpoint_is_documented backend/tests/test_repositories.py::test_create_asset_record_persists_stock_metadata backend/tests/test_stock_metadata.py -q
```

Expected: PASS.

- [ ] **Step 3: Run broader backend checks**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py backend/tests/test_db.py backend/tests/test_market_data.py backend/tests/test_market_data_service.py backend/tests/test_repositories.py -q
.venv/bin/python -m ruff check backend/src/portfolio_app/api/assets.py backend/src/portfolio_app/repositories.py backend/src/portfolio_app/migrations.py backend/src/portfolio_app/services/stock_metadata.py backend/tests/test_api.py backend/tests/test_db.py backend/tests/test_repositories.py backend/tests/test_stock_metadata.py
```

Expected: PASS.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: PASS.

- [ ] **Step 5: Inspect diff before commit**

Run:

```bash
git status --short --branch
git diff --stat
git diff --cached --stat
```

Expected: diff includes only the feature files listed in this plan plus any pre-existing user changes that were already present before execution. Do not stage unrelated deleted docs unless the user explicitly includes them.

- [ ] **Step 6: Commit only after user approval**

If the user approves committing this feature scope, run:

```bash
git add backend/src/portfolio_app/schema.sql backend/src/portfolio_app/migrations.py backend/src/portfolio_app/api/assets.py backend/src/portfolio_app/repositories.py backend/src/portfolio_app/services/stock_metadata.py backend/tests/test_db.py backend/tests/test_api.py backend/tests/test_repositories.py backend/tests/test_stock_metadata.py frontend/src/types.ts frontend/src/components/HoldingsPage.tsx frontend/tests/holdings-page-form.test.mjs docs/toss-open-api-integration.md
git commit -m "feat: add manual stock metadata input"
```

Expected: one focused feature commit with no attribution trailers.

## Self-Review

- Spec coverage: The plan covers manual metadata input, Toss stock-info prefill, backend persistence, frontend form controls, tests, and docs.
- Placeholder scan: No task uses TBD or an unspecified implementation step.
- Type consistency: Backend field names are `is_listed`, `instrument_type`, `metadata_source`; frontend form fields map them from `isListed`, `instrumentType`, `metadataSource`.
- Risk: Toss stock-info response fields must be checked against the official Toss Open API reference before implementation. If field names differ, adjust only `stock_metadata.py` parser tests and implementation while keeping the local API response unchanged.
