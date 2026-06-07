# Architecture contract: merge only real provider data — never fill gaps with invented values.
from __future__ import annotations

from .base import FinancialDataProvider
from .cache import Cache, DiskCache, NullCache
from .fmp import FMPProvider
from .models import (
    UNAVAILABLE,
    AnalystEstimate,
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
    RawFinancials,
)
from .yfinance_provider import YFinanceProvider


def _merge_field(primary: object, fallback: object) -> object:
    """Return fallback value when primary is UNAVAILABLE; else keep primary."""
    return fallback if primary == UNAVAILABLE else primary


def _merge_income(p: IncomeStatement, f: IncomeStatement) -> IncomeStatement:
    return IncomeStatement(
        symbol=p.symbol,
        fiscal_year=p.fiscal_year,
        period=p.period,
        report_date=p.report_date,
        revenue=_merge_field(p.revenue, f.revenue),
        cost_of_revenue=_merge_field(p.cost_of_revenue, f.cost_of_revenue),
        gross_profit=_merge_field(p.gross_profit, f.gross_profit),
        operating_income=_merge_field(p.operating_income, f.operating_income),
        net_income=_merge_field(p.net_income, f.net_income),
        ebitda=_merge_field(p.ebitda, f.ebitda),
        interest_expense=_merge_field(p.interest_expense, f.interest_expense),
        depreciation_amortization=_merge_field(p.depreciation_amortization, f.depreciation_amortization),
        income_tax_expense=_merge_field(p.income_tax_expense, f.income_tax_expense),
        eps_basic=_merge_field(p.eps_basic, f.eps_basic),
        eps_diluted=_merge_field(p.eps_diluted, f.eps_diluted),
        shares_basic=_merge_field(p.shares_basic, f.shares_basic),
        shares_diluted=_merge_field(p.shares_diluted, f.shares_diluted),
    )  # type: ignore[return-value]


def _merge_balance(p: BalanceSheet, f: BalanceSheet) -> BalanceSheet:
    return BalanceSheet(
        symbol=p.symbol,
        fiscal_year=p.fiscal_year,
        period=p.period,
        report_date=p.report_date,
        total_assets=_merge_field(p.total_assets, f.total_assets),
        total_equity=_merge_field(p.total_equity, f.total_equity),
        total_debt=_merge_field(p.total_debt, f.total_debt),
        net_debt=_merge_field(p.net_debt, f.net_debt),
        cash_and_equivalents=_merge_field(p.cash_and_equivalents, f.cash_and_equivalents),
        short_term_investments=_merge_field(p.short_term_investments, f.short_term_investments),
        current_assets=_merge_field(p.current_assets, f.current_assets),
        current_liabilities=_merge_field(p.current_liabilities, f.current_liabilities),
        inventory=p.inventory if p.inventory is not None else f.inventory,
        accounts_receivable=p.accounts_receivable if p.accounts_receivable is not None else f.accounts_receivable,
        retained_earnings=_merge_field(p.retained_earnings, f.retained_earnings),
        goodwill=p.goodwill if p.goodwill is not None else f.goodwill,
        intangible_assets=p.intangible_assets if p.intangible_assets is not None else f.intangible_assets,
    )  # type: ignore[return-value]


def _merge_cashflow(p: CashFlowStatement, f: CashFlowStatement) -> CashFlowStatement:
    return CashFlowStatement(
        symbol=p.symbol,
        fiscal_year=p.fiscal_year,
        period=p.period,
        report_date=p.report_date,
        operating_cash_flow=_merge_field(p.operating_cash_flow, f.operating_cash_flow),
        capital_expenditure=_merge_field(p.capital_expenditure, f.capital_expenditure),
        free_cash_flow=_merge_field(p.free_cash_flow, f.free_cash_flow),
        stock_based_compensation=p.stock_based_compensation if p.stock_based_compensation is not None else f.stock_based_compensation,
        buybacks=p.buybacks if p.buybacks is not None else f.buybacks,
        dividends_paid=p.dividends_paid if p.dividends_paid is not None else f.dividends_paid,
    )  # type: ignore[return-value]


def _merge_statements(
    primary: list,
    fallback: list,
    merge_fn: object,
) -> list:
    """Merge two statement lists by report_date; primary fields win except when UNAVAILABLE."""
    fb_by_date = {s.report_date: s for s in fallback}
    result = []
    for stmt in primary:
        fb = fb_by_date.get(stmt.report_date)
        result.append(merge_fn(stmt, fb) if fb is not None else stmt)  # type: ignore[operator]
    # Append fallback periods absent from primary
    primary_dates = {s.report_date for s in primary}
    for s in fallback:
        if s.report_date not in primary_dates:
            result.append(s)
    return result


def merge(primary: RawFinancials, fallback: RawFinancials) -> RawFinancials:
    """Merge two RawFinancials; primary wins, fallback fills UNAVAILABLE slots."""
    return RawFinancials(
        ticker=primary.ticker,
        profile=primary.profile,
        income_statements_annual=_merge_statements(
            primary.income_statements_annual,
            fallback.income_statements_annual,
            _merge_income,
        ),
        income_statements_quarterly=_merge_statements(
            primary.income_statements_quarterly,
            fallback.income_statements_quarterly,
            _merge_income,
        ),
        balance_sheets_annual=_merge_statements(
            primary.balance_sheets_annual,
            fallback.balance_sheets_annual,
            _merge_balance,
        ),
        balance_sheets_quarterly=_merge_statements(
            primary.balance_sheets_quarterly,
            fallback.balance_sheets_quarterly,
            _merge_balance,
        ),
        cash_flow_statements_annual=_merge_statements(
            primary.cash_flow_statements_annual,
            fallback.cash_flow_statements_annual,
            _merge_cashflow,
        ),
        cash_flow_statements_quarterly=_merge_statements(
            primary.cash_flow_statements_quarterly,
            fallback.cash_flow_statements_quarterly,
            _merge_cashflow,
        ),
        shares_history=primary.shares_history if primary.shares_history is not None else fallback.shares_history,
        analyst_estimates=primary.analyst_estimates if primary.analyst_estimates is not None else fallback.analyst_estimates,
        price_target=primary.price_target if primary.price_target is not None else fallback.price_target,
        earnings_revisions=primary.earnings_revisions if primary.earnings_revisions is not None else fallback.earnings_revisions,
        insider_transactions=primary.insider_transactions if primary.insider_transactions is not None else fallback.insider_transactions,
    )


class CompositeProvider(FinancialDataProvider):
    """Fetches from FMP first; fills gaps with yfinance."""

    def __init__(
        self,
        fmp: FMPProvider | None = None,
        yf: YFinanceProvider | None = None,
        cache: Cache | None = None,
    ) -> None:
        _cache = cache or DiskCache()
        self._fmp = fmp or FMPProvider(cache=_cache)
        self._yf = yf or YFinanceProvider(cache=_cache)

    def get_raw_financials(
        self,
        ticker: str,
        quarters: int = 12,
        annual_years: int = 10,
    ) -> RawFinancials:
        fmp_data = self._fmp.get_raw_financials(ticker, quarters, annual_years)
        yf_data = self._yf.get_raw_financials(ticker, quarters, annual_years)
        return merge(fmp_data, yf_data)
