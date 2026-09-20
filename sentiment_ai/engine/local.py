"""Motor heuristico local, parametrizado por idioma.

Uma unica implementacao do pipeline; o que muda entre portugues e ingles e o
lexico injetado e o uso (ou nao) do VADER, que e treinado apenas em ingles.
"""

from __future__ import annotations

from functools import lru_cache

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except ImportError:  # pragma: no cover - o fallback lexical continua valendo
    SentimentIntensityAnalyzer = None

from .base import AnalysisEngine
from .heuristic import (
    IRRELEVANCE_THRESHOLD,
    clamp,
    company_relevance,
    confidence_for,
    detect_topics,
    infer_sector_key,
    label_for,
    lexical_score,
    phrase_polarity,
    sector_adjustment,
    surface_map,
    surface_phrase,
)
from .language import LanguageDecision
from .report import build_report
from .schemas import CompanyData, NewsData, SentimentResult

ENGINE_VERSION = "3.0.0"


@lru_cache(maxsize=1)
def _vader():
    return SentimentIntensityAnalyzer() if SentimentIntensityAnalyzer else None


class LocalLexicalEngine(AnalysisEngine):
    """Base dos motores locais. Nao deve ser instanciada diretamente."""

    lexicon = None
    use_vader = False
    lexical_weight = 0.75
    vader_weight = 0.0
    phrase_weight = 0.60
    version = ENGINE_VERSION
    human_label = "motor local"

    def analyze(
        self,
        company: CompanyData,
        news: NewsData,
        decision: LanguageDecision,
    ) -> SentimentResult:
        # O titulo entra duas vezes de proposito: ele carrega o evento principal.
        original = f"{news.title}. {news.title}. {news.summary}".strip()

        topics = detect_topics(original)
        sector_key = infer_sector_key(company)
        relevance, relevance_reasons = company_relevance(original, company, topics, sector_key)

        lex = lexical_score(original, self.lexicon)
        phrase_score, phrase_positive, phrase_negative = phrase_polarity(original)

        vader_score = 0.0
        if self.use_vader:
            analyzer = _vader()
            if analyzer is not None:
                vader_score = float(analyzer.polarity_scores(original)["compound"])

        text_score = clamp(
            lex.score * self.lexical_weight
            + vader_score * self.vader_weight
            + phrase_score * self.phrase_weight
        )

        raw_adjustment, sector_positive, sector_negative = sector_adjustment(
            original, topics, sector_key
        )

        if relevance < IRRELEVANCE_THRESHOLD:
            gated_adjustment = 0.0
            impact = 0.0
        else:
            gated_adjustment = raw_adjustment * relevance
            impact = clamp(text_score + gated_adjustment)

        label = label_for(impact, relevance)
        positive = tuple(sorted({*(f"word:{t}" for t in lex.positive), *phrase_positive, *sector_positive}))
        negative = tuple(sorted({*(f"word:{t}" for t in lex.negative), *phrase_negative, *sector_negative}))
        confidence = confidence_for(label, relevance, text_score, gated_adjustment)

        highlights = self._highlights(original, label, lex, phrase_positive, phrase_negative)
        engine_label = f"{self.human_label} ({self.engine_id})"

        report = build_report(
            ticker=company.ticker,
            company_name=company.name or company.ticker,
            title=news.title,
            summary=news.summary,
            label=label,
            impact_score=impact,
            relevance_score=relevance,
            highlights=highlights,
            relevance_reasons=relevance_reasons,
            topics=topics,
            irrelevance_threshold=IRRELEVANCE_THRESHOLD,
            engine_label=engine_label,
        )

        return SentimentResult(
            ticker=company.ticker,
            company_name=company.name or company.ticker,
            language=decision.language,
            relevance_score=round(relevance, 4),
            text_sentiment_score=round(text_score, 4),
            adjustment_score=round(gated_adjustment, 4),
            impact_score=round(impact, 4),
            sentiment_label=label,
            confidence=confidence,
            detected_topics=topics,
            positive_signals=positive,
            negative_signals=negative,
            # A explicacao passa a ser o proprio relatorio fundamentado: o app
            # ja le esse campo e ganha o texto bom sem mudar uma linha.
            explanation=report,
            report=report,
            engine=self.name,
            engine_version=self.version,
            language_source=decision.source,
            llm_used=False,
            fallback_reason="",
            highlights=highlights,
            relevance_reasons=relevance_reasons,
        )

    def _highlights(self, original, label, lex, phrase_positive, phrase_negative) -> tuple[str, ...]:
        """Expressoes reais do texto que sustentam a nota."""
        words = surface_map(original)
        if label == "negative":
            terms, phrases = lex.negative, phrase_negative
        elif label == "positive":
            terms, phrases = lex.positive, phrase_positive
        else:
            terms = (*lex.positive, *lex.negative)
            phrases = (*phrase_positive, *phrase_negative)

        found: list[str] = []
        for phrase in phrases:
            readable = surface_phrase(original, phrase.split(":", 1)[-1])
            if readable and readable not in found:
                found.append(readable)
        for term in terms:
            readable = words.get(term, term)
            if readable and not any(readable.lower() in f.lower() for f in found):
                found.append(readable)
        return tuple(found[:5])
