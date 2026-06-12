import math
from collections import defaultdict

from portfolio_app.models import Goal, GoalProgress, HoldingValue, PortfolioSummary


def calculate_net_worth(values: list[HoldingValue]) -> PortfolioSummary:
    gross_assets = sum(item.value_krw for item in values if item.asset_type != "debt")
    debt = sum(item.value_krw for item in values if item.asset_type == "debt")
    monthly_income = sum(item.monthly_income_krw for item in values)
    return PortfolioSummary(
        net_worth_krw=gross_assets - debt,
        gross_assets_krw=gross_assets,
        debt_krw=debt,
        monthly_income_krw=monthly_income,
    )


def calculate_asset_mix(values: list[HoldingValue]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for item in values:
        if item.asset_type != "debt":
            totals[item.asset_type] += item.value_krw

    denominator = sum(totals.values())
    if denominator == 0:
        return {}

    return {
        asset_type: round((value / denominator) * 100, 2)
        for asset_type, value in totals.items()
    }


def calculate_goal_progress(goal: Goal, current_amount_krw: float) -> GoalProgress:
    if not math.isfinite(current_amount_krw):
        raise ValueError("current_amount_krw must be finite")

    current_amount = max(0.0, current_amount_krw)
    percent = min(100.0, round((current_amount / goal.target_amount_krw) * 100, 2))
    remaining = max(0.0, goal.target_amount_krw - current_amount)
    return GoalProgress(
        goal=goal,
        current_amount_krw=current_amount,
        percent=percent,
        remaining_krw=remaining,
    )
