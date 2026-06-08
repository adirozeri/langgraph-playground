"""Smoke tests: every module must be importable without side effects."""


def test_import_settings():
    import fundalyzer.settings


def test_import_data():
    import fundalyzer.data
    import fundalyzer.data.base
    import fundalyzer.data.fmp
    import fundalyzer.data.models


def test_import_metrics():
    import fundalyzer.metrics
    import fundalyzer.metrics.models


def test_import_peers():
    import fundalyzer.peers
    import fundalyzer.peers.models


def test_import_dashboards():
    import fundalyzer.dashboards
    import fundalyzer.dashboards.models


def test_import_interpret():
    import fundalyzer.interpret
    import fundalyzer.interpret.models


def test_import_decide():
    import fundalyzer.decide
    import fundalyzer.decide.models


def test_import_report():
    import fundalyzer.report
    import fundalyzer.report.models


def test_import_cli():
    import fundalyzer.cli


def test_provider_is_abstract():
    import inspect
    from fundalyzer.data.base import FinancialDataProvider

    assert inspect.isabstract(FinancialDataProvider)


def test_fmp_provider_subclasses_interface():
    from fundalyzer.data.base import FinancialDataProvider
    from fundalyzer.data.fmp import FMPProvider

    assert issubclass(FMPProvider, FinancialDataProvider)


def test_investment_lean_values():
    from fundalyzer.decide.models import InvestmentLean

    assert set(InvestmentLean) == {
        InvestmentLean.INVEST,
        InvestmentLean.HOLD,
        InvestmentLean.AVOID,
    }
