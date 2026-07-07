import math

from portfolio_app.models import Goal, GoalProgress


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
