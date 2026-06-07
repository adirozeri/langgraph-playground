# Architecture contract: return real yfinance data only — never fabricate or estimate a number.
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .base import FinancialDataProvider
from .cache import Cache, DiskCache
from .models import (
    UNAVAILABLE,
    AnalystEstimate,
    BalanceSheet,
    CashFlowStatement,
    CompanyProfile,
    EarningsRevision,
    IncomeStatement,
    InsiderTransaction,
    MaybeDecimal,
    PriceTargetConsensus,
    RawFinancials,
    SharesOutstanding,
)

log = logging.getLogger(__name__)


def _dec(val: Any) -> MaybeDecimal:
    if val is None:
        return UNAVAILABLE
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return UNAVAILABLE


def _dec_opt(val: Any) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _ts_to_date(ts: Any) -> date | None:
    """Convert pandas Timestamp or datetime to date."""
    try:
        return ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])
    except Exception:
        return None


def _df_val(df: Any, row: str, col: Any) -> Any:
    """Safe cell access on a yfinance DataFrame (index=metrics, columns=dates)."""
    try:
        return df.loc[row, col]
    except (KeyError, TypeError):
        return None


class YFinanceProvider(FinancialDataProvider):
    """yfinance fallback adapter.

    Fills gaps left by FMP's free tier. Called by CompositeProvider, not
    directly by application code.  Not all endpoints are available; missing
    ones return None so the composite knows to keep whatever FMP returned.
    """

    def __init__(self, cache: Cache | None = None) -> None:
        self._cache = cache or DiskCache()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ticker(self, symbol: str) -> Any:
        import yfinance as yf  # lazy import so tests can mock easily
        return yf.Ticker(symbol)

    def _income_from_df(self, symbol: str, df: Any, period: str) -> list[IncomeStatement]:
        """Convert a yfinance income statement DataFrame to our schema."""
        if df is None or df.empty:
            return []
        results = []
        for col in df.columns:
            d = _ts_to_date(col)
            if d is None:
                continue

            def g(row: str) -> Any:
                return _df_val(df, row, col)

            revenue = _dec(g("Total Revenue"))
            cogs = _dec(g("Cost Of Revenue") or g("Cost of Revenue"))
            gross = _dec(g("Gross Profit"))
            opinc = _dec(g("Operating Income") or g("EBIT"))
            netinc = _dec(g("Net Income"))
            ebitda = _dec(g("EBITDA") or g("Normalized EBITDA"))
            interest = _dec(g("Interest Expense") or g("Interest Expense Non Operating"))
            da = _dec(g("Reconciled Depreciation") or g("Depreciation Amortization Depletion"))
            tax = _dec(g("Tax Provision") or g("Income Tax Expense"))
            eps_basic = _dec(g("Basic EPS"))
            eps_dil = _dec(g("Diluted EPS"))
            sh_basic = _dec(g("Basic Average Shares"))
            sh_dil = _dec(g("Diluted Average Shares"))

            results.append(IncomeStatement(
                symbol=symbol,
                fiscal_year=d.year,
                period=period,
                report_date=d,
                revenue=revenue,
                cost_of_revenue=cogs,
                gross_profit=gross,
                operating_income=opinc,
                net_income=netinc,
                ebitda=ebitda,
                interest_expense=interest,
                depreciation_amortization=da,
                income_tax_expense=tax,
                eps_basic=eps_basic,
                eps_diluted=eps_dil,
                shares_basic=sh_basic,
                shares_diluted=sh_dil,
            ))
        return results

    def _balance_from_df(self, symbol: str, df: Any, period: str) -> list[BalanceSheet]:
        if df is None or df.empty:
            return []
        results = []
        for col in df.columns:
            d = _ts_to_date(col)
            if d is None:
                continue

            def g(row: str) -> Any:
                return _df_val(df, row, col)

            results.append(BalanceSheet(
                symbol=symbol,
                fiscal_year=d.year,
                period=period,
                report_date=d,
                total_assets=_dec(g("Total Assets")),
                total_equity=_dec(g("Stockholders Equity") or g("Total Equity Gross Minority Interest")),
                total_debt=_dec(g("Total Debt")),
                net_debt=_dec(g("Net Debt")),
                cash_and_equivalents=_dec(g("Cash And Cash Equivalents")),
                short_term_investments=_dec(g("Other Short Term Investments") or g("Available For Sale Securities")),
                current_assets=_dec(g("Current Assets")),
                current_liabilities=_dec(g("Current Liabilities")),
                inventory=_dec_opt(g("Inventory")),
                accounts_receivable=_dec_opt(g("Receivables") or g("Accounts Receivable")),
                retained_earnings=_dec(g("Retained Earnings")),
                goodwill=_dec_opt(g("Goodwill")),
                intangible_assets=_dec_opt(g("Other Intangible Assets")),
            ))
        return results

    def _cashflow_from_df(self, symbol: str, df: Any, period: str) -> list[CashFlowStatement]:
        if df is None or df.empty:
            return []
        results = []
        for col in df.columns:
            d = _ts_to_date(col)
            if d is None:
                continue

            def g(row: str) -> Any:
                return _df_val(df, row, col)

            ocf = _dec(g("Operating Cash Flow") or g("Cash Flow From Continuing Operating Activities"))
            capex = _dec(g("Capital Expenditure") or g("Purchase Of PPE"))
            fcf = _dec(g("Free Cash Flow"))
            sbc = _dec_opt(g("Stock Based Compensation"))
            buybacks = _dec_opt(g("Repurchase Of Capital Stock") or g("Common Stock Repurchased"))
            divs = _dec_opt(g("Cash Dividends Paid") or g("Common Stock Dividend Paid"))

            results.append(CashFlowStatement(
                symbol=symbol,
                fiscal_year=d.year,
                period=period,
                report_date=d,
                operating_cash_flow=ocf,
                capital_expenditure=capex,
                free_cash_flow=fcf,
                stock_based_compensation=sbc,
                buybacks=buybacks,
                dividends_paid=divs,
            ))
        return results

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_raw_financials(
        self,
        ticker: str,
        quarters: int = 12,
        annual_years: int = 10,
    ) -> RawFinancials:
        ticker = ticker.upper()
        t = self._ticker(ticker)

        try:
            info = t.info or {}
        except Exception:
            info = {}

        profile = CompanyProfile(
            symbol=ticker,
            company_name=info.get("longName", ""),
            sector=info.get("sector", ""),
            industry=info.get("industry", ""),
            market_cap=_dec(info.get("marketCap")),
            price=_dec(info.get("currentPrice") or info.get("regularMarketPrice")),
            description=info.get("longBusinessSummary", ""),
        )

        def safe(fn: Any) -> Any:
            try:
                return fn()
            except Exception as exc:
                log.debug("yfinance error: %s", exc)
                return None

        income_a = self._income_from_df(ticker, safe(lambda: t.income_stmt), "annual")
        income_q = self._income_from_df(ticker, safe(lambda: t.quarterly_income_stmt), "Q")
        balance_a = self._balance_from_df(ticker, safe(lambda: t.balance_sheet), "annual")
        balance_q = self._balance_from_df(ticker, safe(lambda: t.quarterly_balance_sheet), "Q")
        cashflow_a = self._cashflow_from_df(ticker, safe(lambda: t.cashflow), "annual")
        cashflow_q = self._cashflow_from_df(ticker, safe(lambda: t.quarterly_cashflow), "Q")

        # Shares outstanding history from info snapshot (single point)
        shares_history: list[SharesOutstanding] | None = None
        sh = info.get("sharesOutstanding")
        if sh:
            shares_history = [SharesOutstanding(
                symbol=ticker,
                date=date.today(),
                shares=Decimal(str(sh)),
            )]

        # Analyst price targets
        price_target: PriceTargetConsensus | None = None
        try:
            pt = t.analyst_price_targets
            if isinstance(pt, dict) and pt:
                price_target = PriceTargetConsensus(
                    symbol=ticker,
                    target_high=_dec(pt.get("high")),
                    target_low=_dec(pt.get("low")),
                    target_consensus=_dec(pt.get("mean")),
                    target_median=_dec(pt.get("median")),
                )
        except Exception:
            pass

        # Analyst EPS estimates (annual forward periods)
        analyst_estimates: list[AnalystEstimate] | None = None
        try:
            ee = t.earnings_estimate
            if ee is not None and not ee.empty:
                analyst_estimates = []
                for idx in ee.index:
                    row = ee.loc[idx]
                    analyst_estimates.append(AnalystEstimate(
                        symbol=ticker,
                        period_end=date.today(),  # yfinance doesn't give exact period end
                        period=str(idx),
                        revenue_avg=UNAVAILABLE,
                        revenue_low=UNAVAILABLE,
                        revenue_high=UNAVAILABLE,
                        eps_avg=_dec(row.get("avg")),
                        eps_low=_dec(row.get("low")),
                        eps_high=_dec(row.get("high")),
                        net_income_avg=UNAVAILABLE,
                        num_analysts_revenue=UNAVAILABLE,
                        num_analysts_eps=_dec(row.get("numberOfAnalysts")),  # type: ignore[arg-type]
                    ))
        except Exception:
            pass

        # Insider transactions
        insider_transactions: list[InsiderTransaction] | None = None
        try:
            df = t.insider_transactions
            if df is not None and not df.empty:
                insider_transactions = []
                for _, row in df.iterrows():
                    d = _ts_to_date(row.get("Start Date") or row.get("startDate"))
                    shares_tx = _dec_opt(row.get("Shares") or row.get("shares"))
                    if d is None or shares_tx is None:
                        continue
                    tx_text = str(row.get("Transaction", "") or row.get("transaction", "")).lower()
                    tx_type = "buy" if "buy" in tx_text or "purchase" in tx_text else "sell"
                    insider_transactions.append(InsiderTransaction(
                        symbol=ticker,
                        filing_date=d,
                        transaction_date=d,
                        name=str(row.get("Insider", "") or row.get("insider", "")),
                        title=str(row.get("Position", "") or "") or None,
                        transaction_type=tx_type,
                        shares=shares_tx,
                        price_per_share=None,
                        value=_dec_opt(row.get("Value") or row.get("value")),
                    ))
        except Exception:
            pass

        return RawFinancials(
            ticker=ticker,
            profile=profile,
            income_statements_annual=income_a,
            income_statements_quarterly=income_q,
            balance_sheets_annual=balance_a,
            balance_sheets_quarterly=balance_q,
            cash_flow_statements_annual=cashflow_a,
            cash_flow_statements_quarterly=cashflow_q,
            shares_history=shares_history,
            analyst_estimates=analyst_estimates,
            price_target=price_target,
            earnings_revisions=None,  # yfinance doesn't provide revision history
            insider_transactions=insider_transactions,
        )
