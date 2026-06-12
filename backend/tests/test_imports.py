from pathlib import Path

from fastapi.testclient import TestClient

from portfolio_app.config import Settings
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


def test_parse_portfolio_csv_ignores_formula_errors():
    csv_text = "종류,이름,평가액\n현금,오류행,#DIV/0!\n"

    preview = parse_portfolio_csv(csv_text)

    assert preview.mapped_rows == []
    assert preview.ignored_rows[0].message == "평가액을 읽을 수 없습니다."


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
