"""Nucleo de pontuacao compartilhado pelos motores por idioma.

O motor de ingles e o de portugues usam as mesmas regras setoriais e o mesmo
calculo de relevancia, mas NUNCA compartilham lexico: cada um recebe o modulo
do seu idioma. Era exatamente essa mistura que produzia falso positivo em
portugues e falso negativo em ingles na versao anterior.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .lexicons import en, pt_br
from .rules import PHRASE_POLARITY, SECTOR_RULES, TOPIC_KEYWORDS
from .schemas import CompanyData
from .text_processing import contains_phrase, meaningful_tokens, normalize_text, phrase_hits, tokenize

IRRELEVANCE_THRESHOLD = 0.22

_NEGATION_WINDOW = 3
_INTENSIFIER_WINDOW = 2


def clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def surface_map(original_text: str) -> dict[str, str]:
    """Mapeia token normalizado -> palavra como ela aparece no texto original.

    Serve para o relatorio citar "lucro recorde" e nao "word:lucro".
    """
    mapping: dict[str, str] = {}
    for raw_word in (original_text or "").split():
        cleaned = raw_word.strip("\"'.,;:!?()[]{}<>«»—–-")
        if not cleaned:
            continue
        normalized = normalize_text(cleaned)
        if normalized and normalized not in mapping:
            mapping[normalized] = cleaned
    return mapping


@dataclass(frozen=True)
class LexicalOutcome:
    score: float
    positive: tuple[str, ...] = field(default_factory=tuple)
    negative: tuple[str, ...] = field(default_factory=tuple)
    negated: tuple[str, ...] = field(default_factory=tuple)


def lexical_score(text: str, lexicon) -> LexicalOutcome:
    """Pontua o texto usando UM lexico, com negacao e intensificadores.

    ``lexicon`` e o modulo ``lexicons.pt_br`` ou ``lexicons.en``.
    """
    tokens = tokenize(text)
    positive_total = 0.0
    negative_total = 0.0
    positives: list[str] = []
    negatives: list[str] = []
    negated: list[str] = []

    for index, token in enumerate(tokens):
        if token in lexicon.POSITIVE_WEIGHTS:
            weight = lexicon.POSITIVE_WEIGHTS[token]
            polarity = 1.0
        elif token in lexicon.NEGATIVE_WEIGHTS:
            weight = lexicon.NEGATIVE_WEIGHTS[token]
            polarity = -1.0
        else:
            continue

        window_start = max(0, index - _NEGATION_WINDOW)
        window = tokens[window_start:index]
        if any(word in lexicon.NEGATORS for word in window):
            polarity *= -1.0
            negated.append(token)

        intensifier_start = max(0, index - _INTENSIFIER_WINDOW)
        for word in tokens[intensifier_start:index]:
            if word in lexicon.INTENSIFIERS:
                weight *= lexicon.INTENSIFIERS[word]
                break

        if polarity > 0:
            positive_total += weight
            positives.append(token)
        else:
            negative_total += weight
            negatives.append(token)

    if positive_total == 0.0 and negative_total == 0.0:
        raw = 0.0
    else:
        raw = (positive_total - negative_total) / (positive_total + negative_total + 1.5)

    return LexicalOutcome(
        score=clamp(raw),
        positive=tuple(sorted(set(positives))),
        negative=tuple(sorted(set(negatives))),
        negated=tuple(sorted(set(negated))),
    )


def phrase_polarity(text: str) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    """Aplica ``PHRASE_POLARITY``, com a frase mais longa tendo prioridade."""
    matched = sorted(
        (phrase for phrase in PHRASE_POLARITY if contains_phrase(text, phrase)),
        key=len,
        reverse=True,
    )
    consumed: list[str] = []
    total = 0.0
    positives: list[str] = []
    negatives: list[str] = []

    for phrase in matched:
        if any(phrase in longer for longer in consumed):
            continue
        consumed.append(phrase)
        weight = PHRASE_POLARITY[phrase]
        total += weight
        if weight > 0:
            positives.append(f"phrase:{phrase}")
        elif weight < 0:
            negatives.append(f"phrase:{phrase}")

    return clamp(total, -0.8, 0.8), tuple(sorted(set(positives))), tuple(sorted(set(negatives)))


def infer_sector_key(company: CompanyData) -> str:
    joined = normalize_text(" ".join((company.sector, company.industry, company.description)))
    mappings = (
        ("energy", ("energy", "oil", "gas", "petroleum", "refining", "energia", "petroleo", "refino")),
        ("basic materials", ("mining", "materials", "ore", "steel", "metals", "mineracao", "minerio", "aco")),
        ("financial services", ("bank", "financial", "insurance", "credit", "banco", "financeiro", "seguro", "credito")),
        ("airlines", ("airline", "aviation", "air transport", "companhia aerea", "aviacao", "transporte aereo")),
        ("technology", ("technology", "software", "semiconductor", "it services", "tecnologia", "semicondutor")),
        ("consumer cyclicals", ("retail", "e-commerce", "consumer cyclical", "varejo", "comercio eletronico")),
        ("industrials", ("industrial", "capital goods", "machinery", "bens de capital", "maquinas")),
    )
    for key, terms in mappings:
        if any(contains_phrase(joined, term) for term in terms):
            return key
    return "default"


def detect_topics(text: str) -> tuple[str, ...]:
    topics = [
        topic
        for topic, phrases in TOPIC_KEYWORDS.items()
        if any(contains_phrase(text, phrase) for phrase in phrases)
    ]
    return tuple(sorted(topics))


def company_relevance(
    text: str, company: CompanyData, topics: tuple[str, ...], sector_key: str
) -> tuple[float, tuple[str, ...]]:
    """Relevancia da noticia para o ativo, com os motivos que a sustentam."""
    score = 0.0
    reasons: list[str] = []
    normalized_ticker = normalize_text(company.ticker).replace(".sa", "")
    direct_names = [company.name, *company.aliases]

    if normalized_ticker and contains_phrase(text, normalized_ticker):
        score += 0.58
        reasons.append("ticker citado")
    matched_name = next((n for n in direct_names if n and contains_phrase(text, n)), None)
    if matched_name:
        score += 0.58
        reasons.append("nome da empresa citado")

    # Stopwords das duas linguas: aqui a uniao e correta, pois so serve para
    # descartar palavras vazias antes de medir sobreposicao de vocabulario.
    stopwords = en.STOPWORDS | pt_br.STOPWORDS
    company_terms = meaningful_tokens(" ".join((company.name, company.description)), set(stopwords))
    article_terms = meaningful_tokens(text, set(stopwords))
    overlap = company_terms & article_terms
    if overlap:
        score += min(len(overlap) * 0.045, 0.24)
        reasons.append("vocabulario da empresa presente")

    relevant_topics = set(SECTOR_RULES[sector_key]["topic_weights"])  # type: ignore[index]
    topic_overlap = set(topics) & relevant_topics
    if topic_overlap:
        score += min(len(topic_overlap) * 0.10, 0.24)
        reasons.append("tema relevante para o setor: " + ", ".join(sorted(topic_overlap)))

    return round(clamp(score, 0.0, 1.0), 4), tuple(reasons)


def sector_adjustment(
    text: str, topics: tuple[str, ...], sector_key: str
) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    rules = SECTOR_RULES[sector_key]
    topic_weights: dict[str, float] = rules["topic_weights"]  # type: ignore[assignment]
    phrase_weights: dict[str, float] = rules["phrase_weights"]  # type: ignore[assignment]
    adjustment = 0.0
    positive: list[str] = []
    negative: list[str] = []

    for topic in topics:
        weight = topic_weights.get(topic, 0.0)
        adjustment += weight
        if weight > 0:
            positive.append(f"topic:{topic}")
        elif weight < 0:
            negative.append(f"topic:{topic}")

    for phrase in phrase_hits(text, phrase_weights):
        weight = phrase_weights[phrase]
        adjustment += weight
        if weight > 0:
            positive.append(f"phrase:{phrase}")
        elif weight < 0:
            negative.append(f"phrase:{phrase}")

    return clamp(adjustment, -0.5, 0.5), tuple(sorted(set(positive))), tuple(sorted(set(negative)))


def label_for(impact: float, relevance: float) -> str:
    if relevance < IRRELEVANCE_THRESHOLD:
        return "irrelevant"
    if impact >= 0.15:
        return "positive"
    if impact <= -0.15:
        return "negative"
    return "neutral"


def confidence_for(label: str, relevance: float, text_score: float, adjustment: float) -> float:
    if label == "irrelevant":
        return round(clamp(0.55 + (IRRELEVANCE_THRESHOLD - relevance), 0.0, 0.92), 3)
    raw = 0.30 + relevance * 0.35 + abs(text_score) * 0.20 + min(abs(adjustment), 0.25)
    return round(clamp(raw, 0.0, 0.95), 3)


def surface_phrase(original_text: str, normalized_phrase: str) -> str:
    """Recupera a frase como ela aparece no texto original, com acentos.

    Usado para o relatorio citar 'juros sobre capital próprio' em vez da forma
    normalizada interna.
    """
    words = [w for w in (original_text or "").split() if w]
    if not words:
        return normalized_phrase
    cleaned = [w.strip("\"'.,;:!?()[]{}<>«»—–") for w in words]
    normalized_words = [normalize_text(w) for w in cleaned]
    target = normalize_text(normalized_phrase).split()
    if not target:
        return normalized_phrase
    span = len(target)
    for start in range(0, len(normalized_words) - span + 1):
        if normalized_words[start:start + span] == target:
            return " ".join(cleaned[start:start + span])
    return normalized_phrase
