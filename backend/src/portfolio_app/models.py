from pydantic import BaseModel, Field


class HoldingValue(BaseModel):
    asset_type: str
    value_krw: float
    monthly_income_krw: float = 0


class PortfolioSummary(BaseModel):
    net_worth_krw: float
    gross_assets_krw: float
    debt_krw: float
    monthly_income_krw: float


class Goal(BaseModel):
    id: int
    name: str
    type: str
    target_amount_krw: float = Field(gt=0)


class GoalProgress(BaseModel):
    goal: Goal
    current_amount_krw: float
    percent: float
    remaining_krw: float
