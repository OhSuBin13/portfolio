import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from portfolio_app.config import Settings
from portfolio_app.main import create_app
from portfolio_app.models import GrowthAnnualHistoryRow, GrowthMonthHistoryRow
from portfolio_app.services.growth_history import (
    GrowthMonthInput,
    build_annual_history,
    build_month_history,
)


def month(
    year: int,
    month_number: int,
    net_worth_krw: float,
    monthly_dividend_krw: float = 0,
    *,
    account_seq: str = "account-1",
) -> GrowthMonthInput:
    return GrowthMonthInput(
        account_seq=account_seq,
        year=year,
        month=month_number,
        net_worth_krw=net_worth_krw,
        monthly_dividend_krw=monthly_dividend_krw,
        created_at=f"{year}-{month_number:02d}-created",
        updated_at=f"{year}-{month_number:02d}-updated",
    )


def create_test_client(tmp_path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
        toss_api_key="",
        toss_secret_key="",
        backup_enabled=False,
    )
    return TestClient(create_app(settings=settings))


def put_month(
    client: TestClient,
    *,
    account_seq: str,
    year: int,
    month_number: int,
    net_worth_krw: float,
    monthly_dividend_krw: float,
):
    return client.put(
        f"/api/growth/month-history/{year}/{month_number}",
        params={"account_seq": account_seq},
        json={
            "net_worth_krw": net_worth_krw,
            "monthly_dividend_krw": monthly_dividend_krw,
        },
    )


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/api/growth/month-history", {}),
        ("get", "/api/growth/annual-history", {}),
        (
            "put",
            "/api/growth/month-history/2026/6",
            {"json": {"net_worth_krw": 1_000_000, "monthly_dividend_krw": 10_000}},
        ),
    ],
)
def test_growth_history_endpoints_require_account_seq(tmp_path, method, path, kwargs):
    client = create_test_client(tmp_path)

    response = client.request(method, path, **kwargs)

    assert response.status_code == 400
    assert "account_seq" in str(response.json()["detail"])


def test_put_month_history_upserts_row_from_payload(tmp_path):
    client = create_test_client(tmp_path)

    first_response = put_month(
        client,
        account_seq=" acct-1 ",
        year=2026,
        month_number=6,
        net_worth_krw=1_000_000,
        monthly_dividend_krw=10_000,
    )
    second_response = put_month(
        client,
        account_seq="acct-1",
        year=2026,
        month_number=6,
        net_worth_krw=1_250_000,
        monthly_dividend_krw=15_000,
    )
    list_response = client.get(
        "/api/growth/month-history",
        params={"account_seq": "acct-1"},
    )

    assert first_response.status_code == 200
    assert first_response.json()["account_seq"] == "acct-1"
    assert second_response.status_code == 200
    body = second_response.json()
    assert body["account_seq"] == "acct-1"
    assert body["year"] == 2026
    assert body["month"] == 6
    assert body["net_worth_krw"] == 1_250_000.0
    assert body["monthly_dividend_krw"] == 15_000.0
    assert body["monthly_return_ratio"] is None
    assert body["average_return_ratio"] is None
    assert body["cumulative_dividend_krw"] == 15_000.0
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["net_worth_krw"] == 1_250_000.0
    assert list_response.json()[0]["monthly_dividend_krw"] == 15_000.0


def test_get_month_history_returns_computed_rows_for_account(tmp_path):
    client = create_test_client(tmp_path)
    put_month(
        client,
        account_seq="acct-1",
        year=2026,
        month_number=7,
        net_worth_krw=1_500_000,
        monthly_dividend_krw=30_000,
    )
    put_month(
        client,
        account_seq="acct-1",
        year=2026,
        month_number=5,
        net_worth_krw=1_000_000,
        monthly_dividend_krw=10_000,
    )
    put_month(
        client,
        account_seq="acct-1",
        year=2026,
        month_number=6,
        net_worth_krw=1_250_000,
        monthly_dividend_krw=20_000,
    )

    response = client.get("/api/growth/month-history", params={"account_seq": "acct-1"})

    assert response.status_code == 200
    rows = response.json()
    assert [(row["year"], row["month"]) for row in rows] == [
        (2026, 5),
        (2026, 6),
        (2026, 7),
    ]
    assert rows[0]["cumulative_dividend_krw"] == 10_000.0
    assert rows[0]["monthly_return_ratio"] is None
    assert rows[0]["average_return_ratio"] is None
    assert rows[1]["cumulative_dividend_krw"] == 30_000.0
    assert rows[1]["monthly_return_ratio"] == pytest.approx(1.25)
    assert rows[1]["average_return_ratio"] == pytest.approx(1.25)
    assert rows[2]["cumulative_dividend_krw"] == 60_000.0
    assert rows[2]["monthly_return_ratio"] == pytest.approx(1.2)
    assert rows[2]["average_return_ratio"] == pytest.approx(1.225)


def test_get_annual_history_returns_derived_rows_for_account(tmp_path):
    client = create_test_client(tmp_path)
    for year, month_number, net_worth in [
        (2024, 12, 1_000_000),
        (2025, 11, 1_200_000),
        (2025, 12, 1_400_000),
        (2026, 6, 2_100_000),
    ]:
        put_month(
            client,
            account_seq="acct-1",
            year=year,
            month_number=month_number,
            net_worth_krw=net_worth,
            monthly_dividend_krw=0,
        )

    response = client.get("/api/growth/annual-history", params={"account_seq": "acct-1"})

    assert response.status_code == 200
    rows = response.json()
    assert [
        (row["year"], row["display_year"], row["source_month"], row["net_worth_krw"])
        for row in rows
    ] == [
        (2024, "24", 12, 1_000_000.0),
        (2025, "25", 12, 1_400_000.0),
        (2026, "26", 6, 2_100_000.0),
    ]
    assert rows[0]["annual_return_ratio"] is None
    assert rows[0]["average_return_ratio"] is None
    assert rows[1]["annual_return_ratio"] == pytest.approx(1.4)
    assert rows[1]["average_return_ratio"] == pytest.approx(1.4)
    assert rows[2]["annual_return_ratio"] == pytest.approx(1.5)
    assert rows[2]["average_return_ratio"] == pytest.approx(1.45)


def test_growth_history_is_isolated_by_account_seq(tmp_path):
    client = create_test_client(tmp_path)
    put_month(
        client,
        account_seq="acct-1",
        year=2026,
        month_number=6,
        net_worth_krw=1_000_000,
        monthly_dividend_krw=10_000,
    )
    put_month(
        client,
        account_seq="acct-2",
        year=2026,
        month_number=6,
        net_worth_krw=2_000_000,
        monthly_dividend_krw=20_000,
    )

    month_response = client.get(
        "/api/growth/month-history",
        params={"account_seq": "acct-2"},
    )
    annual_response = client.get(
        "/api/growth/annual-history",
        params={"account_seq": "acct-2"},
    )

    assert month_response.status_code == 200
    assert annual_response.status_code == 200
    assert [row["account_seq"] for row in month_response.json()] == ["acct-2"]
    assert month_response.json()[0]["net_worth_krw"] == 2_000_000.0
    assert month_response.json()[0]["cumulative_dividend_krw"] == 20_000.0
    assert [row["account_seq"] for row in annual_response.json()] == ["acct-2"]
    assert annual_response.json()[0]["net_worth_krw"] == 2_000_000.0


def test_month_history_uses_adjacent_month_return_ratios_and_running_averages():
    rows = build_month_history(
        [
            month(2026, 3, 1_500_000, 30_000),
            month(2026, 1, 1_000_000, 10_000),
            month(2026, 2, 1_200_000, 20_000),
        ]
    )

    assert all(isinstance(row, GrowthMonthHistoryRow) for row in rows)
    assert [(row.year, row.month) for row in rows] == [(2026, 1), (2026, 2), (2026, 3)]

    january, february, march = rows
    assert january.monthly_return_ratio is None
    assert january.average_return_ratio is None
    assert january.cumulative_dividend_krw == 10_000

    february_ratio = 1_200_000 / 1_000_000
    assert february.monthly_return_ratio == pytest.approx(february_ratio)
    assert february.average_return_ratio == pytest.approx(february_ratio)
    assert february.cumulative_dividend_krw == 30_000

    march_ratio = 1_500_000 / 1_200_000
    assert march.monthly_return_ratio == pytest.approx(march_ratio)
    assert march.average_return_ratio == pytest.approx((february_ratio + march_ratio) / 2)
    assert march.cumulative_dividend_krw == 60_000


def test_month_history_missing_immediately_previous_calendar_month_has_no_return_ratio():
    rows = build_month_history(
        [
            month(2026, 1, 1_000_000, 10_000),
            month(2026, 3, 1_500_000, 30_000),
        ]
    )

    march = rows[1]
    assert march.monthly_return_ratio is None
    assert march.average_return_ratio is None
    assert march.cumulative_dividend_krw == 40_000


def test_month_history_previous_zero_net_worth_has_no_return_ratio():
    rows = build_month_history(
        [
            month(2026, 1, 0, 5_000),
            month(2026, 2, 1_000_000, 15_000),
        ]
    )

    february = rows[1]
    assert february.monthly_return_ratio is None
    assert february.average_return_ratio is None
    assert february.cumulative_dividend_krw == 20_000


def test_month_history_rejects_duplicate_account_period_inputs():
    duplicate_rows = [
        month(2026, 6, 1_000_000),
        month(2026, 6, 1_100_000),
    ]

    with pytest.raises(ValueError, match="Duplicate growth month input: account-1 2026-06"):
        build_month_history(duplicate_rows)
    with pytest.raises(ValueError, match="Duplicate growth month input: account-1 2026-06"):
        build_annual_history(duplicate_rows)


def test_month_history_resets_cumulative_dividends_and_averages_per_account():
    rows = build_month_history(
        [
            month(2026, 2, 1_100_000, 200_000, account_seq="account-2"),
            month(2026, 1, 1_000_000, 100_000, account_seq="account-2"),
            month(2026, 2, 2_000_000, 20_000, account_seq="account-1"),
            month(2026, 1, 1_000_000, 10_000, account_seq="account-1"),
        ]
    )

    by_period = {(row.account_seq, row.month): row for row in rows}
    assert [(row.account_seq, row.month) for row in rows] == [
        ("account-1", 1),
        ("account-1", 2),
        ("account-2", 1),
        ("account-2", 2),
    ]

    account_1_february_ratio = 2_000_000 / 1_000_000
    assert by_period[("account-1", 2)].monthly_return_ratio == pytest.approx(
        account_1_february_ratio
    )
    assert by_period[("account-1", 2)].average_return_ratio == pytest.approx(
        account_1_february_ratio
    )
    assert by_period[("account-1", 2)].cumulative_dividend_krw == 30_000

    account_2_february_ratio = 1_100_000 / 1_000_000
    assert by_period[("account-2", 2)].monthly_return_ratio == pytest.approx(
        account_2_february_ratio
    )
    assert by_period[("account-2", 2)].average_return_ratio == pytest.approx(
        account_2_february_ratio
    )
    assert by_period[("account-2", 2)].cumulative_dividend_krw == 300_000


def test_month_history_treats_january_as_adjacent_to_previous_december():
    rows = build_month_history(
        [
            month(2025, 12, 1_000_000, 10_000),
            month(2026, 1, 1_250_000, 20_000),
        ]
    )

    january_ratio = 1_250_000 / 1_000_000
    january = rows[1]
    assert january.monthly_return_ratio == pytest.approx(january_ratio)
    assert january.average_return_ratio == pytest.approx(january_ratio)
    assert january.cumulative_dividend_krw == 30_000


def test_annual_history_uses_latest_month_per_year_and_adjacent_year_returns():
    rows = build_annual_history(
        [
            month(2026, 2, 1_500_000),
            month(2025, 12, 1_200_000),
            month(2024, 12, 1_000_000),
            month(2026, 8, 1_800_000),
            month(2025, 1, 1_050_000),
        ]
    )

    assert all(isinstance(row, GrowthAnnualHistoryRow) for row in rows)
    assert [(row.year, row.display_year, row.source_month) for row in rows] == [
        (2024, "24", 12),
        (2025, "25", 12),
        (2026, "26", 8),
    ]
    assert [row.net_worth_krw for row in rows] == [1_000_000, 1_200_000, 1_800_000]

    ratio_2025 = 1_200_000 / 1_000_000
    ratio_2026 = 1_800_000 / 1_200_000
    assert rows[0].annual_return_ratio is None
    assert rows[0].average_return_ratio is None
    assert rows[1].annual_return_ratio == pytest.approx(ratio_2025)
    assert rows[1].average_return_ratio == pytest.approx(ratio_2025)
    assert rows[2].annual_return_ratio == pytest.approx(ratio_2026)
    assert rows[2].average_return_ratio == pytest.approx((ratio_2025 + ratio_2026) / 2)


def test_annual_history_missing_previous_calendar_year_has_no_return_ratio():
    rows = build_annual_history(
        [
            month(2024, 12, 1_000_000),
            month(2026, 6, 1_400_000),
        ]
    )

    assert [(row.year, row.display_year, row.source_month) for row in rows] == [
        (2024, "24", 12),
        (2026, "26", 6),
    ]
    assert rows[1].annual_return_ratio is None
    assert rows[1].average_return_ratio is None


def test_growth_history_models_reject_extra_and_non_finite_values():
    valid_month = {
        "account_seq": "account-1",
        "year": 2026,
        "month": 6,
        "net_worth_krw": 1_000_000.0,
        "monthly_dividend_krw": 10_000.0,
        "monthly_return_ratio": None,
        "average_return_ratio": None,
        "cumulative_dividend_krw": 10_000.0,
        "created_at": "created",
        "updated_at": "updated",
    }
    with pytest.raises(ValidationError):
        GrowthMonthHistoryRow(**valid_month, unexpected=True)
    with pytest.raises(ValidationError):
        GrowthMonthHistoryRow(**{**valid_month, "net_worth_krw": float("nan")})

    valid_annual = {
        "account_seq": "account-1",
        "year": 2026,
        "display_year": "26",
        "source_month": 6,
        "net_worth_krw": 1_000_000.0,
        "annual_return_ratio": None,
        "average_return_ratio": None,
    }
    with pytest.raises(ValidationError):
        GrowthAnnualHistoryRow(**valid_annual, unexpected=True)
    with pytest.raises(ValidationError):
        GrowthAnnualHistoryRow(**{**valid_annual, "annual_return_ratio": float("inf")})
