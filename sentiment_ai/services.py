from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction

from news.models import Analysis

logger = logging.getLogger(__name__)

DEFAULT_MODEL_VERSION = "rules-v2.0.0"
DEFAULT_QUEUE = "sentiment_analysis"


def model_version() -> str:
    return getattr(settings, "SENTIMENT_MODEL_VERSION", DEFAULT_MODEL_VERSION)


def queue_name() -> str:
    return getattr(settings, "SENTIMENT_QUEUE", DEFAULT_QUEUE)


def request_analysis(article_id: int, ticker: str) -> Analysis:
    """Create the Analysis row and publish only its ID to RabbitMQ.

    The same database row is later completed by the sentiment worker. Existing
    rows for the same article, ticker and model version are reused so repeated
    M2M events do not create duplicate requests.
    """
    normalized_ticker = (ticker or "").strip().upper()
    if not normalized_ticker:
        raise ValueError("Ticker is required to request sentiment analysis.")

    version = model_version()

    with transaction.atomic():
        # Oracle does not allow LIMIT/OFFSET with SELECT FOR UPDATE, so we
        # first retrieve the PK without a lock, then lock the specific row.
        existing_id = (
            Analysis.objects.filter(
                article_id=article_id,
                ticker=normalized_ticker,
                model_version=version,
            )
            .order_by("id")
            .values_list("id", flat=True)
            .first()
        )
        analysis = (
            Analysis.objects.select_for_update().get(pk=existing_id)
            if existing_id
            else None
        )

        created = analysis is None
        if created:
            analysis = Analysis.objects.create(
                article_id=article_id,
                ticker=normalized_ticker,
                status=Analysis.Status.PENDING,
                model_version=version,
                analise="",
            )

        should_publish = created or analysis.status in {
            Analysis.Status.PENDING,
            Analysis.Status.FAILED,
        }
        if should_publish:
            if analysis.status == Analysis.Status.FAILED:
                analysis.status = Analysis.Status.PENDING
                analysis.last_error = ""
                analysis.save(update_fields=("status", "last_error", "updated_at"))

            analysis_id = analysis.pk

            def publish() -> None:
                from .tasks import process_analysis

                try:
                    process_analysis.apply_async(
                        args=(analysis_id,),
                        queue=queue_name(),
                    )
                except Exception:
                    logger.exception(
                        "Could not publish sentiment analysis %s to RabbitMQ.",
                        analysis_id,
                    )

            transaction.on_commit(publish)

    return analysis
