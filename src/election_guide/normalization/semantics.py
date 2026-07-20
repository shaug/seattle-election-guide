"""Canonical endorsement states and explicit wording classification."""

from typing import Literal

from election_guide.normalization.text import normalize_match_text

EndorsementStatus = Literal[
    "endorsed",
    "dual_endorsement",
    "multiple_endorsement",
    "no_endorsement",
    "declined_to_endorse",
    "not_covered",
    "not_published",
    "unverified",
    "source_unavailable",
    "ambiguous",
]
EXPLICIT_STATUSES = {"endorsed", "dual_endorsement", "multiple_endorsement"}
REVIEW_REQUIRED_STATUSES = {"unverified", "ambiguous"}
STATUS_ALIASES: dict[str, EndorsementStatus] = {
    "endorse": "endorsed",
    "endorsed": "endorsed",
    "endorsement": "endorsed",
    "dual endorsement": "dual_endorsement",
    "co endorsement": "dual_endorsement",
    "multiple endorsement": "multiple_endorsement",
    "no endorsement": "no_endorsement",
    "declined to endorse": "declined_to_endorse",
    "not covered": "not_covered",
    "not published": "not_published",
    "unverified": "unverified",
    "source unavailable": "source_unavailable",
    "ambiguous": "ambiguous",
}


def classify_endorsement_status(raw_status: str) -> EndorsementStatus | None:
    """Map only explicit known semantics; unknown wording remains ambiguous."""
    return STATUS_ALIASES.get(normalize_match_text(raw_status))
