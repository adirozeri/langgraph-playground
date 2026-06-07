"""Peers module tests.

Stats functions (median, percentile_rank, relative_position) are tested
exhaustively with small synthetic data sets so expected values can be verified
by hand.

build_comparisons is tested with synthetic TickerKPIs built from fixture data
so the wiring from extraction through aggregation is covered without live calls.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from fundalyzer.data.cache import NullCache
from fundalyzer.data.fmp import FMPProvider
from fundalyzer.data.models import UNAVAILABLE
from fundalyzer.metrics.compute import compute
from fundalyzer.metrics.models import (
    CashFlowKPIs,
    FinancialStrengthKPIs,
    MetricPoint,
    MetricSeries,
    ProfitabilityKPIs,
    TickerKPIs,
    ValuationKPIs,
)
from fundalyzer.peers._aggregator import build_comparisons
from fundalyzer.peers._extract import KPI_CATALOG, extract_kpi_values
from fundalyzer.peers._selector import derive_peers
from fundalyzer.peers._stats import (
    DEFAULT_IN_LINE_BAND,
    median,
    percentile_rank,
    relative_position,
)
from fundalyzer.peers.models import KPIComparison, PeerMetrics, RelativePosition, SectorMedian

# ── Fixture helpers ───────────────────────────────────────────────────────────

FIXTURES = Path(__file__).parent / "fixtures" / "fmp"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def _make_fmp() -> FMPProvider:
    responses = {
        "profile":                  _load("aapl_profile.json"),
        "income_annual_10":         _load("aapl_income_annual.json"),
        "income_quarter_12":        _load("aapl_income_quarter.json"),
        "balance_annual_10":        _load("aapl_balance_annual.json"),
        "balance_quarter_12":       _load("aapl_balance_quarter.json"),
        "cashflow_annual_10":       _load("aapl_cashflow_annual.json"),
        "cashflow_quarter_12":      _load("aapl_cashflow_quarter.json"),
        "shares_outstanding":       _load("aapl_shares_outstanding.json"),
        "analyst_estimates":        _load("aapl_analyst_estimates.json"),
        "price_target_consensus":   _load("aapl_price_target_consensus.json"),
        "earnings_surprises":       _load("aapl_earnings_surprises.json"),
        "insider_trading":          _load("aapl_insider_trading.json"),
    }
    provider = FMPProvider(api_key="test", cache=NullCache())
    def fake_get(path, ticker, cache_key, **params):
        return responses.get(cache_key)
    provider._get = fake_get  # type: ignore[method-assign]
    return provider


# ── Synthetic TickerKPIs builder ──────────────────────────────────────────────

def _pt(value: Any) -> MetricPoint:
    v = Decimal(str(value)) if value != UNAVAILABLE else UNAVAILABLE
    return MetricPoint(
        value=v,
        period="annual",
        period_date=date(2024, 9, 30),
        formula="synthetic",
        inputs={},
    )


def _s(*vals: Any) -> MetricSeries:
    return [_pt(v) for v in vals]


def _profitability(
    gross_margin=UNAVAILABLE,
    operating_margin=UNAVAILABLE,
    net_margin=UNAVAILABLE,
    ebitda_margin=UNAVAILABLE,
    revenue_growth_yoy=UNAVAILABLE,
    eps_growth_yoy=UNAVAILABLE,
) -> ProfitabilityKPIs:
    return ProfitabilityKPIs(
        revenue=_s(UNAVAILABLE),
        revenue_growth_yoy=_s(revenue_growth_yoy),
        gross_margin=_s(gross_margin),
        operating_margin=_s(operating_margin),
        net_margin=_s(net_margin),
        ebitda_margin=_s(ebitda_margin),
        eps_diluted=_s(UNAVAILABLE),
        eps_growth_yoy=_s(eps_growth_yoy),
    )


def _valuation(
    trailing_pe=UNAVAILABLE,
    forward_pe=UNAVAILABLE,
    price_to_sales=UNAVAILABLE,
    ev_to_ebitda=UNAVAILABLE,
    price_to_book=UNAVAILABLE,
) -> ValuationKPIs:
    return ValuationKPIs(
        trailing_pe=_s(trailing_pe),
        forward_pe=_s(forward_pe),
        price_to_sales=_s(price_to_sales),
        ev_to_ebitda=_s(ev_to_ebitda),
        peg=_s(UNAVAILABLE),
        price_to_book=_s(price_to_book),
    )


def _cashflow(
    fcf_margin=UNAVAILABLE,
    fcf_yield=UNAVAILABLE,
) -> CashFlowKPIs:
    return CashFlowKPIs(
        operating_cash_flow=_s(UNAVAILABLE),
        free_cash_flow=_s(UNAVAILABLE),
        fcf_margin=_s(fcf_margin),
        fcf_yield=_s(fcf_yield),
    )


def _strength(
    debt_to_equity=UNAVAILABLE,
    current_ratio=UNAVAILABLE,
    roe=UNAVAILABLE,
    roic=UNAVAILABLE,
) -> FinancialStrengthKPIs:
    return FinancialStrengthKPIs(
        debt_to_equity=_s(debt_to_equity),
        net_cash_position=_s(UNAVAILABLE),
        current_ratio=_s(current_ratio),
        roe=_s(roe),
        roic=_s(roic),
    )


def _ticker_kpis(
    ticker: str = "SYNTHETIC",
    gross_margin=UNAVAILABLE,
    operating_margin=UNAVAILABLE,
    net_margin=UNAVAILABLE,
    ebitda_margin=UNAVAILABLE,
    revenue_growth_yoy=UNAVAILABLE,
    eps_growth_yoy=UNAVAILABLE,
    trailing_pe=UNAVAILABLE,
    forward_pe=UNAVAILABLE,
    price_to_sales=UNAVAILABLE,
    ev_to_ebitda=UNAVAILABLE,
    price_to_book=UNAVAILABLE,
    fcf_margin=UNAVAILABLE,
    fcf_yield=UNAVAILABLE,
    debt_to_equity=UNAVAILABLE,
    current_ratio=UNAVAILABLE,
    roe=UNAVAILABLE,
    roic=UNAVAILABLE,
) -> TickerKPIs:
    return TickerKPIs(
        ticker=ticker,
        as_of=date(2024, 9, 30),
        profitability_annual=_profitability(
            gross_margin=gross_margin,
            operating_margin=operating_margin,
            net_margin=net_margin,
            ebitda_margin=ebitda_margin,
            revenue_growth_yoy=revenue_growth_yoy,
            eps_growth_yoy=eps_growth_yoy,
        ),
        profitability_quarterly=_profitability(),
        valuation=_valuation(
            trailing_pe=trailing_pe,
            forward_pe=forward_pe,
            price_to_sales=price_to_sales,
            ev_to_ebitda=ev_to_ebitda,
            price_to_book=price_to_book,
        ),
        cash_flow_annual=_cashflow(fcf_margin=fcf_margin, fcf_yield=fcf_yield),
        cash_flow_quarterly=_cashflow(),
        financial_strength_annual=_strength(
            debt_to_equity=debt_to_equity,
            current_ratio=current_ratio,
            roe=roe,
            roic=roic,
        ),
        financial_strength_quarterly=_strength(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# MEDIAN
# ─────────────────────────────────────────────────────────────────────────────

class TestMedian:
    def test_empty_returns_none(self) -> None:
        assert median([]) is None

    def test_single_element(self) -> None:
        assert median([Decimal("7")]) == Decimal("7")

    def test_odd_count(self) -> None:
        # [1, 2, 3] → 2
        vals = [Decimal("1"), Decimal("3"), Decimal("2")]
        assert median(vals) == Decimal("2")

    def test_even_count_average_of_middle(self) -> None:
        # [1, 2, 3, 4] → (2 + 3) / 2 = 2.5
        vals = [Decimal(str(i)) for i in [4, 1, 3, 2]]
        assert median(vals) == Decimal("2.5")

    def test_five_elements(self) -> None:
        # [10, 20, 30, 40, 50] → 30
        vals = [Decimal(str(i)) for i in [50, 10, 30, 20, 40]]
        assert median(vals) == Decimal("30")

    def test_negative_values(self) -> None:
        # [-3, -1, 2] → -1
        vals = [Decimal(str(v)) for v in [2, -3, -1]]
        assert median(vals) == Decimal("-1")

    def test_all_same(self) -> None:
        vals = [Decimal("5")] * 7
        assert median(vals) == Decimal("5")

    def test_fractions(self) -> None:
        # [0.1, 0.3, 0.5] → 0.3
        vals = [Decimal(s) for s in ("0.5", "0.1", "0.3")]
        assert median(vals) == Decimal("0.3")

    def test_large_set_even(self) -> None:
        # [1..10] → (5 + 6) / 2 = 5.5
        vals = [Decimal(str(i)) for i in range(1, 11)]
        assert median(vals) == Decimal("5.5")


# ─────────────────────────────────────────────────────────────────────────────
# PERCENTILE RANK
# ─────────────────────────────────────────────────────────────────────────────

class TestPercentileRank:
    """Using population [1, 2, 3, 4, 5] for most hand-checked cases."""

    def _pop(self) -> list[Decimal]:
        return [Decimal(str(i)) for i in [1, 2, 3, 4, 5]]

    def test_highest_value(self) -> None:
        # 4 out of 5 are strictly below 5 → 4/5 × 100 = 80
        assert percentile_rank(Decimal("5"), self._pop()) == Decimal("80")

    def test_lowest_value(self) -> None:
        # 0 out of 5 are below 1 → 0
        assert percentile_rank(Decimal("1"), self._pop()) == Decimal("0")

    def test_middle_value(self) -> None:
        # 2 out of 5 are below 3 (values 1 and 2) → 2/5 × 100 = 40
        assert percentile_rank(Decimal("3"), self._pop()) == Decimal("40")

    def test_second_lowest(self) -> None:
        # 1 out of 5 below 2 → 20
        assert percentile_rank(Decimal("2"), self._pop()) == Decimal("20")

    def test_second_highest(self) -> None:
        # 3 out of 5 below 4 → 60
        assert percentile_rank(Decimal("4"), self._pop()) == Decimal("60")

    def test_empty_population(self) -> None:
        assert percentile_rank(Decimal("5"), []) == Decimal("0")

    def test_single_element_equal(self) -> None:
        # Target equals only element → 0 below it → 0 %
        assert percentile_rank(Decimal("3"), [Decimal("3")]) == Decimal("0")

    def test_single_element_above(self) -> None:
        # Target 5 > sole population member 3 → 1/1 × 100 = 100
        assert percentile_rank(Decimal("5"), [Decimal("3")]) == Decimal("100")

    def test_ties_not_counted(self) -> None:
        # population [3, 3, 3, 5], value = 3 → 0 strictly below → 0 %
        pop = [Decimal("3"), Decimal("3"), Decimal("3"), Decimal("5")]
        assert percentile_rank(Decimal("3"), pop) == Decimal("0")

    def test_value_between_elements(self) -> None:
        # population [1, 2, 4, 5], value = 3 → 2 below (1, 2) → 2/4 × 100 = 50
        pop = [Decimal(str(v)) for v in [1, 2, 4, 5]]
        assert percentile_rank(Decimal("3"), pop) == Decimal("50")


# ─────────────────────────────────────────────────────────────────────────────
# RELATIVE POSITION
# ─────────────────────────────────────────────────────────────────────────────

class TestRelativePosition:
    """5 % default band.  All values chosen to be clearly inside or outside it."""

    # ── higher_is_better = True (e.g. gross margin) ───────────────────────────

    def test_clearly_better_higher_is_better(self) -> None:
        # target 0.40, median 0.30 → deviation +33 % > 5 % → BETTER
        pos = relative_position(Decimal("0.40"), Decimal("0.30"), higher_is_better=True)
        assert pos == RelativePosition.BETTER

    def test_clearly_worse_higher_is_better(self) -> None:
        # target 0.20, median 0.30 → deviation −33 % < −5 % → WORSE
        pos = relative_position(Decimal("0.20"), Decimal("0.30"), higher_is_better=True)
        assert pos == RelativePosition.WORSE

    def test_in_line_higher_is_better_above(self) -> None:
        # target 0.312 vs median 0.30 → deviation = 4 % < 5 % → IN_LINE
        pos = relative_position(Decimal("0.312"), Decimal("0.30"), higher_is_better=True)
        assert pos == RelativePosition.IN_LINE

    def test_in_line_higher_is_better_below(self) -> None:
        # target 0.288 vs median 0.30 → deviation = −4 % > −5 % → IN_LINE
        pos = relative_position(Decimal("0.288"), Decimal("0.30"), higher_is_better=True)
        assert pos == RelativePosition.IN_LINE

    def test_exact_boundary_higher_is_better(self) -> None:
        # deviation exactly 5 % → IN_LINE (≤ not <)
        pos = relative_position(Decimal("0.315"), Decimal("0.30"), higher_is_better=True)
        assert pos == RelativePosition.IN_LINE

    # ── higher_is_better = False (e.g. P/E, D/E) ─────────────────────────────

    def test_clearly_better_lower_is_better(self) -> None:
        # target P/E 15, median 20 → deviation −25 % < −5 % → BETTER (lower = cheaper)
        pos = relative_position(Decimal("15"), Decimal("20"), higher_is_better=False)
        assert pos == RelativePosition.BETTER

    def test_clearly_worse_lower_is_better(self) -> None:
        # target P/E 30, median 20 → deviation +50 % > 5 % → WORSE
        pos = relative_position(Decimal("30"), Decimal("20"), higher_is_better=False)
        assert pos == RelativePosition.WORSE

    def test_in_line_lower_is_better(self) -> None:
        # target 20.8, median 20 → deviation = 4 % → IN_LINE
        pos = relative_position(Decimal("20.8"), Decimal("20"), higher_is_better=False)
        assert pos == RelativePosition.IN_LINE

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_zero_peer_median_is_in_line(self) -> None:
        # Cannot normalise by zero → treat as IN_LINE
        pos = relative_position(Decimal("5"), Decimal("0"), higher_is_better=True)
        assert pos == RelativePosition.IN_LINE

    def test_equal_to_median_is_in_line(self) -> None:
        pos = relative_position(Decimal("0.30"), Decimal("0.30"), higher_is_better=True)
        assert pos == RelativePosition.IN_LINE

    def test_custom_band(self) -> None:
        # With 1 % band: deviation of 4 % is now BETTER (not IN_LINE)
        pos = relative_position(
            Decimal("0.312"),
            Decimal("0.30"),
            higher_is_better=True,
            in_line_band=Decimal("0.01"),
        )
        assert pos == RelativePosition.BETTER

    def test_negative_median(self) -> None:
        # Negative median (e.g. shrinking earnings): value less negative = BETTER
        # median = −0.05, target = −0.02  → deviation = (-0.02 - (-0.05)) / 0.05 = 0.6 > 5 %
        pos = relative_position(Decimal("-0.02"), Decimal("-0.05"), higher_is_better=True)
        assert pos == RelativePosition.BETTER


# ─────────────────────────────────────────────────────────────────────────────
# KPI EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractKPIValues:
    def test_returns_all_catalog_names(self) -> None:
        kpis = _ticker_kpis()
        vals = extract_kpi_values(kpis)
        catalog_names = {s.name for s in KPI_CATALOG}
        assert set(vals.keys()) == catalog_names

    def test_extracts_known_value(self) -> None:
        kpis = _ticker_kpis(gross_margin="0.35")
        vals = extract_kpi_values(kpis)
        assert vals["gross_margin"] == Decimal("0.35")

    def test_unavailable_when_no_series(self) -> None:
        kpis = _ticker_kpis()  # all UNAVAILABLE
        vals = extract_kpi_values(kpis)
        assert vals["gross_margin"] == UNAVAILABLE

    def test_latest_chosen_from_multi_period_series(self) -> None:
        """_latest() walks backwards — most recent non-UNAVAILABLE wins."""
        kpis = _ticker_kpis()
        # Manually insert a 2-point series for gross_margin
        kpis.profitability_annual.gross_margin.append(_pt("0.40"))
        vals = extract_kpi_values(kpis)
        # The appended point (0.40) is the new latest
        assert vals["gross_margin"] == Decimal("0.40")


# ─────────────────────────────────────────────────────────────────────────────
# BUILD_COMPARISONS — integration of stats + extraction
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildComparisons:
    """Synthetic peer set: 4 peers with known gross margins.

    Target:  0.46  (Apple-ish)
    Peer A:  0.30
    Peer B:  0.40
    Peer C:  0.50
    Peer D:  0.60

    Peer-only median gross_margin = median([0.30, 0.40, 0.50, 0.60])
                                  = (0.40 + 0.50) / 2 = 0.45

    Combined population for percentile = [0.30, 0.40, 0.46, 0.50, 0.60]
    Percentile of 0.46 = count(v < 0.46) / 5 × 100 = 2/5 × 100 = 40
    Deviation from median = (0.46 − 0.45) / 0.45 ≈ 2.2 % < 5 % → IN_LINE
    """

    TARGET_GM = Decimal("0.46")
    PEER_GMS = {"A": Decimal("0.30"), "B": Decimal("0.40"), "C": Decimal("0.50"), "D": Decimal("0.60")}
    PEER_MEDIAN = (Decimal("0.40") + Decimal("0.50")) / Decimal("2")  # 0.45
    PERCENTILE = Decimal("40")  # 2 of 5 below 0.46

    def _build(self) -> tuple:
        target = _ticker_kpis("TARGET", gross_margin=self.TARGET_GM)
        peers = [
            PeerMetrics(ticker=t, kpis=_ticker_kpis(t, gross_margin=v))
            for t, v in self.PEER_GMS.items()
        ]
        sector_med, comparisons = build_comparisons("TARGET", target, peers)
        return sector_med, comparisons

    def test_peer_median_gross_margin(self) -> None:
        sector_med, _ = self._build()
        assert sector_med.gross_margin == self.PEER_MEDIAN

    def test_comparison_peer_median(self) -> None:
        _, comparisons = self._build()
        cmp = comparisons.gross_margin
        assert cmp.peer_median == self.PEER_MEDIAN

    def test_comparison_target_value(self) -> None:
        _, comparisons = self._build()
        assert comparisons.gross_margin.target_value == self.TARGET_GM

    def test_comparison_percentile(self) -> None:
        _, comparisons = self._build()
        assert comparisons.gross_margin.percentile == self.PERCENTILE

    def test_comparison_position_in_line(self) -> None:
        # 0.46 vs median 0.45 → 2.2 % deviation < 5 % band → IN_LINE
        _, comparisons = self._build()
        assert comparisons.gross_margin.position == RelativePosition.IN_LINE

    def test_comparison_position_better(self) -> None:
        # Use a target clearly above the median: 0.60 vs peers {0.30, 0.40, 0.50}
        # peer median = 0.40; deviation = (0.60−0.40)/0.40 = 50 % > 5 % → BETTER
        target = _ticker_kpis("T", gross_margin="0.60")
        peers = [
            PeerMetrics(ticker="A", kpis=_ticker_kpis("A", gross_margin="0.30")),
            PeerMetrics(ticker="B", kpis=_ticker_kpis("B", gross_margin="0.40")),
            PeerMetrics(ticker="C", kpis=_ticker_kpis("C", gross_margin="0.50")),
        ]
        _, comparisons = build_comparisons("T", target, peers)
        assert comparisons.gross_margin.position == RelativePosition.BETTER

    def test_comparison_position_worse_lower_is_better(self) -> None:
        # P/E: target 30 vs peers {15, 20, 25} → median 20
        # deviation = (30−20)/20 = 50 % > 5 %, higher_is_better=False → WORSE
        target = _ticker_kpis("T", trailing_pe="30")
        peers = [
            PeerMetrics(ticker="A", kpis=_ticker_kpis("A", trailing_pe="15")),
            PeerMetrics(ticker="B", kpis=_ticker_kpis("B", trailing_pe="20")),
            PeerMetrics(ticker="C", kpis=_ticker_kpis("C", trailing_pe="25")),
        ]
        _, comparisons = build_comparisons("T", target, peers)
        assert comparisons.trailing_pe.position == RelativePosition.WORSE

    def test_unavailable_target_produces_none_position(self) -> None:
        # Target has UNAVAILABLE gross_margin → no comparison possible
        target = _ticker_kpis("T")  # all UNAVAILABLE
        peers = [PeerMetrics(ticker="A", kpis=_ticker_kpis("A", gross_margin="0.30"))]
        _, comparisons = build_comparisons("T", target, peers)
        assert comparisons.gross_margin.position is None
        assert comparisons.gross_margin.percentile is None
        assert comparisons.gross_margin.target_value == UNAVAILABLE

    def test_zero_peers_all_unavailable_medians(self) -> None:
        target = _ticker_kpis("T", gross_margin="0.40")
        sector_med, comparisons = build_comparisons("T", target, [])
        assert sector_med.gross_margin == UNAVAILABLE
        # No peers → no median → position is None
        assert comparisons.gross_margin.position is None

    def test_peer_values_dict_populated(self) -> None:
        _, comparisons = self._build()
        cmp = comparisons.gross_margin
        assert set(cmp.peer_values.keys()) == set(self.PEER_GMS.keys())
        assert cmp.peer_values["A"] == Decimal("0.30")
        assert cmp.peer_values["D"] == Decimal("0.60")

    def test_higher_is_better_flag_set_correctly(self) -> None:
        _, comparisons = self._build()
        assert comparisons.gross_margin.higher_is_better is True
        assert comparisons.trailing_pe.higher_is_better is False
        assert comparisons.debt_to_equity.higher_is_better is False
        assert comparisons.roe.higher_is_better is True


# ─────────────────────────────────────────────────────────────────────────────
# SECTOR MEDIAN — full-pillar check with AAPL fixture
# ─────────────────────────────────────────────────────────────────────────────

class TestSectorMedianFromFixture:
    """Three-peer set: AAPL ×3 (same fixture data).

    With identical peers, the median of any KPI equals that KPI's value.
    This verifies round-trip extraction→median without hand-coding everything.
    """

    @pytest.fixture(scope="class")
    def aapl_kpis(self) -> TickerKPIs:
        return compute(_make_fmp().get_raw_financials("AAPL"))

    @pytest.fixture(scope="class")
    def peer_set_result(self, aapl_kpis: TickerKPIs):
        peers = [
            PeerMetrics(ticker="PEER1", kpis=aapl_kpis),
            PeerMetrics(ticker="PEER2", kpis=aapl_kpis),
        ]
        sector_med, comparisons = build_comparisons("AAPL", aapl_kpis, peers)
        return sector_med, comparisons, aapl_kpis

    def test_sector_median_equals_target_when_all_identical(self, peer_set_result) -> None:
        sector_med, comparisons, aapl_kpis = peer_set_result
        # With identical peers, the median gross_margin = AAPL's gross_margin
        from fundalyzer.peers._extract import extract_kpi_values
        aapl_vals = extract_kpi_values(aapl_kpis)
        if aapl_vals["gross_margin"] != UNAVAILABLE:
            assert sector_med.gross_margin == aapl_vals["gross_margin"]

    def test_position_in_line_when_identical(self, peer_set_result) -> None:
        _, comparisons, _ = peer_set_result
        # Target == median → deviation = 0 → IN_LINE for all available metrics
        for spec in KPI_CATALOG:
            cmp = getattr(comparisons, spec.name)
            if cmp.target_value != UNAVAILABLE and cmp.peer_median != UNAVAILABLE:
                assert cmp.position == RelativePosition.IN_LINE, (
                    f"Expected IN_LINE for {spec.name} "
                    f"(target={cmp.target_value}, median={cmp.peer_median})"
                )

    def test_percentile_with_three_identical_values(self, peer_set_result) -> None:
        # population = [v, v, v] (target + 2 peers), all equal
        # count strictly below v = 0 → percentile = 0
        _, comparisons, _ = peer_set_result
        gm_cmp = comparisons.gross_margin
        if gm_cmp.percentile is not None:
            assert gm_cmp.percentile == Decimal("0")


# ─────────────────────────────────────────────────────────────────────────────
# PEER SELECTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestDerivePerrs:
    def test_strips_target_from_result(self) -> None:
        provider = MagicMock()
        provider.get_peer_tickers.return_value = ["AAPL", "MSFT", "GOOGL"]
        result = derive_peers("AAPL", provider, max_peers=10)
        assert "AAPL" not in result

    def test_caps_at_max_peers(self) -> None:
        provider = MagicMock()
        provider.get_peer_tickers.return_value = [f"T{i}" for i in range(20)]
        result = derive_peers("AAPL", provider, max_peers=5)
        assert len(result) <= 5

    def test_returns_empty_on_provider_exception(self) -> None:
        provider = MagicMock()
        provider.get_peer_tickers.side_effect = RuntimeError("network error")
        result = derive_peers("AAPL", provider)
        assert result == []

    def test_normalises_to_upper(self) -> None:
        provider = MagicMock()
        provider.get_peer_tickers.return_value = ["msft", "googl"]
        result = derive_peers("aapl", provider)
        assert all(t == t.upper() for t in result)
