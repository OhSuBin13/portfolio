from datetime import date

from fastapi import HTTPException

from portfolio_app.api.validation import (
    normalize_account_seq,
    normalize_marker_key,
    normalize_optional_uppercase,
    normalize_required_symbol,
    validate_date_range,
)


def test_normalize_account_seq_trims_value():
    assert normalize_account_seq("  account-1  ") == "account-1"


def test_normalize_account_seq_rejects_blank_value():
    try:
        normalize_account_seq("   ")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "Toss 계좌 식별자를 입력해 주세요."
    else:
        raise AssertionError("Expected blank account_seq to be rejected")


def test_normalize_optional_uppercase_trims_and_uppercases_values():
    assert normalize_optional_uppercase(None) is None
    assert normalize_optional_uppercase("   ") is None
    assert normalize_optional_uppercase(" aapl ") == "AAPL"


def test_normalize_required_symbol_rejects_blank_symbols():
    assert normalize_required_symbol(" aapl ") == "AAPL"

    try:
        normalize_required_symbol("   ")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "Toss 캔들 조회 종목 심볼을 입력해 주세요."
    else:
        raise AssertionError("Expected blank symbol to be rejected")


def test_normalize_marker_key_rejects_blank_marker_key():
    assert normalize_marker_key(" marker-1 ") == "marker-1"

    try:
        normalize_marker_key("   ")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "차트 마커 식별자를 입력해 주세요."
    else:
        raise AssertionError("Expected blank marker key to be rejected")


def test_validate_date_range_rejects_inverted_range():
    validate_date_range(date(2026, 1, 1), date(2026, 1, 2))

    try:
        validate_date_range(date(2026, 1, 2), date(2026, 1, 1))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "조회 시작일은 종료일보다 늦을 수 없습니다."
    else:
        raise AssertionError("Expected inverted date range to be rejected")
