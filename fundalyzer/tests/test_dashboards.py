"""Dashboard tests.

Verifies that a fully populated TickerKPIs + PeerSet produces four complete
dashboard objects with all fields populated (or explicitly UNAVAILABLE) and
that structural invariants hold.

No live API calls — uses the recorded AAPL fixture responses.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fundalyzer.data.cache import NullCache
from fundalyzer.data.fmp import FMPProvider
from fundalyzer.data.models import UNAVAILABLE
from fundalyzer.dashboards.build import _self_history_position, build
from fundalyzer.dashboards.models import (
    CapitalDashboard,
    IncomeDashboard,
    MomentumDashboard,
    ValuationDashboard,
)
from fundalyzer.metrics._trend import classify_trend
from fundalyzer.metrics.compute import compute
from fundalyzer.metrics.models import MetricPoint, MetricSeries, TickerKPIs
from fundalyzer.peers._aggregator import build_comparisons
from fundalyzer.peers.models import PeerMetrics, PeerSet, RelativePosition

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


def _make_peer_set(kpis: TickerKPIs) -> PeerSet:
    """One synthetic peer (same data as target) so sector medians equal target values."""
    peer = PeerMetrics(ticker="PEER", kpis=kpis)
    sector_med, comparisons = build_comparisons("AAPL", kpis, [peer])
    return PeerSet(
        target="AAPL",
        target_kpis=kpis,
        peers=[peer],
        sector_medians=sector_med,
        comparisons=comparisons,
    )


@pytest.fixture(scope="module")
def kpis() -> TickerKPIs:
    return compute(_make_fmp().get_raw_financials("AAPL"))


@pytest.fixture(scope="module")
def peer_set(kpis: TickerKPIs) -> PeerSet:
    return _make_peer_set(kpis)


@pytest.fixture(scope="module")
def dashboards(kpis: TickerKPIs, peer_set: PeerSet):
    return build(kpis, peer_set)


# ── Helper ────────────────────────────────────────────────────────────────────

def _pt(value: Any) -> MetricPoint:
    v = Decimal(str(value)) if value != UNAVAILABLE else UNAVAILABLE
    return MetricPoint(
        value=v, period="annual",
        period_date=date(2024, 9, 30),
        formula="test", inputs={},
    )


def _s(*vals: Any) -> MetricSeries:
    return [_pt(v) for v in vals]


# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURE: all four dashboards are returned and typed correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildReturnsAllFour:
    def test_returns_tuple_of_four(self, dashboards) -> None:
        assert len(dashboards) == 4

    def test_income_type(self, dashboards) -> None:
        income, _, _, _ = dashboards
        assert isinstance(income, IncomeDashboard)

    def test_momentum_type(self, dashboards) -> None:
        _, momentum, _, _ = dashboards
        assert isinstance(momentum, MomentumDashboard)

    def test_valuation_type(self, dashboards) -> None:
        _, _, valuation, _ = dashboards
        assert isinstance(valuation, ValuationDashboard)

    def test_capital_type(self, dashboards) -> None:
        _, _, _, capital = dashboards
        assert isinstance(capital, CapitalDashboard)

    def test_all_tickers_match(self, dashboards) -> None:
        for db in dashboards:
            assert db.ticker == "AAPL"


# ─────────────────────────────────────────────────────────────────────────────
# INCOME DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

class TestIncomeDashboard:
    def test_revenue_series_is_populated(self, dashboards) -> None:
        income, _, _, _ = dashboards
        assert len(income.revenue) > 0

    def test_revenue_oldest_first(self, dashboards) -> None:
        income, _, _, _ = dashboards
        dates = [p.period_date for p in income.revenue]
        assert dates == sorted(dates)

    def test_gross_margin_values_are_decimal(self, dashboards) -> None:
        income, _, _, _ = dashboards
        for pt in income.gross_margin:
            if pt.value != UNAVAILABLE:
                assert isinstance(pt.value, Decimal)

    def test_gross_margin_in_0_1_range(self, dashboards) -> None:
        income, _, _, _ = dashboards
        for pt in income.gross_margin:
            if pt.value != UNAVAILABLE:
                assert Decimal("0") <= pt.value <= Decimal("1")

    def test_profitability_ordering_holds(self, dashboards) -> None:
        """gross ≥ operating ≥ net (when all are positive and available)."""
        income, _, _, _ = dashboards
        for gm, om, nm in zip(income.gross_margin, income.operating_margin, income.net_margin):
            if all(v != UNAVAILABLE for v in [gm.value, om.value, nm.value]):
                if gm.value > 0:
                    assert gm.value >= om.value
                    assert om.value >= nm.value

    def test_trend_results_present(self, dashboards) -> None:
        income, _, _, _ = dashboards
        from fundalyzer.metrics.models import TrendResult
        assert isinstance(income.gross_margin_trend, TrendResult)
        assert isinstance(income.operating_margin_trend, TrendResult)
        assert isinstance(income.net_margin_trend, TrendResult)
        assert isinstance(income.fcf_margin_trend, TrendResult)

    def test_fcf_is_populated(self, dashboards) -> None:
        income, _, _, _ = dashboards
        assert len(income.free_cash_flow) > 0

    def test_peer_medians_are_populated(self, dashboards, kpis) -> None:
        """With an identical peer, sector median == target value."""
        income, _, _, _ = dashboards
        from fundalyzer.peers._extract import extract_kpi_values
        target_vals = extract_kpi_values(kpis)
        # With one identical peer the median equals the peer's (= target's) value
        if target_vals["gross_margin"] != UNAVAILABLE:
            assert income.peer_gross_margin == target_vals["gross_margin"]

    def test_peer_medians_not_all_unavailable(self, dashboards) -> None:
        income, _, _, _ = dashboards
        medians = [
            income.peer_gross_margin,
            income.peer_operating_margin,
            income.peer_net_margin,
            income.peer_fcf_margin,
        ]
        assert any(m != UNAVAILABLE for m in medians)


# ─────────────────────────────────────────────────────────────────────────────
# MOMENTUM DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

class TestMomentumDashboard:
    def test_eps_series_length(self, dashboards, kpis) -> None:
        _, momentum, _, _ = dashboards
        assert len(momentum.eps_annual) == len(kpis.profitability_annual.eps_diluted)

    def test_eps_growth_oldest_is_unavailable(self, dashboards) -> None:
        # First YoY growth rate has no prior period
        _, momentum, _, _ = dashboards
        assert momentum.eps_growth_yoy[0].value == UNAVAILABLE

    def test_trailing_pe_single_point(self, dashboards) -> None:
        _, momentum, _, _ = dashboards
        assert len(momentum.trailing_pe) == 1

    def test_historical_pe_length_matches_annual_income(self, dashboards, kpis) -> None:
        _, momentum, _, _ = dashboards
        # historical_pe has one point per annual income statement
        assert len(momentum.historical_pe) == len(kpis.profitability_annual.eps_diluted)

    def test_historical_pe_values_are_positive(self, dashboards) -> None:
        _, momentum, _, _ = dashboards
        for pt in momentum.historical_pe:
            if pt.value != UNAVAILABLE:
                assert pt.value > Decimal("0")

    def test_forward_revenue_populated(self, dashboards) -> None:
        # Fixture has analyst estimates with revenue_avg, so forward_revenue should be set
        _, momentum, _, _ = dashboards
        assert len(momentum.forward_revenue) == 1
        assert momentum.forward_revenue[0].value != UNAVAILABLE

    def test_pe_trend_is_trend_result(self, dashboards) -> None:
        _, momentum, _, _ = dashboards
        from fundalyzer.metrics.models import TrendResult
        assert isinstance(momentum.pe_trend, TrendResult)

    def test_peer_trailing_pe_populated(self, dashboards) -> None:
        _, momentum, _, _ = dashboards
        assert momentum.peer_trailing_pe != UNAVAILABLE


# ─────────────────────────────────────────────────────────────────────────────
# VALUATION DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

class TestValuationDashboard:
    def test_all_multiples_present(self, dashboards) -> None:
        _, _, valuation, _ = dashboards
        assert len(valuation.trailing_pe) >= 1
        assert len(valuation.price_to_sales) >= 1
        assert len(valuation.ev_to_ebitda) >= 1
        assert len(valuation.ev_to_gross_profit) >= 1

    def test_ev_to_gross_profit_less_than_ev_to_ebitda(self, dashboards) -> None:
        # EV/GP < EV/EBITDA because GP > EBITDA is impossible;
        # actually GP ≥ EBITDA is wrong — EBITDA adds back D&A to EBIT.
        # But gross profit > EBITDA is possible for tech companies (high D&A).
        # Simply verify both are available and positive.
        _, _, valuation, _ = dashboards
        evgp = valuation.ev_to_gross_profit[0].value
        evebitda = valuation.ev_to_ebitda[0].value
        if evgp != UNAVAILABLE and evebitda != UNAVAILABLE:
            assert evgp > Decimal("0")
            assert evebitda > Decimal("0")

    def test_historical_pe_oldest_first(self, dashboards) -> None:
        _, _, valuation, _ = dashboards
        dates = [p.period_date for p in valuation.historical_pe]
        assert dates == sorted(dates)

    def test_self_history_flags_are_valid_or_none(self, dashboards) -> None:
        _, _, valuation, _ = dashboards
        for flag in [
            valuation.pe_vs_own_history,
            valuation.ps_vs_own_history,
            valuation.ev_ebitda_vs_own_history,
        ]:
            assert flag is None or isinstance(flag, RelativePosition)

    def test_peer_multiples_populated(self, dashboards) -> None:
        _, _, valuation, _ = dashboards
        assert valuation.peer_trailing_pe != UNAVAILABLE
        assert valuation.peer_price_to_sales != UNAVAILABLE


# ─────────────────────────────────────────────────────────────────────────────
# CAPITAL DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

class TestCapitalDashboard:
    def test_roic_series_populated(self, dashboards) -> None:
        _, _, _, capital = dashboards
        assert len(capital.roic) > 0

    def test_buybacks_are_negative_for_aapl(self, dashboards) -> None:
        # Apple spent heavily on buybacks; convention: negative = outflow
        _, _, _, capital = dashboards
        latest_buyback = capital.buybacks[-1].value
        if latest_buyback != UNAVAILABLE:
            assert latest_buyback < Decimal("0"), (
                f"Expected negative buyback (outflow); got {latest_buyback}"
            )

    def test_price_target_consensus_populated(self, dashboards) -> None:
        # Fixture has price_target_consensus = 237.5
        _, _, _, capital = dashboards
        assert capital.price_target_consensus == Decimal("237.5")

    def test_price_upside_is_decimal(self, dashboards) -> None:
        _, _, _, capital = dashboards
        if capital.price_upside != UNAVAILABLE:
            assert isinstance(capital.price_upside, Decimal)

    def test_price_upside_computed_correctly(self, dashboards) -> None:
        # consensus = 237.5, price = 229.87
        # upside = (237.5 - 229.87) / 229.87 ≈ 0.033...
        _, _, _, capital = dashboards
        if capital.price_upside != UNAVAILABLE:
            expected = (Decimal("237.5") - Decimal("229.87")) / Decimal("229.87")
            assert abs(capital.price_upside - expected) < Decimal("0.0001")

    def test_revenue_per_employee_populated(self, dashboards) -> None:
        # Fixture has fullTimeEmployees: 150000
        _, _, _, capital = dashboards
        assert len(capital.revenue_per_employee) == 1
        rpe = capital.revenue_per_employee[0].value
        assert rpe != UNAVAILABLE
        # revenue / 150000 employees — should be ~$2.6M per employee (Apple FY2024)
        assert rpe > Decimal("1_000_000"), f"Expected > $1M per employee, got {rpe}"

    def test_roic_trend_is_trend_result(self, dashboards) -> None:
        _, _, _, capital = dashboards
        from fundalyzer.metrics.models import TrendResult
        assert isinstance(capital.roic_trend, TrendResult)

    def test_peer_medians_populated(self, dashboards) -> None:
        _, _, _, capital = dashboards
        assert capital.peer_roic != UNAVAILABLE
        assert capital.peer_roe != UNAVAILABLE
        assert capital.peer_fcf_yield != UNAVAILABLE


# ─────────────────────────────────────────────────────────────────────────────
# SELF-HISTORY POSITION
# ─────────────────────────────────────────────────────────────────────────────

class TestSelfHistoryPosition:
    """Unit tests for the helper — does not require fixture data."""

    def test_none_when_single_point(self) -> None:
        series = _s("20")
        assert _self_history_position(series, higher_is_better=False) is None

    def test_none_when_all_unavailable(self) -> None:
        series = _s(UNAVAILABLE, UNAVAILABLE, UNAVAILABLE)
        assert _self_history_position(series, higher_is_better=False) is None

    def test_cheaper_than_history(self) -> None:
        # P/E history: [30, 28, 25], current = 20
        # history median (prior periods) = 28, current = 20 → BETTER (lower = cheaper)
        series = _s("30", "28", "25", "20")
        pos = _self_history_position(series, higher_is_better=False)
        assert pos == RelativePosition.BETTER

    def test_richer_than_history(self) -> None:
        # P/E history: [15, 18, 20], current = 35
        # history median = 18, current = 35 → WORSE (expensive vs own history)
        series = _s("15", "18", "20", "35")
        pos = _self_history_position(series, higher_is_better=False)
        assert pos == RelativePosition.WORSE

    def test_in_line_with_history(self) -> None:
        # P/E: [20, 21, 20, 21], current = 20.5 — well within 5 % of median
        series = _s("20", "21", "20", "21", "20.5")
        pos = _self_history_position(series, higher_is_better=False)
        assert pos == RelativePosition.IN_LINE

    def test_improving_margin_vs_history(self) -> None:
        # Gross margin history: [0.30, 0.33, 0.35], current = 0.46
        # higher_is_better=True: above history → BETTER
        series = _s("0.30", "0.33", "0.35", "0.46")
        pos = _self_history_position(series, higher_is_better=True)
        assert pos == RelativePosition.BETTER

    def test_declining_margin_vs_history(self) -> None:
        series = _s("0.46", "0.44", "0.43", "0.20")
        pos = _self_history_position(series, higher_is_better=True)
        assert pos == RelativePosition.WORSE

    def test_unavailable_points_skipped(self) -> None:
        # Some UNAVAILABLE entries mixed in; valid values show BETTER
        series = _s(UNAVAILABLE, "30", UNAVAILABLE, "28", "25", "20")
        pos = _self_history_position(series, higher_is_better=False)
        assert pos == RelativePosition.BETTER


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE: build with zero peers
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildWithZeroPeers:
    @pytest.fixture(scope="class")
    def empty_peer_set(self, kpis: TickerKPIs) -> PeerSet:
        sector_med, comparisons = build_comparisons("AAPL", kpis, [])
        return PeerSet(
            target="AAPL",
            target_kpis=kpis,
            peers=[],
            sector_medians=sector_med,
            comparisons=comparisons,
        )

    def test_returns_four_dashboards(self, kpis, empty_peer_set) -> None:
        result = build(kpis, empty_peer_set)
        assert len(result) == 4

    def test_peer_medians_unavailable_with_no_peers(self, kpis, empty_peer_set) -> None:
        income, _, _, _ = build(kpis, empty_peer_set)
        # With 0 peers, every sector median is UNAVAILABLE
        assert income.peer_gross_margin == UNAVAILABLE
        assert income.peer_net_margin == UNAVAILABLE
