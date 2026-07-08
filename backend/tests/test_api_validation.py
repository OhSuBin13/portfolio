from fastapi import HTTPException

from portfolio_app.api.validation import normalize_account_seq


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
