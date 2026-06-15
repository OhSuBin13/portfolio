from portfolio_app.api.summary import build_summary
from portfolio_app.db import connect
from portfolio_app.migrations import migrate


def create_summary_db(tmp_path):
    db = connect(tmp_path / "portfolio.sqlite")
    migrate(db)
    return db


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
