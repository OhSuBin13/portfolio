import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from portfolio_app.models import (
    Currency,
    TossMarket,
)
from portfolio_app.services.market_data import (
    FxRateProvider,
    default_fx_rate_provider,
)
from portfolio_app.services.toss_http import Sleep, TossAuthClient, request_with_toss_retry
from portfolio_app.services.toss_payloads import (
    non_negative_number,
    optional_text,
    required_text,
)
from portfolio_app.services.toss_summary import TossSummaryResult, build_toss_summary


@dataclass(frozen=True)
class TossAccount:
    account_seq: str
    account_no: str
    account_type: str
    display_name: str


@dataclass(frozen=True)
class TossHolding:
    symbol: str
    name: str
    market: TossMarket
    currency: Currency
    quantity: float
    average_purchase_price: float
    last_price: float | None
    market_value: float


@dataclass(frozen=True)
class TossBuyingPower:
    currency: Currency
    cash_buying_power: float


@dataclass(frozen=True)
class TossOrderExecution:
    filled_quantity: str
    average_filled_price: str | None
    filled_amount: str | None
    commission: str | None
    tax: str | None
    filled_at: str | None
    settlement_date: str | None


@dataclass(frozen=True)
class TossOrder:
    order_id: str
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    status: str
    price: str | None
    quantity: str
    order_amount: str | None
    currency: str
    ordered_at: str
    canceled_at: str | None
    execution: TossOrderExecution
    raw: dict[str, Any]


@dataclass(frozen=True)
class TossOrderPage:
    orders: list[TossOrder]
    next_cursor: str | None
    has_next: bool


TOSS_ACCOUNTS_CACHE_TTL_SECONDS = 60.0


@dataclass
class _TossAccountsCacheEntry:
    fetched_at: float
    accounts: list[TossAccount]


class TossAccountsCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = TOSS_ACCOUNTS_CACHE_TTL_SECONDS,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._now = now
        self._entry: _TossAccountsCacheEntry | None = None
        self._refresh_lock = asyncio.Lock()

    def get(self) -> list[TossAccount] | None:
        entry = self._entry
        if entry is None:
            return None
        if self._now() - entry.fetched_at >= self.ttl_seconds:
            return None
        return list(entry.accounts)

    def set(self, accounts: list[TossAccount]) -> None:
        self._entry = _TossAccountsCacheEntry(
            fetched_at=self._now(),
            accounts=list(accounts),
        )

    async def get_or_fetch(
        self,
        fetch_accounts: Callable[[], Awaitable[list[TossAccount]]],
    ) -> list[TossAccount]:
        cached = self.get()
        if cached is not None:
            return cached

        async with self._refresh_lock:
            cached = self.get()
            if cached is not None:
                return cached

            accounts = await fetch_accounts()
            self.set(accounts)
            return list(accounts)


class TossSummaryProvider(Protocol):
    async def fetch_holdings(self, account_seq: str) -> list[TossHolding]:
        pass

    async def fetch_buying_power(
        self,
        account_seq: str,
        currency: Currency,
    ) -> TossBuyingPower:
        pass


class TossBrokerageProvider:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = "https://openapi.tossinvest.com",
        auth_client: TossAuthClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._auth_client = auth_client or TossAuthClient(
            client_id,
            client_secret,
            base_url=self.base_url,
            sleep=sleep,
        )

    async def _token(self) -> str:
        return await self._auth_client.token()

    async def fetch_accounts(self) -> list[TossAccount]:
        token = await self._token()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/accounts",
                headers={"Authorization": f"Bearer {token}"},
                sleep=self._sleep,
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, list):
            raise ValueError("Toss 응답에서 계좌 목록을 찾을 수 없습니다.")

        accounts: list[TossAccount] = []
        for item in result:
            if not isinstance(item, dict):
                raise ValueError("Toss 계좌 항목은 객체여야 합니다.")
            account_no = required_text(item.get("accountNo"), "Toss 계좌번호가 필요합니다.")
            account_seq = required_text(
                item.get("accountSeq"),
                "Toss 계좌 식별자가 필요합니다.",
            )
            account_type = required_text(
                item.get("accountType"),
                "Toss 계좌 유형이 필요합니다.",
            )
            accounts.append(
                TossAccount(
                    account_seq=account_seq,
                    account_no=account_no,
                    account_type=account_type,
                    display_name=f"토스증권 {account_no}",
                )
            )
        return accounts

    async def fetch_holdings(self, account_seq: str) -> list[TossHolding]:
        token = await self._token()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/holdings",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-tossinvest-account": account_seq,
                },
                sleep=self._sleep,
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("result") if isinstance(payload, dict) else None
        items = result.get("items") if isinstance(result, dict) else None
        if not isinstance(items, list):
            raise ValueError("Toss 응답에서 보유자산 목록을 찾을 수 없습니다.")

        holdings: list[TossHolding] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Toss 보유자산 항목은 객체여야 합니다.")
            holdings.append(_parse_holding(item))
        return holdings

    async def fetch_buying_power(
        self,
        account_seq: str,
        currency: Currency,
    ) -> TossBuyingPower:
        token = await self._token()
        requested_currency = currency.strip().upper()
        if requested_currency not in {"KRW", "USD"}:
            raise ValueError("Toss 매수 가능 금액 통화는 KRW 또는 USD여야 합니다.")

        async with httpx.AsyncClient(timeout=10) as client:
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/buying-power",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-tossinvest-account": account_seq,
                },
                params={"currency": requested_currency},
                sleep=self._sleep,
            )
            response.raise_for_status()
            payload = response.json()

        return _parse_buying_power(payload, requested_currency)

    async def fetch_orders(
        self,
        account_seq: str,
        *,
        status: str,
        symbol: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> TossOrderPage:
        token = await self._token()
        params: dict[str, object] = {"status": status, "limit": limit}
        if symbol:
            params["symbol"] = symbol
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if cursor:
            params["cursor"] = cursor

        async with httpx.AsyncClient(timeout=10) as client:
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-tossinvest-account": account_seq,
                },
                params=params,
                sleep=self._sleep,
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ValueError("Toss 응답에서 주문 목록을 찾을 수 없습니다.")
        orders = result.get("orders")
        if not isinstance(orders, list):
            raise ValueError("Toss 주문 목록은 배열이어야 합니다.")
        has_next = result.get("hasNext")
        if not isinstance(has_next, bool):
            raise ValueError("Toss 주문 목록 hasNext 값은 참/거짓이어야 합니다.")
        return TossOrderPage(
            orders=[_parse_order(item) for item in orders],
            next_cursor=optional_text(result.get("nextCursor")),
            has_next=has_next,
        )

    async def fetch_order(self, account_seq: str, order_id: str) -> TossOrder:
        token = await self._token()
        encoded_order_id = quote(order_id, safe="")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await request_with_toss_retry(
                client,
                "GET",
                f"{self.base_url}/api/v1/orders/{encoded_order_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-tossinvest-account": account_seq,
                },
                sleep=self._sleep,
            )
            response.raise_for_status()
            payload = response.json()

        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ValueError("Toss 응답에서 주문 상세를 찾을 수 없습니다.")
        return _parse_order(result)


async def fetch_toss_summary(
    account_seq: str,
    provider: TossSummaryProvider,
    fx_provider: FxRateProvider | None = None,
) -> TossSummaryResult:
    holdings = await provider.fetch_holdings(account_seq)
    buying_power = [
        await provider.fetch_buying_power(account_seq, "KRW"),
        await provider.fetch_buying_power(account_seq, "USD"),
    ]
    usd_krw_rate: float | None = None
    if any(
        holding.currency == "USD" and holding.market_value > 0 for holding in holdings
    ) or any(
        row.currency == "USD" and row.cash_buying_power > 0 for row in buying_power
    ):
        resolved_fx_provider = fx_provider or default_fx_rate_provider()
        usd_krw_rate = (
            await resolved_fx_provider.fetch_rate("USD", "KRW")
        ).rate
    return build_toss_summary(
        holdings,
        buying_power=buying_power,
        usd_krw_rate=usd_krw_rate,
    )


def _parse_order(item: dict[str, Any]) -> TossOrder:
    if not isinstance(item, dict):
        raise ValueError("Toss 주문 항목은 객체여야 합니다.")
    status = required_text(item.get("status"), "Toss 주문 상태가 필요합니다.")
    execution = _execution_payload_for_order(item.get("execution"), status)
    filled_quantity = optional_text(execution.get("filledQuantity"))
    if filled_quantity is None:
        if _allows_empty_execution(status):
            filled_quantity = "0"
        else:
            raise ValueError("Toss 체결 수량이 필요합니다.")
    return TossOrder(
        order_id=required_text(item.get("orderId"), "Toss 주문 식별자가 필요합니다."),
        symbol=required_text(item.get("symbol"), "Toss 주문 종목 심볼이 필요합니다.").upper(),
        side=required_text(item.get("side"), "Toss 주문 방향이 필요합니다."),
        order_type=required_text(item.get("orderType"), "Toss 주문 유형이 필요합니다."),
        time_in_force=required_text(item.get("timeInForce"), "Toss 주문 유효 조건이 필요합니다."),
        status=status,
        price=optional_text(item.get("price")),
        quantity=required_text(item.get("quantity"), "Toss 주문 수량이 필요합니다."),
        order_amount=optional_text(item.get("orderAmount")),
        currency=required_text(item.get("currency"), "Toss 주문 통화가 필요합니다."),
        ordered_at=required_text(item.get("orderedAt"), "Toss 주문 시간이 필요합니다."),
        canceled_at=optional_text(item.get("canceledAt")),
        execution=TossOrderExecution(
            filled_quantity=filled_quantity,
            average_filled_price=optional_text(execution.get("averageFilledPrice")),
            filled_amount=optional_text(execution.get("filledAmount")),
            commission=optional_text(execution.get("commission")),
            tax=optional_text(execution.get("tax")),
            filled_at=optional_text(execution.get("filledAt")),
            settlement_date=optional_text(execution.get("settlementDate")),
        ),
        raw=dict(item),
    )


def _execution_payload_for_order(value: Any, status: str) -> dict[str, Any]:
    if value is None and _allows_empty_execution(status):
        return {}
    if not isinstance(value, dict):
        raise ValueError("Toss 주문 체결 정보가 필요합니다.")
    return value


def _allows_empty_execution(status: str) -> bool:
    return status.strip().upper() in {"OPEN", "CANCELED", "CANCELLED", "REJECTED", "EXPIRED"}


def _parse_buying_power(payload: Any, requested_currency: str) -> TossBuyingPower:
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise ValueError("Toss 응답에서 매수 가능 금액을 찾을 수 없습니다.")

    currency = required_text(
        result.get("currency"),
        "Toss 매수 가능 금액 통화가 필요합니다.",
    ).upper()
    if currency not in {"KRW", "USD"}:
        raise ValueError("Toss 매수 가능 금액 통화는 KRW 또는 USD여야 합니다.")
    if currency != requested_currency:
        raise ValueError("Toss 매수 가능 금액 통화가 요청 통화와 일치하지 않습니다.")

    return TossBuyingPower(
        currency=currency,
        cash_buying_power=non_negative_number(
            result.get("cashBuyingPower"),
            "Toss 매수 가능 금액은 0 이상이어야 합니다.",
        ),
    )


def _parse_holding(item: dict[str, Any]) -> TossHolding:
    market, currency = _market_currency_pair(item)

    market_value = item.get("marketValue")
    if not isinstance(market_value, dict):
        raise ValueError("Toss 보유자산 평가금액이 필요합니다.")

    last_price = item.get("lastPrice")
    return TossHolding(
        symbol=required_text(item.get("symbol"), "Toss 보유자산 심볼이 필요합니다.").upper(),
        name=required_text(item.get("name"), "Toss 보유자산명이 필요합니다."),
        market=market,
        currency=currency,
        quantity=non_negative_number(item.get("quantity"), "Toss 보유수량은 0 이상이어야 합니다."),
        average_purchase_price=non_negative_number(
            item.get("averagePurchasePrice"),
            "Toss 평균매입가는 0 이상이어야 합니다.",
        ),
        last_price=(
            non_negative_number(last_price, "Toss 현재가는 0 이상이어야 합니다.")
            if last_price is not None
            else None
        ),
        market_value=non_negative_number(
            market_value.get("amount"),
            "Toss 평가금액은 0 이상이어야 합니다.",
        ),
    )


def _market_currency_pair(item: dict[str, Any]) -> tuple[TossMarket, Currency]:
    market = required_text(item.get("marketCountry"), "Toss 시장 국가가 필요합니다.").upper()
    currency = required_text(item.get("currency"), "Toss 보유자산 통화가 필요합니다.").upper()
    if (market, currency) == ("KR", "KRW"):
        return "KR", "KRW"
    if (market, currency) == ("US", "USD"):
        return "US", "USD"
    if market not in {"KR", "US"}:
        raise ValueError("Toss 보유자산 시장은 KR 또는 US여야 합니다.")
    if currency not in {"KRW", "USD"}:
        raise ValueError("Toss 보유자산 통화는 KRW 또는 USD여야 합니다.")
    raise ValueError("Toss 보유자산 시장과 통화 조합이 일치하지 않습니다.")
