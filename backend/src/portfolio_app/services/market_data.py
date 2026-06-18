import logging
import math
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Protocol

import httpx

NAVER_USD_KRW_URL = (
    "https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW"
)
NUMBER_PATTERN = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?")
ALPHA_VANTAGE_MESSAGE_KEYS = ("Note", "Information", "Error Message")
logger = logging.getLogger(__name__)


@dataclass
class MarketQuote:
    symbol: str
    price: float
    currency: str
    source: str
    status: str = "ok"
    error_message: str = ""


@dataclass
class FxRate:
    base_currency: str
    quote_currency: str
    rate: float
    source: str
    change_percent: float | None = None


class FxRateProvider(Protocol):
    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        pass


def _positive_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(message)
    return number


def _finite_number(value: Any, message: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(message) from exc
    if not math.isfinite(number):
        raise ValueError(message)
    return number


def _number_from_text(text: str, message: str) -> float:
    compact_text = "".join(text.replace("\xa0", " ").split())
    match = NUMBER_PATTERN.search(compact_text)
    if match is None:
        raise ValueError(message)
    return _finite_number(match.group(0).replace(",", ""), message)


def _alpha_vantage_payload_summary(payload: Any) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {"payload_type": type(payload).__name__}

    summary: dict[str, object] = {"keys": sorted(str(key) for key in payload)}
    messages = {
        key: str(payload[key])
        for key in ALPHA_VANTAGE_MESSAGE_KEYS
        if isinstance(payload.get(key), str | int | float | bool)
    }
    if messages:
        summary["messages"] = messages
    return summary


class _NaverExchangeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.today_text_parts: list[str] = []
        self.exday_text_parts: list[str] = []
        self.exday_em_groups: list[tuple[set[str], str]] = []
        self._section: str | None = None
        self._em_depth = 0
        self._active_em_classes: set[str] = set()
        self._active_em_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        classes = set((attr_map.get("class") or "").split())

        if tag == "p":
            if "no_today" in classes:
                self._section = "today"
            elif "no_exday" in classes:
                self._section = "exday"

        if (
            self._section == "exday"
            and tag == "em"
            and classes.intersection({"no_up", "no_down", "no_change"})
        ):
            if self._em_depth == 0:
                self._active_em_classes = classes
                self._active_em_text_parts = []
            self._em_depth += 1

    def handle_data(self, data: str) -> None:
        if self._section == "today":
            self.today_text_parts.append(data)
            return

        if self._section == "exday":
            self.exday_text_parts.append(data)
            if self._em_depth > 0:
                self._active_em_text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._section == "exday" and tag == "em" and self._em_depth > 0:
            self._em_depth -= 1
            if self._em_depth == 0:
                self.exday_em_groups.append(
                    (set(self._active_em_classes), "".join(self._active_em_text_parts))
                )
                self._active_em_classes = set()
                self._active_em_text_parts = []

        if tag == "p" and self._section in {"today", "exday"}:
            self._section = None
            self._em_depth = 0
            self._active_em_classes = set()
            self._active_em_text_parts = []


def _parse_naver_change_percent(parser: _NaverExchangeParser) -> float | None:
    for classes, text in parser.exday_em_groups:
        if "%" not in text:
            continue

        value = _number_from_text(
            text,
            "Naver Finance 응답에서 전일대비 변경율을 찾을 수 없습니다.",
        )
        compact_text = "".join(text.split())
        if "-" in compact_text:
            return -abs(value)
        if "+" in compact_text:
            return abs(value)
        if "no_down" in classes:
            return -abs(value)
        return abs(value)

    if "%" not in "".join(parser.exday_text_parts):
        return None

    return _number_from_text(
        "".join(parser.exday_text_parts),
        "Naver Finance 응답에서 전일대비 변경율을 찾을 수 없습니다.",
    )


def keep_last_good_quote(*, previous: MarketQuote, error_message: str) -> MarketQuote:
    return MarketQuote(
        symbol=previous.symbol,
        price=previous.price,
        currency=previous.currency,
        source=previous.source,
        status="stale",
        error_message=error_message,
    )


class FrankfurterProvider:
    source = "frankfurter"

    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        base = base_currency.strip().upper()
        quote = quote_currency.strip().upper()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"https://api.frankfurter.dev/v2/rate/{base}/{quote}")
            response.raise_for_status()
            payload = response.json()

        try:
            rate = payload["rate"]
        except (KeyError, TypeError) as exc:
            raise ValueError("Frankfurter 응답에서 환율을 찾을 수 없습니다.") from exc

        return FxRate(
            base_currency=base,
            quote_currency=quote,
            rate=_positive_number(rate, "Frankfurter 환율은 0보다 큰 숫자여야 합니다."),
            source=self.source,
        )


class NaverFinanceProvider:
    source = "naver_finance"

    def __init__(self, url: str = NAVER_USD_KRW_URL) -> None:
        self.url = url

    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        base = base_currency.strip().upper()
        quote = quote_currency.strip().upper()
        if (base, quote) != ("USD", "KRW"):
            raise ValueError("Naver Finance는 USD/KRW 환율만 지원합니다.")

        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            response = await client.get(self.url)
            response.raise_for_status()

        parser = _NaverExchangeParser()
        parser.feed(response.text)

        rate = _number_from_text(
            "".join(parser.today_text_parts),
            "Naver Finance 응답에서 USD/KRW 환율을 찾을 수 없습니다.",
        )
        return FxRate(
            base_currency=base,
            quote_currency=quote,
            rate=_positive_number(rate, "Naver Finance 환율은 0보다 큰 숫자여야 합니다."),
            source=self.source,
            change_percent=_parse_naver_change_percent(parser),
        )


class FallbackFxRateProvider:
    def __init__(self, *providers: FxRateProvider) -> None:
        self.providers = providers

    async def fetch_rate(self, base_currency: str, quote_currency: str = "KRW") -> FxRate:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return await provider.fetch_rate(base_currency, quote_currency)
            except Exception as exc:
                errors.append(str(exc))

        raise ValueError(f"환율 제공자 요청이 모두 실패했습니다: {'; '.join(errors)}")


def default_fx_rate_provider() -> FxRateProvider:
    return FallbackFxRateProvider(NaverFinanceProvider(), FrankfurterProvider())


class AlphaVantageProvider:
    source = "alpha_vantage"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key.strip()

    async def fetch_equity_quote(self, symbol: str) -> MarketQuote:
        normalized_symbol = symbol.strip().upper()
        if not self.api_key:
            raise ValueError("Alpha Vantage API 키가 필요합니다.")

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": normalized_symbol,
                    "apikey": self.api_key,
                },
            )
            response.raise_for_status()
            payload = response.json()

        payload_summary = _alpha_vantage_payload_summary(payload)
        quote = payload.get("Global Quote") if isinstance(payload, dict) else None
        if not isinstance(quote, dict):
            logger.warning(
                "Alpha Vantage quote response missing Global Quote: symbol=%s payload_summary=%s",
                normalized_symbol,
                payload_summary,
                extra={
                    "symbol": normalized_symbol,
                    "payload_summary": payload_summary,
                },
            )
            raise ValueError("Alpha Vantage 응답에서 시세 정보를 찾을 수 없습니다.")

        price = quote.get("05. price")
        if price is None:
            quote_summary = _alpha_vantage_payload_summary(quote)
            logger.warning(
                "Alpha Vantage quote response missing price: symbol=%s payload_summary=%s",
                normalized_symbol,
                quote_summary,
                extra={
                    "symbol": normalized_symbol,
                    "payload_summary": quote_summary,
                },
            )
            raise ValueError("Alpha Vantage 응답에서 가격을 찾을 수 없습니다.")

        return MarketQuote(
            symbol=normalized_symbol,
            price=_positive_number(price, "Alpha Vantage 가격은 0보다 큰 숫자여야 합니다."),
            currency="USD",
            source=self.source,
        )
