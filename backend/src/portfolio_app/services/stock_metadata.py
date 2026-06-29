from dataclasses import dataclass
from typing import Any

import httpx

from portfolio_app.services.market_data import TossAuthClient

TOSS_STOCKS_URL = "https://openapi.tossinvest.com/api/v1/stocks"

TOSS_MARKET_TO_LOCAL_MARKET = {
    "KOSPI": "KR",
    "KOSDAQ": "KR",
    "KR_ETC": "KR",
    "NYSE": "US",
    "NASDAQ": "US",
    "AMEX": "US",
    "US_ETC": "US",
}


@dataclass
class StockMetadata:
    symbol: str
    name: str
    market: str
    currency: str
    is_listed: bool
    instrument_type: str | None
    metadata_source: str = "toss"


class TossStockMetadataProvider:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        auth_client: TossAuthClient | None = None,
    ) -> None:
        self._auth_client = auth_client or TossAuthClient(client_id, client_secret)

    async def fetch_stock_metadata(self, symbol: str) -> StockMetadata:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("종목 심볼을 입력해 주세요.")

        token = await self._auth_client.token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                TOSS_STOCKS_URL,
                params={"symbols": normalized_symbol},
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload = response.json()

        stock_info = _find_stock_info(payload, normalized_symbol)
        if stock_info is None:
            raise ValueError("Toss 응답에서 요청 종목의 정보를 찾을 수 없습니다.")
        return _stock_metadata_from_toss(stock_info)


def safe_stock_metadata_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        reason = response.reason_phrase or "Unknown"
        return f"종목 메타데이터 제공자 요청 실패: HTTP {response.status_code} {reason}"
    return f"종목 메타데이터 제공자 요청 실패: {exc.__class__.__name__}"


def _find_stock_info(payload: Any, symbol: str) -> dict[str, Any] | None:
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, list):
        return None

    for item in result:
        if not isinstance(item, dict):
            continue
        response_symbol = str(item.get("symbol", "")).strip().upper()
        if response_symbol == symbol:
            return item
    return None


def _stock_metadata_from_toss(stock_info: dict[str, Any]) -> StockMetadata:
    toss_market = str(stock_info.get("market", "")).strip().upper()
    market = TOSS_MARKET_TO_LOCAL_MARKET.get(toss_market)
    if market is None:
        raise ValueError("Toss 응답 시장은 지원하지 않는 값입니다.")

    currency = str(stock_info.get("currency", "")).strip().upper()
    if currency not in {"KRW", "USD"}:
        raise ValueError("Toss 응답 통화는 KRW 또는 USD여야 합니다.")

    instrument_type = str(stock_info.get("securityType", "")).strip().upper() or None

    return StockMetadata(
        symbol=str(stock_info.get("symbol", "")).strip().upper(),
        name=str(stock_info.get("name", "")).strip(),
        market=market,
        currency=currency,
        is_listed=str(stock_info.get("status", "")).strip().upper() == "ACTIVE",
        instrument_type=instrument_type,
    )
