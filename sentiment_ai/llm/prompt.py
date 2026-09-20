"""Prompt e validacao da resposta estruturada.

``PROMPT_VERSION`` entra na versao logica do motor: mudar o prompt invalida o
cache de analises, como o time pediu.
"""

from __future__ import annotations

import json
import re

from .base import LlmAnalysis, LlmInvalidResponse, LlmRequest

PROMPT_VERSION = "p1"

VALID_LABELS = ("positive", "negative", "neutral", "irrelevant")

MAX_TITLE = 400
MAX_SUMMARY = 2000
MAX_SUMMARY_OUT = 400
MAX_REASONING_OUT = 700

SYSTEM_PROMPT = (
    "Voce e um analista financeiro que avalia o impacto de uma noticia sobre um "
    "ativo negociado em bolsa. Responda SOMENTE com um objeto JSON valido, sem "
    "texto antes ou depois, sem cercas de codigo e sem comentarios.\n"
    "Regras obrigatorias:\n"
    "1. Baseie-se exclusivamente no titulo e no resumo fornecidos. Nao use "
    "conhecimento externo, nao invente fatos, numeros, datas ou eventos.\n"
    "2. Se a noticia nao tiver relacao com o ativo, use o rotulo 'irrelevant' e "
    "relevance_score baixo.\n"
    "3. 'reasoning' deve ser uma justificativa curta e verificavel citando "
    "expressoes que aparecem no texto. Nao descreva seu raciocinio interno.\n"
    "4. Escreva 'summary' e 'reasoning' em portugues do Brasil."
)

RESPONSE_CONTRACT = """Formato exato da resposta:
{
  "sentiment_score": <numero entre -1 e 1>,
  "sentiment_label": "positive" | "negative" | "neutral" | "irrelevant",
  "relevance_score": <numero entre 0 e 1>,
  "summary": "<no maximo 2 frases>",
  "reasoning": "<justificativa curta citando trechos do texto>",
  "language": "pt-BR" | "en"
}"""


def build_user_prompt(request: LlmRequest) -> str:
    title = (request.title or "")[:MAX_TITLE]
    summary = (request.summary or "")[:MAX_SUMMARY]
    contexto = request.sector or "nao informado"
    return (
        f"Ativo: {request.ticker}\n"
        f"Empresa: {request.company_name or request.ticker}\n"
        f"Contexto do ativo: {contexto}\n"
        f"Idioma da noticia: {request.language}\n"
        f"Titulo: {title}\n"
        f"Resumo: {summary or '(sem resumo)'}\n\n"
        f"{RESPONSE_CONTRACT}"
    )


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise LlmInvalidResponse("resposta vazia")

    # Cerca de codigo e o desvio mais comum; removemos antes de tentar.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass

    match = _JSON_OBJECT.search(text)
    if not match:
        raise LlmInvalidResponse("nenhum objeto JSON encontrado na resposta")
    try:
        return json.loads(match.group(0))
    except (ValueError, TypeError) as exc:
        raise LlmInvalidResponse("JSON invalido na resposta") from exc


def _as_float(value, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise LlmInvalidResponse(f"campo '{field}' nao numerico") from exc


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def parse_response(raw: str, request: LlmRequest) -> LlmAnalysis:
    """Valida a resposta e converte para o modelo interno.

    Qualquer desvio de contrato vira ``LlmInvalidResponse``, que dispara o
    fallback para o motor local.
    """
    payload = _extract_json(raw)
    if not isinstance(payload, dict):
        raise LlmInvalidResponse("a resposta nao e um objeto JSON")

    score = _clamp(_as_float(payload.get("sentiment_score", 0.0), "sentiment_score"), -1.0, 1.0)
    relevance = _clamp(_as_float(payload.get("relevance_score", 0.0), "relevance_score"), 0.0, 1.0)

    label = str(payload.get("sentiment_label", "")).strip().lower()
    if label not in VALID_LABELS:
        # Deriva o rotulo a partir da nota, mantendo os mesmos cortes do motor local.
        if relevance < 0.22:
            label = "irrelevant"
        elif score >= 0.15:
            label = "positive"
        elif score <= -0.15:
            label = "negative"
        else:
            label = "neutral"

    summary = str(payload.get("summary", "") or "").strip()[:MAX_SUMMARY_OUT]
    reasoning = str(payload.get("reasoning", "") or "").strip()[:MAX_REASONING_OUT]
    if not reasoning:
        raise LlmInvalidResponse("campo 'reasoning' ausente")

    language = str(payload.get("language", "") or request.language).strip() or request.language

    return LlmAnalysis(
        sentiment_score=round(score, 4),
        sentiment_label=label,
        relevance_score=round(relevance, 4),
        summary=summary,
        reasoning=reasoning,
        language=language,
        raw_keys=tuple(sorted(str(k) for k in payload)),
    )
