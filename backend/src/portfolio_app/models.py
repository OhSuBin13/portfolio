from datetime import date
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

AssetType = Literal["cash", "savings", "stock_etf", "debt"]
Currency = Literal["USD", "KRW"]
TossMarket = Literal["KR", "US"]
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
BackupReason = Literal["startup", "automatic", "manual"]
BACKUP_REASONS = frozenset(get_args(BackupReason))
PriceSnapshotStatus = Literal["ok", "stale", "failed", "manual"]
OrderHistoryStatus = Literal["OPEN", "CLOSED"]


class HoldingValue(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    asset_type: AssetType
    value_krw: float = Field(ge=0, allow_inf_nan=False)


class BuyingPower(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    currency: Currency
    cash_buying_power: float = Field(ge=0, allow_inf_nan=False)
    value_krw: float = Field(ge=0, allow_inf_nan=False)


class PortfolioSummary(BaseModel):
    model_config = ConfigDict(strict=True)

    net_worth_krw: float = Field(allow_inf_nan=False)
    gross_assets_krw: float = Field(ge=0, allow_inf_nan=False)
    debt_krw: float = Field(ge=0, allow_inf_nan=False)
    monthly_income_krw: float = Field(ge=0, allow_inf_nan=False)
    buying_power: list[BuyingPower] = Field(default_factory=list)
    buying_power_total_krw: float = Field(default=0, ge=0, allow_inf_nan=False)
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


class TossAssetAllocation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    asset_key: str
    asset_type: Literal["stock_etf"]
    symbol: str
    name: str
    label: str
    market: TossMarket
    currency: Currency
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
    asset_allocations: list[TossAssetAllocation]
    goal_progress: list[GoalProgress]


class BackupRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    path: str
    reason: BackupReason
    created_at: str


class MarketDataStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: int
    source: str
    price_krw: float = Field(allow_inf_nan=False)
    status: PriceSnapshotStatus
    error_message: str
    fetched_at: str


class TossOrderImportCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    account_seq: str = Field(min_length=1)
    status: OrderHistoryStatus = "OPEN"
    symbol: str | None = None
    from_date: date | None = None
    to_date: date | None = None

    @field_validator("from_date", "to_date", mode="before")
    @classmethod
    def _parse_iso_date(cls, value: object) -> object:
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value


class TossOrderImportRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    account_seq: str
    status_filter: OrderHistoryStatus
    symbol_filter: str | None
    from_date: str | None
    to_date: str | None
    run_status: str
    imported_count: int
    error_message: str
    started_at: str
    completed_at: str | None


class TossOrderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    account_seq: str
    order_id: str
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    order_status: str
    price: str | None
    quantity: str
    order_amount: str | None
    currency: str
    ordered_at: str
    canceled_at: str | None
    filled_quantity: str
    average_filled_price: str | None
    filled_amount: str | None
    commission: str | None
    tax: str | None
    filled_at: str | None
    settlement_date: str | None
    imported_at: str
    updated_at: str
