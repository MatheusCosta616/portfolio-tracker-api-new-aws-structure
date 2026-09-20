from __future__ import annotations

from collections import Counter
from functools import lru_cache

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except ImportError:  # pragma: no cover - deterministic lexical fallback remains available
    SentimentIntensityAnalyzer = None

from .lexicons import en, pt_br
from .rules import SECTOR_RULES, TOPIC_KEYWORDS
from .schemas import CompanyData, NewsData, SentimentResult
from .text_processing import contains_phrase, meaningful_tokens, normalize_text, phrase_hits, tokenize

IRRELEVANCE_THRESHOLD = 0.22


@lru_cache(maxsize=1)
def _vader():
    return SentimentIntensityAnalyzer() if SentimentIntensityAnalyzer else None


def _clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def detect_language(text: str) -> str:
    tokens = set(tokenize(text))
    pt_markers = {"de", "da", "do", "para", "com", "lucro", "queda", "alta", "empresa", "acoes"}
    en_markers = {"the", "of", "to", "with", "profit", "fall", "rise", "company", "shares"}
    pt_score = len(tokens & pt_markers) + len(tokens & pt_br.POSITIVE_TERMS) + len(tokens & pt_br.NEGATIVE_TERMS)
    en_score = len(tokens & en_markers) + len(tokens & en.POSITIVE_TERMS) + len(tokens & en.NEGATIVE_TERMS)
    if pt_score == en_score == 0:
        return "unknown"
    return "pt-BR" if pt_score >= en_score else "en"


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


def _company_relevance(text: str, company: CompanyData, topics: tuple[str, ...], sector_key: str) -> float:
    score = 0.0
    normalized_ticker = normalize_text(company.ticker).replace(".sa", "")
    direct_names = [company.name, *company.aliases]

    if normalized_ticker and contains_phrase(text, normalized_ticker):
        score += 0.58
    if any(name and contains_phrase(text, name) for name in direct_names):
        score += 0.58

    stopwords = en.STOPWORDS | pt_br.STOPWORDS
    company_terms = meaningful_tokens(" ".join((company.name, company.description)), stopwords)
    article_terms = meaningful_tokens(text, stopwords)
    overlap = company_terms & article_terms
    score += min(len(overlap) * 0.045, 0.24)

    relevant_topics = set(SECTOR_RULES[sector_key]["topic_weights"])  # type: ignore[index]
    topic_overlap = set(topics) & relevant_topics
    score += min(len(topic_overlap) * 0.10, 0.24)

    return round(_clamp(score, 0.0, 1.0), 4)


def _lexical_sentiment(text: str, language: str) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    tokens = Counter(tokenize(text))
    positive_terms = pt_br.POSITIVE_TERMS | en.POSITIVE_TERMS
    negative_terms = pt_br.NEGATIVE_TERMS | en.NEGATIVE_TERMS
    positive = sorted(term for term in positive_terms if tokens.get(term, 0))
    negative = sorted(term for term in negative_terms if tokens.get(term, 0))
    positive_count = sum(tokens[term] for term in positive)
    negative_count = sum(tokens[term] for term in negative)
    lexical = (positive_count - negative_count) / max(positive_count + negative_count + 2, 2)

    vader_score = 0.0
    analyzer = _vader()
    if analyzer is not None:
        vader_score = float(analyzer.polarity_scores(text)["compound"])

    if language == "pt-BR":
        score = lexical * 0.75 + vader_score * 0.25
    elif language == "en":
        score = lexical * 0.45 + vader_score * 0.55
    else:
        score = lexical * 0.65 + vader_score * 0.35

    return _clamp(score), tuple(f"word:{term}" for term in positive), tuple(f"word:{term}" for term in negative)


def _sector_adjustment(text: str, topics: tuple[str, ...], sector_key: str) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
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

    return _clamp(adjustment, -0.5, 0.5), tuple(sorted(set(positive))), tuple(sorted(set(negative)))


def _label(impact: float, relevance: float) -> str:
    if relevance < IRRELEVANCE_THRESHOLD:
        return "irrelevant"
    if impact >= 0.15:
        return "positive"
    if impact <= -0.15:
        return "negative"
    return "neutral"


def _confidence(label: str, relevance: float, text_score: float, adjustment: float) -> float:
    if label == "irrelevant":
        return round(_clamp(0.55 + (IRRELEVANCE_THRESHOLD - relevance), 0.0, 0.92), 3)
    raw = 0.30 + relevance * 0.35 + abs(text_score) * 0.20 + min(abs(adjustment), 0.25)
    return round(_clamp(raw, 0.0, 0.95), 3)


def _explanation(company: CompanyData, label: str, sector_key: str, topics: tuple[str, ...], signals: tuple[str, ...]) -> str:
    display_name = company.name or company.ticker
    if label == "irrelevant":
        return f"A notícia não apresentou relação suficiente com {display_name}; nenhum impacto direcional foi atribuído."
    label_pt = {"positive": "positivo", "neutral": "neutro", "negative": "negativo"}[label]
    topic_text = ", ".join(topics) if topics else "sem tema setorial dominante"
    signal_text = ", ".join(signals[:4]) if signals else "sem sinais fortes"
    return (
        f"Impacto {label_pt} estimado para {display_name}. Contexto setorial: {sector_key}; "
        f"temas: {topic_text}; sinais considerados: {signal_text}."
    )


def analyze_news_for_company(company: CompanyData, news: NewsData) -> SentimentResult:
    # The title is intentionally weighted twice because it normally carries the clearest event signal.
    text = f"{news.title}. {news.title}. {news.summary}".strip()
    language = detect_language(text)
    topics = detect_topics(text)
    sector_key = infer_sector_key(company)
    relevance = _company_relevance(text, company, topics, sector_key)
    text_score, lexical_positive, lexical_negative = _lexical_sentiment(text, language)
    raw_adjustment, sector_positive, sector_negative = _sector_adjustment(text, topics, sector_key)

    if relevance < IRRELEVANCE_THRESHOLD:
        gated_adjustment = 0.0
        impact = 0.0
    else:
        gated_adjustment = raw_adjustment * relevance
        impact = _clamp(text_score + gated_adjustment)

    label = _label(impact, relevance)
    positive = tuple(sorted(set((*lexical_positive, *sector_positive))))
    negative = tuple(sorted(set((*lexical_negative, *sector_negative))))
    confidence = _confidence(label, relevance, text_score, gated_adjustment)
    explanation = _explanation(company, label, sector_key, topics, (*positive, *negative))

    return SentimentResult(
        ticker=company.ticker,
        company_name=company.name or company.ticker,
        language=language,
        relevance_score=round(relevance, 4),
        text_sentiment_score=round(text_score, 4),
        adjustment_score=round(gated_adjustment, 4),
        impact_score=round(impact, 4),
        sentiment_label=label,
        confidence=confidence,
        detected_topics=topics,
        positive_signals=positive,
        negative_signals=negative,
        explanation=explanation,
    )
