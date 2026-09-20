"""Worker Celery: consome um ``analysis_id`` e conclui a mesma linha.

Pontos que o enunciado exige e que estao garantidos aqui:

* analise ja concluida retorna imediatamente, sem chamar a LLM de novo;
* o motor e escolhido pelo idioma resolvido, num ponto so (``select_engine``);
* o relatorio curto e persistido em coluna propria;
* nenhuma tarefa fica presa em ``pending``: toda saida leva a completed ou
  failed, inclusive estouro de tempo.
"""

from __future__ import annotations

import json
import time

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import transaction
from django.utils import timezone

from news.models import Analysis
from portfolios.models import Asset

from .dedup import engine_model_version
from .engine.language import LanguageDecision, SOURCE_STORED
from .engine.schemas import CompanyData, NewsData
from .engine.selector import local_engine_for, select_engine
from .observability import log_event, log_error, log_warning

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


def _resolve_engine(analysis: Analysis):
    """Motor correspondente ao idioma ja gravado na linha.

    Se a configuracao mudou entre o enfileiramento e o processamento, a versao
    efetiva pode divergir da versao gravada. Isso e registrado em log e a
    ``model_version`` NAO e alterada, para nao quebrar a chave de deduplicacao.
    """
    from .services import describe_article, fallback_language

    language = analysis.language
    if language:
        decision = LanguageDecision(language=language, source=SOURCE_STORED, confidence=1.0)
        engine = select_engine(language)
    else:
        decision, engine = describe_article(analysis.article)

    effective = engine_model_version(engine)
    if effective != analysis.model_version:
        log_warning(
            "engine_version_drift", analysis_id=analysis.pk,
            stored=analysis.model_version, effective=effective,
        )
    return decision, engine


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
    started = time.perf_counter()

    try:
        with transaction.atomic():
            analysis = (
                Analysis.objects.select_for_update()
                .select_related("article", "article__source")
                .get(pk=analysis_id)
            )

            if analysis.status == Analysis.Status.COMPLETED:
                # Nunca reconsulta a LLM para uma analise ja concluida.
                log_event("analysis_already_completed", analysis_id=analysis_id)
                return {"analysis_id": analysis_id, "status": "already_completed"}

            analysis.status = Analysis.Status.PROCESSING
            analysis.attempts += 1
            analysis.started_at = timezone.now()
            analysis.finished_at = None
            analysis.last_error = ""
            analysis.save(update_fields=(
                "status", "attempts", "started_at", "finished_at", "last_error", "updated_at",
            ))

            article = analysis.article
            ticker = analysis.ticker
            model_version = analysis.model_version

        decision, engine = _resolve_engine(analysis)

        log_event(
            "analysis_started", analysis_id=analysis_id, ticker=ticker,
            language=decision.language, language_source=decision.source,
            engine=getattr(engine, "name", "?"), version=model_version,
            attempt=analysis.attempts,
        )

        company = _company_data(ticker)
        news = NewsData(
            title=article.title,
            summary=article.summary or "",
            publisher=article.source.name if article.source_id else "",
            published_at=article.published_at.isoformat(),
            url=article.url,
            language=decision.language,
        )

        result = engine.analyze(company, news, decision)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

        payload = result.to_dict()
        payload.update({
            "analysis_id": analysis_id,
            "article_id": article.pk,
            "model_version": model_version,
            "processed_at": timezone.now().isoformat(),
            "processing_time_ms": elapsed_ms,
        })

        with transaction.atomic():
            analysis = Analysis.objects.select_for_update().get(pk=analysis_id)
            analysis.analise = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            analysis.status = Analysis.Status.COMPLETED
            analysis.finished_at = timezone.now()
            analysis.last_error = ""
            analysis.language = result.language
            analysis.engine = result.engine[:60]
            analysis.sentiment_label = result.sentiment_label
            analysis.sentiment_score = result.impact_score
            analysis.relevance_score = result.relevance_score
            analysis.report = result.report
            analysis.llm_used = result.llm_used
            analysis.fallback_reason = (result.fallback_reason or "")[:60]
            analysis.save(update_fields=(
                "analise", "status", "finished_at", "last_error", "language", "engine",
                "sentiment_label", "sentiment_score", "relevance_score", "report",
                "llm_used", "fallback_reason", "updated_at",
            ))

        log_event(
            "analysis_completed", analysis_id=analysis_id, ticker=ticker,
            language=result.language, engine=result.engine, llm_used=result.llm_used,
            fallback_reason=result.fallback_reason or "-", label=result.sentiment_label,
            duration_ms=elapsed_ms,
        )
        return {"analysis_id": analysis_id, "status": "completed"}

    except Analysis.DoesNotExist:
        log_warning("analysis_not_found", analysis_id=analysis_id)
        return {"analysis_id": analysis_id, "status": "not_found"}

    except SoftTimeLimitExceeded as exc:
        # Sem retry: o tempo ja estourou. A linha vai para failed em vez de
        # ficar presa em pending.
        _mark_retry_or_failure(analysis_id, exc, final=True)
        log_error("analysis_timeout", analysis_id=analysis_id)
        return {"analysis_id": analysis_id, "status": "failed", "reason": "soft_time_limit"}

    except Exception as exc:
        final_attempt = self.request.retries >= self.max_retries
        _mark_retry_or_failure(analysis_id, exc, final=final_attempt)
        log_error(
            "analysis_failed", analysis_id=analysis_id,
            error=type(exc).__name__, final=final_attempt,
            retries=self.request.retries,
        )
        if final_attempt:
            raise
        raise self.retry(exc=exc, countdown=min(60, 5 * (2 ** self.request.retries)))
