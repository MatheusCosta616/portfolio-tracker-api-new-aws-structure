"""Provedores concretos de LLM.

Todos determinismo-first: temperatura 0 e, quando o fornecedor aceita, top_p 1.
A chave nunca aparece em log nem em mensagem de erro.
"""

from __future__ import annotations

import json
import logging
import time

import requests

from .base import (
    LlmAnalysis,
    LlmAuthError,
    LlmError,
    LlmProvider,
    LlmRateLimited,
    LlmRequest,
    LlmTimeout,
    LlmUnavailable,
)
from .config import LlmConfig
from .prompt import SYSTEM_PROMPT, build_user_prompt, parse_response

logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 600


class NullProvider(LlmProvider):
    """Provedor usado quando a LLM esta desligada ou mal configurada."""

    name = "null"

    @property
    def enabled(self) -> bool:
        return False

    def analyze_news(self, request: LlmRequest) -> LlmAnalysis:
        raise LlmUnavailable("provedor de LLM desabilitado")


class HttpLlmProvider(LlmProvider):
    """Base dos provedores HTTP, com timeout e retries limitados."""

    default_base_url = ""

    def __init__(self, config: LlmConfig):
        self._config = config
        self.model = config.model

    @property
    def enabled(self) -> bool:
        return self._config.usable

    @property
    def base_url(self) -> str:
        return self._config.base_url or self.default_base_url

    # --- a implementar por fornecedor ---------------------------------------
    def _endpoint(self) -> str:
        raise NotImplementedError

    def _headers(self) -> dict:
        raise NotImplementedError

    def _body(self, request: LlmRequest) -> dict:
        raise NotImplementedError

    def _extract_text(self, payload: dict) -> str:
        raise NotImplementedError

    # ------------------------------------------------------------------------
    def analyze_news(self, request: LlmRequest) -> LlmAnalysis:
        if not self.enabled:
            raise LlmUnavailable("provedor de LLM nao configurado")

        attempts = self._config.max_retries + 1
        last_error: LlmError | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = requests.post(
                    self._endpoint(),
                    headers=self._headers(),
                    json=self._body(request),
                    timeout=self._config.timeout_seconds,
                )
            except requests.Timeout as exc:
                last_error = LlmTimeout(f"timeout apos {self._config.timeout_seconds}s")
                last_error.__cause__ = exc
            except requests.RequestException as exc:
                last_error = LlmUnavailable(f"falha de rede: {type(exc).__name__}")
                last_error.__cause__ = exc
            else:
                error = self._classify(response)
                if error is None:
                    try:
                        text = self._extract_text(response.json())
                    except (ValueError, KeyError, TypeError, IndexError) as exc:
                        last_error = LlmUnavailable("envelope inesperado do provedor")
                        last_error.__cause__ = exc
                    else:
                        return parse_response(text, request)
                else:
                    last_error = error
                    if isinstance(error, LlmAuthError):
                        # Chave errada nao melhora com retry.
                        break

            logger.warning(
                "llm_retry provider=%s model=%s attempt=%s/%s reason=%s",
                self.name, self.model, attempt, attempts,
                getattr(last_error, "reason", "unknown"),
            )
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 4))

        raise last_error or LlmUnavailable("falha desconhecida no provedor")

    def _classify(self, response) -> LlmError | None:
        status = response.status_code
        if status < 400:
            return None
        if status in (401, 403):
            return LlmAuthError(f"credencial rejeitada (HTTP {status})")
        if status == 429:
            return LlmRateLimited("limite de requisicoes atingido")
        if status in (408, 504):
            return LlmTimeout(f"timeout no provedor (HTTP {status})")
        return LlmUnavailable(f"HTTP {status} do provedor")


class AnthropicProvider(HttpLlmProvider):
    name = "anthropic"
    default_base_url = "https://api.anthropic.com"

    def _endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/messages"

    def _headers(self) -> dict:
        return {
            "x-api-key": self._config.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _body(self, request: LlmRequest) -> dict:
        return {
            "model": self.model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": build_user_prompt(request)}],
        }

    def _extract_text(self, payload: dict) -> str:
        blocks = payload.get("content") or []
        return "".join(block.get("text", "") for block in blocks if isinstance(block, dict))


class OpenAiProvider(HttpLlmProvider):
    name = "openai"
    default_base_url = "https://api.openai.com"

    def _endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/chat/completions"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }

    def _body(self, request: LlmRequest) -> dict:
        return {
            "model": self.model,
            "temperature": 0,
            "top_p": 1,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(request)},
            ],
        }

    def _extract_text(self, payload: dict) -> str:
        return payload["choices"][0]["message"]["content"]


class GeminiProvider(HttpLlmProvider):
    name = "gemini"
    default_base_url = "https://generativelanguage.googleapis.com"

    def _endpoint(self) -> str:
        return (
            f"{self.base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent"
        )

    def _headers(self) -> dict:
        return {
            "x-goog-api-key": self._config.api_key,
            "Content-Type": "application/json",
        }

    def _body(self, request: LlmRequest) -> dict:
        return {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": build_user_prompt(request)}]}],
            "generationConfig": {
                "temperature": 0,
                "topP": 1,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
                "responseMimeType": "application/json",
            },
        }

    def _extract_text(self, payload: dict) -> str:
        parts = payload["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts if isinstance(part, dict))


PROVIDERS: dict[str, type[HttpLlmProvider]] = {
    AnthropicProvider.name: AnthropicProvider,
    OpenAiProvider.name: OpenAiProvider,
    GeminiProvider.name: GeminiProvider,
}
