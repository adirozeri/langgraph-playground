"""Report module tests — no live API or model calls, no file system side effects.

Coverage:
  - _format: number formatting helpers
  - _snapshot: render_snapshot runs without error and produces rich output
  - _markdown: render_deep_dive_md produces a valid Markdown string
    with all required sections and audit trail
  - _pdf: export_pdf raises RuntimeError gracefully when pandoc is absent
  - build_snapshot_report / build_deep_dive_report: assemble correctly
  - render_deep_dive: writes a file and returns path
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from fundalyzer.data.cache import NullCache
from fundalyzer.data.fmp import FMPProvider
from fundalyzer.data.models import UNAVAILABLE
from fundalyzer.decide.models import (
    InvestmentDecision,
    InvestmentLean,
    PillarScore,
    PillarVerdict,
    Projection,
    ProjectionCase,
    ScoreCard,
    SoftSignalDirection,
    SoftSignals,
    ValuationHistoryPosition,
    ValuationPosition,
)
from fundalyzer.interpret.models import Claim, DashboardNarrative, Interpretation
from fundalyzer.metrics.compute import compute
from fundalyzer.peers._aggregator import build_comparisons
from fundalyzer.peers.models import PeerMetrics, PeerSet
from fundalyzer.report import (
    build_deep_dive_report,
    build_snapshot_report,
    render_deep_dive,
    render_snapshot,
)
from fundalyzer.report._format import (
    fmt_num,
    fmt_pct,
    fmt_ratio,
    fmt_val,
    lean_color,
    position_arrow,
)
from fundalyzer.report._markdown import render_deep_dive_md

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


def _stub_narrative(headline: str = "Gross margin held at 46%.") -> DashboardNarrative:
    return DashboardNarrative(
        headline=headline,
        body="Operating leverage was maintained.",
        claims=[
            Claim(
                statement="Gross margin 46%.",
                data_points=["gross_margin_2024=46.2%"],
            )
        ],
        trend_verdict="STABLE",
    )


def _stub_interpretation() -> Interpretation:
    n = _stub_narrative()
    return Interpretation(
        income=n, momentum=n, valuation=n, capital=n,
        overall_summary="Stable business. Fundamentals are sound.",
    )


def _stub_decision(ticker: str = "AAPL") -> InvestmentDecision:
    pillar = PillarScore(
        name="test", score=Decimal("7.00"),
        verdict=PillarVerdict.ABOVE_PEER,
        key_metrics_vs_peers={"gross_margin": "BETTER", "net_margin": "IN_LINE"},
    )
    return InvestmentDecision(
        ticker=ticker,
        lean=InvestmentLean.INVEST,
        scorecard=ScoreCard(
            income=pillar, momentum=pillar, valuation=pillar, capital=pillar,
            composite=Decimal("7.00"),
        ),
        valuation_position=ValuationPosition(
            position=ValuationHistoryPosition.IN_LINE,
            current_pe=Decimal("30"),
            historical_median_pe=Decimal("28"),
            deviation_from_median_pct=Decimal("0.07"),
            current_ps=Decimal("8"),
            peer_median_ps=Decimal("6"),
        ),
        projection=Projection(
            base_case=ProjectionCase(
                label="base_case",
                base_revenue=Decimal("391000000000"),
                year_1_revenue=Decimal("410000000000"),
                year_2_revenue=Decimal("430000000000"),
                year_3_revenue=Decimal("451000000000"),
                revenue_cagr=Decimal("0.049"),
                base_eps=Decimal("6.57"),
                year_1_eps=Decimal("7.00"),
                year_2_eps=Decimal("7.45"),
                year_3_eps=Decimal("7.93"),
                eps_cagr=Decimal("0.065"),
                applied_pe_multiple=Decimal("30"),
                implied_price_year_3=Decimal("237.90"),
                assumption_narrative="Base case uses analyst consensus revenue growth of ~5% pa.",
            ),
            bull_case=ProjectionCase(
                label="bull_case",
                base_revenue=Decimal("391000000000"),
                year_1_revenue=Decimal("430000000000"),
                year_2_revenue=Decimal("473000000000"),
                year_3_revenue=Decimal("520000000000"),
                revenue_cagr=Decimal("0.099"),
                base_eps=Decimal("6.57"),
                year_1_eps=Decimal("7.56"),
                year_2_eps=Decimal("8.70"),
                year_3_eps=Decimal("10.01"),
                eps_cagr=Decimal("0.149"),
                applied_pe_multiple=Decimal("33"),
                implied_price_year_3=Decimal("330.33"),
                assumption_narrative="Bull case applies 15pp growth uplift.",
            ),
        ),
        soft_signals=SoftSignals(
            insider_activity=SoftSignalDirection.NEUTRAL,
            insider_detail="2 buys ($0.5M) vs 3 sells ($1.2M)",
            estimate_revisions=SoftSignalDirection.POSITIVE,
            revision_detail="3 positive surprises vs 1 miss over last 4 quarters",
            buyback_activity=SoftSignalDirection.POSITIVE,
            buyback_detail="Most recent annual buybacks: $90.2B",
            conflict_flag=False,
            conflict_description="",
        ),
        justification=(
            "AAPL scores 7.0/10 composite with ABOVE_PEER across all four pillars. "
            "Valuation is IN_LINE vs own history. EPS revisions are positive."
        ),
    )


@pytest.fixture(scope="module")
def aapl_dashboards():
    fmp = _make_fmp()
    raw = fmp.get_raw_financials("AAPL")
    kpis = compute(raw)
    peer = PeerMetrics(ticker="PEER", kpis=kpis)
    sm, cmp = build_comparisons("AAPL", kpis, [peer])
    peer_set = PeerSet(target="AAPL", target_kpis=kpis, peers=[peer],
                       sector_medians=sm, comparisons=cmp)
    from fundalyzer.dashboards.build import build
    income, momentum, valuation, capital = build(kpis, peer_set)
    return income, momentum, valuation, capital


# ── _format tests ─────────────────────────────────────────────────────────────

class TestFormat:
    def test_fmt_val_billions(self):
        assert fmt_val(Decimal("391_000_000_000")) == "$391.0B"

    def test_fmt_val_millions(self):
        assert fmt_val(Decimal("500_000_000")) == "$500M"

    def test_fmt_val_negative(self):
        result = fmt_val(Decimal("-90_000_000_000"))
        assert result.startswith("-$")

    def test_fmt_val_unavailable(self):
        assert fmt_val(UNAVAILABLE) == "—"

    def test_fmt_pct(self):
        assert fmt_pct(Decimal("0.462")) == "46.2%"

    def test_fmt_pct_unavailable(self):
        assert fmt_pct(UNAVAILABLE) == "—"

    def test_fmt_ratio(self):
        assert fmt_ratio(Decimal("28.5")) == "28.50×"

    def test_fmt_num(self):
        assert fmt_num(Decimal("1.234")) == "1.23"

    def test_lean_colors(self):
        assert "green" in lean_color("INVEST")
        assert "red" in lean_color("AVOID")
        assert "yellow" in lean_color("HOLD")

    def test_position_arrows(self):
        from fundalyzer.peers.models import RelativePosition
        assert position_arrow(RelativePosition.BETTER) == "↑"
        assert position_arrow(RelativePosition.WORSE) == "↓"
        assert position_arrow(RelativePosition.IN_LINE) == "→"
        assert position_arrow(None) == " "


# ── _snapshot tests ───────────────────────────────────────────────────────────

class TestSnapshot:
    def test_render_snapshot_no_error(self, aapl_dashboards):
        from rich.console import Console
        income, momentum, valuation, capital = aapl_dashboards
        decision = _stub_decision()
        report = build_snapshot_report(income, momentum, valuation, capital, decision)

        with tempfile.TemporaryFile(mode="w", suffix=".txt") as f:
            console = Console(file=f, width=120)
            render_snapshot(report, console=console)

    def test_snapshot_report_has_all_fields(self, aapl_dashboards):
        income, momentum, valuation, capital = aapl_dashboards
        decision = _stub_decision()
        report = build_snapshot_report(income, momentum, valuation, capital, decision)

        assert report.ticker == "AAPL"
        assert report.decision.lean == InvestmentLean.INVEST
        assert isinstance(report.generated_at, datetime)


# ── _markdown tests ───────────────────────────────────────────────────────────

class TestMarkdown:
    def _make_report(self, aapl_dashboards) -> "DeepDiveReport":
        income, momentum, valuation, capital = aapl_dashboards
        return build_deep_dive_report(
            income, momentum, valuation, capital,
            _stub_interpretation(), _stub_decision(),
        )

    def test_markdown_contains_ticker(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "AAPL" in md

    def test_markdown_has_all_sections(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        for section in [
            "## Investment Decision",
            "## Income Dashboard",
            "## Momentum Dashboard",
            "## Valuation Dashboard",
            "## Capital Dashboard",
            "## Overall Interpretation",
            "## Audit Trail",
        ]:
            assert section in md, f"Missing section: {section}"

    def test_markdown_has_caveats(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "Fundamentals assess" in md
        assert "3-year projection" in md
        assert "reliable as its inputs" in md

    def test_markdown_has_scorecard_table(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "| Pillar | Score | Verdict |" in md

    def test_markdown_has_projection_table(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "Base Case" in md
        assert "Bull Case" in md
        assert "Revenue CAGR" in md

    def test_markdown_has_audit_trail(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "Claim Citation Coverage" in md
        assert "gross_margin_2024=46.2%" in md

    def test_markdown_has_source_inputs_blocks(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "<details><summary>Source inputs" in md

    def test_markdown_has_trend_tables(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "ACCELERATING" in md or "FLAT" in md or "DECELERATING" in md

    def test_markdown_lean_present(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "INVEST" in md

    def test_markdown_soft_signals(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "Insider activity" in md
        assert "EPS revisions" in md
        assert "Buybacks" in md

    def test_unavailable_renders_as_dash(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "—" in md

    def test_architecture_contract_note_present(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "Architecture contract" in md

    def test_formula_column_present(self, aapl_dashboards):
        report = self._make_report(aapl_dashboards)
        md = render_deep_dive_md(report)
        assert "| Formula |" in md


# ── render_deep_dive file-writing tests ──────────────────────────────────────

class TestRenderDeepDive:
    def test_writes_markdown_file(self, aapl_dashboards):
        from rich.console import Console
        income, momentum, valuation, capital = aapl_dashboards
        report = build_deep_dive_report(
            income, momentum, valuation, capital,
            _stub_interpretation(), _stub_decision(),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            console = Console(file=open("/dev/null", "w"))
            path = render_deep_dive(report, output_dir=tmpdir, pdf=False, console=console)
            assert path.exists()
            assert path.suffix == ".md"
            content = path.read_text()
            assert "AAPL" in content

    def test_pdf_skipped_gracefully_when_pandoc_absent(self, aapl_dashboards):
        """When pandoc is not installed, render_deep_dive should not raise — just warn."""
        from rich.console import Console
        income, momentum, valuation, capital = aapl_dashboards
        report = build_deep_dive_report(
            income, momentum, valuation, capital,
            _stub_interpretation(), _stub_decision(),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("shutil.which", return_value=None):
                output = []
                console = Console(
                    file=type("FakeFile", (), {
                        "write": lambda self, s: output.append(s),
                        "flush": lambda self: None,
                    })(),
                )
                # Should NOT raise — just prints a warning
                path = render_deep_dive(
                    report, output_dir=tmpdir, pdf=True, console=Console()
                )
                assert path.suffix == ".md"


# ── _pdf tests ────────────────────────────────────────────────────────────────

class TestPdf:
    def test_export_pdf_raises_when_pandoc_missing(self):
        from fundalyzer.report._pdf import export_pdf

        with tempfile.NamedTemporaryFile(suffix=".md") as f:
            Path(f.name).write_text("# Test\n")
            with patch("shutil.which", return_value=None):
                with pytest.raises(RuntimeError, match="pandoc is not installed"):
                    export_pdf(Path(f.name))

    def test_export_pdf_raises_when_no_engine(self):
        from fundalyzer.report._pdf import export_pdf

        def fake_which(name):
            return "/usr/bin/pandoc" if name == "pandoc" else None

        with tempfile.NamedTemporaryFile(suffix=".md") as f:
            Path(f.name).write_text("# Test\n")
            with patch("shutil.which", side_effect=fake_which):
                with pytest.raises(RuntimeError, match="no PDF engine"):
                    export_pdf(Path(f.name))
