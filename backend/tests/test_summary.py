from fastapi.testclient import TestClient

from portfolio_app.api.summary import build_summary
from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.main import create_app
from portfolio_app.migrations import migrate


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
        summary, asset_mix = build_summary(db)
    finally:
        db.close()

    assert summary.usd_krw_rate is None
    assert summary.usd_krw_change_percent is None
    assert asset_mix == {}


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

        summary, _asset_mix = build_summary(db)
    finally:
        db.close()

    assert summary.usd_krw_rate == 1390.5
    assert summary.usd_krw_change_percent == -0.15


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
