import pytest

from portfolio_app.services.market_data import TossAuthClient
from portfolio_app.services.stock_metadata import TossStockMetadataProvider


@pytest.mark.asyncio
async def test_toss_stock_metadata_provider_parses_kr_stock_info(httpx_mock):
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
                    "englishName": "SamsungElec",
                    "isinCode": "KR7005930003",
                    "market": "KOSPI",
                    "securityType": "STOCK",
                    "isCommonShare": True,
                    "status": "ACTIVE",
                    "currency": "KRW",
                    "listDate": "1975-06-11",
                    "delistDate": None,
                    "sharesOutstanding": "5919637922",
                    "leverageFactor": None,
                    "koreanMarketDetail": None,
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
    stock_request = httpx_mock.get_requests()[1]
    assert stock_request.headers["authorization"] == "Bearer token-123"


@pytest.mark.asyncio
async def test_toss_stock_metadata_provider_parses_us_etf_info(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/stocks?symbols=VOO",
        json={
            "result": [
                {
                    "symbol": "VOO",
                    "name": "Vanguard S&P 500 ETF",
                    "englishName": "VANGUARD S&P 500 ETF",
                    "isinCode": "US9229083632",
                    "market": "NYSE",
                    "securityType": "ETF",
                    "isCommonShare": True,
                    "status": "ACTIVE",
                    "currency": "USD",
                    "sharesOutstanding": "0",
                }
            ]
        },
    )
    provider = TossStockMetadataProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    metadata = await provider.fetch_stock_metadata("voo")

    assert metadata.symbol == "VOO"
    assert metadata.market == "US"
    assert metadata.currency == "USD"
    assert metadata.is_listed is True
    assert metadata.instrument_type == "ETF"


@pytest.mark.asyncio
async def test_toss_stock_metadata_provider_marks_inactive_stock_unlisted(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://openapi.tossinvest.com/oauth2/token",
        json={"access_token": "token-123", "token_type": "Bearer", "expires_in": 3600},
    )
    httpx_mock.add_response(
        method="GET",
        url="https://openapi.tossinvest.com/api/v1/stocks?symbols=OLD",
        json={
            "result": [
                {
                    "symbol": "OLD",
                    "name": "Old Co",
                    "market": "NASDAQ",
                    "securityType": "STOCK",
                    "status": "DELISTED",
                    "currency": "USD",
                    "sharesOutstanding": "0",
                }
            ]
        },
    )
    provider = TossStockMetadataProvider(
        "toss-client",
        "toss-secret",
        auth_client=TossAuthClient("toss-client", "toss-secret"),
    )

    metadata = await provider.fetch_stock_metadata("old")

    assert metadata.is_listed is False


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


@pytest.mark.asyncio
async def test_toss_stock_metadata_provider_rejects_missing_symbol():
    provider = TossStockMetadataProvider("toss-client", "toss-secret")

    with pytest.raises(ValueError, match="종목 심볼을 입력해 주세요."):
        await provider.fetch_stock_metadata(" ")
