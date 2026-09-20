from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests

from .base import BaseNewsFetcher, FetchedArticle

logger = logging.getLogger(__name__)


class GoogleNewsFetcher(BaseNewsFetcher):
    source_slug = 'google_news'
    _BASE_URL = 'https://news.google.com/rss/search'
    _HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; portfolio-tracker/1.0)'}

    def fetch(self, tickers: list[str]) -> list[FetchedArticle]:
        articles = []
        seen_urls: set[str] = set()

        for ticker in tickers:
            query = f'{ticker} fundo imobiliário' if self._is_fii(ticker) else ticker
            url = f"{self._BASE_URL}?q={quote(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-BR"

            try:
                resp = requests.get(url, timeout=10, headers=self._HEADERS)
                resp.raise_for_status()
            except Exception as exc:
                logger.warning('GoogleNews: request failed for %s: %s', ticker, exc)
                continue

            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError as exc:
                logger.warning('GoogleNews: XML parse error for %s: %s', ticker, exc)
                continue

            for item in root.findall('.//item'):
                link = item.findtext('link') or ''
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)

                pub_date_str = item.findtext('pubDate') or ''
                try:
                    published_at = parsedate_to_datetime(pub_date_str)
                except Exception:
                    published_at = datetime.now(tz=timezone.utc)

                articles.append(FetchedArticle(
                    title=item.findtext('title') or '',
                    url=link,
                    published_at=published_at,
                    summary=item.findtext('description') or '',
                    related_tickers=[ticker],
                ))

        return articles

    @staticmethod
    def _is_fii(ticker: str) -> bool:
        return len(ticker) >= 5 and (ticker.endswith('11') or ticker.endswith('12'))
