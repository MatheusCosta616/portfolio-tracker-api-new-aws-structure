import logging

from celery import shared_task

from .fetchers.registry import get_fetcher
from .models import NewsArticle, NewsSource
from notifications.tasks import send_push_for_article
from portfolios.models import Asset

logger = logging.getLogger(__name__)


@shared_task
def fetch_news_for_ticker(ticker: str):
    """Immediately fetch and save news for a single ticker (called on asset creation)."""
    sources = NewsSource.objects.filter(is_active=True)

    for source in sources:
        try:
            fetcher = get_fetcher(source.slug)
        except ValueError:
            continue

        try:
            articles = fetcher.fetch([ticker])
        except Exception as exc:
            logger.error('fetch_news_for_ticker %s via %s: %s', ticker, source.slug, exc)
            continue

        for article in articles:
            obj, created = NewsArticle.objects.get_or_create(
                url=article.url,
                defaults={
                    'source': source,
                    'title': article.title,
                    'summary': article.summary,
                    'thumbnail_url': article.thumbnail_url,
                    'published_at': article.published_at,
                },
            )
            # Link to ALL asset instances with matching tickers (new and existing)
            related_assets = Asset.objects.filter(ticker__in=article.related_tickers)
            obj.tickers.add(*related_assets)

            if created:
                send_push_for_article.delay(obj.pk)

    logger.info('fetch_news_for_ticker: done for %s', ticker)


@shared_task(bind=True, max_retries=3)
def fetch_news_for_all_active_sources(self):
    """
    Fetches news from every active NewsSource and saves new articles.
    Runs periodically via Celery Beat.
    """
    sources = NewsSource.objects.filter(is_active=True)
    tickers = list(Asset.objects.values_list('ticker', flat=True).distinct())

    if not tickers:
        logger.info('No tickers found, skipping news fetch.')
        return

    for source in sources:
        try:
            fetcher = get_fetcher(source.slug)
        except ValueError:
            logger.warning('No fetcher registered for source slug "%s", skipping.', source.slug)
            continue

        try:
            articles = fetcher.fetch(tickers)
        except Exception as exc:
            logger.error('Fetcher %s raised an error: %s', source.slug, exc)
            self.retry(exc=exc, countdown=60)
            continue

        new_count = 0
        for article in articles:
            obj, created = NewsArticle.objects.get_or_create(
                url=article.url,
                defaults={
                    'source': source,
                    'title': article.title,
                    'summary': article.summary,
                    'thumbnail_url': article.thumbnail_url,
                    'published_at': article.published_at,
                },
            )

            related_assets = Asset.objects.filter(ticker__in=article.related_tickers)
            obj.tickers.add(*related_assets)
            if created:
                new_count += 1
                send_push_for_article.delay(obj.pk)

        logger.info('Source %s: %d new articles saved.', source.slug, new_count)
