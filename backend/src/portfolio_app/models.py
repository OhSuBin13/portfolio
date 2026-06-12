from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AssetType = Literal["cash", "savings", "stock_etf", "crypto", "debt"]
GoalType = Literal["net_worth", "monthly_income"]


class HoldingValue(BaseModel):
    model_config = ConfigDict(strict=True)

    asset_type: AssetType
    value_krw: float = Field(ge=0, allow_inf_nan=False)
    monthly_income_krw: float = Field(default=0, ge=0, allow_inf_nan=False)


class PortfolioSummary(BaseModel):
    model_config = ConfigDict(strict=True)

    net_worth_krw: float = Field(allow_inf_nan=False)
    gross_assets_krw: float = Field(ge=0, allow_inf_nan=False)
    debt_krw: float = Field(ge=0, allow_inf_nan=False)
    monthly_income_krw: float = Field(ge=0, allow_inf_nan=False)


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
