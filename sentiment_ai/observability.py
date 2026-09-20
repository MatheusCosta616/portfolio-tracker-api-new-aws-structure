"""Logs estruturados do pipeline de sentimento.

Formato ``evento chave=valor``, facil de ler no ``docker compose logs`` e facil
de transformar em metrica depois. Nunca registra chave de API, token, corpo
completo da resposta do provedor nem conteudo alem do necessario.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("sentiment_ai.events")

#: Campos que jamais podem ir para o log, mesmo se alguem passar por engano.
FORBIDDEN = frozenset({
    "api_key", "apikey", "token", "authorization", "secret", "password",
    "raw_response", "prompt", "content",
})


def _render(value) -> str:
    text = str(value)
    if len(text) > 200:
        text = text[:197] + "..."
    if " " in text:
        return f'"{text}"'
    return text


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    safe = {
        key: _render(value)
        for key, value in fields.items()
        if key.lower() not in FORBIDDEN and value is not None
    }
    payload = " ".join(f"{key}={value}" for key, value in sorted(safe.items()))
    logger.log(level, "%s %s", event, payload)


def log_warning(event: str, **fields) -> None:
    log_event(event, level=logging.WARNING, **fields)


def log_error(event: str, **fields) -> None:
    log_event(event, level=logging.ERROR, **fields)
