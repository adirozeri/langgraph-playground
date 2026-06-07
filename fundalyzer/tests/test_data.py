"""Data-module tests — no live API calls; all HTTP replaced by fixture responses."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fundalyzer.data.cache import NullCache
from fundalyzer.data.composite import merge
from fundalyzer.data.fmp import FMPProvider
from fundalyzer.data.models import (
    UNAVAILABLE,
    AnalystEstimate,
    BalanceSheet,
    CashFlowStatement,
    CompanyProfile,
    EarningsRevision,
    IncomeStatement,
    InsiderTransaction,
    PriceTargetConsensus,
    RawFinancials,
    SharesOutstanding,
)

FIXTURES = Path(__file__).parent / "fixtures" / "fmp"


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# Fixture-backed FMPProvider factory
# ---------------------------------------------------------------------------

def _fmp_responses() -> dict[str, Any]:
    return {
        "profile":                  load("aapl_profile.json"),
        "income_annual_10":         load("aapl_income_annual.json"),
        "income_quarter_12":        load("aapl_income_quarter.json"),
        "balance_annual_10":        load("aapl_balance_annual.json"),
        "balance_quarter_12":       load("aapl_balance_quarter.json"),
        "cashflow_annual_10":       load("aapl_cashflow_annual.json"),
        "cashflow_quarter_12":      load("aapl_cashflow_quarter.json"),
        "shares_outstanding":       load("aapl_shares_outstanding.json"),
        "analyst_estimates":        load("aapl_analyst_estimates.json"),
        "price_target_consensus":   load("aapl_price_target_consensus.json"),
        "earnings_surprises":       load("aapl_earnings_surprises.json"),
        "insider_trading":          load("aapl_insider_trading.json"),
    }


def make_fmp(responses: dict[str, Any] | None = None) -> FMPProvider:
    """FMPProvider whose _get is replaced by a dict lookup (no HTTP, no cache I/O)."""
    resp = responses or _fmp_responses()

    provider = FMPProvider(api_key="test", cache=NullCache())

    def fake_get(path: str, ticker: str, cache_key: str, **params: Any) -> Any:
        return resp.get(cache_key)

    provider._get = fake_get  # type: ignore[method-assign]
    return provider


@pytest.fixture()
def raw() -> RawFinancials:
    return make_fmp().get_raw_financials("AAPL")


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class TestProfile:
    def test_fields(self, raw: RawFinancials) -> None:
        p = raw.profile
        assert isinstance(p, CompanyProfile)
        assert p.symbol == "AAPL"
        assert p.company_name == "Apple Inc."
        assert p.sector == "Technology"
        assert p.industry == "Consumer Electronics"
        assert p.price == Decimal("229.87")
        assert p.market_cap == Decimal("3484543880000")


# ---------------------------------------------------------------------------
# Income statements
# ---------------------------------------------------------------------------

class TestIncomeStatements:
    def test_annual_count(self, raw: RawFinancials) -> None:
        assert len(raw.income_statements_annual) == 3

    def test_annual_latest_fields(self, raw: RawFinancials) -> None:
        stmt = raw.income_statements_annual[0]
        assert isinstance(stmt, IncomeStatement)
        assert stmt.fiscal_year == 2024
        assert stmt.period == "annual"
        assert stmt.report_date == date(2024, 9, 28)
        assert stmt.revenue == Decimal("391035000000")
        assert stmt.gross_profit == Decimal("180683000000")
        assert stmt.operating_income == Decimal("123516000000")
        assert stmt.net_income == Decimal("93736000000")
        assert stmt.ebitda == Decimal("134958000000")
        assert stmt.eps_diluted == Decimal("6.08")
        assert stmt.shares_diluted == Decimal("15408095000")

    def test_annual_interest_expense(self, raw: RawFinancials) -> None:
        assert raw.income_statements_annual[0].interest_expense == Decimal("3931000000")

    def test_quarterly_count(self, raw: RawFinancials) -> None:
        assert len(raw.income_statements_quarterly) == 4

    def test_quarterly_period_label(self, raw: RawFinancials) -> None:
        periods = [s.period for s in raw.income_statements_quarterly]
        assert "Q4" in periods
        assert "Q3" in periods

    def test_quarterly_latest(self, raw: RawFinancials) -> None:
        q4 = raw.income_statements_quarterly[0]
        assert q4.period == "Q4"
        assert q4.revenue == Decimal("94930000000")


# ---------------------------------------------------------------------------
# Balance sheets
# ---------------------------------------------------------------------------

class TestBalanceSheets:
    def test_annual_count(self, raw: RawFinancials) -> None:
        assert len(raw.balance_sheets_annual) == 2

    def test_annual_latest_fields(self, raw: RawFinancials) -> None:
        bs = raw.balance_sheets_annual[0]
        assert isinstance(bs, BalanceSheet)
        assert bs.fiscal_year == 2024
        assert bs.total_assets == Decimal("364750000000")
        assert bs.total_equity == Decimal("56269000000")
        assert bs.total_debt == Decimal("106629000000")
        assert bs.net_debt == Decimal("76686000000")
        assert bs.cash_and_equivalents == Decimal("29943000000")
        # inventory is a legitimate optional field — not UNAVAILABLE
        assert bs.inventory == Decimal("7286000000")

    def test_retained_earnings_can_be_negative(self, raw: RawFinancials) -> None:
        # Apple's retained earnings are negative (buybacks exceed cumulative income)
        bs = raw.balance_sheets_annual[0]
        assert bs.retained_earnings == Decimal("-19154000000")


# ---------------------------------------------------------------------------
# Cash flow statements
# ---------------------------------------------------------------------------

class TestCashFlowStatements:
    def test_annual_count(self, raw: RawFinancials) -> None:
        assert len(raw.cash_flow_statements_annual) == 2

    def test_annual_latest_fields(self, raw: RawFinancials) -> None:
        cf = raw.cash_flow_statements_annual[0]
        assert isinstance(cf, CashFlowStatement)
        assert cf.operating_cash_flow == Decimal("108807000000")
        assert cf.capital_expenditure == Decimal("-9447000000")
        assert cf.free_cash_flow == Decimal("99360000000")
        assert cf.stock_based_compensation == Decimal("11688000000")
        assert cf.buybacks == Decimal("-94949000000")
        assert cf.dividends_paid == Decimal("-15234000000")


# ---------------------------------------------------------------------------
# Shares outstanding
# ---------------------------------------------------------------------------

class TestSharesOutstanding:
    def test_not_none(self, raw: RawFinancials) -> None:
        assert raw.shares_history is not None

    def test_count(self, raw: RawFinancials) -> None:
        assert len(raw.shares_history) == 4  # type: ignore[arg-type]

    def test_latest_converted_from_thousands(self, raw: RawFinancials) -> None:
        latest = raw.shares_history[0]  # type: ignore[index]
        assert isinstance(latest, SharesOutstanding)
        # fixture has 15204137 (thousands) → should be ×1000
        assert latest.shares == Decimal("15204137000")
        assert latest.date == date(2024, 9, 28)


# ---------------------------------------------------------------------------
# Analyst estimates
# ---------------------------------------------------------------------------

class TestAnalystEstimates:
    def test_not_none(self, raw: RawFinancials) -> None:
        assert raw.analyst_estimates is not None

    def test_count(self, raw: RawFinancials) -> None:
        assert len(raw.analyst_estimates) == 2  # type: ignore[arg-type]

    def test_fields(self, raw: RawFinancials) -> None:
        est = raw.analyst_estimates[0]  # type: ignore[index]
        assert isinstance(est, AnalystEstimate)
        assert est.eps_avg == Decimal("6.80")
        assert est.num_analysts_eps == 32
        assert est.revenue_avg == Decimal("415000000000")


# ---------------------------------------------------------------------------
# Price target consensus
# ---------------------------------------------------------------------------

class TestPriceTarget:
    def test_not_none(self, raw: RawFinancials) -> None:
        assert raw.price_target is not None

    def test_fields(self, raw: RawFinancials) -> None:
        pt = raw.price_target
        assert isinstance(pt, PriceTargetConsensus)
        assert pt.target_consensus == Decimal("237.5")
        assert pt.target_high == Decimal("300.0")
        assert pt.target_low == Decimal("165.0")
        assert pt.target_median == Decimal("240.0")


# ---------------------------------------------------------------------------
# Earnings revisions (surprises)
# ---------------------------------------------------------------------------

class TestEarningsRevisions:
    def test_not_none(self, raw: RawFinancials) -> None:
        assert raw.earnings_revisions is not None

    def test_count(self, raw: RawFinancials) -> None:
        assert len(raw.earnings_revisions) == 4  # type: ignore[arg-type]

    def test_surprise_computed(self, raw: RawFinancials) -> None:
        rev = raw.earnings_revisions[0]  # type: ignore[index]
        assert isinstance(rev, EarningsRevision)
        assert rev.actual_eps == Decimal("0.97")
        assert rev.estimated_eps == Decimal("0.94")
        # surprise = 0.97 - 0.94 = 0.03
        assert rev.surprise == Decimal("0.97") - Decimal("0.94")
        assert rev.surprise != UNAVAILABLE

    def test_surprise_pct_computed(self, raw: RawFinancials) -> None:
        rev = raw.earnings_revisions[0]  # type: ignore[index]
        assert rev.surprise_pct != UNAVAILABLE
        expected = (Decimal("0.03") / abs(Decimal("0.94"))) * 100
        assert abs(rev.surprise_pct - expected) < Decimal("0.01")  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Insider transactions
# ---------------------------------------------------------------------------

class TestInsiderTransactions:
    def test_not_none(self, raw: RawFinancials) -> None:
        assert raw.insider_transactions is not None

    def test_count(self, raw: RawFinancials) -> None:
        assert len(raw.insider_transactions) == 3  # type: ignore[arg-type]

    def test_sell_normalised(self, raw: RawFinancials) -> None:
        tx = raw.insider_transactions[0]  # type: ignore[index]
        assert isinstance(tx, InsiderTransaction)
        assert tx.transaction_type == "sell"
        assert tx.name == "Jeff Williams"
        assert tx.shares == Decimal("5000")
        assert tx.price_per_share == Decimal("228.52")
        assert tx.value == Decimal("5000") * Decimal("228.52")

    def test_buy_normalised(self, raw: RawFinancials) -> None:
        # Cook acquisition (A = Acquisition)
        cook_tx = next(
            t for t in raw.insider_transactions  # type: ignore[union-attr]
            if t.name == "Timothy D. Cook"
        )
        assert cook_tx.transaction_type == "buy"


# ---------------------------------------------------------------------------
# UNAVAILABLE sentinel behaviour
# ---------------------------------------------------------------------------

class TestUnavailableSentinel:
    def test_premium_endpoint_returns_none_list(self) -> None:
        """When FMP returns 402/403 for a list endpoint, the list field is None."""
        responses = _fmp_responses()
        # Simulate premium gate: _get returns None for these keys
        responses["shares_outstanding"] = None
        responses["analyst_estimates"] = None
        responses["insider_trading"] = None

        fmp = make_fmp(responses)
        raw = fmp.get_raw_financials("AAPL")

        assert raw.shares_history is None
        assert raw.analyst_estimates is None
        assert raw.insider_transactions is None

    def test_null_numeric_field_becomes_unavailable(self) -> None:
        """A null value from the API on a required numeric field → UNAVAILABLE, never 0."""
        responses = _fmp_responses()
        # Corrupt the income statement to have null revenue
        mutated = [dict(r) for r in responses["income_annual_10"]]
        mutated[0]["revenue"] = None
        responses["income_annual_10"] = mutated

        fmp = make_fmp(responses)
        raw = fmp.get_raw_financials("AAPL")

        assert raw.income_statements_annual[0].revenue == UNAVAILABLE


# ---------------------------------------------------------------------------
# Composite merge logic
# ---------------------------------------------------------------------------

class TestMerge:
    def _make_income(self, **overrides: Any) -> IncomeStatement:
        defaults = dict(
            symbol="AAPL",
            fiscal_year=2024,
            period="annual",
            report_date=date(2024, 9, 28),
            revenue=UNAVAILABLE,
            cost_of_revenue=UNAVAILABLE,
            gross_profit=UNAVAILABLE,
            operating_income=UNAVAILABLE,
            net_income=UNAVAILABLE,
            ebitda=UNAVAILABLE,
            interest_expense=UNAVAILABLE,
            depreciation_amortization=UNAVAILABLE,
            income_tax_expense=UNAVAILABLE,
            eps_basic=UNAVAILABLE,
            eps_diluted=UNAVAILABLE,
            shares_basic=UNAVAILABLE,
            shares_diluted=UNAVAILABLE,
        )
        defaults.update(overrides)
        return IncomeStatement(**defaults)

    def _stub_raw(self, income_annual: list[IncomeStatement]) -> RawFinancials:
        profile = CompanyProfile(
            symbol="AAPL",
            company_name="Apple",
            sector="Tech",
            industry="CE",
            market_cap=Decimal("1"),
            price=Decimal("1"),
        )
        return RawFinancials(
            ticker="AAPL",
            profile=profile,
            income_statements_annual=income_annual,
            income_statements_quarterly=[],
            balance_sheets_annual=[],
            balance_sheets_quarterly=[],
            cash_flow_statements_annual=[],
            cash_flow_statements_quarterly=[],
        )

    def test_unavailable_filled_by_fallback(self) -> None:
        primary_stmt = self._make_income(revenue=UNAVAILABLE)
        fallback_stmt = self._make_income(revenue=Decimal("391035000000"))

        merged = merge(
            self._stub_raw([primary_stmt]),
            self._stub_raw([fallback_stmt]),
        )
        assert merged.income_statements_annual[0].revenue == Decimal("391035000000")

    def test_primary_wins_over_fallback(self) -> None:
        primary_stmt = self._make_income(revenue=Decimal("100"))
        fallback_stmt = self._make_income(revenue=Decimal("999"))

        merged = merge(
            self._stub_raw([primary_stmt]),
            self._stub_raw([fallback_stmt]),
        )
        assert merged.income_statements_annual[0].revenue == Decimal("100")

    def test_fallback_period_appended_when_absent_in_primary(self) -> None:
        primary_stmt = self._make_income(report_date=date(2024, 9, 28))
        fallback_stmt = self._make_income(
            report_date=date(2023, 9, 30),
            fiscal_year=2023,
            revenue=Decimal("383285000000"),
        )

        merged = merge(
            self._stub_raw([primary_stmt]),
            self._stub_raw([fallback_stmt]),
        )
        assert len(merged.income_statements_annual) == 2

    def test_none_list_filled_by_fallback(self) -> None:
        primary = self._stub_raw([])
        fallback = self._stub_raw([])
        fallback.shares_history = [
            SharesOutstanding(symbol="AAPL", date=date(2024, 9, 28), shares=Decimal("15204137000"))
        ]
        merged = merge(primary, fallback)
        assert merged.shares_history is not None
        assert len(merged.shares_history) == 1
