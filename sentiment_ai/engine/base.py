"""Contrato comum dos motores de analise.

    AnalysisEngine
    ├── EnglishAnalysisEngine
    ├── PortugueseAnalysisEngine
    └── LlmAnalysisEngine   (decora um motor local como fallback)

A escolha do motor acontece em ``selector.select_engine`` — um unico ponto,
testavel, sem condicional de idioma espalhada pelo resto do codigo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .language import LanguageDecision
from .schemas import CompanyData, NewsData, SentimentResult


class AnalysisEngine(ABC):
    """Um motor analisa uma noticia para um ativo, em um idioma."""

    #: Identificador curto e estavel, gravado junto com o resultado.
    name: str = "engine"
    #: Idioma que o motor atende.
    language: str = ""
    #: Versao logica. Entra na chave de deduplicacao.
    version: str = "0"

    @property
    def engine_id(self) -> str:
        return f"{self.name}-{self.version}"

    @abstractmethod
    def analyze(
        self,
        company: CompanyData,
        news: NewsData,
        decision: LanguageDecision,
    ) -> SentimentResult:
        """Produz o resultado. Nunca deve lancar por conteudo malformado."""
        raise NotImplementedError
