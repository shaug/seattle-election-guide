"""Immutable record factories and append-only storage for normalization review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from election_guide.evidence.storage import write_immutable_record
from election_guide.normalization.models import (
    ExtractedClaim,
    NormalizedEndorsement,
    OverrideRecord,
    ReviewDecision,
    ReviewItem,
)
from election_guide.serialization import canonical_json_bytes, read_json

Record = ExtractedClaim | NormalizedEndorsement | ReviewItem | ReviewDecision | OverrideRecord


def new_extracted_claim(**fields: Any) -> ExtractedClaim:
    return _new_record(ExtractedClaim, "claim", fields)


def new_review_item(**fields: Any) -> ReviewItem:
    return _new_record(ReviewItem, "review", fields)


def new_normalized_endorsement(**fields: Any) -> NormalizedEndorsement:
    return _new_record(NormalizedEndorsement, "endorsement", fields)


def new_review_decision(**fields: Any) -> ReviewDecision:
    return _new_record(ReviewDecision, "decision", fields)


def new_override(**fields: Any) -> OverrideRecord:
    return _new_record(OverrideRecord, "override", fields)


def write_record(record: Record, directory: Path) -> Path:
    """Write one canonical record without replacing history."""
    output = directory / f"{record.id}.json"
    write_immutable_record(output, canonical_json_bytes(record.model_dump(mode="json")))
    return output


def write_review_decision(decision: ReviewDecision, directory: Path) -> Path:
    """Atomically claim the one terminal-decision slot for a review item."""
    output = directory / f"{decision.review_item_id}.json"
    write_immutable_record(output, canonical_json_bytes(decision.model_dump(mode="json")))
    return output


def write_review_item(item: ReviewItem, directory: Path) -> Path:
    """Atomically claim the one review-queue slot for an extracted claim."""
    output = directory / f"{item.claim_id}.json"
    write_immutable_record(output, canonical_json_bytes(item.model_dump(mode="json")))
    return output


def read_record[RecordType: Record](path: Path, record_type: type[RecordType]) -> RecordType:
    """Read a strict canonical record and verify its filename identity."""
    try:
        raw = read_json(path)
        record = record_type.model_validate(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise ValueError(str(error)) from error
    if path.name != f"{record.id}.json":
        raise ValueError(f"record filename does not match identity {record.id!r}")
    return record


def list_records[RecordType: Record](
    directory: Path, record_type: type[RecordType]
) -> list[RecordType]:
    """Read records in stable ID order."""
    if not directory.exists():
        return []
    return [read_record(path, record_type) for path in sorted(directory.glob("*.json"))]


def list_review_decisions(directory: Path) -> list[ReviewDecision]:
    """Read terminal decisions keyed by their review item identity."""
    if not directory.exists():
        return []
    decisions: list[ReviewDecision] = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = read_json(path)
            decision = ReviewDecision.model_validate(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
            raise ValueError(str(error)) from error
        if path.name != f"{decision.review_item_id}.json":
            raise ValueError(
                "review decision filename does not match its terminal review item "
                f"{decision.review_item_id!r}"
            )
        decisions.append(decision)
    return decisions


def list_review_items(directory: Path) -> list[ReviewItem]:
    """Read review items keyed by their extracted claim identity."""
    if not directory.exists():
        return []
    items: list[ReviewItem] = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = read_json(path)
            item = ReviewItem.model_validate(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
            raise ValueError(str(error)) from error
        if path.name != f"{item.claim_id}.json":
            raise ValueError(
                f"review item filename does not match its extracted claim {item.claim_id!r}"
            )
        items.append(item)
    return items


def unresolved_review_items(queue_dir: Path, decisions_dir: Path) -> list[ReviewItem]:
    """Return queue items without an append-only terminal decision."""
    items = list_review_items(queue_dir)
    decisions = list_review_decisions(decisions_dir)
    resolved = {decision.review_item_id for decision in decisions}
    if len(resolved) != len(decisions):
        raise ValueError("review decision storage repeats a terminal review item")
    return [item for item in items if item.id not in resolved]


def _new_record[RecordType: Record](
    record_type: type[RecordType],
    prefix: str,
    fields: dict[str, Any],
) -> RecordType:
    payload = record_type.model_validate(
        {"id": f"{prefix}-{'0' * 16}", **fields},
        context={"skip_record_identity": True},
    ).model_dump(mode="json", exclude={"id"})
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return record_type.model_validate({"id": f"{prefix}-{digest[:16]}", **payload})
