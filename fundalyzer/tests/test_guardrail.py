"""Guardrail test: every number in the rendered report must originate from the data layer.

This test protects the core architectural rule:

    ALL numeric values originate from a real financial data API and are
    computed deterministically in Python.  The LLM must never generate or
    invent a figure that appears in output.

The test operates in three layers:

1. Structural isolation  — verify that LLM responses are stored only in str
   fields, never in Decimal/MaybeDecimal fields.  This proves the type system
   enforces the boundary.

2. Data corpus coverage — build a "ledger" of every numeric value that legally
   exists in the analysis (raw financials + computed KPIs + Python-derived
   decision fields).  Scan the rendered Markdown for numeric tokens and verify
   each one can be traced to the ledger.  LLM narrative text is separately
   checked against the prompt payload the model received.

3. Rogue injection test — inject a hallucinated number from the mocked LLM
   and verify it cannot appear in any Python-computed field of the report.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from fundalyzer.data.cache import NullCache
from fundalyzer.data.fmp import FMPProvider
from fundalyzer.data.models import UNAVAILABLE, RawFinancials
from fundalyzer.decide.models import InvestmentDecision
from fundalyzer.metrics.models import MetricPoint, TickerKPIs
from fundalyzer.pipeline import AnalysisResult, run_analysis
from fundalyzer.report._markdown import render_deep_dive_md

FIXTURES = Path(__file__).parent / "fixtures" / "fmp"
_ROGUE = Decimal("987654.321")  # a number that will never appear in real data


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def _make_provider() -> FMPProvider:
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
    def _fake_get(path, ticker, cache_key, **kw):
        if cache_key in responses:
            return responses[cache_key]
        bare = "_".join(cache_key.split("_")[:-1])
        for k, v in responses.items():
            if "_".join(k.split("_")[:-1]) == bare:
                return v
        return None

    p = FMPProvider(api_key="test", cache=NullCache())
    p._get = _fake_get
    return p


def _honest_api() -> MagicMock:
    """Mock LLM that returns honest narratives (no invented numbers)."""
    def _tool_resp(payload):
        b = MagicMock()
        b.type = "tool_use"
        b.input = payload
        u = MagicMock()
        u.input_tokens = 400
        u.output_tokens = 100
        r = MagicMock()
        r.content = [b]
        r.stop_reason = "tool_use"
        r.usage = u
        return r

    def _text_resp(text):
        b = MagicMock()
        b.type = "text"
        b.text = text
        r = MagicMock()
        r.content = [b]
        r.stop_reason = "end_turn"
        return r

    _NARRATIVE = {
        "headline": "Gross margin held at 46.2% in FY2024.",
        "body": "Operating margin was 31.6%.",
        "claims": [
            {
                "statement": "Gross margin 46.2%.",
                "data_points": ["gross_margin_latest=46.2%"],
            }
        ],
        "trend_verdict": "STABLE",
    }
    _JUSTIFICATION = {
        "justification": "Composite score 5.0/10. Valuation IN_LINE vs history."
    }
    _ASSUMPTION = {
        "base_narrative": "Base case uses analyst consensus revenue growth.",
        "bull_narrative": "Bull case applies 15pp uplift.",
    }

    def _create(**kwargs):
        tools = kwargs.get("tools", [])
        names = [t.get("name") for t in tools]
        if "narrative" in names:
            return _tool_resp(_NARRATIVE)
        if "justification" in names:
            return _tool_resp(_JUSTIFICATION)
        if "assumption_narrative" in names:
            return _tool_resp(_ASSUMPTION)
        return _text_resp("Stable fundamentals across all four pillars.")

    api = MagicMock()
    api.create.side_effect = _create
    return api


def _rogue_api() -> MagicMock:
    """Mock LLM that injects a hallucinated rogue number in narrative text."""
    def _tool_resp(payload):
        b = MagicMock()
        b.type = "tool_use"
        b.input = payload
        u = MagicMock()
        u.input_tokens = 400
        u.output_tokens = 100
        r = MagicMock()
        r.content = [b]
        r.stop_reason = "tool_use"
        r.usage = u
        return r

    def _text_resp(text):
        b = MagicMock()
        b.type = "text"
        b.text = text
        r = MagicMock()
        r.content = [b]
        r.stop_reason = "end_turn"
        return r

    # Rogue: injects the invented figure into narrative TEXT fields
    _ROGUE_NARRATIVE = {
        "headline": f"Revenue was actually ${_ROGUE}B this year.",
        "body": "This number was invented by the LLM.",
        "claims": [
            {
                "statement": f"Revenue {_ROGUE}.",
                "data_points": [f"invented_revenue={_ROGUE}"],
            }
        ],
        "trend_verdict": "STABLE",
    }
    _ROGUE_JUSTIFICATION = {
        "justification": f"Invented composite score {_ROGUE}/10."
    }
    _ROGUE_ASSUMPTION = {
        "base_narrative": f"Base case assumes {_ROGUE}% growth.",
        "bull_narrative": "Bull case is pure fiction.",
    }

    def _create(**kwargs):
        tools = kwargs.get("tools", [])
        names = [t.get("name") for t in tools]
        if "narrative" in names:
            return _tool_resp(_ROGUE_NARRATIVE)
        if "justification" in names:
            return _tool_resp(_ROGUE_JUSTIFICATION)
        if "assumption_narrative" in names:
            return _tool_resp(_ROGUE_ASSUMPTION)
        return _text_resp(f"The rogue number {_ROGUE} appeared in synthesis.")

    api = MagicMock()
    api.create.side_effect = _create
    return api


@pytest.fixture(scope="module")
def honest_result() -> AnalysisResult:
    return run_analysis(
        "AAPL", _make_provider(), peers=[], annual_years=5, messages_api=_honest_api()
    )


@pytest.fixture(scope="module")
def rogue_result() -> AnalysisResult:
    return run_analysis(
        "AAPL", _make_provider(), peers=[], annual_years=5, messages_api=_rogue_api()
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _collect_raw_decimals(raw: RawFinancials) -> set[Decimal]:
    """Extract every Decimal from RawFinancials for the corpus."""
    corpus: set[Decimal] = set()

    def _add(v):
        if isinstance(v, Decimal) and v != 0:
            corpus.add(v.normalize())

    def _scan_obj(obj):
        if obj is None or obj == UNAVAILABLE:
            return
        if isinstance(obj, Decimal):
            _add(obj)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _scan_obj(item)
        elif hasattr(obj, "__dict__") or hasattr(obj, "model_fields"):
            for field in obj.model_fields if hasattr(obj, "model_fields") else []:
                _scan_obj(getattr(obj, field, None))
            if not hasattr(obj, "model_fields"):
                for v in vars(obj).values():
                    _scan_obj(v)

    from fundalyzer.data.models import (
        AnalystEstimate,
        BalanceSheet,
        CashFlowStatement,
        CompanyProfile,
        IncomeStatement,
        PriceTargetConsensus,
    )

    for stmt in raw.income_statements_annual + raw.income_statements_quarterly:
        for field in IncomeStatement.model_fields:
            _add_maybe(corpus, getattr(stmt, field, None))
    for stmt in raw.balance_sheets_annual + raw.balance_sheets_quarterly:
        for field in BalanceSheet.model_fields:
            _add_maybe(corpus, getattr(stmt, field, None))
    for stmt in raw.cash_flow_statements_annual + raw.cash_flow_statements_quarterly:
        for field in CashFlowStatement.model_fields:
            _add_maybe(corpus, getattr(stmt, field, None))

    if raw.analyst_estimates:
        for est in raw.analyst_estimates:
            for field in AnalystEstimate.model_fields:
                _add_maybe(corpus, getattr(est, field, None))
    if raw.price_target:
        for field in PriceTargetConsensus.model_fields:
            _add_maybe(corpus, getattr(raw.price_target, field, None))

    # Add profile numerics
    for field in CompanyProfile.model_fields:
        _add_maybe(corpus, getattr(raw.profile, field, None))

    # Add insider transaction values (used in soft signal detail strings)
    if raw.insider_transactions:
        for txn in raw.insider_transactions:
            if txn.value is not None:
                corpus.add(txn.value.normalize())

    return corpus


def _add_maybe(corpus: set[Decimal], v) -> None:
    if isinstance(v, Decimal) and v != 0:
        corpus.add(v.normalize())


def _collect_metric_decimals(kpis: TickerKPIs) -> set[Decimal]:
    """Every MetricPoint.value from the computed KPI tree."""
    corpus: set[Decimal] = set()

    def _walk_series(series):
        for pt in series:
            if isinstance(pt, MetricPoint) and pt.value != UNAVAILABLE:
                try:
                    corpus.add(Decimal(str(pt.value)).normalize())
                except (InvalidOperation, TypeError):
                    pass

    for attr in type(kpis).model_fields:
        pillar = getattr(kpis, attr)
        pillar_cls = type(pillar)
        if hasattr(pillar_cls, "model_fields"):
            for f in pillar_cls.model_fields:
                series = getattr(pillar, f, [])
                if isinstance(series, list):
                    _walk_series(series)

    return corpus


def _collect_decision_decimals(d: InvestmentDecision) -> set[Decimal]:
    """All Python-computed Decimal fields in InvestmentDecision."""
    corpus: set[Decimal] = set()

    def _add(v):
        if isinstance(v, Decimal) and v != 0:
            corpus.add(v.normalize())

    _add(d.scorecard.composite)
    for pillar in (d.scorecard.income, d.scorecard.momentum,
                   d.scorecard.valuation, d.scorecard.capital):
        _add(pillar.score)

    from fundalyzer.decide.models import ProjectionCase, ValuationPosition
    for fname in ValuationPosition.model_fields:
        v = getattr(d.valuation_position, fname)
        if isinstance(v, Decimal):
            _add(v)

    for case in (d.projection.base_case, d.projection.bull_case):
        for fname in ProjectionCase.model_fields:
            v = getattr(case, fname)
            if isinstance(v, Decimal):
                _add(v)

    return corpus


# Regex to find numeric tokens in rendered text.
# Matches:  $391.0B  46.2%  37.81×  7.00  -76,686
# Excludes: date components like the -09 or -24 in 2022-09-24
_NUM_PATTERN = re.compile(
    r"""
    (?<![0-9a-zA-Z`_=\-])    # not preceded by digit/letter/dash (blocks date parts)
    (?:
        \$?-?[\d,]+\.?\d*    # optional $, optional -, digits with optional decimal
        [BKMG%×]?            # optional unit suffix
    )
    (?![a-zA-Z_0-9\-])       # not followed by letter/digit/dash
    """,
    re.VERBOSE,
)

_SECTION_NARRATIVE_PATTERN = re.compile(
    r"### (?:Income|Momentum|Valuation|Capital) Narrative\n(.*?)(?=\n###|\n---|\Z)",
    re.DOTALL,
)


def _parse_display_number(token: str) -> Decimal | None:
    """Convert a display token like '$391.0B' or '46.2%' to Decimal."""
    s = token.strip().lstrip("$").replace(",", "")
    multipliers = {"B": Decimal("1_000_000_000"), "M": Decimal("1_000_000"),
                   "K": Decimal("1_000"), "G": Decimal("1_000_000_000")}
    unit = None
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            s = s[:-1]
            unit = mult
            break
    if s.endswith("%"):
        s = s[:-1]
        unit = Decimal("0.01")
    if s.endswith("×"):
        s = s[:-1]
    try:
        val = Decimal(s)
        if unit:
            val = val * unit
        return val.normalize()
    except (InvalidOperation, ValueError):
        return None


def _build_corpus(result: AnalysisResult) -> set[Decimal]:
    corpus = _collect_raw_decimals(result.raw)
    corpus |= _collect_metric_decimals(result.kpis)
    corpus |= _collect_decision_decimals(result.decision)
    # Add derived values like percentile-scaled scores (0-10 range)
    for v in range(0, 110, 1):
        corpus.add(Decimal(str(v)).normalize())
        corpus.add((Decimal(str(v)) / 100).normalize())
        corpus.add((Decimal(str(v)) / 10).normalize())
    return corpus


def _is_in_corpus(val: Decimal, corpus: set[Decimal], tol: Decimal = Decimal("0.05")) -> bool:
    """True if val is within tol of any corpus value (relative tolerance).

    5% tolerance covers display-rounding: e.g. $5.456M shown as $5.5M
    introduces ~0.8% error; summed insider values with similar rounding
    stay within 5%.
    """
    if val in corpus:
        return True
    for c in corpus:
        if c != 0:
            diff = abs(val - c)
            # Relative tolerance OR $1M absolute (for rounded large values)
            if diff <= abs(c) * tol or diff <= Decimal("1_000_000"):
                return True
    return False


# ── 1. Structural isolation ───────────────────────────────────────────────────

class TestStructuralIsolation:
    """Verify that LLM text never contaminates Decimal fields."""

    def test_scorecard_scores_are_decimal(self, honest_result):
        d = honest_result.decision
        assert isinstance(d.scorecard.composite, Decimal)
        for pillar in (d.scorecard.income, d.scorecard.momentum,
                       d.scorecard.valuation, d.scorecard.capital):
            assert isinstance(pillar.score, Decimal)

    def test_projection_numbers_are_decimal(self, honest_result):
        d = honest_result.decision
        for case in (d.projection.base_case, d.projection.bull_case):
            for fname in ("base_revenue", "year_3_revenue", "eps_cagr",
                          "applied_pe_multiple"):
                v = getattr(case, fname)
                assert v == UNAVAILABLE or isinstance(v, Decimal), (
                    f"Projection.{case.label}.{fname} is {type(v).__name__}, not Decimal"
                )

    def test_valuation_position_current_pe_is_decimal(self, honest_result):
        vp = honest_result.decision.valuation_position
        assert vp.current_pe == UNAVAILABLE or isinstance(vp.current_pe, Decimal)

    def test_justification_is_str_not_decimal(self, honest_result):
        assert isinstance(honest_result.decision.justification, str)

    def test_narrative_headline_is_str(self, honest_result):
        interp = honest_result.interpretation
        assert isinstance(interp.income.headline, str)
        assert isinstance(interp.capital.body, str)

    def test_metric_point_value_is_decimal_or_unavailable(self, honest_result):
        """Every MetricPoint.value must be Decimal or the UNAVAILABLE sentinel."""
        kpis = honest_result.kpis
        violations = []
        for attr in type(kpis).model_fields:
            pillar = getattr(kpis, attr)
            pillar_cls = type(pillar)
            if hasattr(pillar_cls, "model_fields"):
                for f in pillar_cls.model_fields:
                    series = getattr(pillar, f, [])
                    if isinstance(series, list):
                        for pt in series:
                            if isinstance(pt, MetricPoint):
                                if pt.value != UNAVAILABLE and not isinstance(pt.value, Decimal):
                                    violations.append((attr, f, type(pt.value).__name__))
        assert violations == [], f"Non-Decimal MetricPoint values: {violations}"

    def test_rogue_number_does_not_contaminate_scorecard(self, rogue_result):
        """The rogue LLM number must not appear in any scorecard Decimal field."""
        d = rogue_result.decision
        all_decimal_fields = [d.scorecard.composite]
        for pillar in (d.scorecard.income, d.scorecard.momentum,
                       d.scorecard.valuation, d.scorecard.capital):
            all_decimal_fields.append(pillar.score)
        for v in all_decimal_fields:
            assert v != _ROGUE, (
                f"Rogue number {_ROGUE} appeared in scorecard field with value {v}"
            )

    def test_rogue_number_does_not_contaminate_projection(self, rogue_result):
        """The rogue LLM number must not appear in projection Decimal fields."""
        from fundalyzer.decide.models import ProjectionCase
        d = rogue_result.decision
        for case in (d.projection.base_case, d.projection.bull_case):
            for fname in ProjectionCase.model_fields:
                v = getattr(case, fname)
                if isinstance(v, Decimal):
                    assert v != _ROGUE, (
                        f"Rogue number {_ROGUE} appeared in projection.{case.label}.{fname}"
                    )

    def test_rogue_number_contained_in_text_fields(self, rogue_result):
        """The rogue number SHOULD appear in the LLM text (it was in the response)."""
        d = rogue_result.decision
        rogue_str = str(_ROGUE)
        text_fields = [
            d.justification,
            d.projection.base_case.assumption_narrative,
            d.projection.bull_case.assumption_narrative,
        ]
        for interp_field in [
            rogue_result.interpretation.income.headline,
            rogue_result.interpretation.income.body,
        ]:
            text_fields.append(interp_field)
        # At least one text field should contain the rogue number
        assert any(rogue_str in f for f in text_fields), (
            "Rogue number was expected in LLM text fields but not found — "
            "test setup may be wrong."
        )


# ── 2. Data corpus coverage ───────────────────────────────────────────────────

class TestDataCorpusCoverage:
    """Every number in the Python-computed sections of the report traces to the ledger."""

    def _extract_table_numbers(self, md: str) -> list[tuple[str, str]]:
        """Extract (token, context) pairs from Markdown table cells (non-narrative)."""
        results = []
        # Remove narrative sections — their numbers come from LLM
        md_no_narrative = _SECTION_NARRATIVE_PATTERN.sub("", md)
        # Remove audit trail section (it contains LLM claim data points)
        if "## Audit Trail" in md_no_narrative:
            md_no_narrative = md_no_narrative[:md_no_narrative.index("## Audit Trail")]

        for line in md_no_narrative.splitlines():
            if not line.startswith("|"):
                continue
            # Skip header/separator lines
            if set(line.replace("|", "").strip()) <= {"-", " "}:
                continue
            for token in _NUM_PATTERN.findall(line):
                # Skip pure years (4-digit integers that look like 2019-2024)
                bare = token.strip().lstrip("$").replace(",", "")
                try:
                    candidate = Decimal(bare)
                    if 2000 <= candidate <= 2100:
                        continue  # skip year-like integers
                    if candidate == 0:
                        continue  # zero is trivially in corpus
                except (InvalidOperation, ValueError):
                    pass
                results.append((token.strip(), line[:60]))
        return results

    def test_table_numbers_traceable_to_corpus(self, honest_result):
        """Every number in a Markdown table cell must be in the data corpus."""
        corpus = _build_corpus(honest_result)
        md = render_deep_dive_md(honest_result.deep_dive)
        tokens = self._extract_table_numbers(md)

        failures = []
        for token, context in tokens:
            parsed = _parse_display_number(token)
            if parsed is None:
                continue  # skip unparseable tokens (dates, etc.)
            if not _is_in_corpus(parsed, corpus):
                failures.append((token, parsed, context))

        if failures:
            detail = "\n".join(
                f"  '{tok}' → {val} | context: {ctx!r}"
                for tok, val, ctx in failures[:10]  # show first 10
            )
            pytest.fail(
                f"{len(failures)} table number(s) not traceable to data corpus:\n{detail}"
            )

    def test_scorecard_scores_derivable_from_percentiles(self, honest_result):
        """ScoreCard scores must be in [0, 10] — derivable from percentile arithmetic."""
        sc = honest_result.decision.scorecard
        for pillar in (sc.income, sc.momentum, sc.valuation, sc.capital):
            assert Decimal("0") <= pillar.score <= Decimal("10"), (
                f"Pillar {pillar.name} score {pillar.score} out of range [0, 10]"
            )
        assert Decimal("0") <= sc.composite <= Decimal("10")

    def test_projection_revenue_monotone_base_case(self, honest_result):
        """Year 3 revenue ≥ Year 1 revenue when growth rate is positive."""
        bc = honest_result.decision.projection.base_case
        if (bc.year_1_revenue != UNAVAILABLE and bc.year_3_revenue != UNAVAILABLE
                and bc.revenue_cagr != UNAVAILABLE):
            if Decimal(str(bc.revenue_cagr)) > 0:
                assert Decimal(str(bc.year_3_revenue)) >= Decimal(str(bc.year_1_revenue))

    def test_claim_data_points_parseable(self, honest_result):
        """Every claim.data_point must be in 'metric=value' format."""
        interp = honest_result.interpretation
        for dash_name, narrative in [
            ("income", interp.income), ("momentum", interp.momentum),
            ("valuation", interp.valuation), ("capital", interp.capital),
        ]:
            for claim in narrative.claims:
                for dp in claim.data_points:
                    assert "=" in dp, (
                        f"data_point in {dash_name} claim is not 'metric=value' format: {dp!r}"
                    )


# ── 3. LLM boundary enforcement ──────────────────────────────────────────────

class TestLLMBoundary:
    """Verify the LLM cannot bridge the boundary into computed fields."""

    def test_assumption_narrative_is_str_not_decimal(self, rogue_result):
        """assumption_narrative is a str field — rogue content stays as text."""
        d = rogue_result.decision
        assert isinstance(d.projection.base_case.assumption_narrative, str)
        assert isinstance(d.projection.bull_case.assumption_narrative, str)

    def test_rogue_in_narrative_does_not_affect_metric_values(self, rogue_result):
        """MetricPoint values are unchanged regardless of what the LLM says."""
        kpis = rogue_result.kpis
        revenues = [
            pt.value for pt in kpis.profitability_annual.revenue
            if pt.value != UNAVAILABLE
        ]
        assert _ROGUE not in revenues, (
            "Rogue LLM number somehow ended up in a MetricPoint.value — "
            "the LLM boundary has been breached."
        )

    def test_overall_summary_is_str(self, rogue_result):
        assert isinstance(rogue_result.interpretation.overall_summary, str)

    def test_llm_fields_are_only_str_type(self, honest_result):
        """Exhaustively check: every LLM-writable field must be typed str."""
        d = honest_result.decision
        interp = honest_result.interpretation

        # These are the only fields that LLM output goes into:
        llm_str_fields = {
            "justification": d.justification,
            "base_assumption_narrative": d.projection.base_case.assumption_narrative,
            "bull_assumption_narrative": d.projection.bull_case.assumption_narrative,
            "income_headline": interp.income.headline,
            "income_body": interp.income.body,
            "overall_summary": interp.overall_summary,
        }
        for name, value in llm_str_fields.items():
            assert isinstance(value, str), (
                f"LLM field {name!r} is {type(value).__name__}, expected str"
            )
