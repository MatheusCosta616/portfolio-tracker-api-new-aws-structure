"""Identidade canonica de uma noticia e versao logica do motor.

A chave de deduplicacao do sistema e

    noticia + ativo/ticker + versao do motor

A identidade da noticia no banco e ``NewsArticle.url``, que e unica. Isso
sozinho nao basta: URLs de RSS carregam parametros de rastreamento que mudam a
cada coleta, entao a mesma materia pode entrar como artigos diferentes. Por
isso calculamos tambem uma impressao digital de conteudo, gravada na analise.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from .engine.text_processing import normalize_text

#: Parametros descartados ao canonicalizar: rastreamento e redirecionamento.
TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "gclid", "fbclid", "msclkid", "igshid", "mc_cid",
    "mc_eid", "ref", "referrer", "source", "oc", "ved", "usg", "sa", "ei",
    "cd", "cad", "rct", "hl", "gl", "ceid", "guccounter", "guce_referrer",
    "guce_referrer_sig", "yptr", "soc_src", "soc_trk", "_ga", "spm",
})

_WHITESPACE = re.compile(r"\s+")


def canonical_url(url: str) -> str:
    """Forma estavel da URL: sem esquema variavel, sem www, sem rastreamento."""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.lower()

    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.endswith(":443") or host.endswith(":80"):
        host = host.rsplit(":", 1)[0]

    path = (parts.path or "/").rstrip("/") or "/"

    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = "&".join(f"{k}={v}" for k, v in sorted(kept))

    # O fragmento nunca identifica a materia.
    return urlunsplit(("https", host, path, query, ""))


def _normalized_block(value: str, limit: int) -> str:
    text = normalize_text(value or "")
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:limit]


def news_fingerprint(*, title: str, summary: str = "", url: str = "", source: str = "") -> str:
    """SHA-256 de titulo + resumo + URL canonica + fonte.

    Nao depende so do titulo: manchetes iguais de veiculos diferentes, ou sobre
    fatos diferentes, continuam sendo analisadas separadamente porque a URL
    canonica e a fonte entram no calculo.
    """
    seed = "|".join((
        _normalized_block(title, 300),
        _normalized_block(summary, 600),
        canonical_url(url),
        normalize_text(source or ""),
    ))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def engine_model_version(engine) -> str:
    """Versao logica gravada em ``Analysis.model_version`` (<= 50 chars).

    Inclui o motor e, quando ha LLM, o digest de provedor + modelo + versao do
    prompt. Trocar qualquer um desses gera uma chave nova, e portanto uma nova
    analise, em vez de reaproveitar um resultado produzido por outra coisa.
    """
    value = getattr(engine, "engine_id", None) or getattr(engine, "name", "engine")
    return str(value)[:50]
