# Architecture contract: return real FMP data only — never fabricate or estimate a number.
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ..settings import settings
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
    MaybeInt,
    PriceTargetConsensus,
    RawFinancials,
    SharesOutstanding,
)

log = logging.getLogger(__name__)

# 401 = invalid/missing key; treat the same as 402/403 so the pipeline
# can fall back to yfinance instead of crashing.
_PREMIUM_CODES = {401, 402, 403}


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _dec(val: Any) -> MaybeDecimal:
    """Raw API value → Decimal, or UNAVAILABLE if null / unparseable."""
    if val is None:
        return UNAVAILABLE
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return UNAVAILABLE


def _dec_opt(val: Any) -> Decimal | None:
    """Raw API value → Decimal | None.  None is a legitimate absence (e.g. no inventory)."""
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _int(val: Any) -> MaybeInt:
    if val is None:
        return UNAVAILABLE
    try:
        return int(val)
    except (TypeError, ValueError):
        return UNAVAILABLE


def _date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _period(fmp_period: str) -> str:
    """Normalise FMP period strings: 'FY' → 'annual', rest kept as-is."""
    return "annual" if fmp_period == "FY" else fmp_period


# ---------------------------------------------------------------------------
# FMP Provider
# ---------------------------------------------------------------------------

class FMPProvider(FinancialDataProvider):
    """Financial Modeling Prep adapter (v3 API).

    Docs: https://site.financialmodelingprep.com/developer/docs
    Free-tier limitations are handled gracefully: 402/403 responses cause the
    relevant list to be returned as None (endpoint entirely unavailable).
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        cache: Cache | None = None,
    ) -> None:
        self._api_key = api_key or settings.fmp_api_key
        self._base_url = (base_url or settings.fmp_base_url).rstrip("/")
        self._cache = cache or DiskCache()
        self._client = httpx.Client(base_url=self._base_url, timeout=30)

    @property
    def _v4_base(self) -> str:
        """FMP v4 base URL derived from the configured v3 URL."""
        return self._base_url.replace("/api/v3", "/api/v4").replace("/v3", "/v4")

    # ------------------------------------------------------------------
    # Internal HTTP + cache
    # ------------------------------------------------------------------

    def _get(self, path: str, ticker: str, cache_key: str, **params: Any) -> list | dict | None:
        """GET with disk cache.  Returns None when endpoint is premium (402/403)."""
        cached = self._cache.get(ticker, cache_key)
        if cached is not None:
            return cached

        try:
            resp = self._client.get(
                path,
                params={"apikey": self._api_key, **params},
            )
            if resp.status_code in _PREMIUM_CODES:
                log.debug("FMP: premium endpoint %s (status %d)", path, resp.status_code)
                return None
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in _PREMIUM_CODES:
                return None
            raise

        self._cache.set(ticker, cache_key, data)
        return data

    # ------------------------------------------------------------------
    # Fetch + normalise: each method returns the normalised list or None
    # ------------------------------------------------------------------

    def _fetch_profile(self, ticker: str) -> CompanyProfile:
        raw = self._get(f"/profile/{ticker}", ticker, "profile")
        if not raw or not isinstance(raw, list):
            raise ValueError(f"No FMP profile data for {ticker!r}")
        r = raw[0]
        return CompanyProfile(
            symbol=r.get("symbol", ticker),
            company_name=r.get("companyName", ""),
            sector=r.get("sector", ""),
            industry=r.get("industry", ""),
            market_cap=_dec(r.get("mktCap")),
            price=_dec(r.get("price")),
            description=r.get("description", ""),
            peer_symbols=[],  # fetched separately if needed
            employees=int(r["fullTimeEmployees"]) if r.get("fullTimeEmployees") else None,
        )

    def _fetch_income(
        self, ticker: str, period: str, limit: int
    ) -> list[IncomeStatement]:
        key = f"income_{period}_{limit}"
        raw = self._get(
            f"/income-statement/{ticker}",
            ticker,
            key,
            period=period,
            limit=limit,
        )
        if not raw or not isinstance(raw, list):
            return []
        return [self._norm_income(ticker, r) for r in raw]

    def _norm_income(self, ticker: str, r: dict) -> IncomeStatement:
        return IncomeStatement(
            symbol=ticker,
            fiscal_year=int(r.get("calendarYear") or 0),
            period=_period(r.get("period", "")),
            report_date=_date(r.get("date")) or date.min,
            revenue=_dec(r.get("revenue")),
            cost_of_revenue=_dec(r.get("costOfRevenue")),
            gross_profit=_dec(r.get("grossProfit")),
            operating_income=_dec(r.get("operatingIncome")),
            net_income=_dec(r.get("netIncome")),
            ebitda=_dec(r.get("ebitda")),
            interest_expense=_dec(r.get("interestExpense")),
            depreciation_amortization=_dec(r.get("depreciationAndAmortization")),
            income_tax_expense=_dec(r.get("incomeTaxExpense")),
            eps_basic=_dec(r.get("eps")),
            eps_diluted=_dec(r.get("epsDiluted")),
            shares_basic=_dec(r.get("weightedAverageShsOut")),
            shares_diluted=_dec(r.get("weightedAverageShsOutDil")),
        )

    def _fetch_balance(self, ticker: str, period: str, limit: int) -> list[BalanceSheet]:
        key = f"balance_{period}_{limit}"
        raw = self._get(
            f"/balance-sheet-statement/{ticker}",
            ticker,
            key,
            period=period,
            limit=limit,
        )
        if not raw or not isinstance(raw, list):
            return []
        return [self._norm_balance(ticker, r) for r in raw]

    def _norm_balance(self, ticker: str, r: dict) -> BalanceSheet:
        return BalanceSheet(
            symbol=ticker,
            fiscal_year=int(r.get("calendarYear") or 0),
            period=_period(r.get("period", "")),
            report_date=_date(r.get("date")) or date.min,
            total_assets=_dec(r.get("totalAssets")),
            total_equity=_dec(r.get("totalEquity")),
            total_debt=_dec(r.get("totalDebt")),
            net_debt=_dec(r.get("netDebt")),
            cash_and_equivalents=_dec(r.get("cashAndCashEquivalents")),
            short_term_investments=_dec(r.get("shortTermInvestments")),
            current_assets=_dec(r.get("totalCurrentAssets")),
            current_liabilities=_dec(r.get("totalCurrentLiabilities")),
            inventory=_dec_opt(r.get("inventory")),
            accounts_receivable=_dec_opt(r.get("netReceivables")),
            retained_earnings=_dec(r.get("retainedEarnings")),
            goodwill=_dec_opt(r.get("goodwill")),
            intangible_assets=_dec_opt(r.get("intangibleAssets")),
        )

    def _fetch_cashflow(self, ticker: str, period: str, limit: int) -> list[CashFlowStatement]:
        key = f"cashflow_{period}_{limit}"
        raw = self._get(
            f"/cash-flow-statement/{ticker}",
            ticker,
            key,
            period=period,
            limit=limit,
        )
        if not raw or not isinstance(raw, list):
            return []
        return [self._norm_cashflow(ticker, r) for r in raw]

    def _norm_cashflow(self, ticker: str, r: dict) -> CashFlowStatement:
        return CashFlowStatement(
            symbol=ticker,
            fiscal_year=int(r.get("calendarYear") or 0),
            period=_period(r.get("period", "")),
            report_date=_date(r.get("date")) or date.min,
            operating_cash_flow=_dec(r.get("operatingCashFlow") or r.get("netCashProvidedByOperatingActivities")),
            capital_expenditure=_dec(r.get("capitalExpenditure")),
            free_cash_flow=_dec(r.get("freeCashFlow")),
            stock_based_compensation=_dec_opt(r.get("stockBasedCompensation")),
            buybacks=_dec_opt(r.get("commonStockRepurchased")),
            dividends_paid=_dec_opt(r.get("dividendsPaid")),
        )

    def _fetch_shares(self, ticker: str) -> list[SharesOutstanding] | None:
        raw = self._get(
            f"/historical-shares-outstanding/{ticker}",
            ticker,
            "shares_outstanding",
        )
        if raw is None:
            return None
        if not isinstance(raw, list):
            return []
        result = []
        for r in raw:
            d = _date(r.get("date"))
            shares_raw = r.get("outstandingShares")
            if d is None or shares_raw is None:
                continue
            # FMP returns shares in thousands for this endpoint
            result.append(SharesOutstanding(
                symbol=ticker,
                date=d,
                shares=Decimal(str(shares_raw)) * 1000,
            ))
        return result

    def _fetch_estimates(self, ticker: str) -> list[AnalystEstimate] | None:
        raw = self._get(f"/analyst-estimates/{ticker}", ticker, "analyst_estimates")
        if raw is None:
            return None
        if not isinstance(raw, list):
            return []
        result = []
        for r in raw:
            d = _date(r.get("date"))
            if d is None:
                continue
            result.append(AnalystEstimate(
                symbol=ticker,
                period_end=d,
                period=r.get("period", "annual"),
                revenue_avg=_dec(r.get("estimatedRevenueAvg")),
                revenue_low=_dec(r.get("estimatedRevenueLow")),
                revenue_high=_dec(r.get("estimatedRevenueHigh")),
                eps_avg=_dec(r.get("estimatedEpsAvg")),
                eps_low=_dec(r.get("estimatedEpsLow")),
                eps_high=_dec(r.get("estimatedEpsHigh")),
                net_income_avg=_dec(r.get("estimatedNetIncomeAvg")),
                num_analysts_revenue=_int(r.get("numberAnalystEstimatedRevenue")),
                num_analysts_eps=_int(r.get("numberAnalystsEstimatedEps")),
            ))
        return result

    def _fetch_price_target(self, ticker: str) -> PriceTargetConsensus | None:
        raw = self._get(
            f"/price-target-consensus/{ticker}",
            ticker,
            "price_target_consensus",
        )
        if raw is None:
            return None
        # endpoint returns a list with one dict
        r = raw[0] if isinstance(raw, list) and raw else (raw if isinstance(raw, dict) else {})
        return PriceTargetConsensus(
            symbol=ticker,
            target_high=_dec(r.get("targetHigh")),
            target_low=_dec(r.get("targetLow")),
            target_consensus=_dec(r.get("targetConsensus")),
            target_median=_dec(r.get("targetMedian")),
        )

    def _fetch_earnings_surprises(self, ticker: str) -> list[EarningsRevision] | None:
        raw = self._get(f"/earnings-surprises/{ticker}", ticker, "earnings_surprises")
        if raw is None:
            return None
        if not isinstance(raw, list):
            return []
        result = []
        for r in raw:
            d = _date(r.get("date"))
            if d is None:
                continue
            actual = _dec(r.get("actualEarningResult"))
            estimated = _dec(r.get("estimatedEarning"))
            if actual != UNAVAILABLE and estimated != UNAVAILABLE:
                surprise: MaybeDecimal = actual - estimated  # type: ignore[operator]
                try:
                    surprise_pct: MaybeDecimal = (surprise / abs(estimated)) * 100  # type: ignore[arg-type]
                except (InvalidOperation, ZeroDivisionError):
                    surprise_pct = UNAVAILABLE
            else:
                surprise = UNAVAILABLE
                surprise_pct = UNAVAILABLE
            result.append(EarningsRevision(
                symbol=ticker,
                date=d,
                period=r.get("period", "annual"),
                actual_eps=actual,
                estimated_eps=estimated,
                surprise=surprise,
                surprise_pct=surprise_pct,
            ))
        return result

    def _fetch_insider(self, ticker: str) -> list[InsiderTransaction] | None:
        raw = self._get(f"/insider-trading/{ticker}", ticker, "insider_trading")
        if raw is None:
            return None
        if not isinstance(raw, list):
            return []
        result = []
        for r in raw:
            filing_d = _date(r.get("filingDate"))
            tx_d = _date(r.get("transactionDate"))
            if filing_d is None or tx_d is None:
                continue
            acq = r.get("acquistionOrDisposition", "")
            tx_type = "buy" if acq == "A" else "sell"
            shares_raw = _dec_opt(r.get("securitiesTransacted"))
            if shares_raw is None:
                continue
            price = _dec_opt(r.get("price"))
            result.append(InsiderTransaction(
                symbol=ticker,
                filing_date=filing_d,
                transaction_date=tx_d,
                name=r.get("reportingName", ""),
                title=r.get("typeOfOwner") or None,
                transaction_type=tx_type,
                shares=shares_raw,
                price_per_share=price,
                value=shares_raw * price if price is not None else None,
            ))
        return result

    def _get_v4(self, path: str, ticker: str, cache_key: str, **params: Any) -> list | dict | None:
        """GET from FMP v4 API with disk cache.  Returns None on premium gate."""
        cached = self._cache.get(ticker, cache_key)
        if cached is not None:
            return cached

        url = f"{self._v4_base}{path}"
        try:
            resp = httpx.get(url, params={"apikey": self._api_key, **params}, timeout=30)
            if resp.status_code in _PREMIUM_CODES:
                log.debug("FMP v4: premium endpoint %s (status %d)", path, resp.status_code)
                return None
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in _PREMIUM_CODES:
                return None
            raise

        self._cache.set(ticker, cache_key, data)
        return data

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_peer_tickers(self, ticker: str, max_peers: int = 10) -> list[str]:
        """Return FMP's peer list for *ticker* via the v4 stock_peers endpoint.

        Returns [] if the endpoint is gated (402/403) or returns no data.
        Response is cached for the current calendar day.
        """
        ticker = ticker.upper()
        raw = self._get_v4("/stock_peers", ticker, "stock_peers", symbol=ticker)
        if not raw or not isinstance(raw, list):
            return []
        peers_raw = raw[0].get("peersList", []) if raw else []
        return [t for t in peers_raw if t.upper() != ticker][:max_peers]

    def get_raw_financials(
        self,
        ticker: str,
        quarters: int = 12,
        annual_years: int = 10,
    ) -> RawFinancials:
        ticker = ticker.upper()

        profile = self._fetch_profile(ticker)
        income_annual = self._fetch_income(ticker, "annual", annual_years)
        income_quarter = self._fetch_income(ticker, "quarter", quarters)
        balance_annual = self._fetch_balance(ticker, "annual", annual_years)
        balance_quarter = self._fetch_balance(ticker, "quarter", quarters)
        cashflow_annual = self._fetch_cashflow(ticker, "annual", annual_years)
        cashflow_quarter = self._fetch_cashflow(ticker, "quarter", quarters)
        shares = self._fetch_shares(ticker)
        estimates = self._fetch_estimates(ticker)
        price_target = self._fetch_price_target(ticker)
        earnings_revisions = self._fetch_earnings_surprises(ticker)
        insider = self._fetch_insider(ticker)

        return RawFinancials(
            ticker=ticker,
            profile=profile,
            income_statements_annual=income_annual,
            income_statements_quarterly=income_quarter,
            balance_sheets_annual=balance_annual,
            balance_sheets_quarterly=balance_quarter,
            cash_flow_statements_annual=cashflow_annual,
            cash_flow_statements_quarterly=cashflow_quarter,
            shares_history=shares,
            analyst_estimates=estimates,
            price_target=price_target,
            earnings_revisions=earnings_revisions,
            insider_transactions=insider,
        )
