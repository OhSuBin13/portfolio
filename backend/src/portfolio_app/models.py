from datetime import date
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

AssetType = Literal["cash", "savings", "stock_etf", "debt"]
Currency = Literal["USD", "KRW"]
TransactionType = Literal[
    "deposit",
    "withdrawal",
    "buy",
    "sell",
    "dividend",
    "interest",
    "fee",
    "debt_payment",
    "adjustment",
]
TRANSACTION_TYPES = frozenset(get_args(TransactionType))
GoalType = Literal["net_worth", "monthly_income"]
GOAL_TYPES = frozenset(get_args(GoalType))
SnapshotSource = Literal["scheduled", "manual", "market_sync", "import"]
GrowthPeriod = Literal["monthly", "annual"]


class HoldingValue(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    asset_type: AssetType
    value_krw: float = Field(ge=0, allow_inf_nan=False)


class PortfolioSummary(BaseModel):
    model_config = ConfigDict(strict=True)

    net_worth_krw: float = Field(allow_inf_nan=False)
    gross_assets_krw: float = Field(ge=0, allow_inf_nan=False)
    debt_krw: float = Field(ge=0, allow_inf_nan=False)
    monthly_income_krw: float = Field(ge=0, allow_inf_nan=False)
    usd_krw_rate: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    usd_krw_change_percent: float | None = Field(default=None, allow_inf_nan=False)


class PortfolioSnapshot(BaseModel):
    model_config = ConfigDict(strict=True)

    id: int
    snapshot_date: date
    net_worth_krw: float = Field(allow_inf_nan=False)
    gross_assets_krw: float = Field(ge=0, allow_inf_nan=False)
    debt_krw: float = Field(ge=0, allow_inf_nan=False)
    monthly_income_krw: float = Field(ge=0, allow_inf_nan=False)
    asset_mix: dict[str, float]
    source: SnapshotSource
    created_at: str
    updated_at: str


class GrowthHistoryRow(BaseModel):
    model_config = ConfigDict(strict=True)

    period: str
    start_date: date
    end_date: date
    starting_net_worth_krw: float = Field(allow_inf_nan=False)
    ending_net_worth_krw: float = Field(allow_inf_nan=False)
    external_cash_flow_krw: float = Field(allow_inf_nan=False)
    dividend_interest_krw: float = Field(ge=0, allow_inf_nan=False)
    profit_krw: float = Field(allow_inf_nan=False)
    growth_rate: float | None = Field(default=None, allow_inf_nan=False)
    cumulative_profit_krw: float = Field(allow_inf_nan=False)
    cumulative_growth_rate: float | None = Field(default=None, allow_inf_nan=False)


class AssetAllocation(BaseModel):
    model_config = ConfigDict(strict=True)

    asset_id: int
    asset_type: AssetType
    symbol: str | None
    name: str
    label: str
    value_krw: float = Field(ge=0, allow_inf_nan=False)
    percent: float = Field(ge=0, le=100, allow_inf_nan=False)


class TransactionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    occurred_on: date
    type: TransactionType
    account_id: int | None
    asset_id: int | None
    quantity: float | None
    amount: float = Field(allow_inf_nan=False)
    currency: Currency
    fx_rate_to_krw: float | None = Field(default=None, allow_inf_nan=False)
    memo: str
    created_at: str


class Goal(BaseModel):
    model_config = ConfigDict(strict=True)

    id: int
    name: str
    type: GoalType
    target_amount_krw: float = Field(gt=0, allow_inf_nan=False)


class GoalProgress(BaseModel):
    model_config = ConfigDict(strict=True)

    goal: Goal
    current_amount_krw: float = Field(ge=0, allow_inf_nan=False)
    percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    remaining_krw: float = Field(ge=0, allow_inf_nan=False)


class SummaryResponse(PortfolioSummary):
    asset_mix: dict[str, float]
    asset_allocations: list[AssetAllocation]
    goal_progress: list[GoalProgress]
