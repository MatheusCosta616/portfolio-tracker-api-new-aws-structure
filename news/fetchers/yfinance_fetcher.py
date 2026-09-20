from __future__ import annotations

import logging
from datetime import datetime, timezone

import yfinance as yf

from .base import BaseNewsFetcher, FetchedArticle

logger = logging.getLogger(__name__)


class YFinanceFetcher(BaseNewsFetcher):
    source_slug = 'yfinance'

    @staticmethod
    def _yf_symbol(ticker: str) -> str:
        """
        yfinance needs '.SA' suffix for B3 tickers (PETR4 → PETR4.SA).
        Brazilian tickers end with digits (PETR4, VALE3, HGLG11).
        US/crypto tickers (AAPL, BTC-USD) are left as-is.
        """
        if '.' in ticker or '-' in ticker:
            return ticker
        if ticker[-1].isdigit():
            return ticker + '.SA'
        return ticker

    def fetch(self, tickers: list[str]) -> list[FetchedArticle]:
        articles = []
        seen_urls = set()

        for ticker in tickers:
            symbol = self._yf_symbol(ticker)
            try:
                raw_news = yf.Ticker(symbol).news or []
            except Exception as exc:
                logger.warning('yfinance: failed to fetch news for %s: %s', symbol, exc)
                continue

            for item in raw_news:
                content = item.get('content', {})
                url = content.get('canonicalUrl', {}).get('url') or item.get('link', '')
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                pub_raw = content.get('pubDate') or item.get('providerPublishTime')
                if isinstance(pub_raw, int):
                    published_at = datetime.fromtimestamp(pub_raw, tz=timezone.utc)
                elif isinstance(pub_raw, str):
                    try:
                        published_at = datetime.fromisoformat(pub_raw)
                    except ValueError:
                        published_at = datetime.now(tz=timezone.utc)
                else:
                    published_at = datetime.now(tz=timezone.utc)

                thumbnail = ''
                thumb_data = content.get('thumbnail') or item.get('thumbnail', {})
                if isinstance(thumb_data, dict):
                    resolutions = thumb_data.get('resolutions', [])
                    if resolutions:
                        thumbnail = resolutions[0].get('url', '')

                related_raw = [t.get('symbol', '') for t in item.get('relatedTickers', []) if t.get('symbol')]
                # Strip .SA suffix so tickers match what users store (e.g. PETR4, not PETR4.SA)
                related = [s.replace('.SA', '') for s in related_raw] if related_raw else [ticker]

                articles.append(FetchedArticle(
                    title=content.get('title') or item.get('title', ''),
                    url=url,
                    published_at=published_at,
                    summary=content.get('summary') or item.get('summary', ''),
                    thumbnail_url=thumbnail,
                    related_tickers=related,
                ))

        return articles
