"""Fachada de compatibilidade.

O pipeline antigo vivia inteiro neste arquivo. Ele foi quebrado em
``heuristic``/``local``/``english``/``portuguese``/``llm_engine``; o que resta
aqui e a assinatura antiga, para nao quebrar quem ja importava daqui.
"""

from __future__ import annotations

from .heuristic import IRRELEVANCE_THRESHOLD  # noqa: F401 (reexport)
from .language import resolve_language
from .schemas import CompanyData, NewsData, SentimentResult
from .selector import local_engine_for, select_engine


def analyze_news_for_company(
    company: CompanyData,
    news: NewsData,
    *,
    language: str | None = None,
    use_llm: bool = False,
) -> SentimentResult:
    """Analisa uma noticia para um ativo.

    ``language`` informado pula a deteccao. ``use_llm=False`` (padrao) garante
    motor local, que e o que os testes deterministicos usam.
    """
    decision = resolve_language(
        title=news.title,
        summary=news.summary,
        source_language=language or news.language,
    )
    engine = select_engine(decision.language) if use_llm else local_engine_for(decision.language)
    return engine.analyze(company, news, decision)
