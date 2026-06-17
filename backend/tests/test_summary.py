from fastapi.testclient import TestClient

from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app
from portfolio_app.migrations import migrate
from portfolio_app.repositories import create_account, create_asset, upsert_holding
from portfolio_app.services.summary import build_summary


def create_summary_db(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    return db


def create_test_client(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )
    app = create_app(settings=settings)
    return TestClient(app)


def test_build_summary_returns_no_usd_rate_when_rate_is_missing(tmp_path):
    db = create_summary_db(tmp_path)
    try:
        result = build_summary(db)
    finally:
        db.close()

    assert result.summary.usd_krw_rate is None
    assert result.summary.usd_krw_change_percent is None
    assert result.asset_mix == {}
    assert result.asset_allocations == []


def test_build_summary_exposes_latest_usd_krw_rate_for_display(tmp_path):
    db = create_summary_db(tmp_path)
    try:
        db.executemany(
            """
            insert into fx_rates(
              base_currency, quote_currency, rate, source, fetched_at, change_percent
            )
            values (?, ?, ?, ?, ?, ?)
            """,
            [
                ("USD", "KRW", 1300, "test", "2026-06-12T09:00:00", 0.2),
                ("USD", "KRW", 1390.5, "test", "2026-06-12T10:00:00", -0.15),
            ],
        )
        db.commit()

        result = build_summary(db)
    finally:
        db.close()

    assert result.summary.usd_krw_rate == 1390.5
    assert result.summary.usd_krw_change_percent == -0.15


def test_build_summary_exposes_stock_etf_allocations_by_ticker(tmp_path):
    db = create_summary_db(tmp_path)
    try:
        cash_account_id = create_account(db, name="원화 현금", type="cash")
        brokerage_account_id = create_account(db, name="증권", type="brokerage")
        cash_asset_id = create_asset(
            db,
            symbol=None,
            name="KRW",
            type="cash",
            currency="KRW",
            market=None,
        )
        aapl_asset_id = create_asset(
            db,
            symbol="AAPL",
            name="Apple",
            type="stock_etf",
            currency="USD",
            market="US",
        )
        voo_asset_id = create_asset(
            db,
            symbol="VOO",
            name="Vanguard S&P 500 ETF",
            type="stock_etf",
            currency="USD",
            market="US",
        )
        db.executemany(
            "update assets set manual_price_krw = ? where id = ?",
            [
                (100_000, aapl_asset_id),
                (200_000, voo_asset_id),
            ],
        )
        upsert_holding(
            db,
            account_id=cash_account_id,
            asset_id=cash_asset_id,
            quantity=1_000_000,
            average_cost=None,
        )
        upsert_holding(
            db,
            account_id=brokerage_account_id,
            asset_id=aapl_asset_id,
            quantity=10,
            average_cost=100,
        )
        upsert_holding(
            db,
            account_id=brokerage_account_id,
            asset_id=voo_asset_id,
            quantity=10,
            average_cost=100,
        )

        result = build_summary(db)
    finally:
        db.close()

    assert result.asset_mix == {"cash": 25.0, "stock_etf": 75.0}
    assert result.asset_allocations == [
        {
            "asset_id": cash_asset_id,
            "asset_type": "cash",
            "label": "KRW",
            "name": "KRW",
            "percent": 25.0,
            "symbol": None,
            "value_krw": 1_000_000.0,
        },
        {
            "asset_id": aapl_asset_id,
            "asset_type": "stock_etf",
            "label": "AAPL",
            "name": "Apple",
            "percent": 25.0,
            "symbol": "AAPL",
            "value_krw": 1_000_000.0,
        },
        {
            "asset_id": voo_asset_id,
            "asset_type": "stock_etf",
            "label": "VOO",
            "name": "Vanguard S&P 500 ETF",
            "percent": 50.0,
            "symbol": "VOO",
            "value_krw": 2_000_000.0,
        },
    ]


def test_summary_refreshes_missing_usd_krw_rate_by_default(tmp_path, httpx_mock):
    client = create_test_client(tmp_path)
    httpx_mock.add_response(
        text="""
        <p class="no_today">
          <em class="no_down"><em class="no_down">1,410.50</em></em>
        </p>
        <p class="no_exday">
          <em class="no_up">3.20</em>
          <em class="no_up"><span class="ico plus">+</span>0.23%</em>
        </p>
        """,
    )

    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.json()["usd_krw_rate"] == 1410.5
    assert response.json()["usd_krw_change_percent"] == 0.23

    db = connect(client.app.state.settings.database_path)
    try:
        rows = db.execute(
            """
            select base_currency, quote_currency, rate, source, change_percent
            from fx_rates
            order by id
            """
        ).fetchall()
    finally:
        db.close()

    assert [dict(row) for row in rows] == [
        {
            "base_currency": "USD",
            "quote_currency": "KRW",
            "rate": 1410.5,
            "source": "naver_finance",
            "change_percent": 0.23,
        }
    ]


def test_summary_falls_back_to_frankfurter_when_naver_refresh_fails(tmp_path, httpx_mock):
    client = create_test_client(tmp_path)
    httpx_mock.add_response(status_code=500)
    httpx_mock.add_response(json={"base": "USD", "quote": "KRW", "rate": 1410.5})

    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.json()["usd_krw_rate"] == 1410.5
    assert response.json()["usd_krw_change_percent"] is None

    db = connect(client.app.state.settings.database_path)
    try:
        rows = db.execute(
            """
            select base_currency, quote_currency, rate, source, change_percent
            from fx_rates
            order by id
            """
        ).fetchall()
    finally:
        db.close()

    assert [dict(row) for row in rows] == [
        {
            "base_currency": "USD",
            "quote_currency": "KRW",
            "rate": 1410.5,
            "source": "frankfurter",
            "change_percent": None,
        }
    ]


def test_summary_uses_fresh_usd_krw_rate_without_refreshing(tmp_path, httpx_mock):
    client = create_test_client(tmp_path)
    db = connect(client.app.state.settings.database_path)
    try:
        db.execute(
            """
            insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
            values (?, ?, ?, ?, datetime('now'))
            """,
            ("USD", "KRW", 1390.5, "test"),
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.json()["usd_krw_rate"] == 1390.5


def test_summary_refreshes_stale_usd_krw_rate_after_ttl(tmp_path, httpx_mock):
    client = create_test_client(tmp_path)
    db = connect(client.app.state.settings.database_path)
    try:
        db.execute(
            """
            insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
            values (?, ?, ?, ?, ?)
            """,
            ("USD", "KRW", 1390.5, "test", "2026-01-01T00:00:00+00:00"),
        )
        db.commit()
    finally:
        db.close()
    httpx_mock.add_response(
        text="""
        <p class="no_today"><em class="no_down"><em class="no_down">1,410.50</em></em></p>
        <p class="no_exday">
          <em class="no_down">2.30</em>
          <em class="no_down"><span class="ico minus">-</span>0.15%</em>
        </p>
        """,
    )

    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.json()["usd_krw_rate"] == 1410.5
    assert response.json()["usd_krw_change_percent"] == -0.15
