from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower().replace("’", "'")
    return re.sub(r"\s+", " ", value).strip()


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(normalize_text(text)))


def contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = normalize_text(text)
    normalized_phrase = normalize_text(phrase)
    if not normalized_phrase:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(normalized_phrase) + r"(?![a-z0-9])"
    return re.search(pattern, normalized_text) is not None


def phrase_hits(text: str, phrases: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({phrase for phrase in phrases if contains_phrase(text, phrase)}))


def meaningful_tokens(text: str, stopwords: set[str], min_length: int = 3) -> set[str]:
    return {
        token
        for token in tokenize(text)
        if len(token) >= min_length and token not in stopwords and not token.isdigit()
    }
