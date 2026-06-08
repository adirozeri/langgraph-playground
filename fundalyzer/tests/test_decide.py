"""Decide module tests — no live API or model calls.

Coverage:
  - _scoring: pillar scores from PeerComparisons percentiles
  - _valuation_position: CHEAPER / IN_LINE / RICHER classification
  - _projection: base-case and bull-case 3-year math
  - _soft_signals: insider / revision / buyback classification and conflict detection
  - _lean: INVEST / HOLD / AVOID rule derivation
  - decide(): end-to-end wiring with mocked Anthropic client
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
from fundalyzer.data.models import UNAVAILABLE, EarningsRevision, InsiderTransaction
from fundalyzer.decide._lean import derive_lean
from fundalyzer.decide._projection import BULL_PE_EXPANSION, build_projection
from fundalyzer.decide._scoring import score_pillars
from fundalyzer.decide._soft_signals import _read_insider, _read_revisions, build_soft_signals
from fundalyzer.decide._valuation_position import build_valuation_position
from fundalyzer.decide.models import (
    InvestmentLean,
    PillarVerdict,
    ScoreCard,
    SoftSignalDirection,
    SoftSignals,
    ValuationHistoryPosition,
    ValuationPosition,
)
from fundalyzer.metrics.compute import compute
from fundalyzer.peers._aggregator import build_comparisons
from fundalyzer.peers.models import PeerMetrics, PeerSet

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


@pytest.fixture(scope="module")
def aapl_data():
    fmp = _make_fmp()
    raw = fmp.get_raw_financials("AAPL")
    kpis = compute(raw)
    peer = PeerMetrics(ticker="PEER", kpis=kpis)
    sm, cmp = build_comparisons("AAPL", kpis, [peer])
    peer_set = PeerSet(target="AAPL", target_kpis=kpis, peers=[peer],
                       sector_medians=sm, comparisons=cmp)
    return raw, kpis, peer_set


# ── _scoring tests ────────────────────────────────────────────────────────────

class TestScoring:
    def test_scorecard_has_all_pillars(self, aapl_data):
        _, kpis, peer_set = aapl_data
        card = score_pillars(peer_set.comparisons)
        assert card.income is not None
        assert card.momentum is not None
        assert card.valuation is not None
        assert card.capital is not None

    def test_scorecard_composite_in_range(self, aapl_data):
        _, kpis, peer_set = aapl_data
        card = score_pillars(peer_set.comparisons)
        assert Decimal("0") <= card.composite <= Decimal("10")

    def test_pillar_scores_in_range(self, aapl_data):
        _, kpis, peer_set = aapl_data
        card = score_pillars(peer_set.comparisons)
        for pillar in (card.income, card.momentum, card.valuation, card.capital):
            assert Decimal("0") <= pillar.score <= Decimal("10")

    def test_pillar_verdict_matches_score(self, aapl_data):
        _, kpis, peer_set = aapl_data
        card = score_pillars(peer_set.comparisons)
        for pillar in (card.income, card.momentum, card.valuation, card.capital):
            s = pillar.score
            if s >= 8:
                assert pillar.verdict == PillarVerdict.STRONG
            elif s >= 6:
                assert pillar.verdict == PillarVerdict.ABOVE_PEER
            elif s >= 4:
                assert pillar.verdict == PillarVerdict.IN_LINE
            elif s >= 2:
                assert pillar.verdict == PillarVerdict.BELOW_PEER
            else:
                assert pillar.verdict == PillarVerdict.WEAK

    def test_metrics_vs_peers_populated(self, aapl_data):
        _, kpis, peer_set = aapl_data
        card = score_pillars(peer_set.comparisons)
        # At least some KPIs should be compared (AAPL is the only peer of itself here)
        all_metrics = {
            **card.income.key_metrics_vs_peers,
            **card.momentum.key_metrics_vs_peers,
            **card.valuation.key_metrics_vs_peers,
            **card.capital.key_metrics_vs_peers,
        }
        # All values should be valid RelativePosition strings
        assert all(v in ("BETTER", "WORSE", "IN_LINE") for v in all_metrics.values())

    def test_neutral_score_when_no_percentile_data(self):
        """When all KPIs lack percentile data, each pillar defaults to score=5."""
        from fundalyzer.peers.models import KPIComparison, PeerComparisons
        null_cmp = KPIComparison(
            target_value=UNAVAILABLE, peer_median=UNAVAILABLE,
            peer_values={}, percentile=None, position=None,
            higher_is_better=True,
        )
        comparisons = PeerComparisons(
            gross_margin=null_cmp, operating_margin=null_cmp, net_margin=null_cmp,
            ebitda_margin=null_cmp, revenue_growth_yoy=null_cmp, eps_growth_yoy=null_cmp,
            trailing_pe=null_cmp, forward_pe=null_cmp, price_to_sales=null_cmp,
            ev_to_ebitda=null_cmp, price_to_book=null_cmp,
            fcf_margin=null_cmp, fcf_yield=null_cmp,
            debt_to_equity=null_cmp, current_ratio=null_cmp, roe=null_cmp, roic=null_cmp,
        )
        card = score_pillars(comparisons)
        assert card.income.score == Decimal("5.00")
        assert card.capital.score == Decimal("5.00")

    def test_lower_pe_gives_higher_valuation_score(self):
        """A company with P/E in the 20th percentile should score ~80/10 = 8 on valuation."""
        from fundalyzer.peers.models import KPIComparison, PeerComparisons, RelativePosition
        low_pe = KPIComparison(
            target_value=Decimal("15"), peer_median=Decimal("25"),
            peer_values={}, percentile=Decimal("20"),
            position=RelativePosition.BETTER, higher_is_better=False,
        )
        null_cmp = KPIComparison(
            target_value=UNAVAILABLE, peer_median=UNAVAILABLE,
            peer_values={}, percentile=None, position=None, higher_is_better=True,
        )
        comparisons = PeerComparisons(
            gross_margin=null_cmp, operating_margin=null_cmp, net_margin=null_cmp,
            ebitda_margin=null_cmp, revenue_growth_yoy=null_cmp, eps_growth_yoy=null_cmp,
            trailing_pe=low_pe, forward_pe=null_cmp, price_to_sales=null_cmp,
            ev_to_ebitda=null_cmp, price_to_book=null_cmp,
            fcf_margin=null_cmp, fcf_yield=null_cmp,
            debt_to_equity=null_cmp, current_ratio=null_cmp, roe=null_cmp, roic=null_cmp,
        )
        card = score_pillars(comparisons)
        # Only trailing_pe contributes to valuation; effective percentile = 100-20 = 80 → score 8
        assert card.valuation.score == Decimal("8.00")
        assert card.valuation.verdict == PillarVerdict.STRONG


# ── _valuation_position tests ─────────────────────────────────────────────────

class TestValuationPosition:
    def test_produces_valid_position(self, aapl_data):
        _, kpis, peer_set = aapl_data
        pos = build_valuation_position(kpis, peer_set)
        assert pos.position in ValuationHistoryPosition

    def test_insufficient_data_when_few_historical_points(self, aapl_data):
        """With fewer than 3 historical PE data points, result should be INSUFFICIENT_DATA."""
        _, kpis, peer_set = aapl_data
        kpis_copy = kpis.model_copy(deep=True)
        kpis_copy.valuation.historical_pe = kpis_copy.valuation.historical_pe[:1]
        pos = build_valuation_position(kpis_copy, peer_set)
        assert pos.position == ValuationHistoryPosition.INSUFFICIENT_DATA

    def test_cheaper_when_current_pe_well_below_history(self, aapl_data):
        """If current P/E is 30% below historical median, position should be CHEAPER."""
        from fundalyzer.metrics.models import MetricPoint
        _, kpis, peer_set = aapl_data
        kpis_copy = kpis.model_copy(deep=True)
        # Build a historical_pe series where median of first N is 30, latest is 20
        historical = [
            MetricPoint(value=Decimal("30"), period="annual",
                        period_date=date(2019, 9, 30), formula="test", inputs={}),
            MetricPoint(value=Decimal("30"), period="annual",
                        period_date=date(2020, 9, 30), formula="test", inputs={}),
            MetricPoint(value=Decimal("30"), period="annual",
                        period_date=date(2021, 9, 30), formula="test", inputs={}),
            MetricPoint(value=Decimal("20"), period="annual",
                        period_date=date(2022, 9, 30), formula="test", inputs={}),
        ]
        # Replace trailing_pe with a point that matches the latest historical_pe
        kpis_copy.valuation.historical_pe = historical
        kpis_copy.valuation.trailing_pe = [
            MetricPoint(value=Decimal("20"), period="annual",
                        period_date=date(2022, 9, 30), formula="test", inputs={}),
        ]
        pos = build_valuation_position(kpis_copy, peer_set)
        # 20 vs historical median of [30,30,30] = 30 → deviation = (20-30)/30 = -33% → CHEAPER
        assert pos.position == ValuationHistoryPosition.CHEAPER

    def test_note_field_always_present(self, aapl_data):
        _, kpis, peer_set = aapl_data
        pos = build_valuation_position(kpis, peer_set)
        assert "does not" in pos.note.lower()


# ── _projection tests ─────────────────────────────────────────────────────────

class TestProjection:
    def test_produces_base_and_bull(self, aapl_data):
        _, kpis, _ = aapl_data
        proj = build_projection(kpis)
        assert proj.base_case.label == "base_case"
        assert proj.bull_case.label == "bull_case"

    def test_bull_pe_higher_than_base(self, aapl_data):
        _, kpis, _ = aapl_data
        proj = build_projection(kpis)
        if (proj.base_case.applied_pe_multiple != UNAVAILABLE
                and proj.bull_case.applied_pe_multiple != UNAVAILABLE):
            base_pe = Decimal(str(proj.base_case.applied_pe_multiple))
            bull_pe = Decimal(str(proj.bull_case.applied_pe_multiple))
            expected = base_pe * (1 + BULL_PE_EXPANSION)
            # Relative difference should be < 0.01%
            assert abs(bull_pe - expected) / abs(expected) < Decimal("0.0001")

    def test_bull_revenue_higher_than_base_year3(self, aapl_data):
        _, kpis, _ = aapl_data
        proj = build_projection(kpis)
        if (proj.base_case.year_3_revenue != UNAVAILABLE
                and proj.bull_case.year_3_revenue != UNAVAILABLE):
            bull3 = Decimal(str(proj.bull_case.year_3_revenue))
            base3 = Decimal(str(proj.base_case.year_3_revenue))
            assert bull3 > base3

    def test_implied_price_is_eps_times_pe(self, aapl_data):
        _, kpis, _ = aapl_data
        proj = build_projection(kpis)
        bc = proj.base_case
        if (bc.year_3_eps != UNAVAILABLE and bc.applied_pe_multiple != UNAVAILABLE
                and bc.implied_price_year_3 != UNAVAILABLE):
            expected = Decimal(str(bc.year_3_eps)) * Decimal(str(bc.applied_pe_multiple))
            actual = Decimal(str(bc.implied_price_year_3))
            assert actual == expected

    def test_methodology_note_always_present(self, aapl_data):
        _, kpis, _ = aapl_data
        proj = build_projection(kpis)
        assert "analyst" in proj.methodology_note.lower()

    def test_synthetic_projection_math(self):
        """Hand-check: base_revenue=100, growth=10% → yr1=110, yr2=121, yr3=133.1"""
        from fundalyzer.decide._projection import _grow_3yr
        y1, y2, y3, cagr = _grow_3yr(Decimal("100"), Decimal("0.10"))
        assert y1 == Decimal("110")
        assert y2 == Decimal("121")
        assert y3 == Decimal("133.1")
        assert cagr == Decimal("0.10")

    def test_unavailable_growth_propagates(self):
        from fundalyzer.decide._projection import _grow_3yr
        y1, y2, y3, cagr = _grow_3yr(Decimal("100"), UNAVAILABLE)
        assert y1 == UNAVAILABLE
        assert y3 == UNAVAILABLE


# ── _soft_signals tests ───────────────────────────────────────────────────────

class TestSoftSignals:
    def test_produces_all_signals(self, aapl_data):
        raw, kpis, _ = aapl_data
        signals = build_soft_signals(raw, kpis)
        for sig in (signals.insider_activity, signals.estimate_revisions, signals.buyback_activity):
            assert sig in SoftSignalDirection

    def test_conflict_flag_type(self, aapl_data):
        raw, kpis, _ = aapl_data
        signals = build_soft_signals(raw, kpis)
        assert isinstance(signals.conflict_flag, bool)
        if signals.conflict_flag:
            assert signals.conflict_description != ""

    def test_insider_positive_when_buys_dominate(self):
        buys = [
            InsiderTransaction(symbol="X", filing_date=date(2024, 1, 1),
                               transaction_date=date(2024, 1, 1), name="CEO",
                               transaction_type="buy", shares=Decimal("10000"),
                               value=Decimal("5_000_000")),
        ]
        sells = [
            InsiderTransaction(symbol="X", filing_date=date(2024, 1, 2),
                               transaction_date=date(2024, 1, 2), name="CFO",
                               transaction_type="sell", shares=Decimal("100"),
                               value=Decimal("50_000")),
        ]
        raw_stub = MagicMock()
        raw_stub.insider_transactions = buys + sells
        direction, detail = _read_insider(raw_stub)
        assert direction == SoftSignalDirection.POSITIVE
        assert "$5.0M" in detail or "5.0" in detail

    def test_insider_negative_when_sells_dominate(self):
        sells = [
            InsiderTransaction(symbol="X", filing_date=date(2024, 1, 1),
                               transaction_date=date(2024, 1, 1), name="CEO",
                               transaction_type="sell", shares=Decimal("100000"),
                               value=Decimal("20_000_000")),
        ]
        raw_stub = MagicMock()
        raw_stub.insider_transactions = sells
        direction, _ = _read_insider(raw_stub)
        assert direction == SoftSignalDirection.NEGATIVE

    def test_revisions_positive_when_mostly_beats(self):
        revisions = [
            EarningsRevision(symbol="X", date=date(2024, 3, 31), period="Q1",
                             actual_eps=Decimal("2.5"), estimated_eps=Decimal("2.0"),
                             surprise=Decimal("0.5"), surprise_pct=Decimal("25")),
            EarningsRevision(symbol="X", date=date(2023, 12, 31), period="Q4",
                             actual_eps=Decimal("2.1"), estimated_eps=Decimal("2.0"),
                             surprise=Decimal("0.1"), surprise_pct=Decimal("5")),
            EarningsRevision(symbol="X", date=date(2023, 9, 30), period="Q3",
                             actual_eps=Decimal("1.9"), estimated_eps=Decimal("1.8"),
                             surprise=Decimal("0.1"), surprise_pct=Decimal("5.6")),
            EarningsRevision(symbol="X", date=date(2023, 6, 30), period="Q2",
                             actual_eps=Decimal("1.8"), estimated_eps=Decimal("1.7"),
                             surprise=Decimal("0.1"), surprise_pct=Decimal("5.9")),
        ]
        raw_stub = MagicMock()
        raw_stub.earnings_revisions = revisions
        direction, _ = _read_revisions(raw_stub)
        assert direction == SoftSignalDirection.POSITIVE

    def test_conflict_detected(self):
        """POSITIVE insider + NEGATIVE revisions should set conflict_flag."""
        raw_stub = MagicMock()
        raw_stub.insider_transactions = [
            InsiderTransaction(symbol="X", filing_date=date(2024, 1, 1),
                               transaction_date=date(2024, 1, 1), name="CEO",
                               transaction_type="buy", shares=Decimal("100000"),
                               value=Decimal("10_000_000")),
        ]
        raw_stub.earnings_revisions = [
            EarningsRevision(symbol="X", date=date(2024, 3, 31), period="Q1",
                             actual_eps=Decimal("1.0"), estimated_eps=Decimal("2.0"),
                             surprise=Decimal("-1.0"), surprise_pct=Decimal("-50")),
            EarningsRevision(symbol="X", date=date(2023, 12, 31), period="Q4",
                             actual_eps=Decimal("1.5"), estimated_eps=Decimal("2.0"),
                             surprise=Decimal("-0.5"), surprise_pct=Decimal("-25")),
            EarningsRevision(symbol="X", date=date(2023, 9, 30), period="Q3",
                             actual_eps=Decimal("1.4"), estimated_eps=Decimal("1.9"),
                             surprise=Decimal("-0.5"), surprise_pct=Decimal("-26")),
            EarningsRevision(symbol="X", date=date(2023, 6, 30), period="Q2",
                             actual_eps=Decimal("1.4"), estimated_eps=Decimal("1.9"),
                             surprise=Decimal("-0.5"), surprise_pct=Decimal("-26")),
        ]

        kpis_stub = MagicMock()
        kpis_stub.cash_flow_annual.buybacks = []

        signals = build_soft_signals(raw_stub, kpis_stub)
        assert signals.conflict_flag is True
        assert signals.conflict_description != ""


# ── _lean tests ───────────────────────────────────────────────────────────────

class TestLean:
    def _make_scorecard(self, composite: float) -> "ScoreCard":
        from fundalyzer.decide.models import PillarScore, PillarVerdict, ScoreCard
        d = Decimal(str(composite))
        pillar = PillarScore(
            name="test", score=d,
            verdict=PillarVerdict.IN_LINE, key_metrics_vs_peers={},
        )
        return ScoreCard(
            income=pillar, momentum=pillar,
            valuation=pillar, capital=pillar, composite=d,
        )

    def _make_position(self, pos: ValuationHistoryPosition) -> "ValuationPosition":
        from fundalyzer.decide.models import ValuationPosition
        return ValuationPosition(
            position=pos, current_pe=Decimal("20"),
            historical_median_pe=Decimal("20"),
            deviation_from_median_pct=Decimal("0"),
            current_ps=UNAVAILABLE, peer_median_ps=UNAVAILABLE,
        )

    def _make_signals(self, *dirs: SoftSignalDirection) -> "SoftSignals":
        from fundalyzer.decide.models import SoftSignals
        insider, revisions, buybacks = dirs[0], dirs[1], dirs[2]
        return SoftSignals(
            insider_activity=insider, insider_detail="",
            estimate_revisions=revisions, revision_detail="",
            buyback_activity=buybacks, buyback_detail="",
            conflict_flag=False, conflict_description="",
        )

    def test_invest_when_high_score_neutral_signals(self):
        NEU, POS = SoftSignalDirection.NEUTRAL, SoftSignalDirection.POSITIVE
        sc = self._make_scorecard(7.0)
        vp = self._make_position(ValuationHistoryPosition.IN_LINE)
        assert derive_lean(sc, vp, self._make_signals(NEU, POS, NEU)) == InvestmentLean.INVEST

    def test_avoid_when_low_composite(self):
        NEU = SoftSignalDirection.NEUTRAL
        sc = self._make_scorecard(3.0)
        vp = self._make_position(ValuationHistoryPosition.IN_LINE)
        assert derive_lean(sc, vp, self._make_signals(NEU, NEU, NEU)) == InvestmentLean.AVOID

    def test_hold_when_middle_composite(self):
        NEU = SoftSignalDirection.NEUTRAL
        sc = self._make_scorecard(5.0)
        vp = self._make_position(ValuationHistoryPosition.IN_LINE)
        assert derive_lean(sc, vp, self._make_signals(NEU, NEU, NEU)) == InvestmentLean.HOLD

    def test_hold_when_good_score_but_majority_negative_and_richer(self):
        NEG, NEU = SoftSignalDirection.NEGATIVE, SoftSignalDirection.NEUTRAL
        sc = self._make_scorecard(7.0)
        vp = self._make_position(ValuationHistoryPosition.RICHER)
        assert derive_lean(sc, vp, self._make_signals(NEG, NEG, NEU)) == InvestmentLean.HOLD

    def test_avoid_medium_score_richer_majority_negative(self):
        NEG, NEU = SoftSignalDirection.NEGATIVE, SoftSignalDirection.NEUTRAL
        sc = self._make_scorecard(4.5)
        vp = self._make_position(ValuationHistoryPosition.RICHER)
        assert derive_lean(sc, vp, self._make_signals(NEG, NEG, NEU)) == InvestmentLean.AVOID


# ── End-to-end decide() with mocked LLM ──────────────────────────────────────

class TestDecideEndToEnd:
    def _mock_tool(self, raw_input: dict) -> MagicMock:
        block = MagicMock()
        block.type = "tool_use"
        block.input = raw_input
        usage = MagicMock()
        usage.input_tokens = 400
        usage.output_tokens = 100
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = "tool_use"
        resp.usage = usage
        return resp

    def test_decide_returns_investment_decision(self, aapl_data):
        from fundalyzer.decide import decide
        from fundalyzer.decide.models import InvestmentDecision
        from fundalyzer.interpret.models import Claim, DashboardNarrative, Interpretation

        raw, kpis, peer_set = aapl_data

        # Stub interpretation
        narrative = DashboardNarrative(
            headline="Revenue grew 2% YoY to $391B.",
            body="Margins held steady.",
            claims=[Claim(statement="Revenue grew.", data_points=["revenue=391B"])],
            trend_verdict="STABLE",
        )
        interp = Interpretation(
            income=narrative, momentum=narrative,
            valuation=narrative, capital=narrative,
            overall_summary="Stable business with steady fundamentals.",
        )

        mock_api = MagicMock()
        assumption_resp = self._mock_tool({
            "base_narrative": "Base case assumes 5% annual revenue growth from analyst estimates.",
            "bull_narrative": "Bull case applies 15pp growth uplift and 10% P/E expansion.",
        })
        justification_resp = self._mock_tool({
            "justification": "AAPL composite 6.5/10, IN_LINE valuation, positive signals.",
        })
        mock_api.create.side_effect = [assumption_resp, justification_resp]

        decision = decide(kpis, peer_set, interp, raw, messages_api=mock_api)

        assert isinstance(decision, InvestmentDecision)
        assert decision.ticker == "AAPL"
        assert decision.lean in InvestmentLean
        assert decision.justification != ""

    def test_caveats_always_present(self, aapl_data):
        from fundalyzer.decide import decide
        from fundalyzer.decide.models import (
            CAVEAT_GARBAGE_IN_GARBAGE_OUT,
            CAVEAT_PROJECTION_NOT_GUARANTEED,
            CAVEAT_QUALITY_NOT_TIMING,
        )
        from fundalyzer.interpret.models import DashboardNarrative, Interpretation

        raw, kpis, peer_set = aapl_data
        narrative = DashboardNarrative(
            headline="Revenue grew.", body=".", claims=[], trend_verdict="STABLE"
        )
        interp = Interpretation(
            income=narrative, momentum=narrative,
            valuation=narrative, capital=narrative,
            overall_summary="Summary.",
        )
        mock_api = MagicMock()
        mock_api.create.return_value = self._mock_tool({
            "base_narrative": "Base.", "bull_narrative": "Bull.",
            "justification": "Justification.",
        })

        decision = decide(kpis, peer_set, interp, raw, messages_api=mock_api)

        assert decision.caveat_quality_not_timing == CAVEAT_QUALITY_NOT_TIMING
        assert decision.caveat_projection_not_guaranteed == CAVEAT_PROJECTION_NOT_GUARANTEED
        assert decision.caveat_garbage_in_garbage_out == CAVEAT_GARBAGE_IN_GARBAGE_OUT

    def test_assumption_narrative_filled(self, aapl_data):
        from fundalyzer.decide import decide
        from fundalyzer.interpret.models import DashboardNarrative, Interpretation

        raw, kpis, peer_set = aapl_data
        narrative = DashboardNarrative(
            headline="Revenue grew.", body=".", claims=[], trend_verdict="STABLE"
        )
        interp = Interpretation(
            income=narrative, momentum=narrative,
            valuation=narrative, capital=narrative,
            overall_summary="Summary.",
        )
        mock_api = MagicMock()
        assumption_resp = self._mock_tool({
            "base_narrative": "Base case assumes analyst revenue consensus.",
            "bull_narrative": "Bull case applies 15pp growth uplift.",
        })
        justification_resp = self._mock_tool({"justification": "The lean is INVEST."})
        mock_api.create.side_effect = [assumption_resp, justification_resp]

        decision = decide(kpis, peer_set, interp, raw, messages_api=mock_api)

        assert decision.projection.base_case.assumption_narrative != ""
        assert decision.projection.bull_case.assumption_narrative != ""
