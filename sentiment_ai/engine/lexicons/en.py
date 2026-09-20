"""English financial lexicon.

Same contract as ``pt_br``: accent-free keys, one weight per term, ambiguous
single tokens left out and handled as phrases in ``rules``.
"""

POSITIVE_WEIGHTS: dict[str, float] = {
    "advance": 0.7,
    "advances": 0.7,
    "beat": 0.9,
    "beats": 0.9,
    "benefit": 0.6,
    "boost": 0.7,
    "bullish": 0.9,
    "buyback": 0.8,
    "climb": 0.7,
    "climbs": 0.7,
    "dividend": 0.9,
    "dividends": 0.9,
    "expands": 0.7,
    "expansion": 0.7,
    "gain": 0.8,
    "gains": 0.8,
    "growth": 0.9,
    "higher": 0.7,
    "improved": 0.7,
    "improves": 0.7,
    "jump": 0.8,
    "jumps": 0.8,
    "outperform": 0.9,
    "profit": 1.0,
    "profits": 1.0,
    "rally": 0.7,
    "record": 1.0,
    "recovery": 0.7,
    "rise": 0.8,
    "rises": 0.8,
    "soar": 0.9,
    "soars": 0.9,
    "strong": 0.6,
    "surge": 0.9,
    "surges": 0.9,
    "upgrade": 0.9,
    "upgraded": 0.9,
}

NEGATIVE_WEIGHTS: dict[str, float] = {
    "accident": 0.9,
    "bankruptcy": 1.0,
    "bearish": 0.9,
    "collapse": 1.0,
    "decline": 0.8,
    "default": 0.9,
    "downgrade": 0.9,
    "downgraded": 0.9,
    "drop": 0.8,
    "drops": 0.8,
    "fall": 0.8,
    "falls": 0.8,
    "fraud": 1.0,
    "investigation": 0.8,
    "lawsuit": 0.8,
    "layoffs": 0.7,
    "loss": 0.9,
    "losses": 0.9,
    "miss": 0.8,
    "misses": 0.8,
    "plunge": 1.0,
    "plunges": 1.0,
    "pressure": 0.5,
    "recall": 0.7,
    "risk": 0.6,
    "sanction": 0.8,
    "scandal": 1.0,
    "slump": 0.9,
    "strike": 0.7,
    "tumble": 0.9,
    "tumbles": 0.9,
    "weak": 0.7,
    "weaker": 0.7,
}

POSITIVE_TERMS = frozenset(POSITIVE_WEIGHTS)
NEGATIVE_TERMS = frozenset(NEGATIVE_WEIGHTS)

NEGATORS = frozenset({"no", "not", "never", "without", "neither", "nor"})

INTENSIFIERS: dict[str, float] = {
    "strong": 1.30,
    "sharp": 1.30,
    "record": 1.45,
    "significant": 1.25,
    "steep": 1.30,
    "slight": 0.70,
    "slightly": 0.70,
    "modest": 0.80,
    "marginal": 0.70,
}

STOPWORDS = frozenset({
    "about", "after", "also", "and", "are", "been", "being", "business",
    "company", "could", "from", "have", "into", "more", "over", "said",
    "services", "that", "their", "they", "this", "through", "with", "would",
    "the", "for", "its", "has", "was", "will",
})

FUNCTION_WORDS = frozenset({
    "the", "of", "to", "with", "and", "in", "on", "for", "is", "as", "by",
    "from", "its", "it", "at", "that", "this", "are", "was", "were", "has",
    "have", "after", "over", "but", "not", "shares", "stock", "company",
    "billion", "million", "quarter", "year",
})
