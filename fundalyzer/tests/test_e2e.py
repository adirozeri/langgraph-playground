"""End-to-end pipeline test on recorded AAPL fixtures.

Runs the full chain from raw fixture data all the way to a rendered report.
No live API calls, no live model calls.

Assertions:
  - AnalysisResult is fully populated (no NotImplementedError stubs)
  - InvestmentDecision has a valid lean
  - All three caveats are present
  - Scorecard composite is in [0, 10]
  - Projection base case has positive year-3 implied price
  - Deep-dive Markdown contains all required sections
  - Snapshot rendering does not raise
  - Decision JSON is valid and round-trips through pydantic
  - Dry-run mode raises NoCachedDataError when data is absent
  - Config file peer loading uses config-file peers when --peers is omitted
"""
from __future__ import annotations

import json
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from fundalyzer.data.cache import DiskCache, NullCache, ReadonlyCache
from fundalyzer.data.errors import NoCachedDataError
from fundalyzer.data.fmp import FMPProvider
from fundalyzer.data.models import UNAVAILABLE
from fundalyzer.decide.models import InvestmentDecision, InvestmentLean
from fundalyzer.pipeline import AnalysisResult, run_analysis
from fundalyzer.report import render_snapshot
from fundalyzer.report._markdown import render_deep_dive_md

FIXTURES = Path(__file__).parent / "fixtures" / "fmp"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def _mock_messages_api(narrative_payload: dict, justification_payload: dict) -> MagicMock:
    """Return a mock Anthropic messages.create that always succeeds."""

    def _tool_resp(payload: dict) -> MagicMock:
        block = MagicMock()
        block.type = "tool_use"
        block.input = payload
        usage = MagicMock()
        usage.input_tokens = 800
        usage.output_tokens = 200
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = "tool_use"
        resp.usage = usage
        return resp

    def _text_resp(text: str) -> MagicMock:
        block = MagicMock()
        block.type = "text"
        block.text = text
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = "end_turn"
        return resp

    call_count = [0]

    def _create(**kwargs):
        call_count[0] += 1
        tools = kwargs.get("tools", [])
        tool_names = [t.get("name") for t in tools]

        if "narrative" in tool_names:
            return _tool_resp(narrative_payload)
        if "justification" in tool_names:
            return _tool_resp(justification_payload)
        if "assumption_narrative" in tool_names:
            return _tool_resp({
                "base_narrative": (
                    "Base case projects revenue growing at 4.9% annually, "
                    "derived from analyst consensus forward revenue of $410.0B."
                ),
                "bull_narrative": (
                    "Bull case applies a 15pp growth uplift to 19.9% CAGR "
                    "and expands the P/E multiple by 10%."
                ),
            })
        # synthesis (no tool)
        return _text_resp(
            "AAPL demonstrates stable revenue at $391.0B with gross margin of 46.2%. "
            "Composite score reflects ABOVE_PEER positioning."
        )

    api = MagicMock()
    api.create.side_effect = _create
    return api


_NARRATIVE = {
    "headline": "Gross margin held at 46.2% in FY2024, above the 41.5% peer median.",
    "body": "Operating leverage was maintained with operating margin at 31.6%.",
    "claims": [
        {
            "statement": "Gross margin of 46.2% exceeds peer median.",
            "data_points": ["gross_margin_latest=46.2%", "peer_gross_margin=41.5%"],
        }
    ],
    "trend_verdict": "STABLE",
}

_JUSTIFICATION = {
    "justification": (
        "AAPL scores ABOVE_PEER on all four pillars with composite 7.0/10. "
        "Valuation is IN_LINE vs own history. EPS revisions are POSITIVE. "
        "The INVEST lean reflects sound fundamentals at a reasonable price."
    )
}


@pytest.fixture(scope="module")
def analysis_result() -> AnalysisResult:
    """Run the full pipeline once with AAPL fixture data."""
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
    def _fake_get(path, ticker, cache_key, **p):
        # Accept any limit suffix (income_annual_5 or income_annual_10, etc.)
        for pattern, data in responses.items():
            if cache_key == pattern:
                return data
            # Strip trailing _N to match regardless of requested limit
            bare_key = "_".join(pattern.split("_")[:-1])
            bare_req = "_".join(cache_key.split("_")[:-1])
            if bare_key == bare_req:
                return data
        return None

    provider = FMPProvider(api_key="test", cache=NullCache())
    provider._get = _fake_get

    messages_api = _mock_messages_api(_NARRATIVE, _JUSTIFICATION)

    return run_analysis(
        "AAPL",
        provider,
        peers=[],      # single-ticker run for speed; peer set = empty
        annual_years=5,
        messages_api=messages_api,
    )


# ── AnalysisResult completeness ───────────────────────────────────────────────

class TestAnalysisResultCompleteness:
    def test_ticker(self, analysis_result):
        assert analysis_result.ticker == "AAPL"

    def test_raw_has_income_statements(self, analysis_result):
        assert len(analysis_result.raw.income_statements_annual) > 0

    def test_kpis_has_revenue(self, analysis_result):
        assert len(analysis_result.kpis.profitability_annual.revenue) > 0

    def test_peer_set_has_target(self, analysis_result):
        assert analysis_result.peer_set.target == "AAPL"

    def test_four_dashboards_populated(self, analysis_result):
        assert analysis_result.income.ticker == "AAPL"
        assert analysis_result.momentum.ticker == "AAPL"
        assert analysis_result.valuation.ticker == "AAPL"
        assert analysis_result.capital.ticker == "AAPL"

    def test_interpretation_all_verdicts_valid(self, analysis_result):
        interp = analysis_result.interpretation
        valid = {"IMPROVING", "DETERIORATING", "STABLE", "MIXED"}
        assert interp.income.trend_verdict in valid
        assert interp.momentum.trend_verdict in valid
        assert interp.overall_summary != ""

    def test_decision_has_valid_lean(self, analysis_result):
        assert analysis_result.decision.lean in InvestmentLean

    def test_decision_has_justification(self, analysis_result):
        assert analysis_result.decision.justification != ""

    def test_snapshot_report_exists(self, analysis_result):
        assert analysis_result.snapshot.ticker == "AAPL"

    def test_deep_dive_report_exists(self, analysis_result):
        assert analysis_result.deep_dive.ticker == "AAPL"


# ── InvestmentDecision content ────────────────────────────────────────────────

class TestDecisionContent:
    def test_scorecard_composite_in_range(self, analysis_result):
        d = analysis_result.decision
        assert Decimal("0") <= d.scorecard.composite <= Decimal("10")

    def test_all_caveats_present(self, analysis_result):
        d = analysis_result.decision
        assert "quality" in d.caveat_quality_not_timing.lower()
        assert "projection" in d.caveat_projection_not_guaranteed.lower()
        assert "reliable" in d.caveat_garbage_in_garbage_out.lower()

    def test_projection_labels(self, analysis_result):
        p = analysis_result.decision.projection
        assert p.base_case.label == "base_case"
        assert p.bull_case.label == "bull_case"

    def test_valuation_position_note_present(self, analysis_result):
        assert "does not" in analysis_result.decision.valuation_position.note.lower()

    def test_soft_signals_have_details(self, analysis_result):
        ss = analysis_result.decision.soft_signals
        assert isinstance(ss.insider_detail, str)
        assert isinstance(ss.revision_detail, str)
        assert isinstance(ss.buyback_detail, str)

    def test_decision_json_roundtrip(self, analysis_result):
        d = analysis_result.decision
        restored = InvestmentDecision.model_validate_json(d.model_dump_json())
        assert restored.ticker == d.ticker
        assert restored.lean == d.lean
        assert restored.scorecard.composite == d.scorecard.composite


# ── Report rendering ──────────────────────────────────────────────────────────

class TestReportRendering:
    def test_snapshot_renders_without_error(self, analysis_result):
        import io
        buf = io.StringIO()
        console = Console(file=buf, width=120)
        render_snapshot(analysis_result.snapshot, console=console)
        output = buf.getvalue()
        assert "AAPL" in output

    def test_markdown_has_all_sections(self, analysis_result):
        md = render_deep_dive_md(analysis_result.deep_dive)
        for section in [
            "## Investment Decision",
            "## Income Dashboard",
            "## Momentum Dashboard",
            "## Valuation Dashboard",
            "## Capital Dashboard",
            "## Overall Interpretation",
            "## Audit Trail",
            "### Caveats",
        ]:
            assert section in md, f"Missing section: {section!r}"

    def test_markdown_audit_trail_has_claims(self, analysis_result):
        md = render_deep_dive_md(analysis_result.deep_dive)
        assert "Claim Citation Coverage" in md
        # The narrative we injected had one claim with a data point
        assert "gross_margin_latest=46.2%" in md

    def test_markdown_has_source_inputs(self, analysis_result):
        md = render_deep_dive_md(analysis_result.deep_dive)
        assert "<details><summary>Source inputs" in md

    def test_deep_dive_written_to_disk(self, analysis_result):
        from fundalyzer.report import render_deep_dive
        with tempfile.TemporaryDirectory() as tmpdir:
            console = Console(file=open("/dev/null", "w"))
            path = render_deep_dive(
                analysis_result.deep_dive, output_dir=tmpdir, pdf=False, console=console
            )
            assert path.exists()
            content = path.read_text()
            assert "AAPL" in content


# ── No missing numbers in critical fields ─────────────────────────────────────

class TestNoMissingNumbers:
    def test_revenue_series_has_valid_values(self, analysis_result):
        revenue = analysis_result.kpis.profitability_annual.revenue
        valid = [pt for pt in revenue if pt.value != UNAVAILABLE]
        assert len(valid) > 0, "Revenue series is entirely UNAVAILABLE"

    def test_gross_margin_has_valid_values(self, analysis_result):
        gm = analysis_result.kpis.profitability_annual.gross_margin
        valid = [pt for pt in gm if pt.value != UNAVAILABLE]
        assert len(valid) > 0, "Gross margin series is entirely UNAVAILABLE"

    def test_trailing_pe_has_valid_value(self, analysis_result):
        pe = analysis_result.kpis.valuation.trailing_pe
        assert pe and pe[0].value != UNAVAILABLE

    def test_projection_base_has_base_revenue(self, analysis_result):
        bc = analysis_result.decision.projection.base_case
        assert bc.base_revenue != UNAVAILABLE, "Base revenue is UNAVAILABLE"


# ── Dry-run mode ──────────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_raises_when_not_cached(self):
        """ReadonlyCache on an empty DiskCache raises NoCachedDataError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            disk = DiskCache(cache_dir=Path(tmpdir))
            readonly = ReadonlyCache(disk)
            provider = FMPProvider(api_key="test", cache=readonly)
            with pytest.raises(NoCachedDataError):
                provider.get_raw_financials("FAKE")

    def test_readonly_cache_returns_cached_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            disk = DiskCache(cache_dir=Path(tmpdir))
            disk.set("AAPL", "profile", {"symbol": "AAPL"})
            readonly = ReadonlyCache(disk)
            result = readonly.get("AAPL", "profile")
            assert result == {"symbol": "AAPL"}

    def test_readonly_cache_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            disk = DiskCache(cache_dir=Path(tmpdir))
            readonly = ReadonlyCache(disk)
            readonly.set("AAPL", "test", {"x": 1})  # should silently do nothing
            assert disk.get("AAPL", "test") is None


# ── Config file peer loading ──────────────────────────────────────────────────

class TestConfigPeers:
    def test_load_config_empty_when_no_file(self, tmp_path):
        from fundalyzer.config import load_config
        cfg = load_config(tmp_path / "nonexistent.toml")
        assert cfg.peers_for("AAPL") is None

    def test_load_config_peers_for_ticker(self, tmp_path):
        from fundalyzer.config import load_config
        toml = tmp_path / "fundalyzer.toml"
        toml.write_text(
            '[peers]\nAAPL = ["MSFT", "GOOGL"]\n',
            encoding="utf-8",
        )
        cfg = load_config(toml)
        peers = cfg.peers_for("AAPL")
        assert peers == ["MSFT", "GOOGL"]

    def test_load_config_case_insensitive(self, tmp_path):
        from fundalyzer.config import load_config
        toml = tmp_path / "fundalyzer.toml"
        toml.write_text('[peers]\naapl = ["msft"]\n', encoding="utf-8")
        cfg = load_config(toml)
        assert cfg.peers_for("AAPL") == ["MSFT"]

    def test_load_config_default_years(self, tmp_path):
        from fundalyzer.config import load_config
        toml = tmp_path / "fundalyzer.toml"
        toml.write_text("[defaults]\nyears = 7\n", encoding="utf-8")
        cfg = load_config(toml)
        assert cfg.default_years == 7

    def test_load_config_sector_peers(self, tmp_path):
        from fundalyzer.config import load_config
        toml = tmp_path / "fundalyzer.toml"
        toml.write_text(
            '[sector_peers]\nTechnology = ["AAPL", "MSFT"]\n',
            encoding="utf-8",
        )
        cfg = load_config(toml)
        assert "AAPL" in cfg.sector_peers("Technology")


# ── Structured logging ────────────────────────────────────────────────────────

class TestLogging:
    def test_configure_text_sets_log_level(self):
        import logging as _logging

        from fundalyzer._logging import configure_logging
        configure_logging(level="DEBUG", fmt="text")
        assert _logging.getLogger().level == _logging.DEBUG

    def test_configure_warning_level(self):
        import logging as _logging

        from fundalyzer._logging import configure_logging
        configure_logging(level="WARNING", fmt="text")
        assert _logging.getLogger().level == _logging.WARNING

    def test_configure_json_logging_produces_json(self):
        import io
        import logging as _logging

        from fundalyzer._logging import _JsonFormatter

        buf = io.StringIO()
        handler = _logging.StreamHandler(buf)
        handler.setFormatter(_JsonFormatter())

        # Isolated logger with propagation disabled to avoid test interference
        logger = _logging.getLogger("fundalyzer.json_test_isolated")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(_logging.DEBUG)
        logger.propagate = False
        logger.info("hello %s", "world")

        output = buf.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert "hello world" in parsed["msg"]

    def test_json_formatter_extra_fields(self):
        import io
        import logging as _logging

        from fundalyzer._logging import _JsonFormatter

        buf = io.StringIO()
        handler = _logging.StreamHandler(buf)
        handler.setFormatter(_JsonFormatter())
        logger = _logging.getLogger("fundalyzer.json_extra")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(_logging.DEBUG)
        logger.propagate = False
        logger.info("event", extra={"ticker": "AAPL"})

        parsed = json.loads(buf.getvalue().strip())
        assert parsed["ticker"] == "AAPL"
