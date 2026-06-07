# Architecture contract: implementations must return real API data only — no LLM-generated figures.
from abc import ABC, abstractmethod
from .models import RawFinancials


class FinancialDataProvider(ABC):
    """Adapter interface for financial data providers.

    Add a new provider by subclassing and implementing get_raw_financials.
    Nothing outside the data package should import a concrete provider directly.
    """

    @abstractmethod
    def get_raw_financials(
        self,
        ticker: str,
        quarters: int = 12,
        annual_years: int = 10,
    ) -> RawFinancials:
        """Fetch and normalise all financial data for *ticker*.

        Args:
            ticker: Uppercase stock symbol, e.g. "AAPL".
            quarters: How many trailing quarters of statements to fetch.
            annual_years: How many trailing annual statements to fetch.

        Returns:
            RawFinancials with every field either a real value or UNAVAILABLE.
            Never a fabricated zero or estimate.
        """
        ...

    def get_peer_tickers(self, ticker: str, max_peers: int = 10) -> list[str]:
        """Return comparable tickers for *ticker*.

        Override in providers that support a peer-list endpoint.
        The default returns an empty list so callers can always call this
        without checking whether the provider implements it.
        """
        return []
