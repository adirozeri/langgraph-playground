from typing import TypedDict, Annotated
from operator import add


class ResearchResult(TypedDict):
    ticker: str
    headline: str
    sentiment: str  # "positive" | "negative" | "neutral"
    summary: str


class Holding(TypedDict):
    ticker: str
    shares: float
    avg_price: float


class TradeDecision(TypedDict):
    ticker: str
    action: str  # "buy" | "sell" | "hold"
    quantity: float
    reasoning: str


class AgentState(TypedDict):
    # Input
    tickers: list[str]
    date: str

    # Populated by Research node
    research: Annotated[list[ResearchResult], add]

    # Populated by Portfolio node
    holdings: list[Holding]
    cash: float

    # Populated by Analysis node
    analysis_summary: str

    # Populated by Decision node
    decisions: list[TradeDecision]

    # Populated by Memory node
    log_path: str
