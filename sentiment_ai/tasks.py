from __future__ import annotations

import json
import logging
import time

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from news.models import Analysis
from portfolios.models import Asset

from .engine import CompanyData, NewsData, analyze_news_for_company

logger = logging.getLogger(__name__)

ASSET_TYPE_CONTEXT = {
    "stock": "empresa de capital aberto",
    "fii": "fundo de investimento imobiliario",
    "crypto": "criptoativo e tecnologia blockchain",
    "etf": "fundo de indice",
    "bdr": "empresa estrangeira negociada por BDR",
}


def _company_data(ticker: str) -> CompanyData:
    asset = (
        Asset.objects.filter(ticker__iexact=ticker)
        .only("ticker", "name", "asset_type")
        .order_by("id")
        .first()
    )
    if asset is None:
        return CompanyData(ticker=ticker, name=ticker)

    name = asset.name.strip() if asset.name else ticker
    context = ASSET_TYPE_CONTEXT.get(asset.asset_type, asset.asset_type or "")
    return CompanyData(
        ticker=ticker,
        name=name,
        sector=context,
        description=f"{name} ({ticker}) e um {context}." if context else name,
        aliases=(ticker.replace(".SA", ""),),
    )


def _mark_retry_or_failure(analysis_id: int, error: Exception, final: bool) -> None:
    status = Analysis.Status.FAILED if final else Analysis.Status.PENDING
    Analysis.objects.filter(pk=analysis_id).update(
        status=status,
        last_error=str(error)[:2000],
        finished_at=timezone.now() if final else None,
        updated_at=timezone.now(),
    )


@shared_task(
    bind=True,
    name="sentiment_ai.process_analysis",
    max_retries=3,
    soft_time_limit=150,
    time_limit=180,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_analysis(self, analysis_id: int):
    """Consume a request and complete the same row in ``analises``."""
    started = time.perf_counter()

    try:
        with transaction.atomic():
            analysis = (
                Analysis.objects.select_for_update()
                .select_related("article")
                .get(pk=analysis_id)
            )

            if analysis.status == Analysis.Status.COMPLETED:
                return {"analysis_id": analysis_id, "status": "already_completed"}

            analysis.status = Analysis.Status.PROCESSING
            analysis.attempts += 1
            analysis.started_at = timezone.now()
            analysis.finished_at = None
            analysis.last_error = ""
            analysis.save(
                update_fields=(
                    "status",
                    "attempts",
                    "started_at",
                    "finished_at",
                    "last_error",
                    "updated_at",
                )
            )

            article = analysis.article
            ticker = analysis.ticker
            model_version = analysis.model_version

        company = _company_data(ticker)
        news = NewsData(
            title=article.title,
            summary=article.summary or "",
            publisher=article.source.name if article.source_id else "",
            published_at=article.published_at.isoformat(),
            url=article.url,
        )
        result = analyze_news_for_company(company, news).to_dict()
        result.update(
            {
                "analysis_id": analysis_id,
                "article_id": article.pk,
                "model_version": model_version,
                "processed_at": timezone.now().isoformat(),
                "processing_time_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )

        with transaction.atomic():
            analysis = Analysis.objects.select_for_update().get(pk=analysis_id)
            analysis.analise = json.dumps(result, ensure_ascii=False, sort_keys=True)
            analysis.status = Analysis.Status.COMPLETED
            analysis.finished_at = timezone.now()
            analysis.last_error = ""
            analysis.save(
                update_fields=(
                    "analise",
                    "status",
                    "finished_at",
                    "last_error",
                    "updated_at",
                )
            )

        logger.info("Sentiment analysis %s completed for %s.", analysis_id, ticker)
        return {"analysis_id": analysis_id, "status": "completed"}

    except Analysis.DoesNotExist:
        logger.warning("Sentiment analysis %s no longer exists.", analysis_id)
        return {"analysis_id": analysis_id, "status": "not_found"}
    except Exception as exc:
        final_attempt = self.request.retries >= self.max_retries
        _mark_retry_or_failure(analysis_id, exc, final=final_attempt)
        logger.exception("Sentiment analysis %s failed.", analysis_id)
        if final_attempt:
            raise
        raise self.retry(exc=exc, countdown=min(60, 5 * (2 ** self.request.retries)))
