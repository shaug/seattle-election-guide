"""Shared normalization for deterministic human-label matching."""

import re
import unicodedata


def normalize_match_text(value: str) -> str:
    """Normalize accents and punctuation without discarding word boundaries."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    casefolded = without_marks.casefold().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", casefolded).split())
