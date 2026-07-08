from datetime import date

from fastapi import HTTPException, status

ACCOUNT_SEQ_REQUIRED_MESSAGE = "Toss 계좌 식별자를 입력해 주세요."
CANDLE_SYMBOL_REQUIRED_MESSAGE = "Toss 캔들 조회 종목 심볼을 입력해 주세요."
CHART_MARKER_REQUIRED_MESSAGE = "차트 마커 식별자를 입력해 주세요."
DATE_RANGE_MESSAGE = "조회 시작일은 종료일보다 늦을 수 없습니다."


def normalize_account_seq(account_seq: str) -> str:
    normalized = account_seq.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ACCOUNT_SEQ_REQUIRED_MESSAGE,
        )
    return normalized


def normalize_optional_uppercase(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def normalize_required_symbol(symbol: str) -> str:
    normalized = normalize_optional_uppercase(symbol)
    if normalized is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=CANDLE_SYMBOL_REQUIRED_MESSAGE,
        )
    return normalized


def normalize_marker_key(marker_key: str) -> str:
    normalized = marker_key.strip()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=CHART_MARKER_REQUIRED_MESSAGE,
        )
    return normalized


def validate_date_range(from_date: date | None, to_date: date | None) -> None:
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=DATE_RANGE_MESSAGE,
        )
