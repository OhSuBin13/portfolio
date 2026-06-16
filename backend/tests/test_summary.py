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
    assert asset_mix == {}


def test_build_summary_exposes_latest_usd_krw_rate_for_display(tmp_path):
    db = create_summary_db(tmp_path)
    try:
        db.executemany(
            """
            insert into fx_rates(base_currency, quote_currency, rate, source, fetched_at)
            values (?, ?, ?, ?, ?)
            """,
            [
                ("USD", "KRW", 1300, "test", "2026-06-12T09:00:00"),
                ("USD", "KRW", 1390.5, "test", "2026-06-12T10:00:00"),
            ],
        )
        db.commit()

        summary, _asset_mix = build_summary(db)
    finally:
        db.close()

    assert summary.usd_krw_rate == 1390.5


def test_summary_refreshes_missing_usd_krw_rate_by_default(tmp_path, httpx_mock):
    client = create_test_client(tmp_path)
    httpx_mock.add_response(json={"base": "USD", "quote": "KRW", "rate": 1410.5})

    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.json()["usd_krw_rate"] == 1410.5

    db = connect(client.app.state.settings.database_path)
    try:
        rows = db.execute(
            """
            select base_currency, quote_currency, rate, source
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
    httpx_mock.add_response(json={"base": "USD", "quote": "KRW", "rate": 1410.5})

    response = client.get("/api/summary")

    assert response.status_code == 200
    assert response.json()["usd_krw_rate"] == 1410.5
