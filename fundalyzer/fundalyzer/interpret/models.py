# Architecture contract: LLM produces narrative text only.
# Every number that appears in output must originate from a pre-computed field
# passed into the prompt — the LLM must not invent figures.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# Allowed directional verdicts.  "GOOD" / "BAD" / "BULLISH" are prohibited.
TrendVerdict = Literal["IMPROVING", "DETERIORATING", "STABLE", "MIXED"]


class Claim(BaseModel):
    """A single factual assertion with an explicit citation trail.

    data_points lists every specific value the statement relies on, formatted
    as "metric_name=value" strings (e.g. "gross_margin_2024=46.2%").
    This lets callers verify the LLM did not drift from the provided numbers.
    """

    statement: str
    data_points: list[str]


class DashboardNarrative(BaseModel):
    """Narrative for one dashboard, fully traceable to provided data.

    headline    — one sentence that includes at least one specific value.
    body        — 2-3 sentences of directional analysis.
    claims      — every assertion the narrative makes, each citing the exact values used.
    trend_verdict — one of IMPROVING / DETERIORATING / STABLE / MIXED.
    """

    headline: str
    body: str
    claims: list[Claim]
    trend_verdict: TrendVerdict


class Interpretation(BaseModel):
    """Structured narrative over all four dashboards."""

    income: DashboardNarrative
    momentum: DashboardNarrative
    valuation: DashboardNarrative
    capital: DashboardNarrative
    overall_summary: str  # 2-3 sentences synthesising all four verdicts — no invented numbers
