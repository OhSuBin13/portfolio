from typing import Literal

from pydantic import BaseModel, Field

AssetType = Literal["cash", "savings", "stock_etf", "crypto", "debt"]
GoalType = Literal["net_worth", "monthly_income"]


class HoldingValue(BaseModel):
    asset_type: AssetType
    value_krw: float = Field(ge=0)
    monthly_income_krw: float = Field(default=0, ge=0)


class PortfolioSummary(BaseModel):
    net_worth_krw: float
    gross_assets_krw: float
    debt_krw: float
    monthly_income_krw: float


class Goal(BaseModel):
    id: int
    name: str
    type: GoalType
    target_amount_krw: float = Field(gt=0)


class GoalProgress(BaseModel):
    goal: Goal
    current_amount_krw: float = Field(ge=0)
    percent: float = Field(ge=0, le=100)
    remaining_krw: float = Field(ge=0)
