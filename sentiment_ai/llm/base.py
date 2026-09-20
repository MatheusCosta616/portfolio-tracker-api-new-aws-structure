"""Contrato de provedor de LLM.

    LlmProvider
    └── analyze_news(request) -> LlmAnalysis

Nenhum fornecedor e fixado no restante do sistema. Trocar de provedor e mudar
``LLM_PROVIDER`` no ambiente.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LlmError(RuntimeError):
    """Falha generica ao consultar o provedor."""

    #: Rotulo curto, usado em log e no campo ``fallback_reason``.
    reason = "llm_error"


class LlmTimeout(LlmError):
    reason = "timeout"


class LlmRateLimited(LlmError):
    reason = "rate_limited"


class LlmAuthError(LlmError):
    reason = "auth_error"


class LlmUnavailable(LlmError):
    reason = "unavailable"


class LlmInvalidResponse(LlmError):
    reason = "invalid_response"


class LlmPayloadTooLarge(LlmError):
    reason = "payload_too_large"


@dataclass(frozen=True)
class LlmRequest:
    """Somente o que a LLM precisa ver. Nada de dado de usuario."""

    ticker: str
    company_name: str
    sector: str
    title: str
    summary: str
    language: str
    published_at: str = ""
    publisher: str = ""


@dataclass(frozen=True)
class LlmAnalysis:
    """Saida ja validada e normalizada para a escala interna."""

    sentiment_score: float
    sentiment_label: str
    relevance_score: float
    summary: str
    reasoning: str
    language: str
    raw_keys: tuple[str, ...] = field(default_factory=tuple)


class LlmProvider(ABC):
    """Implementacao concreta de um fornecedor."""

    name: str = "null"
    model: str = ""

    @property
    def enabled(self) -> bool:
        return False

    @abstractmethod
    def analyze_news(self, request: LlmRequest) -> LlmAnalysis:
        raise NotImplementedError
