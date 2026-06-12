import pytest
from pydantic import ValidationError

from portfolio_app.finance import calculate_asset_mix, calculate_goal_progress, calculate_net_worth
from portfolio_app.models import Goal, HoldingValue


def test_net_worth_subtracts_debt_from_krw_values():
    values = [
        HoldingValue(asset_type="cash", value_krw=1_000_000, monthly_income_krw=0),
        HoldingValue(asset_type="stock_etf", value_krw=2_500_000, monthly_income_krw=30_000),
        HoldingValue(asset_type="debt", value_krw=700_000, monthly_income_krw=0),
    ]

    summary = calculate_net_worth(values)

    assert summary.net_worth_krw == 2_800_000
    assert summary.gross_assets_krw == 3_500_000
    assert summary.debt_krw == 700_000
    assert summary.monthly_income_krw == 30_000


def test_asset_mix_excludes_debt_from_positive_allocation():
    values = [
        HoldingValue(asset_type="cash", value_krw=1_000_000, monthly_income_krw=0),
        HoldingValue(asset_type="stock_etf", value_krw=3_000_000, monthly_income_krw=0),
        HoldingValue(asset_type="debt", value_krw=500_000, monthly_income_krw=0),
    ]

    mix = calculate_asset_mix(values)

    assert mix["cash"] == 25.0
    assert mix["stock_etf"] == 75.0
    assert "debt" not in mix


def test_asset_mix_returns_empty_for_no_values():
    assert calculate_asset_mix([]) == {}


def test_asset_mix_returns_empty_for_debt_only_values():
    values = [
        HoldingValue(asset_type="debt", value_krw=500_000, monthly_income_krw=0),
    ]

    assert calculate_asset_mix(values) == {}


def test_asset_mix_groups_duplicate_positive_asset_types():
    values = [
        HoldingValue(asset_type="cash", value_krw=1_000_000, monthly_income_krw=0),
        HoldingValue(asset_type="cash", value_krw=2_000_000, monthly_income_krw=0),
        HoldingValue(asset_type="stock_etf", value_krw=1_000_000, monthly_income_krw=0),
    ]

    mix = calculate_asset_mix(values)

    assert mix == {"cash": 75.0, "stock_etf": 25.0}


def test_goal_progress_caps_percent_at_100():
    goal = Goal(id=1, name="순자산 1억", type="net_worth", target_amount_krw=100_000_000)

    progress = calculate_goal_progress(goal, current_amount_krw=120_000_000)

    assert progress.percent == 100.0
    assert progress.remaining_krw == 0


def test_holding_value_rejects_unknown_asset_type():
    with pytest.raises(ValidationError):
        HoldingValue(asset_type="debt ", value_krw=1, monthly_income_krw=0)


def test_goal_rejects_unknown_type():
    with pytest.raises(ValidationError):
        Goal(id=1, name="부자 되기", type="wealth", target_amount_krw=100_000_000)


def test_holding_value_rejects_negative_value():
    with pytest.raises(ValidationError):
        HoldingValue(asset_type="cash", value_krw=-1, monthly_income_krw=0)


def test_holding_value_rejects_infinite_value():
    with pytest.raises(ValidationError):
        HoldingValue(asset_type="cash", value_krw=float("inf"))


def test_holding_value_rejects_nan_value():
    with pytest.raises(ValidationError):
        HoldingValue(asset_type="cash", value_krw=float("nan"))


def test_holding_value_rejects_negative_monthly_income():
    with pytest.raises(ValidationError):
        HoldingValue(asset_type="cash", value_krw=1, monthly_income_krw=-1)


def test_goal_rejects_zero_target_amount():
    with pytest.raises(ValidationError):
        Goal(id=1, name="bad", type="net_worth", target_amount_krw=0)


def test_goal_rejects_infinite_target_amount():
    with pytest.raises(ValidationError):
        Goal(id=1, name="bad", type="net_worth", target_amount_krw=float("inf"))


def test_goal_progress_clamps_negative_current_amount():
    goal = Goal(id=1, name="순자산 1억", type="net_worth", target_amount_krw=100_000_000)

    progress = calculate_goal_progress(goal, current_amount_krw=-1)

    assert progress.current_amount_krw == 0
    assert progress.percent == 0
    assert progress.remaining_krw == 100_000_000
