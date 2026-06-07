"""Default peer list derivation from the data provider."""
from __future__ import annotations

import logging

from ..data.base import FinancialDataProvider

log = logging.getLogger(__name__)

MAX_PEERS: int = 10


def derive_peers(
    ticker: str,
    provider: FinancialDataProvider,
    max_peers: int = MAX_PEERS,
) -> list[str]:
    """Return up to *max_peers* comparable tickers for *ticker*.

    Calls ``provider.get_peer_tickers()``; providers that do not support
    the endpoint return an empty list (the base-class default).

    The target ticker is always stripped from the returned list.
    """
    ticker = ticker.upper()
    try:
        raw = provider.get_peer_tickers(ticker, max_peers=max_peers + 1)
    except Exception as exc:
        log.warning("Could not derive peer list for %s: %s", ticker, exc)
        return []

    filtered = [t.upper() for t in raw if t.upper() != ticker]
    return filtered[:max_peers]
