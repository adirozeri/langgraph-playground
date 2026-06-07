"""Metrics module tests — pure-Python arithmetic verified against hand-checked values.

Fixture data: AAPL from tests/fixtures/fmp/ (same recorded responses as test_data.py).
All expected values computed from the fixture numbers by hand; formula shown in each test.

Pillars with full hand-checked coverage: Profitability, Financial Strength.
Trend classifier and valuation have targeted coverage.
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
from fundalyzer.data.models import UNAVAILABLE, RawFinancials
from fundalyzer.metrics._trend import classify_trend
from fundalyzer.metrics.compute import compute
from fundalyzer.metrics.models import (
    MetricPoint,
    MetricSeries,
    Trend,
    TickerKPIs,
)

# ── Fixture helpers ───────────────────────────────────────────────────────────

FIXTURES = Path(__file__).parent / "fixtures" / "fmp"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def make_fmp() -> FMPProvider:
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
def raw() -> RawFinancials:
    return make_fmp().get_raw_financials("AAPL")


@pytest.fixture(scope="module")
def kpis(raw: RawFinancials) -> TickerKPIs:
    return compute(raw)


# ── Hand-checked constants (from fixture JSON) ────────────────────────────────
#
# FY2024 (index -1 in oldest-first annual series after sorting)
REV_2024  = Decimal("391035000000")
GP_2024   = Decimal("180683000000")
OPINC_2024 = Decimal("123516000000")
NETINC_2024 = Decimal("93736000000")
EBITDA_2024 = Decimal("134958000000")
EPS_2024  = Decimal("6.08")
TAX_2024  = Decimal("29749000000")

REV_2023  = Decimal("383285000000")
EPS_2023  = Decimal("6.13")
REV_2022  = Decimal("394328000000")
EPS_2022  = Decimal("6.11")

# Balance sheet FY2024
ASSETS_2024   = Decimal("364750000000")
EQUITY_2024   = Decimal("56269000000")
DEBT_2024     = Decimal("106629000000")
CASH_2024     = Decimal("29943000000")
CURASSETS_2024 = Decimal("152987000000")
CURLIAB_2024  = Decimal("176392000000")
EQUITY_2023   = Decimal("62146000000")

# Profile
PRICE      = Decimal("229.87")
MKTCAP     = Decimal("3484543880000")


# ─────────────────────────────────────────────────────────────────────────────
# PROFITABILITY PILLAR — full hand-checked coverage
# ─────────────────────────────────────────────────────────────────────────────

class TestProfitabilityAnnual:
    """All expected values computed as: formula(fixture_values)."""

    def _latest(self, series: MetricSeries) -> MetricPoint:
        return series[-1]  # oldest-first → last element is most recent

    def test_series_length(self, kpis: TickerKPIs) -> None:
        # Fixture has 3 annual records
        assert len(kpis.profitability_annual.gross_margin) == 3

    def test_oldest_first_ordering(self, kpis: TickerKPIs) -> None:
        dates = [p.period_date for p in kpis.profitability_annual.revenue]
        assert dates == sorted(dates)

    # ── Revenue ───────────────────────────────────────────────────────────────

    def test_revenue_value(self, kpis: TickerKPIs) -> None:
        # revenue is a passthrough; should equal fixture value exactly
        assert self._latest(kpis.profitability_annual.revenue).value == REV_2024

    def test_revenue_has_formula(self, kpis: TickerKPIs) -> None:
        pt = self._latest(kpis.profitability_annual.revenue)
        assert "revenue" in pt.formula

    def test_revenue_inputs_present(self, kpis: TickerKPIs) -> None:
        pt = self._latest(kpis.profitability_annual.revenue)
        assert "revenue" in pt.inputs

    # ── Gross Margin: gross_profit / revenue ─────────────────────────────────

    def test_gross_margin_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked: 180_683_000_000 / 391_035_000_000
        expected = GP_2024 / REV_2024
        actual = self._latest(kpis.profitability_annual.gross_margin).value
        assert actual == expected

    def test_gross_margin_inputs_traceable(self, kpis: TickerKPIs) -> None:
        pt = self._latest(kpis.profitability_annual.gross_margin)
        assert pt.inputs["gross_profit"] == str(GP_2024)
        assert pt.inputs["revenue"] == str(REV_2024)

    def test_gross_margin_formula_string(self, kpis: TickerKPIs) -> None:
        pt = self._latest(kpis.profitability_annual.gross_margin)
        assert "gross_profit" in pt.formula
        assert "revenue" in pt.formula

    def test_gross_margin_exceeds_operating(self, kpis: TickerKPIs) -> None:
        # gross > operating (SG&A and R&D are additional costs)
        gm = self._latest(kpis.profitability_annual.gross_margin).value
        om = self._latest(kpis.profitability_annual.operating_margin).value
        assert gm > om  # type: ignore[operator]

    # ── Operating Margin: operating_income / revenue ──────────────────────────

    def test_operating_margin_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked: 123_516_000_000 / 391_035_000_000
        expected = OPINC_2024 / REV_2024
        actual = self._latest(kpis.profitability_annual.operating_margin).value
        assert actual == expected

    # ── Net Margin: net_income / revenue ─────────────────────────────────────

    def test_net_margin_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked: 93_736_000_000 / 391_035_000_000
        expected = NETINC_2024 / REV_2024
        actual = self._latest(kpis.profitability_annual.net_margin).value
        assert actual == expected

    def test_net_margin_below_operating(self, kpis: TickerKPIs) -> None:
        om = self._latest(kpis.profitability_annual.operating_margin).value
        nm = self._latest(kpis.profitability_annual.net_margin).value
        assert nm <= om  # type: ignore[operator]

    # ── EBITDA Margin: ebitda / revenue ──────────────────────────────────────

    def test_ebitda_margin_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked: 134_958_000_000 / 391_035_000_000
        expected = EBITDA_2024 / REV_2024
        actual = self._latest(kpis.profitability_annual.ebitda_margin).value
        assert actual == expected

    def test_ebitda_margin_exceeds_operating(self, kpis: TickerKPIs) -> None:
        # EBITDA adds back D&A → higher than operating income
        em = self._latest(kpis.profitability_annual.ebitda_margin).value
        om = self._latest(kpis.profitability_annual.operating_margin).value
        assert em > om  # type: ignore[operator]

    # ── EPS ───────────────────────────────────────────────────────────────────

    def test_eps_diluted_fy2024(self, kpis: TickerKPIs) -> None:
        # direct passthrough from fixture
        assert self._latest(kpis.profitability_annual.eps_diluted).value == EPS_2024

    # ── Revenue Growth YoY ────────────────────────────────────────────────────

    def test_revenue_growth_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked: (391_035 - 383_285) / |383_285| = 7_750 / 383_285
        expected = (REV_2024 - REV_2023) / REV_2023
        actual = self._latest(kpis.profitability_annual.revenue_growth_yoy).value
        assert actual == expected

    def test_revenue_growth_fy2023(self, kpis: TickerKPIs) -> None:
        # hand-checked: (383_285 - 394_328) / |394_328| = -11_043 / 394_328 (negative)
        expected = (REV_2023 - REV_2022) / REV_2022
        # oldest-first: index 1 is FY2023
        actual = kpis.profitability_annual.revenue_growth_yoy[1].value
        assert actual == expected

    def test_revenue_growth_fy2023_is_negative(self, kpis: TickerKPIs) -> None:
        # Apple had revenue contraction in FY2023
        g = kpis.profitability_annual.revenue_growth_yoy[1].value
        assert g < Decimal("0")  # type: ignore[operator]

    def test_revenue_growth_oldest_is_unavailable(self, kpis: TickerKPIs) -> None:
        # No prior period available for the oldest record
        assert kpis.profitability_annual.revenue_growth_yoy[0].value == UNAVAILABLE

    # ── EPS Growth YoY ────────────────────────────────────────────────────────

    def test_eps_growth_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked: (6.08 - 6.13) / |6.13| = -0.05 / 6.13
        expected = (EPS_2024 - EPS_2023) / EPS_2023
        actual = self._latest(kpis.profitability_annual.eps_growth_yoy).value
        assert actual == expected

    def test_eps_growth_oldest_is_unavailable(self, kpis: TickerKPIs) -> None:
        assert kpis.profitability_annual.eps_growth_yoy[0].value == UNAVAILABLE

    # ── UNAVAILABLE propagation ───────────────────────────────────────────────

    def test_unavailable_revenue_produces_unavailable_margin(self, raw: RawFinancials) -> None:
        # FMP returns newest-first: stmts[0] = FY2024.
        # compute() sorts oldest-first, so FY2024 ends up at gross_margin[-1].
        stmts = list(raw.income_statements_annual)
        patched = stmts[0].model_copy(update={"revenue": UNAVAILABLE})
        stmts[0] = patched
        mutated = raw.model_copy(update={"income_statements_annual": stmts})
        kpis = compute(mutated)
        assert kpis.profitability_annual.gross_margin[-1].value == UNAVAILABLE


# ─────────────────────────────────────────────────────────────────────────────
# FINANCIAL STRENGTH PILLAR — full hand-checked coverage
# ─────────────────────────────────────────────────────────────────────────────

class TestFinancialStrengthAnnual:
    """All expected values computed from fixture constants defined above."""

    def _latest(self, series: MetricSeries) -> MetricPoint:
        return series[-1]

    def test_series_length(self, kpis: TickerKPIs) -> None:
        # 3 income statements × 2 balance sheets → 2 matched, 1 with UNAVAILABLE BS
        # Actually fixture has 3 income but only 2 balance sheet rows
        # So 2 rows will have a matching BS and 1 will emit UNAVAILABLE
        assert len(kpis.financial_strength_annual.debt_to_equity) == 3

    def test_unmatched_bs_is_unavailable(self, kpis: TickerKPIs) -> None:
        # FY2022 income has no matching balance sheet → D/E is UNAVAILABLE
        oldest_de = kpis.financial_strength_annual.debt_to_equity[0].value
        assert oldest_de == UNAVAILABLE

    # ── Debt / Equity: total_debt / total_equity ──────────────────────────────

    def test_debt_to_equity_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked: 106_629_000_000 / 56_269_000_000
        expected = DEBT_2024 / EQUITY_2024
        actual = self._latest(kpis.financial_strength_annual.debt_to_equity).value
        assert actual == expected

    def test_debt_to_equity_inputs(self, kpis: TickerKPIs) -> None:
        pt = self._latest(kpis.financial_strength_annual.debt_to_equity)
        assert pt.inputs["total_debt"] == str(DEBT_2024)
        assert pt.inputs["total_equity"] == str(EQUITY_2024)

    # ── Net Cash Position: cash − total_debt ─────────────────────────────────

    def test_net_cash_position_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked: 29_943_000_000 - 106_629_000_000 = -76_686_000_000 (net debt)
        expected = CASH_2024 - DEBT_2024
        actual = self._latest(kpis.financial_strength_annual.net_cash_position).value
        assert actual == expected

    def test_net_cash_is_negative_for_aapl(self, kpis: TickerKPIs) -> None:
        # Apple carries more debt than cash — net debt, not net cash
        pos = self._latest(kpis.financial_strength_annual.net_cash_position).value
        assert pos < Decimal("0")  # type: ignore[operator]

    # ── Current Ratio: current_assets / current_liabilities ──────────────────

    def test_current_ratio_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked: 152_987_000_000 / 176_392_000_000
        expected = CURASSETS_2024 / CURLIAB_2024
        actual = self._latest(kpis.financial_strength_annual.current_ratio).value
        assert actual == expected

    def test_current_ratio_below_one_for_aapl(self, kpis: TickerKPIs) -> None:
        # Apple famously runs with a sub-1 current ratio (paying suppliers slowly)
        cr = self._latest(kpis.financial_strength_annual.current_ratio).value
        assert cr < Decimal("1")  # type: ignore[operator]

    # ── ROE: net_income / avg_total_equity ───────────────────────────────────

    def test_roe_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked: 93_736_000_000 / ((62_146_000_000 + 56_269_000_000) / 2)
        avg_equity = (EQUITY_2023 + EQUITY_2024) / Decimal("2")
        expected = NETINC_2024 / avg_equity
        actual = self._latest(kpis.financial_strength_annual.roe).value
        assert actual == expected

    def test_roe_is_very_high_for_aapl(self, kpis: TickerKPIs) -> None:
        # Apple's ROE > 100 % due to aggressive buybacks shrinking equity base
        roe = self._latest(kpis.financial_strength_annual.roe).value
        assert roe > Decimal("1")  # type: ignore[operator]

    def test_roe_inputs_include_avg_equity(self, kpis: TickerKPIs) -> None:
        pt = self._latest(kpis.financial_strength_annual.roe)
        assert "avg_total_equity" in pt.inputs
        assert "net_income" in pt.inputs

    # ── ROIC: nopat / invested_capital ───────────────────────────────────────

    def test_roic_fy2024(self, kpis: TickerKPIs) -> None:
        # hand-checked step by step:
        # effective_tax_rate = income_tax / (net_income + income_tax)
        #                    = 29_749 / (93_736 + 29_749) = 29_749 / 123_485
        income_before_tax = NETINC_2024 + TAX_2024
        tax_rate = TAX_2024 / income_before_tax
        nopat = OPINC_2024 * (Decimal("1") - tax_rate)
        # invested_capital = equity + debt - cash
        inv_cap = EQUITY_2024 + DEBT_2024 - CASH_2024
        expected = nopat / inv_cap
        actual = self._latest(kpis.financial_strength_annual.roic).value
        assert actual == expected

    def test_roic_formula_string_references_nopat(self, kpis: TickerKPIs) -> None:
        pt = self._latest(kpis.financial_strength_annual.roic)
        assert "nopat" in pt.formula

    def test_roic_inputs_include_tax(self, kpis: TickerKPIs) -> None:
        pt = self._latest(kpis.financial_strength_annual.roic)
        assert "income_tax_expense" in pt.inputs


# ─────────────────────────────────────────────────────────────────────────────
# TREND CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────

def _make_series(values: list) -> MetricSeries:
    return [
        MetricPoint(
            value=Decimal(str(v)) if v != UNAVAILABLE else UNAVAILABLE,
            period="annual",
            period_date=date(2020 + i, 9, 30),
            formula="test",
            inputs={},
        )
        for i, v in enumerate(values)
    ]


class TestTrendClassifier:
    def test_accelerating(self) -> None:
        s = _make_series([1, 2, 3, 4, 5])
        r = classify_trend(s)
        assert r.trend == Trend.ACCELERATING

    def test_decelerating(self) -> None:
        s = _make_series([5, 4, 3, 2, 1])
        r = classify_trend(s)
        assert r.trend == Trend.DECELERATING

    def test_flat(self) -> None:
        s = _make_series([3, 3, 3, 3, 3])
        r = classify_trend(s)
        assert r.trend == Trend.FLAT

    def test_insufficient_data_two_points(self) -> None:
        s = _make_series([1, 2])
        r = classify_trend(s)
        assert r.trend == Trend.INSUFFICIENT_DATA
        assert r.normalized_slope is None
        assert r.n_periods == 2

    def test_insufficient_data_empty(self) -> None:
        r = classify_trend([])
        assert r.trend == Trend.INSUFFICIENT_DATA

    def test_unavailable_values_skipped(self) -> None:
        # Insert UNAVAILABLE in the middle; the 3 valid values still trend up
        s = _make_series([1, UNAVAILABLE, 2, UNAVAILABLE, 3])
        r = classify_trend(s)
        assert r.trend == Trend.ACCELERATING
        assert r.n_periods == 3

    def test_normalized_slope_is_decimal(self) -> None:
        s = _make_series([1, 2, 3, 4, 5])
        r = classify_trend(s)
        assert isinstance(r.normalized_slope, Decimal)

    def test_n_periods_counts_valid_only(self) -> None:
        s = _make_series([1, UNAVAILABLE, 2, 3])
        r = classify_trend(s)
        assert r.n_periods == 3

    def test_accelerating_applied_to_real_data(self, kpis: TickerKPIs) -> None:
        # Gross margin — just verify it returns a valid TrendResult (3 periods)
        r = classify_trend(kpis.profitability_annual.gross_margin)
        assert r.trend in Trend.__members__.values()
        assert r.n_periods == 3


# ─────────────────────────────────────────────────────────────────────────────
# VALUATION PILLAR — targeted coverage
# ─────────────────────────────────────────────────────────────────────────────

class TestValuation:
    def test_trailing_pe_series_has_one_point(self, kpis: TickerKPIs) -> None:
        assert len(kpis.valuation.trailing_pe) == 1

    def test_trailing_pe_value(self, kpis: TickerKPIs) -> None:
        # TTM EPS from quarterly fixture: 0.97 + 1.40 + 1.53 + 2.18 = 6.08
        ttm_eps = Decimal("0.97") + Decimal("1.40") + Decimal("1.53") + Decimal("2.18")
        expected = PRICE / ttm_eps
        actual = kpis.valuation.trailing_pe[0].value
        assert actual == expected

    def test_forward_pe_value(self, kpis: TickerKPIs) -> None:
        # Fixture forward_eps_avg = 6.80 (first annual estimate)
        expected = PRICE / Decimal("6.80")
        actual = kpis.valuation.forward_pe[0].value
        assert actual == expected

    def test_price_to_sales(self, kpis: TickerKPIs) -> None:
        # TTM revenue = sum of 4 quarters = 94930+85777+90753+119575
        ttm_rev = (
            Decimal("94930000000") + Decimal("85777000000")
            + Decimal("90753000000") + Decimal("119575000000")
        )
        expected = MKTCAP / ttm_rev
        actual = kpis.valuation.price_to_sales[0].value
        assert actual == expected

    def test_ev_ebitda(self, kpis: TickerKPIs) -> None:
        # EV = market_cap + debt - cash; TTM EBITDA = sum of 4 quarters
        ev = MKTCAP + DEBT_2024 - CASH_2024
        ttm_ebitda = (
            Decimal("34545000000") + Decimal("30620000000")
            + Decimal("31741000000") + Decimal("43562000000")
        )
        expected = ev / ttm_ebitda
        actual = kpis.valuation.ev_to_ebitda[0].value
        assert actual == expected

    def test_price_to_book(self, kpis: TickerKPIs) -> None:
        # latest balance sheet equity = EQUITY_2024
        expected = MKTCAP / EQUITY_2024
        actual = kpis.valuation.price_to_book[0].value
        assert actual == expected

    def test_all_valuation_points_have_formula(self, kpis: TickerKPIs) -> None:
        for series in (
            kpis.valuation.trailing_pe,
            kpis.valuation.forward_pe,
            kpis.valuation.price_to_sales,
            kpis.valuation.ev_to_ebitda,
            kpis.valuation.price_to_book,
        ):
            for pt in series:
                assert pt.formula, "formula must not be empty"
                assert pt.inputs, "inputs must not be empty"


# ─────────────────────────────────────────────────────────────────────────────
# CASH FLOW PILLAR — targeted coverage
# ─────────────────────────────────────────────────────────────────────────────

class TestCashFlow:
    def _latest(self, series: MetricSeries) -> MetricPoint:
        return series[-1]

    def test_fcf_margin_fy2024(self, kpis: TickerKPIs) -> None:
        # fcf = 99_360_000_000, revenue = 391_035_000_000
        fcf = Decimal("99360000000")
        expected = fcf / REV_2024
        actual = self._latest(kpis.cash_flow_annual.fcf_margin).value
        assert actual == expected

    def test_fcf_yield_fy2024(self, kpis: TickerKPIs) -> None:
        # fcf = 99_360_000_000, market_cap = 3_484_543_880_000
        fcf = Decimal("99360000000")
        expected = fcf / MKTCAP
        actual = self._latest(kpis.cash_flow_annual.fcf_yield).value
        assert actual == expected

    def test_ocf_passthrough(self, kpis: TickerKPIs) -> None:
        ocf = self._latest(kpis.cash_flow_annual.operating_cash_flow).value
        assert ocf == Decimal("108807000000")

    def test_fcf_passthrough(self, kpis: TickerKPIs) -> None:
        fcf = self._latest(kpis.cash_flow_annual.free_cash_flow).value
        assert fcf == Decimal("99360000000")
