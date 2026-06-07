# Architecture contract: peer aggregates are computed from API data — no LLM-generated figures.
from decimal import Decimal
from pydantic import BaseModel
from ..metrics.models import TickerKPIs


class PeerMetrics(BaseModel):
    ticker: str
    kpis: TickerKPIs


class SectorMedian(BaseModel):
    """Sector-level median values for key KPIs, derived from peer data."""

    pe_ratio: Decimal | None = None
    ev_to_ebitda: Decimal | None = None
    gross_margin: Decimal | None = None
    net_margin: Decimal | None = None
    roe: Decimal | None = None
    revenue_yoy: Decimal | None = None
    debt_to_equity: Decimal | None = None


class PeerSet(BaseModel):
    subject: str
    peers: list[PeerMetrics]
    sector_median: SectorMedian
