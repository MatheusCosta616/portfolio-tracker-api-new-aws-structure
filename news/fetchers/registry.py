from __future__ import annotations

from .base import BaseNewsFetcher
from .yfinance_fetcher import YFinanceFetcher
from .google_news_fetcher import GoogleNewsFetcher

# Map slug → fetcher class.
# To add a new hub, import its class and add it here.
FETCHER_REGISTRY: dict[str, type[BaseNewsFetcher]] = {
    YFinanceFetcher.source_slug: YFinanceFetcher,
    GoogleNewsFetcher.source_slug: GoogleNewsFetcher,
    # 'finnhub': FinnhubFetcher,
    # 'newsapi': NewsApiFetcher,
}


def get_fetcher(slug: str) -> BaseNewsFetcher:
    cls = FETCHER_REGISTRY.get(slug)
    if cls is None:
        raise ValueError(f'No fetcher registered for slug "{slug}"')
    return cls()
