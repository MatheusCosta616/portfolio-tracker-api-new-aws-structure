from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FetchedArticle:
    title: str
    url: str
    published_at: datetime
    summary: str = ''
    thumbnail_url: str = ''
    related_tickers: list[str] = field(default_factory=list)


class BaseNewsFetcher(ABC):
    """
    Base class for all news source integrations.
    To add a new hub: subclass this, implement `fetch`, and register in registry.py.
    """
    source_slug: str = ''

    @abstractmethod
    def fetch(self, tickers: list[str]) -> list[FetchedArticle]:
        """Fetch news articles for the given list of tickers."""
        ...
