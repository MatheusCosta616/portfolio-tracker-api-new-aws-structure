"""Configuracao da LLM, sempre vinda do ambiente.

Nenhuma credencial e lida de codigo, gravada em log ou enviada ao frontend. O
``.env.example`` traz apenas os nomes das variaveis.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.conf import settings

from .prompt import PROMPT_VERSION

DEFAULT_TIMEOUT = 20
DEFAULT_MAX_RETRIES = 2


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool
    provider: str
    model: str
    api_key: str
    base_url: str
    timeout_seconds: int
    max_retries: int
    languages: tuple[str, ...]

    @property
    def usable(self) -> bool:
        """Ligada, com provedor, modelo e chave. Faltando qualquer um, nao usa."""
        return bool(self.enabled and self.provider and self.model and self.api_key)

    @property
    def fingerprint(self) -> str:
        """Digest curto de provedor + modelo + versao do prompt.

        Entra na versao logica do motor para que trocar de modelo ou de prompt
        invalide o cache de analises, sem estourar o limite de 50 caracteres da
        coluna ``model_version``.
        """
        seed = f"{self.provider}|{self.model}|{PROMPT_VERSION}".encode("utf-8")
        return hashlib.sha256(seed).hexdigest()[:8]

    def describe(self) -> str:
        """Descricao legivel para log e auditoria. Nunca inclui a chave."""
        return f"{self.provider}:{self.model}:{PROMPT_VERSION}"


def _as_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def load_config() -> LlmConfig:
    raw_languages = getattr(settings, "LLM_LANGUAGES", ("pt-BR",))
    if isinstance(raw_languages, str):
        raw_languages = tuple(part.strip() for part in raw_languages.split(",") if part.strip())

    return LlmConfig(
        enabled=bool(getattr(settings, "LLM_ENABLED", False)),
        provider=str(getattr(settings, "LLM_PROVIDER", "") or "").strip().lower(),
        model=str(getattr(settings, "LLM_MODEL", "") or "").strip(),
        api_key=str(getattr(settings, "LLM_API_KEY", "") or "").strip(),
        base_url=str(getattr(settings, "LLM_BASE_URL", "") or "").strip(),
        timeout_seconds=_as_int(getattr(settings, "LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT), DEFAULT_TIMEOUT),
        max_retries=_as_int(getattr(settings, "LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES), DEFAULT_MAX_RETRIES),
        languages=tuple(raw_languages),
    )
