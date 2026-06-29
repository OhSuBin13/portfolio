# Toss Request Throttling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce Toss 429 failures on dashboard and holdings page loads by sharing the Toss auth client, caching account-list reads briefly, and retrying one 429 response using Toss rate-limit headers.

**Architecture:** Keep the fix backend-owned. A single app-scoped `TossAuthClient` prevents repeated OAuth token issuance, `TossAccountsCache` collapses repeated `/api/toss/accounts` reads, and a shared Toss request helper retries one 429 after `Retry-After` or `X-RateLimit-Reset`. Frontend duplicate requests may still happen in React development mode, but the backend becomes tolerant of them.

**Tech Stack:** FastAPI, httpx, pytest, pytest-httpx, Python 3.12, React/Vite frontend as caller only.

---

## File Structure

- Modify `backend/src/portfolio_app/services/market_data.py`
  - Add the shared Toss 429 retry helper.
  - Add concurrent-token single-flight locking and optional sleep injection to `TossAuthClient`.
  - Use the retry helper in `TossAuthClient`, `TossFxRateProvider`, and `TossMarketDataProvider`.
- Modify `backend/src/portfolio_app/services/toss_portfolio.py`
  - Add `TossAccountsCache`.
  - Use the retry helper in `TossBrokerageProvider.fetch_accounts()` and `fetch_holdings()`.
- Modify `backend/src/portfolio_app/services/stock_metadata.py`
  - Use the shared retry helper for the Toss stocks endpoint.
- Modify `backend/src/portfolio_app/main.py`
  - Create app-scoped `TossAuthClient` and `TossAccountsCache`.
- Modify `backend/src/portfolio_app/api/toss_portfolio.py`
  - Use the app-scoped auth client for brokerage provider creation.
  - Serve `/api/toss/accounts` through `TossAccountsCache.get_or_fetch()`.
- Modify `backend/src/portfolio_app/api/summary.py`
  - Use the same app-scoped auth client for holdings and FX providers.
- Modify `backend/tests/test_toss_portfolio.py`
  - Add regression coverage for concurrent token single-flight, account cache TTL/single-flight, and brokerage 429 retry.
- Modify `backend/tests/test_api.py`
  - Add HTTP-path coverage that `/api/toss/accounts` is cached and Toss auth is shared across `/api/toss/accounts` and `/api/summary`.
- Modify `backend/tests/test_stock_metadata.py`
  - Add stocks endpoint 429 retry coverage.
- Modify `docs/toss-open-api-integration.md`
  - Document backend rate-limit mitigation.

---

### Task 1: Shared 429 Retry Helper And Token Single-Flight

**Files:**
- Modify: `backend/src/portfolio_app/services/market_data.py`
- Test: `backend/tests/test_toss_portfolio.py`

- [ ] **Step 1: Write failing tests for shared token concurrency and token 429 retry**

Add `import asyncio` at the top of `backend/tests/test_toss_portfolio.py`.

Append these tests after `test_toss_auth_client_posts_client_credentials_form()`:

```python
@pytest.mark.asyncio
async def test_toss_auth_client_serializes_concurrent_token_fetches(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    auth_client = TossAuthClient("toss-client", "toss-secret")

    tokens = await asyncio.gather(auth_client.token(), auth_client.token())

    assert tokens == ["token-123", "token-123"]
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].method == "POST"


@pytest.mark.asyncio
async def test_toss_auth_client_retries_token_once_after_429_retry_after(httpx_mock):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        status_code=429,
        headers={"Retry-After": "0.25", "X-RateLimit-Remaining": "0"},
        json={"error": "rate-limit-exceeded"},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    auth_client = TossAuthClient("toss-client", "toss-secret", sleep=fake_sleep)

    token = await auth_client.token()

    assert token == "token-123"
    assert sleeps == [0.25]
    assert len(httpx_mock.get_requests()) == 2
```

- [ ] **Step 2: Run the focused failing tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py::test_toss_auth_client_serializes_concurrent_token_fetches backend/tests/test_toss_portfolio.py::test_toss_auth_client_retries_token_once_after_429_retry_after -q
```

Expected: FAIL. The first test fails because concurrent token calls can make more than one token request. The second fails because `TossAuthClient` does not accept `sleep` and does not retry 429.

- [ ] **Step 3: Implement retry helper and token single-flight**

In `backend/src/portfolio_app/services/market_data.py`, add these imports near the top:

```python
import asyncio
from collections.abc import Awaitable, Callable
```

After the `MarketDataProvider` protocol definitions and before `UnavailableMarketDataProvider`, add:

```python
TOSS_MAX_RETRIES = 1
TOSS_DEFAULT_RETRY_AFTER_SECONDS = 1.0

Sleep = Callable[[float], Awaitable[None]]


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
```

Replace `TossAuthClient.__init__` and `token()` with:

```python
class TossAuthClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = "https://openapi.tossinvest.com",
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._token_lock = asyncio.Lock()
        self._access_token: str | None = None

    async def token(self) -> str:
        if self._access_token:
            return self._access_token

        async with self._token_lock:
            if self._access_token:
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
            return self._access_token
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py::test_toss_auth_client_serializes_concurrent_token_fetches backend/tests/test_toss_portfolio.py::test_toss_auth_client_retries_token_once_after_429_retry_after -q
```

Expected: PASS.

- [ ] **Step 5: Commit this task**

Only commit after user approval if this plan is being executed in a checkpointed workflow.

```bash
git add backend/src/portfolio_app/services/market_data.py backend/tests/test_toss_portfolio.py
git commit -m "fix: reuse toss token request under concurrency"
```

---

### Task 2: App-Scoped Shared Toss Auth Client

**Files:**
- Modify: `backend/src/portfolio_app/main.py`
- Modify: `backend/src/portfolio_app/api/toss_portfolio.py`
- Modify: `backend/src/portfolio_app/api/summary.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing HTTP-path test for shared auth across endpoints**

Append this test after `test_summary_endpoint_uses_toss_account_seq()` in `backend/tests/test_api.py`:

```python
def test_toss_endpoints_share_app_auth_client(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        json={
            "result": [
                {
                    "accountNo": "123-45-67890",
                    "accountSeq": "acct-1",
                    "accountType": "BROKERAGE",
                }
            ]
        },
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
                        "marketValue": {"amount": "750000"},
                    }
                ]
            }
        },
    )

    accounts_response = client.get("/api/toss/accounts")
    summary_response = client.get("/api/summary?account_seq=acct-1")

    assert accounts_response.status_code == 200
    assert summary_response.status_code == 200
    token_requests = [
        request
        for request in httpx_mock.get_requests()
        if request.method == "POST" and request.url.path == "/oauth2/token"
    ]
    assert len(token_requests) == 1
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_toss_endpoints_share_app_auth_client -q
```

Expected: FAIL because the current API factories create a new `TossAuthClient` per endpoint path.

- [ ] **Step 3: Create app-scoped auth client**

In `backend/src/portfolio_app/main.py`, add:

```python
from portfolio_app.services.market_data import TossAuthClient
```

In `create_app()`, after `app.state.settings = app_settings`, add:

```python
    app.state.toss_auth_client = TossAuthClient(
        app_settings.toss_api_key,
        app_settings.toss_secret_key,
    )
```

- [ ] **Step 4: Use app-scoped auth in Toss account and holding endpoints**

In `backend/src/portfolio_app/api/toss_portfolio.py`, replace `_provider()` with:

```python
def _provider(request: Request) -> TossBrokerageProvider:
    settings = request.app.state.settings
    return TossBrokerageProvider(
        settings.toss_api_key,
        settings.toss_secret_key,
        auth_client=request.app.state.toss_auth_client,
    )
```

- [ ] **Step 5: Use app-scoped auth in summary**

In `backend/src/portfolio_app/api/summary.py`, replace provider creation with:

```python
    auth_client = request.app.state.toss_auth_client
    provider = TossBrokerageProvider(
        settings.toss_api_key,
        settings.toss_secret_key,
        auth_client=auth_client,
    )
```

Replace the `fx_provider` argument with:

```python
            fx_provider=default_fx_rate_provider(settings, auth_client=auth_client),
```

- [ ] **Step 6: Run the focused test**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py::test_toss_endpoints_share_app_auth_client -q
```

Expected: PASS.

- [ ] **Step 7: Commit this task**

Only commit after user approval if this plan is being executed in a checkpointed workflow.

```bash
git add backend/src/portfolio_app/main.py backend/src/portfolio_app/api/toss_portfolio.py backend/src/portfolio_app/api/summary.py backend/tests/test_api.py
git commit -m "fix: share toss auth client across api requests"
```

---

### Task 3: Toss Accounts TTL Cache With Single-Flight Refresh

**Files:**
- Modify: `backend/src/portfolio_app/services/toss_portfolio.py`
- Modify: `backend/src/portfolio_app/main.py`
- Modify: `backend/src/portfolio_app/api/toss_portfolio.py`
- Test: `backend/tests/test_toss_portfolio.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing unit tests for TTL and single-flight**

Append these tests after the `StubTossBrokerageProvider` class in `backend/tests/test_toss_portfolio.py`:

```python
def test_toss_accounts_cache_returns_entry_until_ttl_expires():
    now = 100.0

    def fake_now() -> float:
        return now

    from portfolio_app.services.toss_portfolio import TossAccount, TossAccountsCache

    cache = TossAccountsCache(ttl_seconds=10, now=fake_now)
    account = TossAccount(
        account_seq="acct-1",
        account_no="123-45-67890",
        account_type="BROKERAGE",
        display_name="토스증권 123-45-67890",
    )

    cache.set([account])
    assert cache.get() == [account]

    now = 111.0
    assert cache.get() is None


@pytest.mark.asyncio
async def test_toss_accounts_cache_collapses_concurrent_fetches():
    from portfolio_app.services.toss_portfolio import TossAccount, TossAccountsCache

    cache = TossAccountsCache(ttl_seconds=60)
    account = TossAccount(
        account_seq="acct-1",
        account_no="123-45-67890",
        account_type="BROKERAGE",
        display_name="토스증권 123-45-67890",
    )
    calls = 0

    async def fetch_accounts() -> list[TossAccount]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return [account]

    results = await asyncio.gather(
        cache.get_or_fetch(fetch_accounts),
        cache.get_or_fetch(fetch_accounts),
    )

    assert results == [[account], [account]]
    assert calls == 1
```

- [ ] **Step 2: Write failing HTTP-path test for `/api/toss/accounts` cache**

Append this test after `test_toss_accounts_endpoint_returns_provider_accounts()` in `backend/tests/test_api.py`:

```python
def test_toss_accounts_endpoint_uses_ttl_cache(tmp_path, httpx_mock):
    client = create_test_client(
        tmp_path,
        toss_api_key="toss-client",
        toss_secret_key="toss-secret",
    )
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        json={
            "result": [
                {
                    "accountNo": "123-45-67890",
                    "accountSeq": "acct-1",
                    "accountType": "BROKERAGE",
                }
            ]
        },
    )

    first = client.get("/api/toss/accounts")
    second = client.get("/api/toss/accounts")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    account_requests = [
        request
        for request in httpx_mock.get_requests()
        if request.method == "GET" and request.url.path == "/api/v1/accounts"
    ]
    assert len(account_requests) == 1
```

- [ ] **Step 3: Run the focused failing tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py::test_toss_accounts_cache_returns_entry_until_ttl_expires backend/tests/test_toss_portfolio.py::test_toss_accounts_cache_collapses_concurrent_fetches backend/tests/test_api.py::test_toss_accounts_endpoint_uses_ttl_cache -q
```

Expected: FAIL because `TossAccountsCache` does not exist and the endpoint always fetches from Toss.

- [ ] **Step 4: Implement `TossAccountsCache`**

In `backend/src/portfolio_app/services/toss_portfolio.py`, add imports:

```python
import asyncio
import time
from collections.abc import Awaitable, Callable
```

After `TossSummaryResult`, add:

```python
TOSS_ACCOUNTS_CACHE_TTL_SECONDS = 60.0


@dataclass
class _TossAccountsCacheEntry:
    fetched_at: float
    accounts: list[TossAccount]


class TossAccountsCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = TOSS_ACCOUNTS_CACHE_TTL_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._now = now
        self._entry: _TossAccountsCacheEntry | None = None
        self._refresh_lock = asyncio.Lock()

    def get(self) -> list[TossAccount] | None:
        entry = self._entry
        if entry is None:
            return None
        if self._now() - entry.fetched_at >= self.ttl_seconds:
            return None
        return list(entry.accounts)

    def set(self, accounts: list[TossAccount]) -> None:
        self._entry = _TossAccountsCacheEntry(
            fetched_at=self._now(),
            accounts=list(accounts),
        )

    async def get_or_fetch(
        self,
        fetch_accounts: Callable[[], Awaitable[list[TossAccount]]],
    ) -> list[TossAccount]:
        cached = self.get()
        if cached is not None:
            return cached

        async with self._refresh_lock:
            cached = self.get()
            if cached is not None:
                return cached

            accounts = await fetch_accounts()
            self.set(accounts)
            return list(accounts)
```

- [ ] **Step 5: Register cache in app state**

In `backend/src/portfolio_app/main.py`, add:

```python
from portfolio_app.services.toss_portfolio import TossAccountsCache
```

After `app.state.toss_auth_client = ...`, add:

```python
    app.state.toss_accounts_cache = TossAccountsCache()
```

- [ ] **Step 6: Use cache in `/api/toss/accounts`**

In `backend/src/portfolio_app/api/toss_portfolio.py`, import `TossAccountsCache`:

```python
    TossAccountsCache,
```

Add this helper after `_provider()`:

```python
def _accounts_cache(request: Request) -> TossAccountsCache:
    return request.app.state.toss_accounts_cache
```

Replace the fetch line inside `list_toss_accounts()` with:

```python
        provider = _provider(request)
        accounts = await _accounts_cache(request).get_or_fetch(provider.fetch_accounts)
```

- [ ] **Step 7: Run the focused tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py::test_toss_accounts_cache_returns_entry_until_ttl_expires backend/tests/test_toss_portfolio.py::test_toss_accounts_cache_collapses_concurrent_fetches backend/tests/test_api.py::test_toss_accounts_endpoint_uses_ttl_cache -q
```

Expected: PASS.

- [ ] **Step 8: Commit this task**

Only commit after user approval if this plan is being executed in a checkpointed workflow.

```bash
git add backend/src/portfolio_app/services/toss_portfolio.py backend/src/portfolio_app/main.py backend/src/portfolio_app/api/toss_portfolio.py backend/tests/test_toss_portfolio.py backend/tests/test_api.py
git commit -m "fix: cache toss accounts briefly"
```

---

### Task 4: Apply 429 Retry To Toss Resource Endpoints

**Files:**
- Modify: `backend/src/portfolio_app/services/market_data.py`
- Modify: `backend/src/portfolio_app/services/toss_portfolio.py`
- Modify: `backend/src/portfolio_app/services/stock_metadata.py`
- Test: `backend/tests/test_toss_portfolio.py`
- Test: `backend/tests/test_stock_metadata.py`

- [ ] **Step 1: Write failing brokerage retry tests**

Append these tests after `test_toss_brokerage_provider_fetches_accounts()` in `backend/tests/test_toss_portfolio.py`:

```python
@pytest.mark.asyncio
async def test_toss_brokerage_provider_retries_accounts_once_after_429(httpx_mock):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        status_code=429,
        headers={"Retry-After": "0.5", "X-RateLimit-Remaining": "0"},
        json={"error": {"code": "rate-limit-exceeded"}},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/accounts",
        json={
            "result": [
                {
                    "accountNo": "123-45-67890",
                    "accountSeq": "acct-1",
                    "accountType": "BROKERAGE",
                }
            ]
        },
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
        sleep=fake_sleep,
    )

    accounts = await provider.fetch_accounts()

    assert accounts[0].account_seq == "acct-1"
    assert sleeps == [0.5]
    account_requests = [
        request
        for request in httpx_mock.get_requests()
        if request.method == "GET" and request.url.path == "/api/v1/accounts"
    ]
    assert len(account_requests) == 2


@pytest.mark.asyncio
async def test_toss_brokerage_provider_retries_holdings_with_ratelimit_reset(httpx_mock):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        status_code=429,
        headers={"X-RateLimit-Reset": "0.75", "X-RateLimit-Remaining": "0"},
        json={"error": {"code": "rate-limit-exceeded"}},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/holdings",
        json={"result": {"items": []}},
    )
    provider = TossBrokerageProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
        sleep=fake_sleep,
    )

    holdings = await provider.fetch_holdings("acct-1")

    assert holdings == []
    assert sleeps == [0.75]
```

- [ ] **Step 2: Write failing stock metadata retry test**

Append this test to `backend/tests/test_stock_metadata.py`:

```python
@pytest.mark.asyncio
async def test_toss_stock_metadata_provider_retries_after_429(httpx_mock):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/stocks?symbols=005930",
        status_code=429,
        headers={"Retry-After": "0.5"},
        json={"error": {"code": "rate-limit-exceeded"}},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/stocks?symbols=005930",
        json={
            "result": [
                {
                    "symbol": "005930",
                    "name": "삼성전자",
                    "market": "KOSPI",
                    "securityType": "STOCK",
                    "status": "ACTIVE",
                    "currency": "KRW",
                }
            ]
        },
    )
    provider = TossStockMetadataProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
        sleep=fake_sleep,
    )

    metadata = await provider.fetch_stock_metadata("005930")

    assert metadata.symbol == "005930"
    assert sleeps == [0.5]
```

- [ ] **Step 3: Run the focused failing tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py::test_toss_brokerage_provider_retries_accounts_once_after_429 backend/tests/test_toss_portfolio.py::test_toss_brokerage_provider_retries_holdings_with_ratelimit_reset backend/tests/test_stock_metadata.py::test_toss_stock_metadata_provider_retries_after_429 -q
```

Expected: FAIL because providers do not accept `sleep` and resource endpoints do not retry 429.

- [ ] **Step 4: Apply retry helper to FX and market-data providers**

In `backend/src/portfolio_app/services/market_data.py`, update `TossFxRateProvider.__init__`:

```python
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
```

In `TossFxRateProvider.fetch_rate()`, replace `client.get(...)` with:

```python
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/exchange-rate",
                params={"baseCurrency": base, "quoteCurrency": quote},
                headers={"Authorization": f"Bearer {token}"},
                sleep=self._sleep,
            )
```

Update `TossMarketDataProvider.__init__`:

```python
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
```

In `TossMarketDataProvider.fetch_equity_quotes()`, replace the prices `client.get(...)` with:

```python
                response = await request_with_toss_retry(
                    client,
                    "GET",
                    f"{self.base_url}/api/v1/prices",
                    params={"symbols": ",".join(chunk)},
                    headers={"Authorization": f"Bearer {token}"},
                    sleep=self._sleep,
                )
```

- [ ] **Step 5: Apply retry helper to brokerage provider**

In `backend/src/portfolio_app/services/toss_portfolio.py`, extend the market-data import:

```python
    Sleep,
    request_with_toss_retry,
```

Update `TossBrokerageProvider.__init__`:

```python
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
```

In `fetch_accounts()`, replace `client.get(...)` with:

```python
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/accounts",
                headers={"Authorization": f"Bearer {token}"},
                sleep=self._sleep,
            )
```

In `fetch_holdings()`, replace `client.get(...)` with:

```python
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/holdings",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-tossinvest-account": account_seq,
                },
                sleep=self._sleep,
            )
```

- [ ] **Step 6: Apply retry helper to stock metadata provider**

In `backend/src/portfolio_app/services/stock_metadata.py`, change the import to:

```python
from portfolio_app.services.market_data import Sleep, TossAuthClient, request_with_toss_retry
```

Add `import asyncio` near the top.

Update `TossStockMetadataProvider.__init__`:

```python
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        auth_client: TossAuthClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._sleep = sleep
        self._auth_client = auth_client or TossAuthClient(client_id, client_secret, sleep=sleep)
```

Replace `client.get(...)` in `fetch_stock_metadata()` with:

```python
            response = await request_with_toss_retry(
                client,
                "GET",
                TOSS_STOCKS_URL,
                params={"symbols": normalized_symbol},
                headers={"Authorization": f"Bearer {token}"},
                sleep=self._sleep,
            )
```

- [ ] **Step 7: Run the focused retry tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py::test_toss_brokerage_provider_retries_accounts_once_after_429 backend/tests/test_toss_portfolio.py::test_toss_brokerage_provider_retries_holdings_with_ratelimit_reset backend/tests/test_stock_metadata.py::test_toss_stock_metadata_provider_retries_after_429 -q
```

Expected: PASS.

- [ ] **Step 8: Commit this task**

Only commit after user approval if this plan is being executed in a checkpointed workflow.

```bash
git add backend/src/portfolio_app/services/market_data.py backend/src/portfolio_app/services/toss_portfolio.py backend/src/portfolio_app/services/stock_metadata.py backend/tests/test_toss_portfolio.py backend/tests/test_stock_metadata.py
git commit -m "fix: retry toss rate limit responses once"
```

---

### Task 5: Documentation And Regression Verification

**Files:**
- Modify: `docs/toss-open-api-integration.md`
- Verify: backend tests and ruff

- [ ] **Step 1: Document rate-limit mitigation**

In `docs/toss-open-api-integration.md`, add this subsection after the existing error-handling example:

```markdown
### Rate-limit mitigation

Toss rate limits are enforced per client and API group. The backend reduces
burst traffic in three places:

- a single app-scoped `TossAuthClient` reuses the OAuth access token across
  account, holding, summary, FX, and market-data calls;
- `/api/toss/accounts` uses a short in-memory TTL cache so repeated dashboard
  and holdings page loads do not hit the `ACCOUNT` group every time;
- Toss providers retry one `429` response after the provider's `Retry-After`
  header, falling back to `X-RateLimit-Reset` when `Retry-After` is absent.

The cache is process-local and intentionally short-lived. It protects the local
UI from refresh and React development-mode duplicate requests without making
Toss account data a durable local source of truth.
```

- [ ] **Step 2: Run focused backend regression tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_toss_portfolio.py backend/tests/test_api.py backend/tests/test_summary.py backend/tests/test_stock_metadata.py -q
```

Expected: PASS.

- [ ] **Step 3: Run backend lint**

Run:

```bash
.venv/bin/python -m ruff check backend
```

Expected: `All checks passed!`

- [ ] **Step 4: Run full backend test suite if focused tests pass**

Run:

```bash
.venv/bin/python -m pytest backend/tests -q
```

Expected: PASS.

- [ ] **Step 5: Check whitespace and diff scope**

Run:

```bash
git diff --check
git diff --stat
```

Expected: `git diff --check` prints no output. `git diff --stat` only includes the backend Toss service/API/test files and `docs/toss-open-api-integration.md`.

- [ ] **Step 6: Optional live smoke test with configured Toss credentials**

Run only if the user explicitly asks for live validation:

```bash
PORTFOLIO_BACKUP_ENABLED=false .venv/bin/python -m uvicorn portfolio_app.asgi:app --host 127.0.0.1 --port 8001
curl -sS http://127.0.0.1:8001/api/toss/accounts
```

Expected: a normalized account list or a safe backend error that does not include Toss secrets.

- [ ] **Step 7: Final commit**

Only commit after user approval if this plan is being executed in a checkpointed workflow.

```bash
git add backend/src/portfolio_app/services/market_data.py backend/src/portfolio_app/services/toss_portfolio.py backend/src/portfolio_app/services/stock_metadata.py backend/src/portfolio_app/main.py backend/src/portfolio_app/api/toss_portfolio.py backend/src/portfolio_app/api/summary.py backend/tests/test_toss_portfolio.py backend/tests/test_api.py backend/tests/test_stock_metadata.py docs/toss-open-api-integration.md
git commit -m "fix: throttle toss portfolio requests"
```

---

## Self-Review Notes

- Spec coverage: shared Toss auth client is covered by Task 2; accounts TTL cache and concurrent fetch collapse are covered by Task 3; 429 header-based retry is covered by Tasks 1 and 4; docs and verification are covered by Task 5.
- Scope boundary: no frontend behavior change is included. The backend fix protects both dashboard and holdings page traffic without changing UI state flow.
- Risk to inspect during execution: `pytest-httpx` request ordering assertions may need minor adjustment if existing optional responses are reused by neighboring tests. Keep assertions scoped to method and URL path, as shown above.
