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


@dataclass(frozen=True)
class SentimentResult:
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

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["detected_topics"] = list(self.detected_topics)
        value["positive_signals"] = list(self.positive_signals)
        value["negative_signals"] = list(self.negative_signals)
        return value
