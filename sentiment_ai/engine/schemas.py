from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CompanyData:
    ticker: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    country: str = ""
    description: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NewsData:
    title: str
    summary: str = ""
    publisher: str = ""
    published_at: str = ""
    url: str = ""
    language: str = ""


@dataclass(frozen=True)
class SentimentResult:
    """Resultado de uma analise.

    Os campos ate ``explanation`` sao os mesmos da versao anterior e continuam
    no mesmo formato: o app mobile le esse dicionario e nao pode quebrar. Tudo
    que vem depois e aditivo e tem valor padrao.
    """

    ticker: str
    company_name: str
    language: str
    relevance_score: float
    text_sentiment_score: float
    adjustment_score: float
    impact_score: float
    sentiment_label: str
    confidence: float
    detected_topics: tuple[str, ...]
    positive_signals: tuple[str, ...]
    negative_signals: tuple[str, ...]
    explanation: str

    # --- Campos aditivos (P1) -------------------------------------------------
    report: str = ""
    engine: str = ""
    engine_version: str = ""
    language_source: str = ""
    llm_used: bool = False
    fallback_reason: str = ""
    highlights: tuple[str, ...] = field(default_factory=tuple)
    relevance_reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "detected_topics",
            "positive_signals",
            "negative_signals",
            "highlights",
            "relevance_reasons",
        ):
            value[key] = list(getattr(self, key))
        return value
