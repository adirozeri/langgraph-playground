# Architecture contract: errors communicate real failures, never invented state.
from __future__ import annotations


class ProviderUnavailableError(RuntimeError):
    """A financial data provider returned an unrecoverable error.

    Raised when the primary provider fails and no cache or fallback can fill
    the gap.  The caller should display this message and abort gracefully.
    """

    def __init__(self, ticker: str, provider: str, reason: str) -> None:
        self.ticker = ticker
        self.provider = provider
        self.reason = reason
        super().__init__(f"Provider {provider!r} unavailable for {ticker}: {reason}")


class NoCachedDataError(RuntimeError):
    """Dry-run requested but no cached data exists for this ticker/endpoint.

    Raised by ReadonlyCache when the caller asked for cache-only mode
    (--dry-run) and the requested data is not on disk.
    """

    def __init__(self, ticker: str, endpoint: str) -> None:
        self.ticker = ticker
        self.endpoint = endpoint
        super().__init__(
            f"No cached data for {ticker!r} endpoint {endpoint!r}. "
            "Remove --dry-run to fetch live data."
        )
