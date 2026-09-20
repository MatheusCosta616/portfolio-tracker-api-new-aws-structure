import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from news.fetchers.yfinance_fetcher import YFinanceFetcher
from news.models import NewsArticle, NewsSource
from sentiment_ai.services import request_analysis

from .models import Asset

logger = logging.getLogger(__name__)

_yfinance_fetcher = YFinanceFetcher()


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=90,
    time_limit=120,
)
def analyse_portfolio(self, portfolio_id: int, tickers: list[str]):
    """Fetch portfolio news and enqueue sentiment analysis outside the HTTP request."""
    try:
        source, _ = NewsSource.objects.get_or_create(
            slug='yfinance',
            defaults={'name': 'Yahoo Finance', 'is_active': True},
        )
        fetched = _yfinance_fetcher.fetch(tickers)
        tickers_set = {ticker.upper() for ticker in tickers}
        articles_queued = 0

        for article in fetched:
            obj, _ = NewsArticle.objects.get_or_create(
                url=article.url,
                defaults={
                    'source': source,
                    'title': article.title,
                    'summary': article.summary or '',
                    'thumbnail_url': article.thumbnail_url or '',
                    'published_at': article.published_at,
                },
            )
            related_assets = Asset.objects.filter(
                portfolio_id=portfolio_id,
                ticker__in=article.related_tickers,
            )
            if related_assets.exists():
                obj.tickers.add(*related_assets)

            for ticker in article.related_tickers:
                if ticker.upper() in tickers_set:
                    request_analysis(article_id=obj.pk, ticker=ticker)
                    articles_queued += 1

        logger.info(
            'Portfolio analysis %s queued %s article analyses.',
            portfolio_id,
            articles_queued,
        )
        return {'portfolio_id': portfolio_id, 'articles_queued': articles_queued}
    except SoftTimeLimitExceeded as exc:
        logger.error('Portfolio analysis %s exceeded its soft time limit.', portfolio_id)
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception('Portfolio analysis %s failed.', portfolio_id)
        raise self.retry(exc=exc)