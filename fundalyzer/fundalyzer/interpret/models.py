# Architecture contract: LLM produces narrative text only.
# Every number in DashboardNarrative must originate from a pre-computed field
# passed into the prompt — the LLM must not invent figures.
from pydantic import BaseModel


class DashboardNarrative(BaseModel):
    headline: str
    body: str
    key_strengths: list[str]
    key_risks: list[str]


class Interpretation(BaseModel):
    valuation: DashboardNarrative
    growth: DashboardNarrative
    health: DashboardNarrative
    competitive: DashboardNarrative
    overall_summary: str
