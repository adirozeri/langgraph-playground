"""Interpret module tests — no live model calls.

The Anthropic client is fully mocked so these tests run in CI without an API key.
Tests cover:
  - Prompt content (rules, peer comparison, unavailable handling)
  - Serialisation formatting
  - Response parsing and Claim extraction
  - End-to-end interpret() wiring
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fundalyzer.data.cache import NullCache
from fundalyzer.data.fmp import FMPProvider
from fundalyzer.data.models import UNAVAILABLE
from fundalyzer.dashboards.build import build
from fundalyzer.dashboards.models import (
    CapitalDashboard,
    IncomeDashboard,
    MomentumDashboard,
    ValuationDashboard,
)
from fundalyzer.interpret import interpret
from fundalyzer.interpret._prompts import (
    SYSTEM_PROMPT,
    build_capital_prompt,
    build_income_prompt,
    build_momentum_prompt,
    build_synthesis_prompt,
    build_valuation_prompt,
)
from fundalyzer.interpret._serialise import (
    serialise_capital,
    serialise_income,
    serialise_momentum,
    serialise_valuation,
    _pct,
    _usd_b,
    _ratio,
)
from fundalyzer.interpret.models import Claim, DashboardNarrative, Interpretation
from fundalyzer.metrics.compute import compute
from fundalyzer.peers._aggregator import build_comparisons
from fundalyzer.peers.models import PeerMetrics, PeerSet

# ── Fixture plumbing ──────────────────────────────────────────────────────────

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


@pytest.fixture(scope="module")
def dashboards():
    kpis = compute(_make_fmp().get_raw_financials("AAPL"))
    peer = PeerMetrics(ticker="PEER", kpis=kpis)
    sm, cmp = build_comparisons("AAPL", kpis, [peer])
    peer_set = PeerSet(target="AAPL", target_kpis=kpis, peers=[peer],
                       sector_medians=sm, comparisons=cmp)
    income, momentum, valuation, capital = build(kpis, peer_set)
    return income, momentum, valuation, capital


# ── Mock Anthropic response builder ──────────────────────────────────────────

def _mock_tool_response(raw_input: dict[str, Any]) -> MagicMock:
    """Build a mock that looks like an anthropic.Message with tool_use content."""
    block = MagicMock()
    block.type = "tool_use"
    block.input = raw_input

    usage = MagicMock()
    usage.input_tokens = 500
    usage.output_tokens = 200

    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "tool_use"
    resp.usage = usage
    return resp


def _mock_text_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text

    resp = MagicMock()
    resp.content = [block]
    resp.stop_reason = "end_turn"
    return resp


SAMPLE_NARRATIVE_INPUT = {
    "headline": "Gross margin expanded to 46.2% in FY2024, above the 41.5% peer median.",
    "body": (
        "Operating margin held at 31.6% while net margin reached 24.0%. "
        "FCF margin of 25.4% exceeded the 18.2% peer median, indicating strong cash conversion."
    ),
    "claims": [
        {
            "statement": "Gross margin of 46.2% is 4.7pp above the 41.5% peer median.",
            "data_points": ["gross_margin_latest=46.2%", "peer_gross_margin=41.5%"],
        },
        {
            "statement": "FCF margin of 25.4% exceeds peer median of 18.2%.",
            "data_points": ["fcf_margin_latest=25.4%", "peer_fcf_margin=18.2%"],
        },
    ],
    "trend_verdict": "STABLE",
}

SAMPLE_SYNTHESIS = (
    "Income and capital verdicts are STABLE while momentum is IMPROVING, "
    "suggesting growth is accelerating into a stable margin base. "
    "Valuation is DETERIORATING relative to own history."
)


def _make_mock_api(n_narrative_calls: int = 4) -> MagicMock:
    """API that returns SAMPLE_NARRATIVE_INPUT for tool calls and SAMPLE_SYNTHESIS for text."""
    mock_api = MagicMock()
    tool_resp = _mock_tool_response(SAMPLE_NARRATIVE_INPUT)
    text_resp = _mock_text_response(SAMPLE_SYNTHESIS)

    # First 4 calls are tool_use (one per dashboard); 5th is text (synthesis)
    mock_api.create.side_effect = [tool_resp] * n_narrative_calls + [text_resp]
    return mock_api


# ─────────────────────────────────────────────────────────────────────────────
# SERIALISATION
# ─────────────────────────────────────────────────────────────────────────────

class TestSerialise:
    def test_pct_formats_correctly(self) -> None:
        assert _pct(Decimal("0.462")) == "46.2%"

    def test_pct_unavailable(self) -> None:
        assert _pct(UNAVAILABLE) == "UNAVAILABLE"

    def test_pct_sign(self) -> None:
        assert _pct(Decimal("0.02"), sign=True) == "+2.0%"
        assert _pct(Decimal("-0.028"), sign=True) == "-2.8%"

    def test_usd_b_formats_correctly(self) -> None:
        assert _usd_b(Decimal("391035000000")) == "+$391.0B"

    def test_ratio_formats_correctly(self) -> None:
        assert _ratio(Decimal("37.8")) == "37.8x"

    def test_serialise_income_has_required_keys(self, dashboards) -> None:
        income, _, _, _ = dashboards
        data = serialise_income(income)
        assert "ticker" in data
        assert "gross_margin" in data
        assert "operating_margin" in data
        assert "net_margin" in data
        assert "fcf_margin" in data
        assert "revenue_growth_yoy" in data

    def test_serialise_income_latest_is_string(self, dashboards) -> None:
        income, _, _, _ = dashboards
        data = serialise_income(income)
        assert isinstance(data["gross_margin"]["latest"], str)
        assert "%" in data["gross_margin"]["latest"]

    def test_serialise_income_peer_median_present(self, dashboards) -> None:
        income, _, _, _ = dashboards
        data = serialise_income(income)
        assert "peer_median" in data["gross_margin"]

    def test_serialise_income_history_is_list(self, dashboards) -> None:
        income, _, _, _ = dashboards
        data = serialise_income(income)
        assert isinstance(data["gross_margin"]["history"], list)

    def test_serialise_momentum_has_pe_data(self, dashboards) -> None:
        _, momentum, _, _ = dashboards
        data = serialise_momentum(momentum)
        assert "trailing_pe" in data
        assert "forward_pe" in data
        assert "historical_pe" in data

    def test_serialise_momentum_forward_revenue(self, dashboards) -> None:
        _, momentum, _, _ = dashboards
        data = serialise_momentum(momentum)
        # Fixture has analyst estimates so forward_revenue_estimate should be a real value
        assert data["forward_revenue_estimate"] != "UNAVAILABLE"

    def test_serialise_valuation_has_self_history_flags(self, dashboards) -> None:
        _, _, valuation, _ = dashboards
        data = serialise_valuation(valuation)
        assert "vs_own_history" in data["trailing_pe"]
        assert "vs_own_history" in data["price_to_sales"]
        assert "vs_own_history" in data["ev_to_ebitda"]

    def test_serialise_capital_has_price_target(self, dashboards) -> None:
        _, _, _, capital = dashboards
        data = serialise_capital(capital)
        assert "analyst_price_target" in data
        pt = data["analyst_price_target"]
        assert pt["consensus"] == "$237.50"
        assert "implied_upside" in pt


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT CONTRACT
# ─────────────────────────────────────────────────────────────────────────────

class TestSystemPrompt:
    def test_no_invention_rule_present(self) -> None:
        assert "never invent" in SYSTEM_PROMPT.lower() or "do not invent" in SYSTEM_PROMPT.lower()

    def test_unavailable_rule_present(self) -> None:
        assert "UNAVAILABLE" in SYSTEM_PROMPT
        assert "do not estimate" in SYSTEM_PROMPT.lower() or "not available" in SYSTEM_PROMPT.lower()

    def test_forbidden_phrases_listed(self) -> None:
        forbidden = ["good stock", "strong company", "bullish", "bearish"]
        for phrase in forbidden:
            assert phrase in SYSTEM_PROMPT

    def test_trend_verdicts_defined(self) -> None:
        for verdict in ("IMPROVING", "DETERIORATING", "STABLE", "MIXED"):
            assert verdict in SYSTEM_PROMPT


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT BUILDERS — smart question pattern
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptBuilders:
    def test_income_prompt_includes_peer_comparison(self, dashboards) -> None:
        income, _, _, _ = dashboards
        prompt = build_income_prompt(serialise_income(income))
        assert "peer" in prompt.lower()

    def test_income_prompt_includes_time_window(self, dashboards) -> None:
        income, _, _, _ = dashboards
        prompt = build_income_prompt(serialise_income(income))
        assert "annual periods" in prompt.lower()

    def test_income_prompt_asks_improving_or_deteriorating(self, dashboards) -> None:
        income, _, _, _ = dashboards
        prompt = build_income_prompt(serialise_income(income))
        assert "improving" in prompt.lower() or "deteriorating" in prompt.lower()

    def test_income_prompt_contains_ticker(self, dashboards) -> None:
        income, _, _, _ = dashboards
        prompt = build_income_prompt(serialise_income(income))
        assert "AAPL" in prompt

    def test_income_prompt_contains_json_data(self, dashboards) -> None:
        income, _, _, _ = dashboards
        data = serialise_income(income)
        prompt = build_income_prompt(data)
        # JSON data is embedded verbatim
        assert '"gross_margin"' in prompt

    def test_momentum_prompt_asks_about_eps_growth(self, dashboards) -> None:
        _, momentum, _, _ = dashboards
        prompt = build_momentum_prompt(serialise_momentum(momentum))
        assert "eps" in prompt.lower()

    def test_momentum_prompt_asks_about_pe_comparison(self, dashboards) -> None:
        _, momentum, _, _ = dashboards
        prompt = build_momentum_prompt(serialise_momentum(momentum))
        assert "p/e" in prompt.lower() or "trailing" in prompt.lower()

    def test_momentum_prompt_asks_directional_question(self, dashboards) -> None:
        _, momentum, _, _ = dashboards
        prompt = build_momentum_prompt(serialise_momentum(momentum))
        # Prompt must ask whether metrics are accelerating or decelerating
        assert "accelerating" in prompt.lower() or "decelerating" in prompt.lower()

    def test_valuation_prompt_asks_own_history(self, dashboards) -> None:
        _, _, valuation, _ = dashboards
        prompt = build_valuation_prompt(serialise_valuation(valuation))
        assert "own history" in prompt.lower() or "vs_own_history" in prompt

    def test_valuation_prompt_covers_four_multiples(self, dashboards) -> None:
        _, _, valuation, _ = dashboards
        prompt = build_valuation_prompt(serialise_valuation(valuation))
        assert "P/E" in prompt
        assert "P/S" in prompt
        assert "EV/EBITDA" in prompt
        assert "EV/Gross Profit" in prompt

    def test_capital_prompt_asks_roic_vs_peers(self, dashboards) -> None:
        _, _, _, capital = dashboards
        prompt = build_capital_prompt(serialise_capital(capital))
        assert "roic" in prompt.lower()
        assert "peer" in prompt.lower()

    def test_capital_prompt_mentions_buybacks(self, dashboards) -> None:
        _, _, _, capital = dashboards
        prompt = build_capital_prompt(serialise_capital(capital))
        assert "buyback" in prompt.lower()

    def test_capital_prompt_mentions_analyst_target(self, dashboards) -> None:
        _, _, _, capital = dashboards
        prompt = build_capital_prompt(serialise_capital(capital))
        assert "price target" in prompt.lower() or "analyst" in prompt.lower()

    def test_synthesis_prompt_includes_all_four_verdicts(self) -> None:
        prompt = build_synthesis_prompt("STABLE", "IMPROVING", "DETERIORATING", "MIXED", "AAPL")
        assert "STABLE" in prompt
        assert "IMPROVING" in prompt
        assert "DETERIORATING" in prompt
        assert "MIXED" in prompt

    def test_synthesis_prompt_prohibits_recommendation(self) -> None:
        # The synthesis prompt must instruct Claude not to make a buy/sell recommendation.
        prompt = build_synthesis_prompt("STABLE", "STABLE", "STABLE", "STABLE", "AAPL")
        assert "recommendation" in prompt.lower()


# ─────────────────────────────────────────────────────────────────────────────
# PARSING — Claim extraction
# ─────────────────────────────────────────────────────────────────────────────

class TestParsing:
    def test_parse_narrative_fields(self) -> None:
        from fundalyzer.interpret import _parse_narrative
        narrative = _parse_narrative(SAMPLE_NARRATIVE_INPUT)
        assert isinstance(narrative, DashboardNarrative)
        assert narrative.headline != ""
        assert narrative.body != ""
        assert narrative.trend_verdict == "STABLE"

    def test_parse_narrative_claims(self) -> None:
        from fundalyzer.interpret import _parse_narrative
        narrative = _parse_narrative(SAMPLE_NARRATIVE_INPUT)
        assert len(narrative.claims) == 2
        claim = narrative.claims[0]
        assert isinstance(claim, Claim)
        assert "gross_margin_latest=46.2%" in claim.data_points

    def test_parse_narrative_trend_verdict_is_valid(self) -> None:
        from fundalyzer.interpret import _parse_narrative
        from fundalyzer.interpret.models import TrendVerdict
        narrative = _parse_narrative(SAMPLE_NARRATIVE_INPUT)
        assert narrative.trend_verdict in ("IMPROVING", "DETERIORATING", "STABLE", "MIXED")

    def test_claims_have_data_points(self) -> None:
        from fundalyzer.interpret import _parse_narrative
        narrative = _parse_narrative(SAMPLE_NARRATIVE_INPUT)
        for claim in narrative.claims:
            assert len(claim.data_points) > 0, "Every claim must cite at least one value"


# ─────────────────────────────────────────────────────────────────────────────
# END-TO-END interpret() with mocked API
# ─────────────────────────────────────────────────────────────────────────────

class TestInterpretEndToEnd:
    def test_returns_interpretation_object(self, dashboards) -> None:
        income, momentum, valuation, capital = dashboards
        mock_api = _make_mock_api()
        result = interpret(income, momentum, valuation, capital, messages_api=mock_api)
        assert isinstance(result, Interpretation)

    def test_makes_five_api_calls(self, dashboards) -> None:
        income, momentum, valuation, capital = dashboards
        mock_api = _make_mock_api()
        interpret(income, momentum, valuation, capital, messages_api=mock_api)
        assert mock_api.create.call_count == 5  # 4 dashboards + 1 synthesis

    def test_four_narratives_populated(self, dashboards) -> None:
        income, momentum, valuation, capital = dashboards
        mock_api = _make_mock_api()
        result = interpret(income, momentum, valuation, capital, messages_api=mock_api)
        for attr in ("income", "momentum", "valuation", "capital"):
            narrative = getattr(result, attr)
            assert isinstance(narrative, DashboardNarrative)
            assert narrative.headline != ""

    def test_overall_summary_is_the_synthesis_text(self, dashboards) -> None:
        income, momentum, valuation, capital = dashboards
        mock_api = _make_mock_api()
        result = interpret(income, momentum, valuation, capital, messages_api=mock_api)
        assert result.overall_summary == SAMPLE_SYNTHESIS

    def test_system_prompt_passed_to_all_calls(self, dashboards) -> None:
        income, momentum, valuation, capital = dashboards
        mock_api = _make_mock_api()
        interpret(income, momentum, valuation, capital, messages_api=mock_api)
        for call in mock_api.create.call_args_list:
            _, kwargs = call
            assert kwargs.get("system") == SYSTEM_PROMPT, (
                "Every API call must use the shared system prompt"
            )

    def test_tool_choice_forced_for_structured_calls(self, dashboards) -> None:
        income, momentum, valuation, capital = dashboards
        mock_api = _make_mock_api()
        interpret(income, momentum, valuation, capital, messages_api=mock_api)
        # First 4 calls are tool_use calls
        for call in mock_api.create.call_args_list[:4]:
            _, kwargs = call
            tool_choice = kwargs.get("tool_choice", {})
            assert tool_choice.get("type") == "tool", (
                "Structured calls must force tool_choice to prevent free-text drift"
            )

    def test_synthesis_call_has_no_tool(self, dashboards) -> None:
        income, momentum, valuation, capital = dashboards
        mock_api = _make_mock_api()
        interpret(income, momentum, valuation, capital, messages_api=mock_api)
        # 5th call (synthesis) should NOT have tools
        fifth_call = mock_api.create.call_args_list[4]
        _, kwargs = fifth_call
        assert "tools" not in kwargs or not kwargs["tools"]

    def test_ticker_in_income_prompt(self, dashboards) -> None:
        income, momentum, valuation, capital = dashboards
        mock_api = _make_mock_api()
        interpret(income, momentum, valuation, capital, messages_api=mock_api)
        first_call = mock_api.create.call_args_list[0]
        _, kwargs = first_call
        user_content = kwargs["messages"][0]["content"]
        assert "AAPL" in user_content

    def test_synthesis_prompt_includes_verdicts(self, dashboards) -> None:
        income, momentum, valuation, capital = dashboards
        mock_api = _make_mock_api()
        interpret(income, momentum, valuation, capital, messages_api=mock_api)
        synthesis_call = mock_api.create.call_args_list[4]
        _, kwargs = synthesis_call
        user_content = kwargs["messages"][0]["content"]
        assert "STABLE" in user_content  # from the mocked SAMPLE_NARRATIVE_INPUT
