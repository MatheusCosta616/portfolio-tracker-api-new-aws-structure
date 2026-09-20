"""Criacao idempotente do pedido de analise.

Garantias desta camada, na ordem em que o time pediu:

* analise concluida para a mesma combinacao logica e reaproveitada;
* analise pendente devolve o MESMO ``analysis_id``;
* nunca sao criados dois registros — a UniqueConstraint em
  (article, ticker, model_version) fecha a corrida no banco;
* uma linha ja publicada na fila nao e publicada de novo;
* a LLM nunca e chamada para uma analise que ja existe concluida.
"""

from __future__ import annotations

import json

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from news.models import Analysis, NewsArticle

from .dedup import engine_model_version, news_fingerprint
from .engine.language import PT_BR, resolve_language
from .engine.selector import select_engine
from .observability import log_event, log_warning

DEFAULT_QUEUE = "sentiment_analysis"
DEFAULT_FALLBACK_LANGUAGE = PT_BR

#: Idioma declarado por fonte de noticia. O Google News e consultado com
#: hl=pt-BR&gl=BR, entao tudo que vem dele e portugues por construcao.
DEFAULT_SOURCE_LANGUAGES = {
    "google_news": PT_BR,
}


def queue_name() -> str:
    return getattr(settings, "SENTIMENT_QUEUE", DEFAULT_QUEUE)


def fallback_language() -> str:
    return getattr(settings, "SENTIMENT_FALLBACK_LANGUAGE", DEFAULT_FALLBACK_LANGUAGE)


def source_languages() -> dict:
    configured = getattr(settings, "SENTIMENT_SOURCE_LANGUAGES", None)
    return configured if isinstance(configured, dict) else DEFAULT_SOURCE_LANGUAGES


def source_language_for(article: NewsArticle) -> str | None:
    slug = getattr(getattr(article, "source", None), "slug", None)
    if not slug:
        return None
    return source_languages().get(slug)


def describe_article(article: NewsArticle):
    """Idioma resolvido e motor escolhido para um artigo."""
    stored = (
        Analysis.objects.filter(article_id=article.pk)
        .exclude(language="")
        .values_list("language", flat=True)
        .first()
    )
    decision = resolve_language(
        title=article.title,
        summary=article.summary or "",
        source_language=source_language_for(article),
        stored_language=stored,
        fallback=fallback_language(),
    )
    engine = select_engine(decision.language)
    return decision, engine


def _reuse_completed_twin(article_id: int, ticker: str, version: str, fingerprint: str):
    """Analise concluida para a MESMA noticia canonica, em outro registro.

    Cobre o caso de a mesma materia ter entrado com URLs diferentes (parametros
    de rastreamento). Evita reprocessar e, principalmente, evita chamar a LLM
    de novo.
    """
    if not fingerprint:
        return None
    return (
        Analysis.objects.filter(
            ticker=ticker,
            model_version=version,
            news_fingerprint=fingerprint,
            status=Analysis.Status.COMPLETED,
        )
        .exclude(article_id=article_id)
        .order_by("id")
        .first()
    )


def request_analysis(article_id: int, ticker: str) -> Analysis:
    """Cria (ou reaproveita) o pedido e publica o ID na fila quando preciso."""
    normalized_ticker = (ticker or "").strip().upper()
    if not normalized_ticker:
        raise ValueError("Ticker is required to request sentiment analysis.")

    try:
        article = NewsArticle.objects.select_related("source").get(pk=article_id)
    except NewsArticle.DoesNotExist as exc:
        raise ValueError(f"NewsArticle {article_id} nao existe.") from exc

    decision, engine = describe_article(article)
    version = engine_model_version(engine)
    fingerprint = news_fingerprint(
        title=article.title,
        summary=article.summary or "",
        url=article.url or "",
        source=getattr(getattr(article, "source", None), "slug", "") or "",
    )

    with transaction.atomic():
        try:
            analysis, created = Analysis.objects.get_or_create(
                article_id=article_id,
                ticker=normalized_ticker,
                model_version=version,
                defaults={
                    "status": Analysis.Status.PENDING,
                    "analise": "",
                    "language": decision.language,
                    "news_fingerprint": fingerprint,
                },
            )
        except IntegrityError:
            # Duas requisicoes simultaneas: a constraint do banco barrou a
            # segunda. A linha vencedora ja existe, entao apenas a lemos.
            analysis = Analysis.objects.get(
                article_id=article_id,
                ticker=normalized_ticker,
                model_version=version,
            )
            created = False

        if created:
            twin = _reuse_completed_twin(article_id, normalized_ticker, version, fingerprint)
            if twin is not None:
                analysis.analise = twin.analise
                analysis.status = Analysis.Status.COMPLETED
                analysis.language = twin.language
                analysis.engine = twin.engine
                analysis.sentiment_label = twin.sentiment_label
                analysis.sentiment_score = twin.sentiment_score
                analysis.relevance_score = twin.relevance_score
                analysis.report = twin.report
                analysis.llm_used = twin.llm_used
                analysis.finished_at = timezone.now()
                analysis.save()
                log_event(
                    "analysis_reused_fingerprint",
                    analysis_id=analysis.pk, twin_id=twin.pk,
                    ticker=normalized_ticker, version=version,
                )
                return analysis

        if analysis.status == Analysis.Status.COMPLETED:
            log_event(
                "analysis_reused", analysis_id=analysis.pk,
                ticker=normalized_ticker, version=version, language=analysis.language,
            )
            return analysis

        # Publicar somente quando ha motivo: registro novo, ou tentativa
        # anterior que falhou, ou pendente que nunca chegou a ser publicada
        # (queda do broker). Um pendente ja enfileirado NAO e republicado.
        should_publish = (
            created
            or analysis.status == Analysis.Status.FAILED
            or (analysis.status == Analysis.Status.PENDING and analysis.queued_at is None)
        )
        if not should_publish:
            log_event(
                "analysis_already_queued", analysis_id=analysis.pk,
                ticker=normalized_ticker, status=analysis.status,
            )
            return analysis

        if analysis.status == Analysis.Status.FAILED:
            analysis.status = Analysis.Status.PENDING
            analysis.last_error = ""
        if not analysis.language:
            analysis.language = decision.language
        if not analysis.news_fingerprint:
            analysis.news_fingerprint = fingerprint
        analysis.queued_at = timezone.now()
        analysis.save(update_fields=(
            "status", "last_error", "language", "news_fingerprint", "queued_at", "updated_at",
        ))

        analysis_id = analysis.pk
        target_queue = queue_name()

        def publish() -> None:
            from .tasks import process_analysis

            try:
                process_analysis.apply_async(args=(analysis_id,), queue=target_queue)
                log_event(
                    "analysis_published", analysis_id=analysis_id,
                    ticker=normalized_ticker, queue=target_queue, version=version,
                    language=decision.language, language_source=decision.source,
                    engine=getattr(engine, "name", "?"),
                )
            except Exception as exc:
                # A linha fica com queued_at preenchido mas em pending; o
                # backfill ou uma nova requisicao reenfileira.
                Analysis.objects.filter(pk=analysis_id).update(queued_at=None)
                log_warning(
                    "analysis_publish_failed", analysis_id=analysis_id,
                    ticker=normalized_ticker, error=type(exc).__name__,
                )

        transaction.on_commit(publish)

    return analysis
