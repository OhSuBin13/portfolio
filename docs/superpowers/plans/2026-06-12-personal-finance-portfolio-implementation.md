# Personal Finance Portfolio MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private local Korean personal finance portfolio app with SQLite persistence, holdings, transactions, goals, CSV import, market sync, and automatic backups.

**Architecture:** Use a local full-stack web app. A FastAPI backend owns the SQLite database, finance calculations, imports, market data, and backups. A Vite React TypeScript frontend renders the Korean Snapshot First UI and talks to the backend over HTTP.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, stdlib `sqlite3`, pytest, httpx, Vite, React, TypeScript, CSS modules, lucide-react.

---

## Source Notes

Market-data provider choices must be verified during implementation because provider coverage and limits change. As of this plan:

- Alpha Vantage documents global equity APIs, ticker search, quote endpoints, FX exchange-rate endpoints, and API-key usage.
- CoinGecko documents the simple price endpoint with `ids`, `symbols`, and `vs_currencies` parameters for crypto quotes.
- Frankfurter documents a free v2 FX API with no API key, latest rates, pair rates, and provider attribution.

Initial provider plan:

- Use Alpha Vantage for US stocks/ETFs, symbol search, and as the first keyed equity adapter.
- Use Alpha Vantage symbol search for Korean stock/ETF symbols; store unsupported symbols as sync failures with manual price override until a Korean-specific adapter is added.
- Use CoinGecko for major crypto assets.
- Use Frankfurter for fiat FX into KRW.

## Scope Check

The approved spec contains several subsystems, but they are not independent products. This plan keeps them in one MVP implementation sequence because each subsystem depends on the same accounts, assets, holdings, transactions, and KRW valuation model.

The plan is split into small tasks that produce working software incrementally:

1. Repository scaffold and tooling.
2. SQLite schema and migration runner.
3. Domain models and finance calculations.
4. Transaction application.
5. Backend API.
6. Backup service.
7. CSV import.
8. Market data sync.
9. Frontend shell.
10. Dashboard, holdings, transactions, and goals UI.
11. Import, settings, backup, and sync UI.
12. End-to-end verification and docs.

## File Structure

Create this structure:

```text
backend/
  pyproject.toml
  src/portfolio_app/
    __init__.py
    main.py
    config.py
    db.py
    migrations.py
    schema.sql
    models.py
    finance.py
    repositories.py
    services/
      __init__.py
      backups.py
      imports.py
      market_data.py
      transactions.py
    api/
      __init__.py
      accounts.py
      assets.py
      backups.py
      goals.py
      imports.py
      market_data.py
      summary.py
      transactions.py
  tests/
    conftest.py
    test_db.py
    test_finance.py
    test_transactions.py
    test_backups.py
    test_imports.py
    test_market_data.py
    test_api.py
frontend/
  package.json
  index.html
  src/
    main.tsx
    App.tsx
    api.ts
    types.ts
    styles.css
    components/
      AppShell.tsx
      Dashboard.tsx
      HoldingsPage.tsx
      TransactionsPage.tsx
      GoalsPage.tsx
      ImportPage.tsx
      SettingsPage.tsx
data/
  .gitkeep
  backups/
    .gitkeep
.gitignore
README.md
```

Do not commit `data/portfolio.sqlite`, backup database files, API keys, virtualenvs, build outputs, node modules, or `.superpowers/`.

## Task 1: Repository Scaffold And Tooling

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `backend/pyproject.toml`
- Create: `backend/src/portfolio_app/__init__.py`
- Create: `backend/src/portfolio_app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `data/.gitkeep`
- Create: `data/backups/.gitkeep`

- [ ] **Step 1: Add ignore rules**

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
*.pyc
node_modules/
frontend/dist/
data/*.sqlite
data/*.sqlite-*
data/backups/*.sqlite
.env
.env.*
.superpowers/
```

- [ ] **Step 2: Add backend package metadata**

Create `backend/pyproject.toml`:

```toml
[project]
name = "portfolio-app-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "httpx>=0.27",
  "pydantic>=2.8",
  "pydantic-settings>=2.4",
  "python-multipart>=0.0.9",
  "uvicorn[standard]>=0.30",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pytest-cov>=5.0",
  "ruff>=0.5",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

- [ ] **Step 3: Add minimal FastAPI app**

Create `backend/src/portfolio_app/main.py`:

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Personal Finance Portfolio", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: Add a health test**

Create `backend/tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from portfolio_app.main import create_app


def test_health_returns_ok():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 5: Install backend dependencies**

Run:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e "backend[dev]"
```

Expected: dependencies install without errors.

- [ ] **Step 6: Run backend checks**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py -q
.venv/bin/python -m ruff check backend
```

Expected: both commands pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add .gitignore README.md backend data
git commit -m "chore: scaffold local portfolio app"
```

## Task 2: SQLite Schema And Migration Runner

**Files:**
- Create: `backend/src/portfolio_app/config.py`
- Create: `backend/src/portfolio_app/db.py`
- Create: `backend/src/portfolio_app/migrations.py`
- Create: `backend/src/portfolio_app/schema.sql`
- Create: `backend/tests/test_db.py`

- [ ] **Step 1: Write failing migration test**

Create `backend/tests/test_db.py`:

```python
import sqlite3

from portfolio_app.db import connect
from portfolio_app.migrations import migrate


def table_names(db: sqlite3.Connection) -> set[str]:
    rows = db.execute(
        "select name from sqlite_master where type = 'table' and name not like 'sqlite_%'"
    ).fetchall()
    return {row["name"] for row in rows}


def test_migrate_creates_core_tables(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    db = connect(db_path)

    migrate(db)

    assert {
        "schema_migrations",
        "accounts",
        "assets",
        "holdings",
        "transactions",
        "price_snapshots",
        "fx_rates",
        "goals",
        "import_runs",
        "import_rows",
        "backups",
        "settings",
    }.issubset(table_names(db))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py -q
```

Expected: FAIL because `portfolio_app.db` or `portfolio_app.migrations` is missing.

- [ ] **Step 3: Add config and connection helper**

Create `backend/src/portfolio_app/config.py`:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    data_dir: Path = Path("data")
    database_path: Path = Path("data/portfolio.sqlite")
    backup_dir: Path = Path("data/backups")
    alpha_vantage_api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="PORTFOLIO_", env_file=".env")


def get_settings() -> Settings:
    return Settings()
```

Create `backend/src/portfolio_app/db.py`:

```python
import sqlite3
from pathlib import Path


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("pragma foreign_keys = on")
    return db
```

- [ ] **Step 4: Add schema**

Create `backend/src/portfolio_app/schema.sql` with these tables:

```sql
create table if not exists schema_migrations (
  version integer primary key,
  applied_at text not null default current_timestamp
);

create table if not exists accounts (
  id integer primary key,
  name text not null,
  type text not null check (type in ('cash','savings','brokerage','crypto_wallet','debt')),
  currency text not null default 'KRW',
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists assets (
  id integer primary key,
  symbol text,
  name text not null,
  type text not null check (type in ('cash','savings','stock_etf','crypto','debt')),
  currency text not null default 'KRW',
  market text not null default 'KR',
  manual_price_krw real,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create unique index if not exists idx_assets_symbol_market
on assets(symbol, market)
where symbol is not null;

create table if not exists holdings (
  id integer primary key,
  account_id integer not null references accounts(id) on delete cascade,
  asset_id integer not null references assets(id) on delete cascade,
  quantity real not null default 0,
  average_cost real,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp,
  unique(account_id, asset_id)
);

create table if not exists transactions (
  id integer primary key,
  occurred_on text not null,
  type text not null check (
    type in ('deposit','withdrawal','buy','sell','dividend','interest','fee','debt_payment','adjustment')
  ),
  account_id integer references accounts(id) on delete set null,
  asset_id integer references assets(id) on delete set null,
  quantity real,
  amount real not null default 0,
  currency text not null default 'KRW',
  fx_rate_to_krw real,
  memo text not null default '',
  created_at text not null default current_timestamp
);

create table if not exists price_snapshots (
  id integer primary key,
  asset_id integer not null references assets(id) on delete cascade,
  source text not null,
  price real not null,
  currency text not null,
  price_krw real not null,
  fetched_at text not null,
  status text not null default 'ok',
  error_message text not null default ''
);

create table if not exists fx_rates (
  id integer primary key,
  base_currency text not null,
  quote_currency text not null default 'KRW',
  rate real not null,
  source text not null,
  fetched_at text not null,
  unique(base_currency, quote_currency, fetched_at)
);

create table if not exists goals (
  id integer primary key,
  name text not null,
  type text not null check (type in ('net_worth','monthly_income')),
  target_amount_krw real not null,
  created_at text not null default current_timestamp,
  updated_at text not null default current_timestamp
);

create table if not exists import_runs (
  id integer primary key,
  filename text not null,
  status text not null check (status in ('previewed','confirmed','failed')),
  created_at text not null default current_timestamp
);

create table if not exists import_rows (
  id integer primary key,
  import_run_id integer not null references import_runs(id) on delete cascade,
  row_number integer not null,
  status text not null check (status in ('mapped','ignored','error')),
  raw_json text not null,
  message text not null default ''
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

- [ ] **Step 5: Add migration runner**

Create `backend/src/portfolio_app/migrations.py`:

```python
from pathlib import Path
import sqlite3


SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def migrate(db: sqlite3.Connection) -> None:
    current = db.execute(
        "select name from sqlite_master where type = 'table' and name = 'schema_migrations'"
    ).fetchone()
    if current:
        row = db.execute("select max(version) as version from schema_migrations").fetchone()
        if row["version"] == SCHEMA_VERSION:
            return

    db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    db.execute("insert or ignore into schema_migrations(version) values (?)", (SCHEMA_VERSION,))
    db.commit()
```

- [ ] **Step 6: Run test to verify it passes**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_db.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add backend/src/portfolio_app/config.py backend/src/portfolio_app/db.py backend/src/portfolio_app/migrations.py backend/src/portfolio_app/schema.sql backend/tests/test_db.py
git commit -m "feat: add sqlite schema and migrations"
```

## Task 3: Domain Models And Finance Calculations

**Files:**
- Create: `backend/src/portfolio_app/models.py`
- Create: `backend/src/portfolio_app/finance.py`
- Create: `backend/tests/test_finance.py`

- [ ] **Step 1: Write failing finance tests**

Create `backend/tests/test_finance.py`:

```python
from portfolio_app.finance import calculate_asset_mix, calculate_goal_progress, calculate_net_worth
from portfolio_app.models import Goal, HoldingValue


def test_net_worth_subtracts_debt_and_converts_to_krw():
    values = [
        HoldingValue(asset_type="cash", value_krw=1_000_000, monthly_income_krw=0),
        HoldingValue(asset_type="stock_etf", value_krw=2_500_000, monthly_income_krw=30_000),
        HoldingValue(asset_type="debt", value_krw=700_000, monthly_income_krw=0),
    ]

    summary = calculate_net_worth(values)

    assert summary.net_worth_krw == 2_800_000
    assert summary.monthly_income_krw == 30_000


def test_asset_mix_excludes_debt_from_positive_allocation():
    values = [
        HoldingValue(asset_type="cash", value_krw=1_000_000, monthly_income_krw=0),
        HoldingValue(asset_type="stock_etf", value_krw=3_000_000, monthly_income_krw=0),
        HoldingValue(asset_type="debt", value_krw=500_000, monthly_income_krw=0),
    ]

    mix = calculate_asset_mix(values)

    assert mix["cash"] == 25.0
    assert mix["stock_etf"] == 75.0
    assert "debt" not in mix


def test_goal_progress_caps_percent_at_100():
    goal = Goal(id=1, name="순자산 1억", type="net_worth", target_amount_krw=100_000_000)

    progress = calculate_goal_progress(goal, current_amount_krw=120_000_000)

    assert progress.percent == 100.0
    assert progress.remaining_krw == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_finance.py -q
```

Expected: FAIL because `models.py` and `finance.py` are missing.

- [ ] **Step 3: Add domain models**

Create `backend/src/portfolio_app/models.py`:

```python
from pydantic import BaseModel, Field


class HoldingValue(BaseModel):
    asset_type: str
    value_krw: float
    monthly_income_krw: float = 0


class PortfolioSummary(BaseModel):
    net_worth_krw: float
    gross_assets_krw: float
    debt_krw: float
    monthly_income_krw: float


class Goal(BaseModel):
    id: int
    name: str
    type: str
    target_amount_krw: float = Field(gt=0)


class GoalProgress(BaseModel):
    goal: Goal
    current_amount_krw: float
    percent: float
    remaining_krw: float
```

- [ ] **Step 4: Add finance calculations**

Create `backend/src/portfolio_app/finance.py`:

```python
from collections import defaultdict

from portfolio_app.models import Goal, GoalProgress, HoldingValue, PortfolioSummary


def calculate_net_worth(values: list[HoldingValue]) -> PortfolioSummary:
    gross_assets = sum(item.value_krw for item in values if item.asset_type != "debt")
    debt = sum(item.value_krw for item in values if item.asset_type == "debt")
    monthly_income = sum(item.monthly_income_krw for item in values)
    return PortfolioSummary(
        net_worth_krw=gross_assets - debt,
        gross_assets_krw=gross_assets,
        debt_krw=debt,
        monthly_income_krw=monthly_income,
    )


def calculate_asset_mix(values: list[HoldingValue]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for item in values:
        if item.asset_type != "debt":
            totals[item.asset_type] += item.value_krw

    denominator = sum(totals.values())
    if denominator == 0:
        return {}

    return {asset_type: round((value / denominator) * 100, 2) for asset_type, value in totals.items()}


def calculate_goal_progress(goal: Goal, current_amount_krw: float) -> GoalProgress:
    percent = min(100.0, round((current_amount_krw / goal.target_amount_krw) * 100, 2))
    remaining = max(0.0, goal.target_amount_krw - current_amount_krw)
    return GoalProgress(
        goal=goal,
        current_amount_krw=current_amount_krw,
        percent=percent,
        remaining_krw=remaining,
    )
```

- [ ] **Step 5: Run finance tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_finance.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/portfolio_app/models.py backend/src/portfolio_app/finance.py backend/tests/test_finance.py
git commit -m "feat: add portfolio finance calculations"
```

## Task 4: Repositories And Transaction Application

**Files:**
- Create: `backend/src/portfolio_app/repositories.py`
- Create: `backend/src/portfolio_app/services/transactions.py`
- Create: `backend/tests/test_transactions.py`

- [ ] **Step 1: Write failing transaction tests**

Create `backend/tests/test_transactions.py`:

```python
from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.repositories import create_account, create_asset, get_holding
from portfolio_app.services.transactions import apply_transaction, edit_holding_balance


def setup_db(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    return db


def test_buy_transaction_increases_holding_quantity(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="증권계좌", type="brokerage", currency="KRW")
    asset_id = create_asset(db, symbol="005930.KS", name="삼성전자", type="stock_etf", currency="KRW", market="KR")

    tx_id = apply_transaction(
        db,
        occurred_on="2026-06-12",
        type="buy",
        account_id=account_id,
        asset_id=asset_id,
        quantity=10,
        amount=700_000,
        currency="KRW",
        memo="첫 매수",
    )

    holding = get_holding(db, account_id=account_id, asset_id=asset_id)
    assert tx_id > 0
    assert holding["quantity"] == 10
    assert holding["average_cost"] == 70_000


def test_sell_more_than_holding_is_rejected(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="증권계좌", type="brokerage", currency="KRW")
    asset_id = create_asset(db, symbol="VOO", name="Vanguard S&P 500 ETF", type="stock_etf", currency="USD", market="US")

    try:
        apply_transaction(
            db,
            occurred_on="2026-06-12",
            type="sell",
            account_id=account_id,
            asset_id=asset_id,
            quantity=1,
            amount=500,
            currency="USD",
            memo="보유량 초과",
        )
    except ValueError as exc:
        assert "보유 수량" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_direct_holding_edit_creates_adjustment_transaction(tmp_path):
    db = setup_db(tmp_path)
    account_id = create_account(db, name="원화 현금", type="cash", currency="KRW")
    asset_id = create_asset(db, symbol=None, name="KRW", type="cash", currency="KRW", market="KR")

    tx_id = edit_holding_balance(
        db,
        account_id=account_id,
        asset_id=asset_id,
        quantity=1_500_000,
        memo="초기 현금 입력",
    )

    holding = get_holding(db, account_id=account_id, asset_id=asset_id)
    tx = db.execute("select type, amount, memo from transactions where id = ?", (tx_id,)).fetchone()
    assert holding["quantity"] == 1_500_000
    assert tx["type"] == "adjustment"
    assert tx["amount"] == 1_500_000
    assert tx["memo"] == "초기 현금 입력"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_transactions.py -q
```

Expected: FAIL because repository and transaction services are missing.

- [ ] **Step 3: Add repository helpers**

Create `backend/src/portfolio_app/repositories.py` with these function signatures and behavior:

```python
import sqlite3


def create_account(db: sqlite3.Connection, *, name: str, type: str, currency: str) -> int:
    cursor = db.execute(
        "insert into accounts(name, type, currency) values (?, ?, ?)",
        (name, type, currency),
    )
    db.commit()
    return int(cursor.lastrowid)


def create_asset(
    db: sqlite3.Connection,
    *,
    symbol: str | None,
    name: str,
    type: str,
    currency: str,
    market: str,
) -> int:
    cursor = db.execute(
        "insert into assets(symbol, name, type, currency, market) values (?, ?, ?, ?, ?)",
        (symbol, name, type, currency, market),
    )
    db.commit()
    return int(cursor.lastrowid)


def get_holding(db: sqlite3.Connection, *, account_id: int, asset_id: int) -> sqlite3.Row:
    row = db.execute(
        "select * from holdings where account_id = ? and asset_id = ?",
        (account_id, asset_id),
    ).fetchone()
    if row is None:
        raise ValueError("보유자산을 찾을 수 없습니다.")
    return row


def upsert_holding(
    db: sqlite3.Connection,
    *,
    account_id: int,
    asset_id: int,
    quantity: float,
    average_cost: float | None,
) -> None:
    db.execute(
        """
        insert into holdings(account_id, asset_id, quantity, average_cost)
        values (?, ?, ?, ?)
        on conflict(account_id, asset_id)
        do update set quantity = excluded.quantity,
                      average_cost = excluded.average_cost,
                      updated_at = current_timestamp
        """,
        (account_id, asset_id, quantity, average_cost),
    )
    db.commit()
```

- [ ] **Step 4: Add transaction service**

Create `backend/src/portfolio_app/services/__init__.py` as an empty file.

Create `backend/src/portfolio_app/services/transactions.py` with this behavior:

```python
import sqlite3

from portfolio_app.repositories import get_holding, upsert_holding


def _current_holding(db: sqlite3.Connection, account_id: int, asset_id: int) -> tuple[float, float | None]:
    row = db.execute(
        "select quantity, average_cost from holdings where account_id = ? and asset_id = ?",
        (account_id, asset_id),
    ).fetchone()
    if row is None:
        return 0.0, None
    return float(row["quantity"]), row["average_cost"]


def apply_transaction(
    db: sqlite3.Connection,
    *,
    occurred_on: str,
    type: str,
    account_id: int,
    asset_id: int,
    quantity: float | None,
    amount: float,
    currency: str,
    memo: str,
    fx_rate_to_krw: float | None = None,
) -> int:
    current_quantity, current_average = _current_holding(db, account_id, asset_id)

    if type == "buy":
        if quantity is None or quantity <= 0:
            raise ValueError("매수 수량은 0보다 커야 합니다.")
        new_quantity = current_quantity + quantity
        existing_cost = current_quantity * (current_average or 0)
        new_average = (existing_cost + amount) / new_quantity
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=asset_id,
            quantity=new_quantity,
            average_cost=new_average,
        )
    elif type == "sell":
        if quantity is None or quantity <= 0:
            raise ValueError("매도 수량은 0보다 커야 합니다.")
        if quantity > current_quantity:
            raise ValueError("보유 수량보다 많이 매도할 수 없습니다.")
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=asset_id,
            quantity=current_quantity - quantity,
            average_cost=current_average,
        )
    elif type in {"deposit", "interest", "dividend"}:
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=asset_id,
            quantity=current_quantity + amount,
            average_cost=current_average,
        )
    elif type in {"withdrawal", "fee", "debt_payment"}:
        next_quantity = current_quantity - amount
        if next_quantity < 0 and type != "debt_payment":
            raise ValueError("잔고보다 큰 금액을 차감할 수 없습니다.")
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=asset_id,
            quantity=next_quantity,
            average_cost=current_average,
        )
    elif type == "adjustment":
        upsert_holding(
            db,
            account_id=account_id,
            asset_id=asset_id,
            quantity=amount,
            average_cost=current_average,
        )
    else:
        raise ValueError("지원하지 않는 거래 유형입니다.")

    cursor = db.execute(
        """
        insert into transactions(
          occurred_on, type, account_id, asset_id, quantity, amount, currency, fx_rate_to_krw, memo
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (occurred_on, type, account_id, asset_id, quantity, amount, currency, fx_rate_to_krw, memo),
    )
    db.commit()
    return int(cursor.lastrowid)


def edit_holding_balance(
    db: sqlite3.Connection,
    *,
    account_id: int,
    asset_id: int,
    quantity: float,
    memo: str,
) -> int:
    return apply_transaction(
        db,
        occurred_on="2026-06-12",
        type="adjustment",
        account_id=account_id,
        asset_id=asset_id,
        quantity=None,
        amount=quantity,
        currency="KRW",
        memo=memo,
    )
```

- [ ] **Step 5: Run transaction tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_transactions.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/portfolio_app/repositories.py backend/src/portfolio_app/services backend/tests/test_transactions.py
git commit -m "feat: apply portfolio transactions"
```

## Task 5: Backend API And Portfolio Summary

**Files:**
- Modify: `backend/src/portfolio_app/main.py`
- Create: `backend/src/portfolio_app/api/summary.py`
- Create: `backend/src/portfolio_app/api/accounts.py`
- Create: `backend/src/portfolio_app/api/assets.py`
- Create: `backend/src/portfolio_app/api/transactions.py`
- Create: `backend/src/portfolio_app/api/goals.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Add failing API tests**

Append to `backend/tests/test_api.py`:

```python
from pathlib import Path

from portfolio_app.config import Settings


def test_summary_endpoint_returns_empty_snapshot(tmp_path):
    settings = Settings(data_dir=tmp_path, database_path=tmp_path / "portfolio.sqlite", backup_dir=tmp_path / "backups")
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.json()["net_worth_krw"] == 0
    assert response.json()["asset_mix"] == {}


def test_can_create_account_asset_and_transaction(tmp_path):
    settings = Settings(data_dir=tmp_path, database_path=tmp_path / "portfolio.sqlite", backup_dir=tmp_path / "backups")
    app = create_app(settings=settings)
    client = TestClient(app)

    account = client.post("/api/accounts", json={"name": "원화 현금", "type": "cash", "currency": "KRW"}).json()
    asset = client.post("/api/assets", json={"symbol": None, "name": "KRW", "type": "cash", "currency": "KRW", "market": "KR"}).json()
    tx = client.post(
        "/api/transactions",
        json={
            "occurred_on": "2026-06-12",
            "type": "deposit",
            "account_id": account["id"],
            "asset_id": asset["id"],
            "quantity": None,
            "amount": 1_000_000,
            "currency": "KRW",
            "memo": "초기 입금",
        },
    )

    assert tx.status_code == 201
    summary = client.get("/api/summary").json()
    assert summary["net_worth_krw"] == 1_000_000
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py -q
```

Expected: FAIL because `create_app` does not accept settings and API routers are missing.

- [ ] **Step 3: Add API routers**

Implement routers with these endpoints:

```text
GET    /api/summary
POST   /api/accounts
GET    /api/accounts
POST   /api/assets
GET    /api/assets
POST   /api/transactions
GET    /api/transactions
POST   /api/goals
GET    /api/goals
```

Use Pydantic request models in each API module. Every write endpoint returns the created row as JSON and uses Korean validation messages when rejecting input.

- [ ] **Step 4: Wire database lifecycle in `main.py`**

Modify `create_app` to accept optional settings, migrate the database on startup, and attach `app.state.db_path`.

Use this shape:

```python
from fastapi import FastAPI

from portfolio_app.config import Settings, get_settings
from portfolio_app.db import connect
from portfolio_app.migrations import migrate


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app_settings.data_dir.mkdir(parents=True, exist_ok=True)
    app_settings.backup_dir.mkdir(parents=True, exist_ok=True)

    db = connect(app_settings.database_path)
    migrate(db)
    db.close()

    app = FastAPI(title="Personal Finance Portfolio", version="0.1.0")
    app.state.settings = app_settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

- [ ] **Step 5: Run API tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/portfolio_app/main.py backend/src/portfolio_app/api backend/tests/test_api.py
git commit -m "feat: expose portfolio backend api"
```

## Task 6: Backup Service

**Files:**
- Create: `backend/src/portfolio_app/services/backups.py`
- Create: `backend/src/portfolio_app/api/backups.py`
- Create: `backend/tests/test_backups.py`
- Modify: `backend/src/portfolio_app/main.py`

- [ ] **Step 1: Write failing backup tests**

Create `backend/tests/test_backups.py`:

```python
from portfolio_app.db import connect
from portfolio_app.migrations import migrate
from portfolio_app.services.backups import create_backup, prune_backups


def test_create_backup_copies_sqlite_file(tmp_path):
    db_path = tmp_path / "portfolio.sqlite"
    backup_dir = tmp_path / "backups"
    db = connect(db_path)
    migrate(db)
    db.close()

    backup_path = create_backup(db_path=db_path, backup_dir=backup_dir, reason="test")

    assert backup_path.exists()
    assert backup_path.name.endswith(".sqlite")


def test_prune_backups_keeps_newest_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for index in range(35):
        path = backup_dir / f"portfolio-2026-06-{index + 1:02d}-test.sqlite"
        path.write_text(str(index), encoding="utf-8")

    prune_backups(backup_dir=backup_dir, keep=30)

    assert len(list(backup_dir.glob("*.sqlite"))) == 30
    assert (backup_dir / "portfolio-2026-06-35-test.sqlite").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_backups.py -q
```

Expected: FAIL because backup service is missing.

- [ ] **Step 3: Add backup service**

Create `backend/src/portfolio_app/services/backups.py`:

```python
from datetime import datetime
from pathlib import Path
import shutil


def create_backup(*, db_path: Path, backup_dir: Path, reason: str) -> Path:
    if not db_path.exists():
        raise FileNotFoundError("데이터베이스 파일을 찾을 수 없습니다.")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"portfolio-{timestamp}-{reason}.sqlite"
    shutil.copy2(db_path, target)
    return target


def prune_backups(*, backup_dir: Path, keep: int = 30) -> None:
    backups = sorted(backup_dir.glob("*.sqlite"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in backups[keep:]:
        path.unlink()
```

- [ ] **Step 4: Add backup API**

Create `backend/src/portfolio_app/api/backups.py` with:

```text
POST /api/backups
GET  /api/backups
```

`POST /api/backups` calls `create_backup` with reason `manual`. `GET /api/backups` lists newest backup paths and created timestamps.

- [ ] **Step 5: Create startup backup**

Modify `create_app` so that after migration it calls `create_backup` with reason `startup` when `database_path` exists and catches no exceptions. Backup failures must raise a startup error.

- [ ] **Step 6: Run backup and API tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_backups.py backend/tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add backend/src/portfolio_app/services/backups.py backend/src/portfolio_app/api/backups.py backend/src/portfolio_app/main.py backend/tests/test_backups.py
git commit -m "feat: add automatic sqlite backups"
```

## Task 7: CSV Import Preview And Confirm

**Files:**
- Create: `backend/src/portfolio_app/services/imports.py`
- Create: `backend/src/portfolio_app/api/imports.py`
- Create: `backend/tests/test_imports.py`

- [ ] **Step 1: Write failing import tests**

Create `backend/tests/test_imports.py`:

```python
from portfolio_app.services.imports import parse_portfolio_csv


def test_parse_portfolio_csv_maps_holding_rows():
    csv_text = "\n".join(
        [
            "종류,이름,수익률,개수,개당 가격,평단가,환율,평가액,투자금,수익,배당,배당률,연배당,비중",
            "현금,달러 예수금,-,1,\"6,375.00\",-,\"1,523.5\",\"₩ 9,712,568\",-,-,-,-,-,100.00%",
            "적금,주택청약,-,1,\"12,800,000\",-,1,\"₩ 12,800,000\",-,-,-,-,-,-",
        ]
    )

    preview = parse_portfolio_csv(csv_text)

    assert len(preview.mapped_rows) == 2
    assert preview.mapped_rows[0].asset_type == "cash"
    assert preview.mapped_rows[0].name == "달러 예수금"
    assert preview.mapped_rows[0].quantity == 1
    assert preview.mapped_rows[0].price == 6375.0
    assert preview.mapped_rows[0].fx_rate_to_krw == 1523.5
    assert preview.mapped_rows[0].value_krw == 9712568


def test_parse_portfolio_csv_ignores_formula_errors():
    csv_text = "종류,이름,평가액\n현금,오류행,#DIV/0!\n"

    preview = parse_portfolio_csv(csv_text)

    assert preview.mapped_rows == []
    assert preview.ignored_rows[0].message == "평가액을 읽을 수 없습니다."
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_imports.py -q
```

Expected: FAIL because import service is missing.

- [ ] **Step 3: Add CSV parser**

Create `backend/src/portfolio_app/services/imports.py` with:

```python
from dataclasses import dataclass
import csv
import io
import re


ASSET_TYPE_MAP = {
    "현금": "cash",
    "적금": "savings",
    "주식": "stock_etf",
    "ETF": "stock_etf",
    "가상자산": "crypto",
    "코인": "crypto",
    "부채": "debt",
}


@dataclass
class ImportRow:
    row_number: int
    asset_type: str
    name: str
    quantity: float
    price: float | None
    average_cost: float | None
    fx_rate_to_krw: float | None
    value_krw: float
    message: str = ""


@dataclass
class IgnoredRow:
    row_number: int
    message: str


@dataclass
class ImportPreview:
    mapped_rows: list[ImportRow]
    ignored_rows: list[IgnoredRow]


def parse_number(value: str) -> float | None:
    cleaned = value.strip().replace("₩", "").replace(",", "").replace("%", "")
    cleaned = re.sub(r"\s+", "", cleaned)
    if cleaned in {"", "-", "#DIV/0!", "#REF!"}:
        return None
    return float(cleaned)


def parse_portfolio_csv(csv_text: str) -> ImportPreview:
    reader = csv.DictReader(io.StringIO(csv_text))
    mapped: list[ImportRow] = []
    ignored: list[IgnoredRow] = []

    for row_number, row in enumerate(reader, start=2):
        raw_type = (row.get("종류") or "").strip()
        name = (row.get("이름") or "").strip()
        asset_type = ASSET_TYPE_MAP.get(raw_type)
        value_krw = parse_number(row.get("평가액") or "")

        if not asset_type or not name:
            ignored.append(IgnoredRow(row_number=row_number, message="종류 또는 이름을 읽을 수 없습니다."))
            continue
        if value_krw is None:
            ignored.append(IgnoredRow(row_number=row_number, message="평가액을 읽을 수 없습니다."))
            continue

        mapped.append(
            ImportRow(
                row_number=row_number,
                asset_type=asset_type,
                name=name,
                quantity=parse_number(row.get("개수") or "") or 0,
                price=parse_number(row.get("개당 가격") or ""),
                average_cost=parse_number(row.get("평단가") or ""),
                fx_rate_to_krw=parse_number(row.get("환율") or ""),
                value_krw=value_krw,
            )
        )

    return ImportPreview(mapped_rows=mapped, ignored_rows=ignored)
```

- [ ] **Step 4: Add import API**

Create `backend/src/portfolio_app/api/imports.py` with:

```text
POST /api/imports/preview
POST /api/imports/confirm
```

`preview` accepts an uploaded CSV file and returns `ImportPreview`. `confirm` accepts mapped rows, creates a pre-import backup, creates accounts/assets/holdings, and creates `adjustment` transactions for starting balances.

- [ ] **Step 5: Run import tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_imports.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/portfolio_app/services/imports.py backend/src/portfolio_app/api/imports.py backend/tests/test_imports.py
git commit -m "feat: add csv import preview"
```

## Task 8: Market Data Sync

**Files:**
- Create: `backend/src/portfolio_app/services/market_data.py`
- Create: `backend/src/portfolio_app/api/market_data.py`
- Create: `backend/tests/test_market_data.py`

- [ ] **Step 1: Write failing market-data tests**

Create `backend/tests/test_market_data.py`:

```python
import pytest

from portfolio_app.services.market_data import (
    CoinGeckoProvider,
    FrankfurterProvider,
    MarketQuote,
    keep_last_good_quote,
)


def test_keep_last_good_quote_uses_previous_value_on_error():
    previous = MarketQuote(symbol="VOO", price=500.0, currency="USD", source="alpha_vantage")

    result = keep_last_good_quote(previous=previous, error_message="rate limit")

    assert result.price == 500.0
    assert result.status == "stale"
    assert result.error_message == "rate limit"


@pytest.mark.asyncio
async def test_coingecko_provider_parses_simple_price(httpx_mock):
    httpx_mock.add_response(json={"bitcoin": {"krw": 150_000_000}})
    provider = CoinGeckoProvider()

    quote = await provider.fetch_crypto_quote("bitcoin", vs_currency="krw")

    assert quote.symbol == "bitcoin"
    assert quote.price == 150_000_000
    assert quote.currency == "KRW"


@pytest.mark.asyncio
async def test_frankfurter_provider_parses_pair_rate(httpx_mock):
    httpx_mock.add_response(json={"base": "USD", "quote": "KRW", "rate": 1375.5})
    provider = FrankfurterProvider()

    rate = await provider.fetch_rate("USD", "KRW")

    assert rate.base_currency == "USD"
    assert rate.quote_currency == "KRW"
    assert rate.rate == 1375.5
```

- [ ] **Step 2: Add test dependency**

Modify `backend/pyproject.toml` dev dependencies to include:

```toml
"pytest-asyncio>=0.23",
"pytest-httpx>=0.30",
```

Run:

```bash
.venv/bin/python -m pip install -e "backend[dev]"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_market_data.py -q
```

Expected: FAIL because market-data service is missing.

- [ ] **Step 4: Add market-data service**

Create `backend/src/portfolio_app/services/market_data.py` with:

```python
from dataclasses import dataclass
import httpx


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


def keep_last_good_quote(*, previous: MarketQuote, error_message: str) -> MarketQuote:
    return MarketQuote(
        symbol=previous.symbol,
        price=previous.price,
        currency=previous.currency,
        source=previous.source,
        status="stale",
        error_message=error_message,
    )


class CoinGeckoProvider:
    source = "coingecko"

    async def fetch_crypto_quote(self, coin_id: str, *, vs_currency: str = "krw") -> MarketQuote:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": coin_id, "vs_currencies": vs_currency},
            )
            response.raise_for_status()
            payload = response.json()
        return MarketQuote(
            symbol=coin_id,
            price=float(payload[coin_id][vs_currency]),
            currency=vs_currency.upper(),
            source=self.source,
        )


class FrankfurterProvider:
    source = "frankfurter"

    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"https://api.frankfurter.dev/v2/rate/{base_currency}/{quote_currency}"
            )
            response.raise_for_status()
            payload = response.json()
        return FxRate(
            base_currency=base_currency.upper(),
            quote_currency=quote_currency.upper(),
            rate=float(payload["rate"]),
            source=self.source,
        )
```

- [ ] **Step 5: Add Alpha Vantage adapter**

In `market_data.py`, add `AlphaVantageProvider`:

```python
class AlphaVantageProvider:
    source = "alpha_vantage"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def fetch_equity_quote(self, symbol: str) -> MarketQuote:
        if not self.api_key:
            raise ValueError("Alpha Vantage API 키가 필요합니다.")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://www.alphavantage.co/query",
                params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": self.api_key},
            )
            response.raise_for_status()
            payload = response.json()

        quote = payload.get("Global Quote", {})
        price = quote.get("05. price")
        if not price:
            raise ValueError("시세 응답에서 가격을 찾을 수 없습니다.")
        return MarketQuote(symbol=symbol, price=float(price), currency="USD", source=self.source)
```

- [ ] **Step 6: Add sync API**

Create `backend/src/portfolio_app/api/market_data.py` with:

```text
POST /api/market-data/sync
GET  /api/market-data/status
POST /api/market-data/manual-price
```

`sync` fetches quotes for assets that have a symbol. It stores successful snapshots. On failure, it leaves the last successful snapshot untouched and stores the failure status for display.

- [ ] **Step 7: Run market tests**

Run:

```bash
.venv/bin/python -m pytest backend/tests/test_market_data.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```bash
git add backend/pyproject.toml backend/src/portfolio_app/services/market_data.py backend/src/portfolio_app/api/market_data.py backend/tests/test_market_data.py
git commit -m "feat: add market data providers"
```

## Task 9: Frontend Shell And API Client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/components/AppShell.tsx`

- [ ] **Step 1: Scaffold frontend**

Run:

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install lucide-react
```

Expected: Vite creates a React TypeScript app.

- [ ] **Step 2: Replace `frontend/package.json` scripts**

Ensure scripts include:

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc -b && vite build",
    "preview": "vite preview --host 127.0.0.1"
  }
}
```

- [ ] **Step 3: Add API types**

Create `frontend/src/types.ts`:

```ts
export type PortfolioSummary = {
  net_worth_krw: number
  gross_assets_krw: number
  debt_krw: number
  monthly_income_krw: number
  asset_mix: Record<string, number>
}

export type Account = {
  id: number
  name: string
  type: string
  currency: string
}

export type Asset = {
  id: number
  symbol: string | null
  name: string
  type: string
  currency: string
  market: string
}

export type Transaction = {
  id: number
  occurred_on: string
  type: string
  account_id: number
  asset_id: number
  quantity: number | null
  amount: number
  currency: string
  memo: string
}
```

- [ ] **Step 4: Add API client**

Create `frontend/src/api.ts`:

```ts
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000"

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`)
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<T>
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<T>
}
```

- [ ] **Step 5: Add Korean app shell**

Create `frontend/src/components/AppShell.tsx`:

```tsx
import { BarChart3, Database, Flag, History, Settings, Upload } from "lucide-react"

type Props = {
  active: string
  onNavigate: (screen: string) => void
  children: React.ReactNode
}

const navItems = [
  { id: "dashboard", label: "대시보드", icon: BarChart3 },
  { id: "holdings", label: "보유자산", icon: Database },
  { id: "transactions", label: "거래내역", icon: History },
  { id: "goals", label: "목표", icon: Flag },
  { id: "import", label: "가져오기", icon: Upload },
  { id: "settings", label: "설정", icon: Settings },
]

export function AppShell({ active, onNavigate, children }: Props) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>개인 포트폴리오</h1>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                className={active === item.id ? "active" : ""}
                onClick={() => onNavigate(item.id)}
                title={item.label}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  )
}
```

- [ ] **Step 6: Add App state**

Create `frontend/src/App.tsx`:

```tsx
import { useState } from "react"
import { AppShell } from "./components/AppShell"

export default function App() {
  const [active, setActive] = useState("dashboard")

  return (
    <AppShell active={active} onNavigate={setActive}>
      <h2>{active}</h2>
    </AppShell>
  )
}
```

- [ ] **Step 7: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: build passes.

- [ ] **Step 8: Commit**

Run:

```bash
git add frontend
git commit -m "feat: add korean frontend shell"
```

## Task 10: Dashboard, Holdings, Transactions, And Goals UI

**Files:**
- Create: `frontend/src/components/Dashboard.tsx`
- Create: `frontend/src/components/HoldingsPage.tsx`
- Create: `frontend/src/components/TransactionsPage.tsx`
- Create: `frontend/src/components/GoalsPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add Dashboard component**

Create `frontend/src/components/Dashboard.tsx`:

```tsx
import { useEffect, useState } from "react"
import { apiGet } from "../api"
import type { PortfolioSummary } from "../types"

const emptySummary: PortfolioSummary = {
  net_worth_krw: 0,
  gross_assets_krw: 0,
  debt_krw: 0,
  monthly_income_krw: 0,
  asset_mix: {},
}

export function Dashboard() {
  const [summary, setSummary] = useState<PortfolioSummary>(emptySummary)
  const [error, setError] = useState("")

  useEffect(() => {
    apiGet<PortfolioSummary>("/api/summary").then(setSummary).catch((err) => setError(String(err)))
  }, [])

  return (
    <section>
      <header className="page-header">
        <h2>오늘의 자산</h2>
        <p>순자산, 목표, 자산 비중, 최근 변화를 확인합니다.</p>
      </header>
      {error && <div className="error">{error}</div>}
      <div className="summary-grid">
        <article className="panel hero-panel">
          <span>순자산</span>
          <strong>{summary.net_worth_krw.toLocaleString("ko-KR")} 원</strong>
        </article>
        <article className="panel">
          <span>월 배당/소득</span>
          <strong>{summary.monthly_income_krw.toLocaleString("ko-KR")} 원</strong>
        </article>
      </div>
    </section>
  )
}
```

- [ ] **Step 2: Add form pages**

Create `HoldingsPage.tsx`, `TransactionsPage.tsx`, and `GoalsPage.tsx` with controlled forms that call the backend create endpoints. Labels must be Korean, and validation errors must display near the relevant form.

Use this transaction type list:

```ts
const transactionTypes = [
  ["deposit", "입금"],
  ["withdrawal", "출금"],
  ["buy", "매수"],
  ["sell", "매도"],
  ["dividend", "배당"],
  ["interest", "이자"],
  ["fee", "수수료"],
  ["debt_payment", "부채상환"],
  ["adjustment", "조정"],
]
```

- [ ] **Step 3: Wire screens in App**

Modify `frontend/src/App.tsx`:

```tsx
import { useState } from "react"
import { AppShell } from "./components/AppShell"
import { Dashboard } from "./components/Dashboard"
import { GoalsPage } from "./components/GoalsPage"
import { HoldingsPage } from "./components/HoldingsPage"
import { TransactionsPage } from "./components/TransactionsPage"

export default function App() {
  const [active, setActive] = useState("dashboard")

  return (
    <AppShell active={active} onNavigate={setActive}>
      {active === "dashboard" && <Dashboard />}
      {active === "holdings" && <HoldingsPage />}
      {active === "transactions" && <TransactionsPage />}
      {active === "goals" && <GoalsPage />}
      {active === "import" && <div>가져오기</div>}
      {active === "settings" && <div>설정</div>}
    </AppShell>
  )
}
```

- [ ] **Step 4: Add focused CSS**

Modify `frontend/src/styles.css` so the app is dense and dashboard-like:

```css
:root {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: #172026;
  background: #f6f7f8;
}

body {
  margin: 0;
}

button,
input,
select {
  font: inherit;
}

.app-shell {
  display: grid;
  grid-template-columns: 220px 1fr;
  min-height: 100vh;
}

.sidebar {
  background: #111827;
  color: white;
  padding: 20px 14px;
}

.sidebar h1 {
  font-size: 18px;
  margin: 0 0 20px;
}

.sidebar button {
  align-items: center;
  background: transparent;
  border: 0;
  color: #d1d5db;
  cursor: pointer;
  display: flex;
  gap: 10px;
  padding: 10px;
  text-align: left;
  width: 100%;
}

.sidebar button.active {
  background: #1f2937;
  color: white;
}

.content {
  padding: 24px;
}

.page-header h2 {
  margin: 0 0 4px;
}

.summary-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: 2fr 1fr;
}

.panel {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}

.hero-panel strong {
  display: block;
  font-size: 32px;
  margin-top: 8px;
}

.error {
  background: #fee2e2;
  border: 1px solid #fecaca;
  color: #991b1b;
  margin: 12px 0;
  padding: 10px;
}
```

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add frontend/src
git commit -m "feat: build portfolio dashboard screens"
```

## Task 11: Import, Settings, Backup, And Sync UI

**Files:**
- Create: `frontend/src/components/ImportPage.tsx`
- Create: `frontend/src/components/SettingsPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Add file upload helper**

Modify `frontend/src/api.ts`:

```ts
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const formData = new FormData()
  formData.append("file", file)
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body: formData,
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<T>
}
```

- [ ] **Step 2: Add import page**

Create `frontend/src/components/ImportPage.tsx`:

```tsx
import { useState } from "react"
import { apiPost, apiUpload } from "../api"

type ImportPreview = {
  mapped_rows: Array<{ row_number: number; asset_type: string; name: string; value_krw: number }>
  ignored_rows: Array<{ row_number: number; message: string }>
}

export function ImportPage() {
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [error, setError] = useState("")

  async function onFile(file: File) {
    setError("")
    try {
      setPreview(await apiUpload<ImportPreview>("/api/imports/preview", file))
    } catch (err) {
      setError(String(err))
    }
  }

  async function confirmImport() {
    if (!preview) return
    await apiPost("/api/imports/confirm", preview)
  }

  return (
    <section>
      <header className="page-header">
        <h2>가져오기</h2>
        <p>스프레드시트에서 내보낸 CSV를 확인한 뒤 반영합니다.</p>
      </header>
      <input type="file" accept=".csv,text/csv" onChange={(event) => event.target.files?.[0] && onFile(event.target.files[0])} />
      {error && <div className="error">{error}</div>}
      {preview && (
        <div className="panel">
          <strong>매핑된 행 {preview.mapped_rows.length}개</strong>
          <strong>무시된 행 {preview.ignored_rows.length}개</strong>
          <button onClick={confirmImport}>백업 후 가져오기</button>
        </div>
      )}
    </section>
  )
}
```

- [ ] **Step 3: Add settings page**

Create `frontend/src/components/SettingsPage.tsx` with controls for:

```text
Alpha Vantage API key
market sync button
manual backup button
latest backup status
market sync status
```

All labels are Korean. API keys are displayed as password inputs and never logged.

- [ ] **Step 4: Wire import and settings**

Modify `frontend/src/App.tsx` to render `ImportPage` and `SettingsPage` for the existing `import` and `settings` navigation ids.

- [ ] **Step 5: Run build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add frontend/src
git commit -m "feat: add import and settings workflows"
```

## Task 12: End-To-End Verification And Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-12-personal-finance-portfolio-design.md` only if implementation decisions require clarifying notes.

- [ ] **Step 1: Add README runbook**

Update `README.md` with:

````markdown
# Personal Finance Portfolio

Private local Korean personal finance portfolio app.

## Backend

```bash
python -m venv .venv
.venv/bin/python -m pip install -e "backend[dev]"
.venv/bin/python -m uvicorn portfolio_app.main:app --app-dir backend/src --reload --host 127.0.0.1 --port 8000
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Data

The local SQLite database lives at `data/portfolio.sqlite`.
Backups live in `data/backups/`.
Do not commit database files or API keys.
````

- [ ] **Step 2: Run backend test suite**

Run:

```bash
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m ruff check backend
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Start local app**

Run backend:

```bash
.venv/bin/python -m uvicorn portfolio_app.main:app --app-dir backend/src --reload --host 127.0.0.1 --port 8000
```

Run frontend in a second shell:

```bash
cd frontend
npm run dev
```

Expected:

- Backend health endpoint returns `{"status":"ok"}`.
- Frontend opens at `http://127.0.0.1:5173`.
- Dashboard displays Korean labels and an empty portfolio without crashing.

- [ ] **Step 5: Manual MVP flow**

Verify these actions in the UI:

```text
1. Create a KRW cash account and KRW cash asset.
2. Add a 1,000,000 KRW deposit transaction.
3. Confirm dashboard net worth shows 1,000,000 원.
4. Create a net worth goal for 100,000,000 원.
5. Confirm goal progress shows 1%.
6. Upload a CSV export and preview rows before confirming.
7. Trigger a manual backup and confirm a new file appears in data/backups.
8. Configure an Alpha Vantage key and run market sync for a test stock symbol.
9. Confirm failed symbols show an error without deleting last known good prices.
```

- [ ] **Step 6: Commit**

Run:

```bash
git add README.md docs/superpowers/specs/2026-06-12-personal-finance-portfolio-design.md
git commit -m "docs: add local runbook"
```

## Self-Review Checklist

Before executing this plan, confirm:

- Every spec requirement has a matching task.
- Every task has tests or a concrete verification command.
- The first implementation step writes failing tests before the production code it exercises.
- SQLite files, backups, API keys, `.superpowers/`, `node_modules/`, and build outputs are ignored.
- Direct holding edits create adjustment transactions.
- CSV import previews before writing and creates a backup before confirm.
- Market-data failures keep last known good prices and surface stale status.
- Korean labels are used for user-facing UI and errors.
