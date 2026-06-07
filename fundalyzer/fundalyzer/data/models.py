# Architecture contract: values here are raw API responses — no LLM-generated figures.
from decimal import Decimal
from datetime import date
from typing import Literal
from pydantic import BaseModel

# Explicit sentinel for a field that no provider returned.
# Never use 0 or None as a stand-in for missing data.
UNAVAILABLE: Literal["UNAVAILABLE"] = "UNAVAILABLE"
Unavailable = Literal["UNAVAILABLE"]

# Convenience union aliases used throughout the schemas.
MaybeDecimal = Decimal | Unavailable
MaybeInt = int | Unavailable


class CompanyProfile(BaseModel):
    symbol: str
    company_name: str
    sector: str
    industry: str
    market_cap: MaybeDecimal
    price: MaybeDecimal
    description: str = ""
    peer_symbols: list[str] = []


class IncomeStatement(BaseModel):
    symbol: str
    fiscal_year: int
    # "annual" | "Q1" | "Q2" | "Q3" | "Q4"
    period: str
    report_date: date
    revenue: MaybeDecimal
    cost_of_revenue: MaybeDecimal
    gross_profit: MaybeDecimal
    operating_income: MaybeDecimal
    net_income: MaybeDecimal
    ebitda: MaybeDecimal
    interest_expense: MaybeDecimal
    depreciation_amortization: MaybeDecimal
    income_tax_expense: MaybeDecimal
    eps_basic: MaybeDecimal
    eps_diluted: MaybeDecimal
    shares_basic: MaybeDecimal
    shares_diluted: MaybeDecimal


class BalanceSheet(BaseModel):
    symbol: str
    fiscal_year: int
    period: str
    report_date: date
    total_assets: MaybeDecimal
    total_equity: MaybeDecimal
    total_debt: MaybeDecimal
    net_debt: MaybeDecimal
    cash_and_equivalents: MaybeDecimal
    short_term_investments: MaybeDecimal
    current_assets: MaybeDecimal
    current_liabilities: MaybeDecimal
    inventory: Decimal | None = None
    accounts_receivable: Decimal | None = None
    retained_earnings: MaybeDecimal
    goodwill: Decimal | None = None
    intangible_assets: Decimal | None = None


class CashFlowStatement(BaseModel):
    symbol: str
    fiscal_year: int
    period: str
    report_date: date
    operating_cash_flow: MaybeDecimal
    capital_expenditure: MaybeDecimal
    free_cash_flow: MaybeDecimal
    stock_based_compensation: Decimal | None = None
    buybacks: Decimal | None = None
    dividends_paid: Decimal | None = None


class SharesOutstanding(BaseModel):
    symbol: str
    date: date
    shares: Decimal  # absolute share count (not in millions)


class AnalystEstimate(BaseModel):
    symbol: str
    period_end: date
    period: str  # "annual" | "Q1" ... "Q4"
    revenue_avg: MaybeDecimal
    revenue_low: MaybeDecimal
    revenue_high: MaybeDecimal
    eps_avg: MaybeDecimal
    eps_low: MaybeDecimal
    eps_high: MaybeDecimal
    net_income_avg: MaybeDecimal
    num_analysts_revenue: MaybeInt
    num_analysts_eps: MaybeInt


class PriceTargetConsensus(BaseModel):
    symbol: str
    target_high: MaybeDecimal
    target_low: MaybeDecimal
    target_consensus: MaybeDecimal
    target_median: MaybeDecimal


class EarningsRevision(BaseModel):
    symbol: str
    date: date  # fiscal period end date
    period: str
    actual_eps: MaybeDecimal
    estimated_eps: MaybeDecimal
    surprise: MaybeDecimal        # actual − estimated
    surprise_pct: MaybeDecimal    # surprise / |estimated| × 100


class InsiderTransaction(BaseModel):
    symbol: str
    filing_date: date
    transaction_date: date
    name: str
    title: str | None = None
    transaction_type: str   # "buy" | "sell"
    shares: Decimal
    price_per_share: Decimal | None = None
    value: Decimal | None = None  # shares × price


class RawFinancials(BaseModel):
    ticker: str
    profile: CompanyProfile
    income_statements_annual: list[IncomeStatement]
    income_statements_quarterly: list[IncomeStatement]
    balance_sheets_annual: list[BalanceSheet]
    balance_sheets_quarterly: list[BalanceSheet]
    cash_flow_statements_annual: list[CashFlowStatement]
    cash_flow_statements_quarterly: list[CashFlowStatement]
    # None = endpoint entirely unavailable from all providers
    # []   = endpoint available but returned no data
    shares_history: list[SharesOutstanding] | None = None
    analyst_estimates: list[AnalystEstimate] | None = None
    price_target: PriceTargetConsensus | None = None
    earnings_revisions: list[EarningsRevision] | None = None
    insider_transactions: list[InsiderTransaction] | None = None
