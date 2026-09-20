"""Identificacao do idioma de uma noticia.

A cadeia de decisao segue exatamente a ordem pedida pelo time:

1. idioma informado pela fonte da noticia;
2. idioma ja gravado no banco para aquela analise;
3. deteccao a partir do titulo e do resumo;
4. fallback configuravel (``SENTIMENT_FALLBACK_LANGUAGE``).

Nenhuma etapa assume ingles por omissao. Quando nada permite decidir, o
resultado e ``UNKNOWN`` e quem chama aplica o fallback de forma explicita.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .lexicons import en, pt_br
from .text_processing import tokenize

PT_BR = "pt-BR"
EN = "en"
UNKNOWN = "unknown"

SUPPORTED_LANGUAGES = (PT_BR, EN)

# Origem da decisao, para log e para o relatorio.
SOURCE_DECLARED = "source"
SOURCE_STORED = "stored"
SOURCE_DETECTED = "detected"
SOURCE_FALLBACK = "fallback"

# Formas de ticker que nao devem influenciar a deteccao: PETR4, HGLG11,
# BTC-USD, VALE3.SA, AAPL.
_TICKER_PATTERNS = (
    re.compile(r"\b[A-Za-z]{4}\d{1,2}(?:\.SA)?\b"),
    re.compile(r"\b[A-Za-z]{2,6}-(?:USD|BRL|EUR)\b"),
    re.compile(r"\b[A-Za-z]{1,6}\.SA\b"),
    re.compile(r"\$[A-Za-z]{1,6}\b"),
)

_ACCENTED = set("ãõçáéíóúâêôàüÃÕÇÁÉÍÓÚÂÊÔÀÜ")

# Tokens que existem nas duas linguas nao servem como evidencia.
_AMBIGUOUS = (pt_br.FUNCTION_WORDS & en.FUNCTION_WORDS) | (
    (pt_br.POSITIVE_TERMS | pt_br.NEGATIVE_TERMS)
    & (en.POSITIVE_TERMS | en.NEGATIVE_TERMS)
)

_MIN_EVIDENCE = 1.5
_MIN_MARGIN = 0.15


@dataclass(frozen=True)
class LanguageDecision:
    """Resultado da cadeia de identificacao."""

    language: str
    source: str
    confidence: float = 0.0
    evidence: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_known(self) -> bool:
        return self.language in SUPPORTED_LANGUAGES


def normalize_language_code(value: str | None) -> str:
    """Converte 'pt', 'pt_BR', 'PT-br', 'en-US' para os codigos internos."""
    if not value:
        return UNKNOWN
    code = str(value).strip().lower().replace("_", "-")
    if not code:
        return UNKNOWN
    if code.startswith("pt"):
        return PT_BR
    if code.startswith("en"):
        return EN
    return UNKNOWN


def strip_tickers(text: str) -> str:
    """Remove formas de ticker para que 'PETR4' nao pese na deteccao."""
    cleaned = text or ""
    for pattern in _TICKER_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def count_accents(text: str) -> int:
    """Conta caracteres acentuados e cedilhas no texto original."""
    return sum(1 for char in (text or "") if char in _ACCENTED)


def _score(tokens: set[str], function_words, positive, negative) -> tuple[float, list[str]]:
    hits: list[str] = []
    score = 0.0
    for token in sorted(tokens & function_words):
        score += 2.0
        hits.append(token)
    for token in sorted(tokens & (positive | negative)):
        score += 1.5
        hits.append(token)
    return score, hits


def detect_language(title: str, summary: str = "") -> LanguageDecision:
    """Detecta o idioma a partir do titulo e do resumo.

    Trata acentos, cedilha, pontuacao, texto curto e titulos que misturam
    ticker com palavras em portugues. Devolve ``UNKNOWN`` quando o texto nao
    oferece evidencia suficiente, em vez de chutar ingles.
    """
    raw = f"{title or ''} {summary or ''}".strip()
    if not raw:
        return LanguageDecision(UNKNOWN, SOURCE_DETECTED, 0.0, ())

    without_tickers = strip_tickers(raw)
    tokens = set(tokenize(without_tickers)) - _AMBIGUOUS

    pt_score, pt_hits = _score(
        tokens, pt_br.FUNCTION_WORDS, pt_br.POSITIVE_TERMS, pt_br.NEGATIVE_TERMS
    )
    en_score, en_hits = _score(
        tokens, en.FUNCTION_WORDS, en.POSITIVE_TERMS, en.NEGATIVE_TERMS
    )

    accents = count_accents(without_tickers)
    if accents:
        pt_score += min(accents, 5) * 1.2
        pt_hits.append(f"acentos:{accents}")

    total = pt_score + en_score
    if total < _MIN_EVIDENCE:
        # Texto curto demais ou sem marcadores. A cedilha/acento sozinha ja e
        # evidencia forte de portugues; fora isso, admitimos que nao sabemos.
        if accents:
            return LanguageDecision(PT_BR, SOURCE_DETECTED, 0.55, (f"acentos:{accents}",))
        return LanguageDecision(UNKNOWN, SOURCE_DETECTED, 0.0, ())

    margin = abs(pt_score - en_score) / total
    if margin < _MIN_MARGIN:
        return LanguageDecision(UNKNOWN, SOURCE_DETECTED, round(margin, 3), ())

    if pt_score > en_score:
        return LanguageDecision(PT_BR, SOURCE_DETECTED, round(margin, 3), tuple(pt_hits[:6]))
    return LanguageDecision(EN, SOURCE_DETECTED, round(margin, 3), tuple(en_hits[:6]))


def resolve_language(
    title: str,
    summary: str = "",
    source_language: str | None = None,
    stored_language: str | None = None,
    fallback: str = PT_BR,
) -> LanguageDecision:
    """Aplica a cadeia completa e devolve sempre um idioma suportado."""
    declared = normalize_language_code(source_language)
    if declared in SUPPORTED_LANGUAGES:
        return LanguageDecision(declared, SOURCE_DECLARED, 1.0, ("fonte",))

    stored = normalize_language_code(stored_language)
    if stored in SUPPORTED_LANGUAGES:
        return LanguageDecision(stored, SOURCE_STORED, 1.0, ("banco",))

    detected = detect_language(title, summary)
    if detected.is_known:
        return detected

    safe_fallback = normalize_language_code(fallback)
    if safe_fallback not in SUPPORTED_LANGUAGES:
        safe_fallback = PT_BR
    return LanguageDecision(safe_fallback, SOURCE_FALLBACK, 0.0, ("fallback",))
