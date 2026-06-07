# Architecture contract: pure Python arithmetic on API values — no LLM involvement.
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ..data.models import BalanceSheet, IncomeStatement
from ._helpers import make_point, ratio
from .models import UNAVAILABLE, MaybeDecimal, MetricPoint, MetricSeries, FinancialStrengthKPIs


def _effective_tax_rate(stmt: IncomeStatement) -> MaybeDecimal:
    """income_tax_expense / (net_income + income_tax_expense).

    income_before_tax ≈ net_income + income_tax_expense when minority interest
    and extraordinary items are negligible — valid for the vast majority of US
    large-caps.
    """
    tax = stmt.income_tax_expense
    net = stmt.net_income
    if tax == UNAVAILABLE or net == UNAVAILABLE:
        return UNAVAILABLE
    try:
        income_before_tax = Decimal(str(net)) + Decimal(str(tax))
        if income_before_tax == 0:
            return UNAVAILABLE
        return Decimal(str(tax)) / income_before_tax
    except (InvalidOperation, TypeError):
        return UNAVAILABLE


def _nopat(stmt: IncomeStatement) -> MaybeDecimal:
    """Net Operating Profit After Tax = operating_income × (1 − effective_tax_rate)."""
    tax_rate = _effective_tax_rate(stmt)
    if tax_rate == UNAVAILABLE or stmt.operating_income == UNAVAILABLE:
        return UNAVAILABLE
    try:
        return Decimal(str(stmt.operating_income)) * (Decimal("1") - Decimal(str(tax_rate)))
    except (InvalidOperation, TypeError):
        return UNAVAILABLE


def _invested_capital(bs: BalanceSheet) -> MaybeDecimal:
    """total_equity + total_debt − cash_and_equivalents."""
    eq = bs.total_equity
    debt = bs.total_debt
    cash = bs.cash_and_equivalents
    if eq == UNAVAILABLE or debt == UNAVAILABLE or cash == UNAVAILABLE:
        return UNAVAILABLE
    try:
        return Decimal(str(eq)) + Decimal(str(debt)) - Decimal(str(cash))
    except (InvalidOperation, TypeError):
        return UNAVAILABLE


def _avg_equity(curr: BalanceSheet, prev: BalanceSheet | None) -> MaybeDecimal:
    """Average of ending equity for current and prior period."""
    curr_eq = curr.total_equity
    if curr_eq == UNAVAILABLE:
        return UNAVAILABLE
    if prev is None:
        return curr_eq  # no prior period: use ending equity only
    prev_eq = prev.total_equity
    if prev_eq == UNAVAILABLE:
        return curr_eq
    try:
        return (Decimal(str(curr_eq)) + Decimal(str(prev_eq))) / Decimal("2")
    except (InvalidOperation, TypeError):
        return UNAVAILABLE


def compute_strength(
    income: list[IncomeStatement],  # oldest-first
    balance: list[BalanceSheet],    # oldest-first
) -> FinancialStrengthKPIs:
    # Index balance sheets by date for O(1) lookup
    bs_by_date = {b.report_date: b for b in balance}
    bs_list = balance  # for prior-period lookup by position

    d2e: MetricSeries = []
    net_cash: MetricSeries = []
    curr_ratio: MetricSeries = []
    roe_series: MetricSeries = []
    roic_series: MetricSeries = []

    for stmt in income:
        bs = bs_by_date.get(stmt.report_date)
        kw = dict(period=stmt.period, period_date=stmt.report_date)

        if bs is None:
            # No matching balance sheet → all strength metrics unavailable this period
            for container in (d2e, net_cash, curr_ratio, roe_series, roic_series):
                container.append(make_point(
                    UNAVAILABLE,
                    formula="(no matching balance sheet)",
                    period=stmt.period,
                    period_date=stmt.report_date,
                ))
            continue

        # ── Debt / Equity ─────────────────────────────────────────────────────
        d2e.append(ratio(
            bs.total_debt, bs.total_equity,
            formula="total_debt / total_equity",
            total_debt=bs.total_debt,
            total_equity=bs.total_equity,
            **kw,
        ))

        # ── Net Cash Position ─────────────────────────────────────────────────
        cash_pos: MaybeDecimal
        if bs.cash_and_equivalents == UNAVAILABLE or bs.total_debt == UNAVAILABLE:
            cash_pos = UNAVAILABLE
        else:
            try:
                cash_pos = Decimal(str(bs.cash_and_equivalents)) - Decimal(str(bs.total_debt))
            except (InvalidOperation, TypeError):
                cash_pos = UNAVAILABLE

        net_cash.append(make_point(
            cash_pos,
            formula="cash_and_equivalents - total_debt",
            period=stmt.period,
            period_date=stmt.report_date,
            cash_and_equivalents=bs.cash_and_equivalents,
            total_debt=bs.total_debt,
        ))

        # ── Current Ratio ─────────────────────────────────────────────────────
        curr_ratio.append(ratio(
            bs.current_assets, bs.current_liabilities,
            formula="current_assets / current_liabilities",
            current_assets=bs.current_assets,
            current_liabilities=bs.current_liabilities,
            **kw,
        ))

        # ── ROE ───────────────────────────────────────────────────────────────
        bs_idx = next((i for i, b in enumerate(bs_list) if b.report_date == bs.report_date), None)
        prior_bs = bs_list[bs_idx - 1] if (bs_idx is not None and bs_idx > 0) else None
        avg_eq = _avg_equity(bs, prior_bs)

        roe_series.append(ratio(
            stmt.net_income, avg_eq,
            formula="net_income / avg_total_equity",
            net_income=stmt.net_income,
            avg_total_equity=avg_eq,
            prior_equity=prior_bs.total_equity if prior_bs else "no_prior",
            current_equity=bs.total_equity,
            **kw,
        ))

        # ── ROIC ──────────────────────────────────────────────────────────────
        nopat = _nopat(stmt)
        inv_cap = _invested_capital(bs)

        roic_series.append(ratio(
            nopat, inv_cap,
            formula="nopat / invested_capital  where  nopat = operating_income × (1 − tax_rate)",
            nopat=nopat,
            invested_capital=inv_cap,
            operating_income=stmt.operating_income,
            income_tax_expense=stmt.income_tax_expense,
            net_income=stmt.net_income,
            **kw,
        ))

    return FinancialStrengthKPIs(
        debt_to_equity=d2e,
        net_cash_position=net_cash,
        current_ratio=curr_ratio,
        roe=roe_series,
        roic=roic_series,
    )
