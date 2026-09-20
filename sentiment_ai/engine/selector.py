"""Escolha do motor de analise — ponto unico e testavel.

Nenhum outro modulo decide idioma ou motor. Quem precisa analisar chama
``select_engine(language)`` e recebe o objeto pronto.
"""

from __future__ import annotations

from .base import AnalysisEngine
from .english import EnglishAnalysisEngine
from .language import EN, PT_BR
from .portuguese import PortugueseAnalysisEngine

#: Mapa explicito idioma -> motor local. Adicionar um idioma e adicionar uma
#: linha aqui, nao um ``if`` novo espalhado pelo codigo.
LOCAL_ENGINES: dict[str, type[AnalysisEngine]] = {
    PT_BR: PortugueseAnalysisEngine,
    EN: EnglishAnalysisEngine,
}

DEFAULT_LANGUAGE = PT_BR


def local_engine_for(language: str) -> AnalysisEngine:
    """Motor heuristico local do idioma pedido."""
    engine_cls = LOCAL_ENGINES.get(language) or LOCAL_ENGINES[DEFAULT_LANGUAGE]
    return engine_cls()


def select_engine(language: str, config=None, provider=None) -> AnalysisEngine:
    """Motor efetivo para o idioma, considerando a configuracao de LLM.

    A LLM so entra quando esta habilitada, utilizavel e cobre aquele idioma.
    Em qualquer outro caso o motor local e devolvido diretamente.
    """
    local = local_engine_for(language)

    from ..llm import get_provider, load_config

    config = config or load_config()
    if not config.usable or language not in config.languages:
        return local

    provider = provider or get_provider(config)
    if not provider.enabled:
        return local

    from .llm_engine import LlmAnalysisEngine

    return LlmAnalysisEngine(provider=provider, config=config, fallback=local)
