"""Integracao com LLM externa, isolada atras de ``LlmProvider``."""

from __future__ import annotations

import logging

from .base import (
    LlmAnalysis,
    LlmAuthError,
    LlmError,
    LlmInvalidResponse,
    LlmProvider,
    LlmRateLimited,
    LlmRequest,
    LlmTimeout,
    LlmUnavailable,
)
from .config import LlmConfig, load_config
from .prompt import PROMPT_VERSION
from .providers import PROVIDERS, NullProvider

logger = logging.getLogger(__name__)

__all__ = [
    "LlmAnalysis", "LlmAuthError", "LlmConfig", "LlmError", "LlmInvalidResponse",
    "LlmProvider", "LlmRateLimited", "LlmRequest", "LlmTimeout", "LlmUnavailable",
    "PROMPT_VERSION", "get_provider", "load_config",
]


def get_provider(config: LlmConfig | None = None) -> LlmProvider:
    """Devolve o provedor configurado, ou ``NullProvider`` se indisponivel."""
    config = config or load_config()
    if not config.enabled:
        return NullProvider()
    if not config.usable:
        logger.warning(
            "llm_misconfigured provider=%s model_set=%s key_set=%s",
            config.provider or "(vazio)", bool(config.model), bool(config.api_key),
        )
        return NullProvider()

    provider_cls = PROVIDERS.get(config.provider)
    if provider_cls is None:
        logger.warning("llm_unknown_provider provider=%s", config.provider)
        return NullProvider()
    return provider_cls(config)
