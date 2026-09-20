from __future__ import annotations

import logging

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from news.models import NewsArticle
from portfolios.models import Asset

from .services import request_analysis

logger = logging.getLogger(__name__)


@receiver(m2m_changed, sender=NewsArticle.tickers.through)
def create_analysis_requests_for_linked_tickers(
    sender,
    instance,
    action,
    reverse,
    model,
    pk_set,
    **kwargs,
):
    """Create one Analysis row per article+ticker after the existing link is made.

    This signal keeps the current news tasks untouched. Their existing call to
    ``article.tickers.add(...)`` is enough to start the sentiment pipeline.
    """
    if action != "post_add" or not pk_set:
        return

    try:
        if reverse:
            # An Asset received one or more NewsArticle relationships.
            ticker = instance.ticker
            article_ids = pk_set
            for article_id in article_ids:
                request_analysis(article_id=article_id, ticker=ticker)
            return

        # A NewsArticle received one or more Asset relationships.
        tickers = (
            Asset.objects.filter(pk__in=pk_set)
            .values_list("ticker", flat=True)
            .distinct()
        )
        for ticker in tickers:
            request_analysis(article_id=instance.pk, ticker=ticker)
    except Exception:
        # The news relationship must not be rolled back only because publishing
        # an asynchronous analysis request failed. The error remains visible in
        # logs and the backfill command can recreate missing requests.
        logger.exception(
            "Could not create sentiment requests for article relationship %s.",
            getattr(instance, "pk", None),
        )
