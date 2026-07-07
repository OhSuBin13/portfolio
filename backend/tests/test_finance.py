import pytest
from pydantic import ValidationError

from portfolio_app.finance import calculate_goal_progress
from portfolio_app.models import GOAL_TYPES, Goal


def test_goal_progress_caps_percent_at_100():
    goal = Goal(id=1, name="순자산 1억", type="net_worth", target_amount_krw=100_000_000)

    progress = calculate_goal_progress(goal, current_amount_krw=120_000_000)

    assert progress.percent == 100.0
    assert progress.remaining_krw == 0


def test_goal_rejects_unknown_type():
    with pytest.raises(ValidationError):
        Goal(id=1, name="부자 되기", type="wealth", target_amount_krw=100_000_000)


def test_goal_types_constant_matches_goal_model_literal():
    assert frozenset({"net_worth", "monthly_income"}) == GOAL_TYPES


def test_goal_rejects_numeric_string_id():
    with pytest.raises(ValidationError):
        Goal(id="1", name="bad", type="net_worth", target_amount_krw=100)


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


@pytest.mark.parametrize("current_amount_krw", [float("nan"), float("inf"), float("-inf")])
def test_goal_progress_rejects_non_finite_current_amount(current_amount_krw):
    goal = Goal(id=1, name="순자산 1억", type="net_worth", target_amount_krw=100_000_000)

    with pytest.raises(ValueError, match="current_amount_krw must be finite"):
        calculate_goal_progress(goal, current_amount_krw=current_amount_krw)
