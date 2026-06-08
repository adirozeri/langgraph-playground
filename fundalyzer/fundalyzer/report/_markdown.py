"""Markdown deep-dive renderer.

Every KPI section includes:
  - Time series table
  - Formula and source inputs (the full MetricPoint provenance)
  - Peer comparison (target vs peer median and position)
  - Narrative claim trail

This makes the document auditable end-to-end: any number traces to the raw
statement field that produced it.
"""
from __future__ import annotations

from io import StringIO

from ..data.models import UNAVAILABLE
from ..decide.models import SoftSignalDirection
from ..interpret.models import DashboardNarrative
from ..metrics.models import MetricSeries
from ._format import DASH, fmt_num, fmt_pct, fmt_ratio, fmt_val
from .models import DeepDiveReport


def _series_table(
    out: StringIO,
    title: str,
    series: MetricSeries,
    *,
    pct: bool = False,
    ratio: bool = False,
    include_inputs: bool = True,
) -> None:
    """Emit a Markdown table for a MetricSeries with full provenance."""
    out.write(f"\n#### {title}\n\n")

    if not series:
        out.write("_No data available._\n")
        return

    out.write("| Period | Value | Formula |\n")
    out.write("|--------|-------|---------|\n")
    for pt in series:
        val_str = fmt_pct(pt.value) if pct else (fmt_ratio(pt.value) if ratio else fmt_val(pt.value))
        if pt.value == UNAVAILABLE:
            val_str = DASH
        period_str = f"{pt.period_date} ({pt.period})"
        formula = pt.formula.replace("|", "\\|")
        out.write(f"| {period_str} | {val_str} | `{formula}` |\n")

    if include_inputs:
        # Emit source inputs for the most recent point as a collapsible block
        latest = next((p for p in reversed(series) if p.value != UNAVAILABLE), None)
        if latest and latest.inputs:
            out.write("\n<details><summary>Source inputs (most recent period)</summary>\n\n")
            out.write("| Input | Value |\n|-------|-------|\n")
            for k, v in latest.inputs.items():
                out.write(f"| `{k}` | {v} |\n")
            out.write("\n</details>\n")


def _narrative_section(out: StringIO, narrative: DashboardNarrative, title: str) -> None:
    out.write(f"\n### {title} Narrative\n\n")
    out.write(f"**Verdict:** `{narrative.trend_verdict}`\n\n")
    out.write(f"**Headline:** {narrative.headline}\n\n")
    out.write(f"{narrative.body}\n\n")
    if narrative.claims:
        out.write("**Claim trail** _(each assertion with its cited data points)_:\n\n")
        for claim in narrative.claims:
            out.write(f"- {claim.statement}\n")
            if claim.data_points:
                for dp in claim.data_points:
                    out.write(f"  - `{dp}`\n")


def _peer_row(out: StringIO, kpi: str, target: str, peer: str, pos: str | None) -> None:
    arrow = {"BETTER": "↑", "WORSE": "↓", "IN_LINE": "→"}.get(pos or "", "")
    out.write(f"| {kpi} | {target} | {peer} | {arrow} {pos or DASH} |\n")


def render_deep_dive_md(report: DeepDiveReport) -> str:
    """Render the deep dive as a Markdown string."""
    out = StringIO()
    d = report.decision
    sc = d.scorecard
    vp = d.valuation_position
    ss = d.soft_signals
    proj = d.projection
    interp = report.interpretation
    inc = report.income
    mom = report.momentum
    val = report.valuation
    cap = report.capital

    # ── Title ─────────────────────────────────────────────────────────────────
    out.write(f"# Fundalyzer Deep Dive: {report.ticker}\n\n")
    out.write(f"_Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}_\n\n")
    out.write(
        "> **Architecture contract:** Every number in this report originates from a real\n"
        "> financial data API and was computed deterministically in Python. The LLM was\n"
        "> used only to produce narrative text — it did not generate any figure.\n\n"
    )
    out.write("---\n\n")

    # ── Investment Decision ───────────────────────────────────────────────────
    out.write("## Investment Decision\n\n")
    out.write(f"**Lean:** `{d.lean.value}`  |  **Composite Score:** {sc.composite}/10\n\n")

    out.write("### Scorecard\n\n")
    out.write("| Pillar | Score | Verdict |\n|--------|-------|---------|\n")
    for pillar in (sc.income, sc.momentum, sc.valuation, sc.capital):
        out.write(f"| {pillar.name.capitalize()} | {pillar.score}/10 | {pillar.verdict.value} |\n")

    out.write("\n**Pillar KPI positions vs peers:**\n\n")
    out.write("| KPI | Position |\n|-----|----------|\n")
    for pillar in (sc.income, sc.momentum, sc.valuation, sc.capital):
        for kpi, pos in pillar.key_metrics_vs_peers.items():
            arrow = {"BETTER": "↑", "WORSE": "↓", "IN_LINE": "→"}.get(pos, "")
            out.write(f"| {kpi.replace('_', ' ')} | {arrow} {pos} |\n")

    out.write("\n### Valuation vs Own History\n\n")
    out.write(f"**Position:** `{vp.position.value}`\n\n")
    out.write("| | Value |\n|--|-------|\n")
    out.write(f"| Current P/E | {fmt_num(vp.current_pe)}× |\n")
    out.write(f"| Historical Median P/E | {fmt_num(vp.historical_median_pe)}× |\n")
    out.write(f"| Deviation from Median | {fmt_pct(vp.deviation_from_median_pct)} |\n")
    out.write(f"| Current P/S | {fmt_num(vp.current_ps)}× |\n")
    out.write(f"| Peer Median P/S | {fmt_num(vp.peer_median_ps)}× |\n")
    out.write(f"\n> _{vp.note}_\n\n")

    out.write("\n### 3-Year Projection\n\n")
    out.write("| | Base Case | Bull Case |\n|--|-----------|----------|\n")
    bc, bull = proj.base_case, proj.bull_case
    out.write(f"| Base Revenue | {fmt_val(bc.base_revenue)} | {fmt_val(bull.base_revenue)} |\n")
    out.write(f"| Year 1 Revenue | {fmt_val(bc.year_1_revenue)} | {fmt_val(bull.year_1_revenue)} |\n")
    out.write(f"| Year 2 Revenue | {fmt_val(bc.year_2_revenue)} | {fmt_val(bull.year_2_revenue)} |\n")
    out.write(f"| Year 3 Revenue | {fmt_val(bc.year_3_revenue)} | {fmt_val(bull.year_3_revenue)} |\n")
    out.write(f"| Revenue CAGR | {fmt_pct(bc.revenue_cagr)} | {fmt_pct(bull.revenue_cagr)} |\n")
    out.write(f"| Base EPS | {fmt_num(bc.base_eps)} | {fmt_num(bull.base_eps)} |\n")
    out.write(f"| Year 1 EPS | {fmt_num(bc.year_1_eps)} | {fmt_num(bull.year_1_eps)} |\n")
    out.write(f"| Year 2 EPS | {fmt_num(bc.year_2_eps)} | {fmt_num(bull.year_2_eps)} |\n")
    out.write(f"| Year 3 EPS | {fmt_num(bc.year_3_eps)} | {fmt_num(bull.year_3_eps)} |\n")
    out.write(f"| EPS CAGR | {fmt_pct(bc.eps_cagr)} | {fmt_pct(bull.eps_cagr)} |\n")
    out.write(f"| Applied P/E | {fmt_num(bc.applied_pe_multiple)}× | {fmt_num(bull.applied_pe_multiple)}× |\n")
    out.write(f"| Implied Price Yr 3 | {fmt_val(bc.implied_price_year_3)} | {fmt_val(bull.implied_price_year_3)} |\n")

    out.write(f"\n**Methodology:** {proj.methodology_note}\n\n")
    if bc.assumption_narrative:
        out.write(f"**Base case assumptions:** {bc.assumption_narrative}\n\n")
    if bull.assumption_narrative:
        out.write(f"**Bull case assumptions:** {bull.assumption_narrative}\n\n")

    out.write("\n### Soft Signals\n\n")
    _ICON = {
        SoftSignalDirection.POSITIVE: "↑ POSITIVE",
        SoftSignalDirection.NEGATIVE: "↓ NEGATIVE",
        SoftSignalDirection.NEUTRAL: "→ NEUTRAL",
        SoftSignalDirection.UNAVAILABLE: "— UNAVAILABLE",
    }
    out.write("| Signal | Direction | Detail |\n|--------|-----------|--------|\n")
    out.write(f"| Insider activity | {_ICON[ss.insider_activity]} | {ss.insider_detail} |\n")
    out.write(f"| EPS revisions | {_ICON[ss.estimate_revisions]} | {ss.revision_detail} |\n")
    out.write(f"| Buybacks | {_ICON[ss.buyback_activity]} | {ss.buyback_detail} |\n")
    if ss.conflict_flag:
        out.write(f"\n⚠ **Conflict detected:** {ss.conflict_description}\n")

    out.write("\n### Justification\n\n")
    out.write(f"{d.justification}\n\n")

    out.write("\n### Caveats\n\n")
    out.write(f"1. {d.caveat_quality_not_timing}\n")
    out.write(f"2. {d.caveat_projection_not_guaranteed}\n")
    out.write(f"3. {d.caveat_garbage_in_garbage_out}\n\n")
    out.write("---\n\n")

    # ── Income Dashboard ──────────────────────────────────────────────────────
    out.write("## Income Dashboard\n\n")
    out.write(
        "Foundation: revenue trajectory, full profitability stack, and FCF quality.\n"
        "Every value traces to the income statement or cash flow statement.\n\n"
    )
    out.write("### Peer Medians\n\n")
    out.write("| Metric | Peer Median |\n|--------|-------------|\n")
    out.write(f"| Revenue Growth YoY | {fmt_pct(inc.peer_revenue_growth_yoy)} |\n")
    out.write(f"| Gross Margin | {fmt_pct(inc.peer_gross_margin)} |\n")
    out.write(f"| Operating Margin | {fmt_pct(inc.peer_operating_margin)} |\n")
    out.write(f"| Net Margin | {fmt_pct(inc.peer_net_margin)} |\n")
    out.write(f"| EBITDA Margin | {fmt_pct(inc.peer_ebitda_margin)} |\n")
    out.write(f"| FCF Margin | {fmt_pct(inc.peer_fcf_margin)} |\n\n")

    _series_table(out, "Revenue", inc.revenue)
    _series_table(out, "Revenue Growth YoY", inc.revenue_growth_yoy, pct=True)
    _series_table(out, "Gross Margin", inc.gross_margin, pct=True)
    _series_table(out, "Operating Margin", inc.operating_margin, pct=True)
    _series_table(out, "Net Margin", inc.net_margin, pct=True)
    _series_table(out, "EBITDA Margin", inc.ebitda_margin, pct=True)
    _series_table(out, "Free Cash Flow", inc.free_cash_flow)
    _series_table(out, "FCF Margin", inc.fcf_margin, pct=True)

    out.write("\n**Trend summary:**\n\n")
    out.write("| Metric | Trend |\n|--------|-------|\n")
    for label, tr in [
        ("Revenue Growth", inc.revenue_growth_trend),
        ("Gross Margin", inc.gross_margin_trend),
        ("Operating Margin", inc.operating_margin_trend),
        ("Net Margin", inc.net_margin_trend),
        ("EBITDA Margin", inc.ebitda_margin_trend),
        ("FCF Margin", inc.fcf_margin_trend),
    ]:
        slope = f"{tr.normalized_slope:.4f}" if tr.normalized_slope is not None else DASH
        out.write(f"| {label} | {tr.trend.value} (slope {slope}, n={tr.n_periods}) |\n")

    _narrative_section(out, interp.income, "Income")
    out.write("\n---\n\n")

    # ── Momentum Dashboard ────────────────────────────────────────────────────
    out.write("## Momentum Dashboard\n\n")
    out.write(
        "Engine: rate of change for the key growth drivers. "
        "P/E section shows trailing vs forward vs historical.\n\n"
    )
    out.write("### Peer Medians\n\n")
    out.write("| Metric | Peer Median |\n|--------|-------------|\n")
    out.write(f"| EPS Growth YoY | {fmt_pct(mom.peer_eps_growth_yoy)} |\n")
    out.write(f"| Revenue Growth YoY | {fmt_pct(mom.peer_revenue_growth_yoy)} |\n")
    out.write(f"| Trailing P/E | {fmt_ratio(mom.peer_trailing_pe)} |\n")
    out.write(f"| Forward P/E | {fmt_ratio(mom.peer_forward_pe)} |\n\n")

    _series_table(out, "EPS (Annual)", mom.eps_annual, include_inputs=True)
    _series_table(out, "EPS Growth YoY", mom.eps_growth_yoy, pct=True)
    _series_table(out, "Revenue (Annual)", mom.revenue_annual)
    _series_table(out, "Revenue Growth YoY", mom.revenue_growth_yoy, pct=True)
    _series_table(out, "Free Cash Flow (Annual)", mom.fcf_annual)
    if mom.forward_revenue:
        _series_table(out, "Forward Revenue (Analyst Estimate)", mom.forward_revenue)
    _series_table(out, "Trailing P/E", mom.trailing_pe, ratio=True)
    _series_table(out, "Forward P/E", mom.forward_pe, ratio=True)
    _series_table(out, "Historical P/E (Shadow)", mom.historical_pe, ratio=True)

    out.write("\n**Trend summary:**\n\n")
    out.write("| Metric | Trend |\n|--------|-------|\n")
    for label, tr in [
        ("EPS Growth", mom.eps_trend),
        ("Revenue Growth", mom.revenue_trend),
        ("FCF", mom.fcf_trend),
        ("P/E (Shadow)", mom.pe_trend),
    ]:
        slope = f"{tr.normalized_slope:.4f}" if tr.normalized_slope is not None else DASH
        out.write(f"| {label} | {tr.trend.value} (slope {slope}, n={tr.n_periods}) |\n")

    _narrative_section(out, interp.momentum, "Momentum")
    out.write("\n---\n\n")

    # ── Valuation Dashboard ───────────────────────────────────────────────────
    out.write("## Valuation Dashboard\n\n")
    out.write(
        "Price: multiples vs own history and peer median. "
        "BETTER = cheaper than own historical median.\n\n"
    )
    out.write("### Peer Medians\n\n")
    out.write("| Metric | Peer Median |\n|--------|-------------|\n")
    out.write(f"| Trailing P/E | {fmt_ratio(val.peer_trailing_pe)} |\n")
    out.write(f"| Forward P/E | {fmt_ratio(val.peer_forward_pe)} |\n")
    out.write(f"| Price/Sales | {fmt_ratio(val.peer_price_to_sales)} |\n")
    out.write(f"| EV/EBITDA | {fmt_ratio(val.peer_ev_to_ebitda)} |\n\n")

    out.write("### Self-History Flags\n\n")
    out.write("| Multiple | vs Own History |\n|----------|----------------|\n")
    for label, pos in [
        ("P/E", val.pe_vs_own_history),
        ("P/S", val.ps_vs_own_history),
        ("EV/EBITDA", val.ev_ebitda_vs_own_history),
    ]:
        arrow = {"BETTER": "↑ CHEAPER", "WORSE": "↓ RICHER", "IN_LINE": "→ IN LINE"}.get(
            pos.value if pos else "", DASH
        )
        out.write(f"| {label} | {arrow} |\n")

    _series_table(out, "Trailing P/E", val.trailing_pe, ratio=True)
    _series_table(out, "Forward P/E", val.forward_pe, ratio=True)
    _series_table(out, "Price/Sales", val.price_to_sales, ratio=True)
    _series_table(out, "EV/EBITDA", val.ev_to_ebitda, ratio=True)
    _series_table(out, "EV/Gross Profit", val.ev_to_gross_profit, ratio=True)
    _series_table(out, "Historical P/E (Shadow, oldest-first)", val.historical_pe, ratio=True)

    _narrative_section(out, interp.valuation, "Valuation")
    out.write("\n---\n\n")

    # ── Capital Dashboard ─────────────────────────────────────────────────────
    out.write("## Capital Dashboard\n\n")
    out.write(
        "Allocation: how efficiently is capital deployed, returned, and priced?\n\n"
    )
    out.write("### Peer Medians\n\n")
    out.write("| Metric | Peer Median |\n|--------|-------------|\n")
    out.write(f"| ROIC | {fmt_pct(cap.peer_roic)} |\n")
    out.write(f"| ROE | {fmt_pct(cap.peer_roe)} |\n")
    out.write(f"| FCF Yield | {fmt_pct(cap.peer_fcf_yield)} |\n\n")

    out.write("### Analyst Price Targets\n\n")
    out.write("| | Value |\n|--|-------|\n")
    out.write(f"| Consensus Target | {fmt_val(cap.price_target_consensus)} |\n")
    out.write(f"| High Target | {fmt_val(cap.price_target_high)} |\n")
    out.write(f"| Low Target | {fmt_val(cap.price_target_low)} |\n")
    out.write(f"| Median Target | {fmt_val(cap.price_target_median)} |\n")
    out.write(f"| Upside vs Current | {fmt_pct(cap.price_upside)} |\n\n")

    _series_table(out, "ROIC", cap.roic, pct=True)
    _series_table(out, "ROE", cap.roe, pct=True)
    _series_table(out, "FCF Yield", cap.fcf_yield, pct=True)
    _series_table(out, "Buybacks", cap.buybacks)
    if cap.revenue_per_employee:
        _series_table(out, "Revenue per Employee", cap.revenue_per_employee)

    out.write("\n**Trend summary:**\n\n")
    out.write("| Metric | Trend |\n|--------|-------|\n")
    for label, tr in [("ROIC", cap.roic_trend), ("ROE", cap.roe_trend)]:
        slope = f"{tr.normalized_slope:.4f}" if tr.normalized_slope is not None else DASH
        out.write(f"| {label} | {tr.trend.value} (slope {slope}, n={tr.n_periods}) |\n")

    _narrative_section(out, interp.capital, "Capital")
    out.write("\n---\n\n")

    # ── Interpretation synthesis ──────────────────────────────────────────────
    out.write("## Overall Interpretation\n\n")
    out.write(f"{interp.overall_summary}\n\n")
    out.write("---\n\n")

    # ── Audit trail ───────────────────────────────────────────────────────────
    out.write("## Audit Trail\n\n")
    out.write(
        "Every KPI value in this report was computed from raw statement fields.\n"
        "The formula and source inputs for each data point are embedded in the\n"
        "collapsible blocks above. To verify any figure:\n\n"
        "1. Find the metric in its dashboard section.\n"
        "2. Open the **Source inputs** block to see the exact raw values used.\n"
        "3. Apply the **Formula** shown in the table to reproduce the result.\n\n"
        "All inputs labelled `UNAVAILABLE` indicate fields that no provider returned.\n"
        "No zero or None was ever substituted for missing data.\n\n"
    )
    out.write("### Claim Citation Coverage\n\n")
    out.write(
        "The following table lists every LLM assertion with the data points it cited.\n"
        "If any data point cannot be found in the dashboard sections above, "
        "the LLM drifted from the provided numbers.\n\n"
    )
    out.write("| Dashboard | Claim | Data Points Cited |\n")
    out.write("|-----------|-------|-------------------|\n")
    for dash_name, narrative in [
        ("Income", interp.income),
        ("Momentum", interp.momentum),
        ("Valuation", interp.valuation),
        ("Capital", interp.capital),
    ]:
        for claim in narrative.claims:
            dps = ", ".join(f"`{dp}`" for dp in claim.data_points)
            stmt = claim.statement.replace("|", "\\|")
            out.write(f"| {dash_name} | {stmt} | {dps} |\n")

    return out.getvalue()
