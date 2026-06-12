from portfolio_app.finance import calculate_asset_mix, calculate_goal_progress, calculate_net_worth
from portfolio_app.models import Goal, HoldingValue


def test_net_worth_subtracts_debt_and_converts_to_krw():
    values = [
        HoldingValue(asset_type="cash", value_krw=1_000_000, monthly_income_krw=0),
        HoldingValue(asset_type="stock_etf", value_krw=2_500_000, monthly_income_krw=30_000),
        HoldingValue(asset_type="debt", value_krw=700_000, monthly_income_krw=0),
    ]

    summary = calculate_net_worth(values)

    assert summary.net_worth_krw == 2_800_000
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


def test_goal_progress_caps_percent_at_100():
    goal = Goal(id=1, name="순자산 1억", type="net_worth", target_amount_krw=100_000_000)

    progress = calculate_goal_progress(goal, current_amount_krw=120_000_000)

    assert progress.percent == 100.0
    assert progress.remaining_krw == 0
