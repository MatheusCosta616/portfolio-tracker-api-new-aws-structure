"""Motor apoiado em LLM externa, com fallback obrigatorio.

Se a LLM falhar por qualquer motivo — timeout, limite de requisicoes, JSON
invalido, credencial rejeitada, provedor fora do ar, resposta incompleta — o
motor local do mesmo idioma assume e o resultado registra qual motor produziu a
analise e por que houve fallback. Uma tarefa nunca fica presa em ``pending``.
"""

from __future__ import annotations

import logging

from ..llm import LlmError, LlmProvider, LlmRequest
from ..llm.config import LlmConfig
from .base import AnalysisEngine
from .heuristic import IRRELEVANCE_THRESHOLD, detect_topics, infer_sector_key
from .language import LanguageDecision
from .local import ENGINE_VERSION
from .report import LABEL_PT, format_score, relevance_word
from .schemas import CompanyData, NewsData, SentimentResult

logger = logging.getLogger(__name__)


class LlmAnalysisEngine(AnalysisEngine):
    name = "llm"
    version = ENGINE_VERSION

    def __init__(self, provider: LlmProvider, config: LlmConfig, fallback: AnalysisEngine):
        self._provider = provider
        self._config = config
        self._fallback = fallback
        self.language = fallback.language
        self.name = f"llm-{provider.name}"

    @property
    def engine_id(self) -> str:
        return f"{self.name}-{self.version}-{self._config.fingerprint}"

    @property
    def fallback_engine(self) -> AnalysisEngine:
        return self._fallback

    def analyze(
        self,
        company: CompanyData,
        news: NewsData,
        decision: LanguageDecision,
    ) -> SentimentResult:
        request = LlmRequest(
            ticker=company.ticker,
            company_name=company.name or company.ticker,
            sector=company.sector or company.industry or "",
            title=news.title or "",
            summary=news.summary or "",
            language=decision.language,
            published_at=news.published_at or "",
            publisher=news.publisher or "",
        )

        try:
            analysis = self._provider.analyze_news(request)
        except LlmError as exc:
            reason = getattr(exc, "reason", "llm_error")
            logger.warning(
                "llm_fallback ticker=%s provider=%s reason=%s detail=%s",
                company.ticker, self._provider.name, reason, str(exc)[:200],
            )
            result = self._fallback.analyze(company, news, decision)
            return self._mark_fallback(result, reason)
        except Exception as exc:  # pragma: no cover - rede de seguranca
            logger.exception("llm_unexpected ticker=%s provider=%s", company.ticker, self._provider.name)
            result = self._fallback.analyze(company, news, decision)
            return self._mark_fallback(result, f"unexpected:{type(exc).__name__}")

        return self._to_result(company, news, decision, analysis)

    def _mark_fallback(self, result: SentimentResult, reason: str) -> SentimentResult:
        from dataclasses import replace

        suffix = f" A LLM externa nao pode ser usada nesta analise ({reason}); o resultado vem do motor local."
        return replace(
            result,
            llm_used=False,
            fallback_reason=reason,
            report=result.report + suffix,
            explanation=result.explanation + suffix,
        )

    def _to_result(self, company, news, decision, analysis) -> SentimentResult:
        topics = detect_topics(f"{news.title}. {news.summary}")
        sector_key = infer_sector_key(company)
        label = analysis.sentiment_label
        display = company.name or company.ticker
        subject = f"{company.ticker} ({display})" if display != company.ticker else company.ticker
        engine_label = f"LLM {self._config.describe()}"

        if label == "irrelevant":
            report = (
                f"A noticia nao foi considerada relevante para {subject}: a relevancia ficou em "
                f"{analysis.relevance_score:.2f}, abaixo do limite de {IRRELEVANCE_THRESHOLD:.2f}. "
                f"{analysis.reasoning} Analise produzida por {engine_label}."
            )
        else:
            resumo = f" {analysis.summary}" if analysis.summary else ""
            report = (
                f"A noticia foi classificada como {LABEL_PT.get(label, label)} para {subject}, "
                f"com nota {format_score(analysis.sentiment_score)} numa escala de -1 a +1."
                f"{resumo} {analysis.reasoning} "
                f"A relevancia para o ativo foi considerada "
                f"{relevance_word(analysis.relevance_score)} ({analysis.relevance_score:.2f}). "
                f"Analise produzida por {engine_label}."
            )

        return SentimentResult(
            ticker=company.ticker,
            company_name=display,
            language=decision.language,
            relevance_score=analysis.relevance_score,
            text_sentiment_score=analysis.sentiment_score,
            adjustment_score=0.0,
            impact_score=analysis.sentiment_score,
            sentiment_label=label,
            confidence=round(min(0.95, 0.45 + analysis.relevance_score * 0.4), 3),
            detected_topics=topics,
            positive_signals=(),
            negative_signals=(),
            explanation=report,
            report=report,
            engine=self.name,
            engine_version=f"{self.version}-{self._config.fingerprint}",
            language_source=decision.source,
            llm_used=True,
            fallback_reason="",
            highlights=(),
            relevance_reasons=(f"setor considerado: {sector_key}",),
        )
