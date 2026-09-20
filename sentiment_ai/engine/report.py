"""Relatorio curto, em portugues, fundamentado na propria noticia.

Regra de ouro: o texto so cita elementos que realmente aparecem no titulo ou no
resumo. Nada de "a IA analisou a noticia e determinou o sentimento".
"""

from __future__ import annotations

from .text_processing import contains_phrase

LABEL_PT = {
    "positive": "positiva",
    "negative": "negativa",
    "neutral": "neutra",
    "irrelevant": "irrelevante",
}

TOPIC_PT = {
    "oil": "petroleo",
    "mining": "mineracao",
    "aviation": "aviacao",
    "banking": "sistema bancario",
    "technology": "tecnologia",
    "retail": "varejo",
    "macro": "macroeconomia",
    "government": "acao governamental",
    "dividends": "proventos",
    "earnings": "resultados financeiros",
    "geopolitics": "geopolitica",
}


def _relevance_word(relevance: float) -> str:
    if relevance >= 0.70:
        return "alta"
    if relevance >= 0.40:
        return "media"
    return "baixa"


def _format_score(value: float) -> str:
    return f"{value:+.2f}".replace(".", ",")


def _where(term: str, title: str, summary: str) -> str:
    if contains_phrase(title or "", term):
        return "titulo"
    if contains_phrase(summary or "", term):
        return "resumo"
    return ""


def _quote_list(items: list[str]) -> str:
    quoted = [f'"{item}"' for item in items]
    if len(quoted) == 1:
        return quoted[0]
    return ", ".join(quoted[:-1]) + " e " + quoted[-1]


def build_report(
    *,
    ticker: str,
    company_name: str,
    title: str,
    summary: str,
    label: str,
    impact_score: float,
    relevance_score: float,
    highlights: tuple[str, ...],
    relevance_reasons: tuple[str, ...],
    topics: tuple[str, ...],
    irrelevance_threshold: float,
    engine_label: str,
) -> str:
    """Responde as quatro perguntas do enunciado em poucas frases."""
    display = company_name or ticker
    subject = f"{ticker} ({display})" if display and display != ticker else ticker

    if label == "irrelevant":
        motivo = (
            "o texto nao cita o ativo nem a empresa e o tema nao afeta o setor"
            if not relevance_reasons
            else "os unicos vinculos encontrados foram fracos: " + "; ".join(relevance_reasons)
        )
        return (
            f"A noticia nao foi considerada relevante para {subject}: a relevancia ficou em "
            f"{relevance_score:.2f} , abaixo do limite de {irrelevance_threshold:.2f}. "
            f"Motivo: {motivo}. Nenhuma nota direcional foi atribuida. "
            f"Analise produzida por {engine_label}."
        ).replace(" , ", ", ")

    partes: list[str] = [
        f"A noticia foi classificada como {LABEL_PT.get(label, label)} para {subject}, "
        f"com nota {_format_score(impact_score)} numa escala de -1 a +1."
    ]

    if highlights:
        selecionados = list(highlights[:3])
        local = {_where(term, title, summary) for term in selecionados}
        local.discard("")
        onde = ""
        if local == {"titulo"}:
            onde = ", presentes no titulo"
        elif local == {"resumo"}:
            onde = ", presentes no resumo"
        elif local:
            onde = ", presentes no titulo e no resumo"
        partes.append(
            f"O resultado foi influenciado por {_quote_list(selecionados)}{onde}."
        )
    else:
        partes.append(
            "Nenhuma expressao de sentimento forte foi encontrada no titulo ou no resumo, "
            "por isso a nota ficou proxima de zero."
        )

    justificativa = ""
    if relevance_reasons:
        justificativa = " porque " + "; ".join(relevance_reasons)
    elif topics:
        legiveis = [TOPIC_PT.get(topic, topic) for topic in topics[:2]]
        justificativa = " porque a noticia trata de " + " e ".join(legiveis)

    partes.append(
        f"A relevancia para o ativo foi considerada {_relevance_word(relevance_score)} "
        f"({relevance_score:.2f}){justificativa}."
    )
    partes.append(f"Analise produzida por {engine_label}.")

    return " ".join(partes)


# Aliases publicos: o motor de LLM monta o proprio texto reaproveitando estes
# helpers, e nao deve depender de nomes privados.
relevance_word = _relevance_word
format_score = _format_score
