import math

import pytest

from portfolio_app.services.toss_payloads import (
    non_negative_number,
    optional_text,
    positive_number,
    required_text,
)


def test_optional_text_trims_blank_values_to_none():
    assert optional_text(None) is None
    assert optional_text("   ") is None
    assert optional_text(" abc ") == "abc"


def test_required_text_rejects_blank_values():
    assert required_text(" abc ", "값이 필요합니다.") == "abc"

    with pytest.raises(ValueError, match="값이 필요합니다."):
        required_text("", "값이 필요합니다.")


def test_positive_number_rejects_non_positive_or_non_finite_values():
    assert positive_number("1.5", "양수가 필요합니다.") == 1.5

    for value in [0, -1, math.inf, "not-a-number", None]:
        with pytest.raises(ValueError, match="양수가 필요합니다."):
            positive_number(value, "양수가 필요합니다.")


def test_non_negative_number_accepts_zero_and_rejects_negative_values():
    assert non_negative_number("0", "0 이상이어야 합니다.") == 0
    assert non_negative_number(3, "0 이상이어야 합니다.") == 3

    with pytest.raises(ValueError, match="0 이상이어야 합니다."):
        non_negative_number(-0.1, "0 이상이어야 합니다.")
