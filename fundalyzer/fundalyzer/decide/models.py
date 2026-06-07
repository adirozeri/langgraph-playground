# Architecture contract: scores computed in Python from API data; rationale is LLM narrative only.
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel


class InvestmentLean(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class ScoreCard(BaseModel):
    """All scores are Python-computed on a 0–10 scale; no LLM-generated values."""

    valuation_score: Decimal
    growth_score: Decimal
    health_score: Decimal
    competitive_score: Decimal
    composite_score: Decimal


class InvestmentDecision(BaseModel):
    ticker: str
    lean: InvestmentLean
    scorecard: ScoreCard
    rationale: str  # LLM narrative referencing scorecard values — no invented numbers
    caveats: list[str]
