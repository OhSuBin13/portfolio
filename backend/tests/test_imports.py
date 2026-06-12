import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from portfolio_app.api.imports import ImportRowPayload
from portfolio_app.config import Settings
from portfolio_app.db import connect
from portfolio_app.services.imports import parse_portfolio_csv

CSV_HEADER = ",".join(
    [
        "종류",
        "이름",
        "수익률",
        "개수",
        "개당 가격",
        "평단가",
        "환율",
        "평가액",
        "투자금",
        "수익",
        "배당",
        "배당률",
        "연배당",
        "비중",
    ]
)


def create_test_client(tmp_path):
    from portfolio_app.main import create_app

    settings = Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "portfolio.sqlite",
        backup_dir=tmp_path / "backups",
    )
    return TestClient(create_app(settings=settings))


def assert_no_import_records(client):
    assert client.get("/api/accounts").json() == []
    assert client.get("/api/assets").json() == []
    assert client.get("/api/transactions").json() == []
    assert client.get("/api/summary").json()["net_worth_krw"] == 0

    db = connect(client.app.state.settings.database_path)
    try:
        assert db.execute("select count(*) from holdings").fetchone()[0] == 0
    finally:
        db.close()


def test_parse_portfolio_csv_maps_holding_rows():
    csv_text = "\n".join(
        [
            CSV_HEADER,
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


def test_parse_portfolio_csv_maps_symbol_columns():
    csv_text = "\n".join(
        [
            "종류,이름,티커,개수,개당 가격,평단가,환율,평가액",
            "ETF,S&P 500,voo,2,500,450,1400,\"₩ 1,400,000\"",
        ]
    )

    preview = parse_portfolio_csv(csv_text)

    assert preview.mapped_rows[0].symbol == "VOO"


def test_parse_portfolio_csv_ignores_formula_errors():
    csv_text = "종류,이름,평가액\n현금,오류행,#DIV/0!\n"

    preview = parse_portfolio_csv(csv_text)

    assert preview.mapped_rows == []
    assert preview.ignored_rows[0].message == "평가액을 읽을 수 없습니다."


def test_parse_portfolio_csv_ignores_common_spreadsheet_errors():
    csv_text = "종류,이름,평가액\n현금,오류행,#N/A\n"

    preview = parse_portfolio_csv(csv_text)

    assert preview.mapped_rows == []
    assert preview.ignored_rows[0].message == "평가액을 읽을 수 없습니다."


def test_parse_portfolio_csv_ignores_non_finite_numbers():
    csv_text = "종류,이름,개수,평가액\n현금,무한대행,1,Infinity\n"

    preview = parse_portfolio_csv(csv_text)

    assert preview.mapped_rows == []
    assert preview.ignored_rows[0].message == "숫자 값을 읽을 수 없습니다."


def test_import_preview_endpoint_maps_uploaded_csv(tmp_path):
    client = create_test_client(tmp_path)
    csv_text = "\n".join(
        [
            CSV_HEADER,
            "적금,주택청약,-,1,\"12,800,000\",-,1,\"₩ 12,800,000\",-,-,-,-,-,-",
        ]
    )

    response = client.post(
        "/api/imports/preview",
        files={"file": ("portfolio.csv", csv_text.encode("utf-8"), "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["mapped_rows"][0]["asset_type"] == "savings"
    assert response.json()["mapped_rows"][0]["name"] == "주택청약"
    assert response.json()["mapped_rows"][0]["value_krw"] == 12_800_000


def test_import_preview_endpoint_handles_utf8_bom_headers(tmp_path):
    client = create_test_client(tmp_path)
    csv_text = "\ufeff종류,이름,평가액\n현금,원화 예수금,\"₩ 1,000\"\n"

    response = client.post(
        "/api/imports/preview",
        files={"file": ("portfolio.csv", csv_text.encode("utf-8"), "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["mapped_rows"][0]["name"] == "원화 예수금"


def test_import_preview_and_confirm_preserve_symbol(tmp_path):
    client = create_test_client(tmp_path)
    csv_text = "\n".join(
        [
            "종류,이름,티커,개수,개당 가격,평단가,환율,평가액",
            "ETF,S&P 500,voo,2,500,450,1400,\"₩ 1,400,000\"",
        ]
    )
    preview = client.post(
        "/api/imports/preview",
        files={"file": ("portfolio.csv", csv_text.encode("utf-8"), "text/csv")},
    )

    assert preview.status_code == 200
    row = preview.json()["mapped_rows"][0]
    assert row["symbol"] == "VOO"

    response = client.post(
        "/api/imports/confirm",
        json={"occurred_on": "2026-06-12", "mapped_rows": [row]},
    )

    assert response.status_code == 201
    assets = client.get("/api/assets").json()
    assert assets[0]["symbol"] == "VOO"


def test_import_confirm_creates_backup_account_asset_holding_and_adjustment(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/imports/confirm",
        json={
            "occurred_on": "2026-06-12",
            "mapped_rows": [
                {
                    "row_number": 2,
                    "asset_type": "savings",
                    "name": "주택청약",
                    "quantity": 1,
                    "price": 12_800_000,
                    "average_cost": None,
                    "fx_rate_to_krw": None,
                    "value_krw": 12_800_000,
                }
            ],
        },
    )

    assert response.status_code == 201
    result = response.json()
    assert result["created_accounts"] == 1
    assert result["created_assets"] == 1
    assert result["created_holdings"] == 1
    assert result["created_transactions"] == 1
    assert Path(result["backup_path"]).exists()

    backups = client.get("/api/backups").json()
    assert any(backup["reason"] == "pre-import" for backup in backups)

    accounts = client.get("/api/accounts").json()
    assert accounts[0]["name"] == "주택청약"
    assert accounts[0]["type"] == "savings"

    assets = client.get("/api/assets").json()
    assert assets[0]["name"] == "주택청약"
    assert assets[0]["type"] == "savings"
    assert assets[0]["currency"] == "KRW"

    transactions = client.get("/api/transactions").json()
    assert transactions[0]["type"] == "adjustment"
    assert transactions[0]["occurred_on"] == "2026-06-12"
    assert transactions[0]["amount"] == 12_800_000

    summary = client.get("/api/summary").json()
    assert summary["net_worth_krw"] == 12_800_000
    assert summary["asset_mix"] == {"savings": 100.0}


def test_import_confirm_rolls_back_all_import_writes_when_later_row_fails(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/imports/confirm",
        json={
            "occurred_on": "2026-06-12",
            "mapped_rows": [
                {
                    "row_number": 2,
                    "asset_type": "stock_etf",
                    "symbol": "VOO",
                    "name": "S&P 500 A",
                    "quantity": 1,
                    "price": 500,
                    "average_cost": 500,
                    "fx_rate_to_krw": 1400,
                    "value_krw": 700_000,
                },
                {
                    "row_number": 3,
                    "asset_type": "stock_etf",
                    "symbol": "VOO",
                    "name": "S&P 500 B",
                    "quantity": 1,
                    "price": 500,
                    "average_cost": 500,
                    "fx_rate_to_krw": 1400,
                    "value_krw": 700_000,
                },
            ],
        },
    )

    assert response.status_code == 400
    assert_no_import_records(client)
    backups = client.get("/api/backups").json()
    assert any(backup["reason"] == "pre-import" for backup in backups)


@pytest.mark.parametrize("field", ["price", "average_cost"])
def test_import_confirm_rejects_negative_optional_numbers_without_persisting(tmp_path, field):
    client = create_test_client(tmp_path)
    row = {
        "row_number": 2,
        "asset_type": "stock_etf",
        "symbol": "VOO",
        "name": "S&P 500",
        "quantity": 2,
        "price": 500,
        "average_cost": 450,
        "fx_rate_to_krw": 1400,
        "value_krw": 1_400_000,
    }
    row[field] = -1

    response = client.post(
        "/api/imports/confirm",
        json={"occurred_on": "2026-06-12", "mapped_rows": [row]},
    )

    assert response.status_code == 400
    assert "숫자" in response.json()["detail"] or "올바르지" in response.json()["detail"]
    assert_no_import_records(client)


def test_import_row_payload_rejects_non_finite_fx_rate():
    with pytest.raises(ValidationError):
        ImportRowPayload(
            row_number=2,
            asset_type="stock_etf",
            name="S&P 500",
            quantity=2,
            price=500,
            average_cost=450,
            fx_rate_to_krw=math.inf,
            value_krw=1_400_000,
        )


def test_import_confirm_values_market_assets_from_import_price(tmp_path):
    client = create_test_client(tmp_path)

    response = client.post(
        "/api/imports/confirm",
        json={
            "occurred_on": "2026-06-12",
            "mapped_rows": [
                {
                    "row_number": 2,
                    "asset_type": "stock_etf",
                    "symbol": "VOO",
                    "name": "S&P 500",
                    "quantity": 2,
                    "price": 500,
                    "average_cost": 450,
                    "fx_rate_to_krw": 1400,
                    "value_krw": 1_400_000,
                }
            ],
        },
    )

    assert response.status_code == 201
    assets = client.get("/api/assets").json()
    assert assets[0]["manual_price_krw"] == 700_000
    transactions = client.get("/api/transactions").json()
    assert transactions[0]["amount"] == 2

    summary = client.get("/api/summary").json()
    assert summary["net_worth_krw"] == 1_400_000
    assert summary["asset_mix"] == {"stock_etf": 100.0}
