"""Immutable incremental refresh orchestration and semantic diffs."""

from __future__ import annotations

import fcntl
import hashlib
import json
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from election_guide.collection.adapters import ExtractionError, extract_decisions, read_artifact
from election_guide.collection.models import (
    AdapterDecision,
    AdapterSpec,
    DecisionDiff,
    ExtractionSnapshot,
    RefreshEvent,
)
from election_guide.evidence.models import CapturedManifest, CaptureRequest, evidence_fingerprint
from election_guide.evidence.storage import (
    read_capture_manifest,
    record_capture,
    verify_capture,
    write_immutable_record,
)
from election_guide.serialization import canonical_json_bytes, read_json, read_yaml


class RefreshOrderError(ValueError):
    """Raised when a refresh timestamp cannot extend the source's committed history."""


def read_adapter_spec(path: Path) -> AdapterSpec:
    return AdapterSpec.model_validate(read_yaml(path))


def read_extraction_snapshot(path: Path) -> ExtractionSnapshot:
    try:
        return _validate_identified(path, ExtractionSnapshot.model_validate(read_json(path)))
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise ValueError(str(error)) from error


def read_refresh_event(path: Path) -> RefreshEvent:
    try:
        return _validate_identified(path, RefreshEvent.model_validate(read_json(path)))
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise ValueError(str(error)) from error


def refresh_source(
    spec: AdapterSpec,
    request: CaptureRequest,
    input_path: Path,
    *,
    storage_root: Path,
    manifest_dir: Path,
    extraction_dir: Path,
    refresh_dir: Path,
    ocr_text: str | None = None,
    ocr_confidence: str | None = None,
) -> RefreshEvent:
    """Refresh one source without replacing its last verified extraction."""
    if request.source_id != spec.source_id:
        raise ValueError("capture request source does not match adapter source")
    artifact = read_artifact(input_path)
    with _source_lock(refresh_dir, spec.source_id):
        return _refresh_source_locked(
            spec,
            request,
            input_path,
            artifact,
            storage_root=storage_root,
            manifest_dir=manifest_dir,
            extraction_dir=extraction_dir,
            refresh_dir=refresh_dir,
            ocr_text=ocr_text,
            ocr_confidence=ocr_confidence,
        )


def _refresh_source_locked(
    spec: AdapterSpec,
    request: CaptureRequest,
    input_path: Path,
    artifact: bytes,
    *,
    storage_root: Path,
    manifest_dir: Path,
    extraction_dir: Path,
    refresh_dir: Path,
    ocr_text: str | None,
    ocr_confidence: str | None,
) -> RefreshEvent:
    latest_event = _latest_event(spec.source_id, refresh_dir)
    _require_later_timestamp(request.retrieved_at, latest_event)
    previous = _committed_snapshot(latest_event, extraction_dir)
    digest = hashlib.sha256(artifact).hexdigest()
    adapter_fingerprint = evidence_fingerprint(spec.model_dump(mode="json"))
    extraction_fingerprint = evidence_fingerprint(
        {
            "adapter_fingerprint": adapter_fingerprint,
            "ocr_text_sha256": (
                hashlib.sha256(ocr_text.encode("utf-8")).hexdigest()
                if ocr_text is not None
                else None
            ),
            "ocr_confidence": ocr_confidence,
        }
    )

    if previous is not None:
        try:
            _verify_snapshot_capture(previous, manifest_dir, storage_root)
        except (OSError, ValueError) as error:
            return _record_failure_locked(
                spec.source_id,
                request.retrieved_at,
                f"stored capture verification failed: {error}",
                refresh_dir,
                previous=previous,
                capture_id=previous.capture_id,
                content_changed=previous.content_sha256 != digest,
            )

    if (
        previous is not None
        and previous.content_sha256 == digest
        and previous.extraction_fingerprint == extraction_fingerprint
    ):
        event_payload = _event_payload(
            source_id=spec.source_id,
            checked_at=request.retrieved_at,
            status="unchanged",
            content_changed=False,
            capture_id=previous.capture_id,
            snapshot_id=previous.id,
            previous_snapshot_id=previous.id,
            diff=[],
            error=None,
        )
        return _write_event(
            RefreshEvent.model_validate(
                {
                    **event_payload,
                    "id": _record_id(
                        "refresh", spec.source_id, request.retrieved_at, event_payload
                    ),
                }
            ),
            refresh_dir,
        )

    try:
        existing = _capture_for_content(spec.source_id, digest, manifest_dir, storage_root)
    except (OSError, ValueError) as error:
        return _record_failure_locked(
            spec.source_id,
            request.retrieved_at,
            f"stored capture verification failed: {error}",
            refresh_dir,
            previous=previous,
            content_changed=previous is None or previous.content_sha256 != digest,
        )

    capture: CapturedManifest
    if existing is None:
        capture_path = record_capture(request, input_path, storage_root, manifest_dir)
        recorded = read_capture_manifest(capture_path)
        if not isinstance(recorded, CapturedManifest):
            raise ValueError("refresh capture unexpectedly recorded unavailable evidence")
        capture = recorded
        if capture.content_sha256 != digest:
            return _record_failure_locked(
                spec.source_id,
                request.retrieved_at,
                "collection input changed while it was being captured",
                refresh_dir,
                previous=previous,
                capture_id=capture.id,
                content_changed=True,
            )
    else:
        capture = existing

    try:
        decisions = extract_decisions(
            spec,
            artifact,
            media_type=request.media_type or "",
            ocr_text=ocr_text,
            ocr_confidence=ocr_confidence,
        )
    except (ExtractionError, UnicodeError) as error:
        return _record_failure_locked(
            spec.source_id,
            request.retrieved_at,
            str(error),
            refresh_dir,
            previous=previous,
            capture_id=capture.id,
            content_changed=previous is None or previous.content_sha256 != digest,
        )

    snapshot_payload = {
        "schema_version": "1.0",
        "source_id": spec.source_id,
        "capture_id": capture.id,
        "content_sha256": digest,
        "adapter_kind": spec.adapter_kind,
        "extractor_version": spec.extractor_version,
        "adapter_fingerprint": adapter_fingerprint,
        "extraction_fingerprint": extraction_fingerprint,
        "extracted_at": _json_timestamp(request.retrieved_at),
        "decisions": [item.model_dump(mode="json") for item in decisions],
    }
    snapshot = ExtractionSnapshot.model_validate(
        {
            **snapshot_payload,
            "id": _record_id("extraction", spec.source_id, request.retrieved_at, snapshot_payload),
        }
    )
    _write_model(snapshot, extraction_dir / f"{snapshot.id}.json")
    diff = semantic_diff(previous.decisions if previous is not None else [], decisions)
    status = "created" if previous is None else "updated"
    event_payload = _event_payload(
        source_id=spec.source_id,
        checked_at=request.retrieved_at,
        status=status,
        content_changed=previous is None or previous.content_sha256 != digest,
        capture_id=capture.id,
        snapshot_id=snapshot.id,
        previous_snapshot_id=previous.id if previous is not None else None,
        diff=diff,
        error=None,
    )
    event = RefreshEvent.model_validate(
        {
            **event_payload,
            "id": _record_id("refresh", spec.source_id, request.retrieved_at, event_payload),
        }
    )
    return _write_event(event, refresh_dir)


def record_refresh_failure(
    source_id: str,
    checked_at: datetime,
    error: str,
    refresh_dir: Path,
    *,
    extraction_dir: Path,
    capture_id: str | None = None,
    content_changed: bool | None = None,
) -> RefreshEvent:
    """Append an explicit failure while retaining the committed verified snapshot."""
    with _source_lock(refresh_dir, source_id):
        latest_event = _latest_event(source_id, refresh_dir)
        _require_later_timestamp(checked_at, latest_event)
        previous = _committed_snapshot(latest_event, extraction_dir)
        return _record_failure_locked(
            source_id,
            checked_at,
            error,
            refresh_dir,
            previous=previous,
            capture_id=capture_id,
            content_changed=content_changed,
        )


def _record_failure_locked(
    source_id: str,
    checked_at: datetime,
    error: str,
    refresh_dir: Path,
    *,
    previous: ExtractionSnapshot | None,
    capture_id: str | None = None,
    content_changed: bool | None = None,
) -> RefreshEvent:
    payload = _event_payload(
        source_id=source_id,
        checked_at=checked_at,
        status="failed",
        content_changed=content_changed,
        capture_id=capture_id,
        snapshot_id=None,
        previous_snapshot_id=previous.id if previous is not None else None,
        diff=[],
        error=error.strip()[:2_000] or "unknown collection failure",
    )
    event = RefreshEvent.model_validate(
        {**payload, "id": _record_id("refresh", source_id, checked_at, payload)}
    )
    return _write_event(event, refresh_dir)


def semantic_diff(
    before: list[AdapterDecision], after: list[AdapterDecision]
) -> list[DecisionDiff]:
    """Compare canonical decisions while ignoring excerpts and parser metadata."""
    old = {item.race_id: item for item in before}
    new = {item.race_id: item for item in after}
    result: list[DecisionDiff] = []
    for race_id in sorted(old.keys() | new.keys()):
        if race_id not in old:
            result.append(DecisionDiff(kind="added", race_id=race_id, after=new[race_id]))
        elif race_id not in new:
            result.append(DecisionDiff(kind="removed", race_id=race_id, before=old[race_id]))
        elif _decision_semantics(old[race_id]) != _decision_semantics(new[race_id]):
            result.append(
                DecisionDiff(
                    kind="changed", race_id=race_id, before=old[race_id], after=new[race_id]
                )
            )
    return result


def _decision_semantics(decision: AdapterDecision) -> tuple[str, tuple[str, ...]]:
    return decision.status, tuple(sorted(decision.candidate_ids))


def _latest_event(source_id: str, directory: Path) -> RefreshEvent | None:
    events = [
        event
        for path in directory.glob("refresh-*.json")
        if (event := read_refresh_event(path)).source_id == source_id
    ]
    return max(events, key=lambda item: (item.checked_at, item.id), default=None)


def _committed_snapshot(
    latest_event: RefreshEvent | None, extraction_dir: Path
) -> ExtractionSnapshot | None:
    if latest_event is None:
        return None
    snapshot_id = latest_event.snapshot_id or latest_event.previous_snapshot_id
    if snapshot_id is None:
        return None
    snapshot = read_extraction_snapshot(extraction_dir / f"{snapshot_id}.json")
    if snapshot.source_id != latest_event.source_id:
        raise ValueError("committed extraction source does not match its refresh event")
    return snapshot


def _require_later_timestamp(checked_at: datetime, latest_event: RefreshEvent | None) -> None:
    if latest_event is not None and checked_at <= latest_event.checked_at:
        raise RefreshOrderError(
            "refresh timestamp must be later than the source's latest committed event"
        )


def _verify_snapshot_capture(
    snapshot: ExtractionSnapshot, manifest_dir: Path, storage_root: Path
) -> CapturedManifest:
    manifest = read_capture_manifest(manifest_dir / f"{snapshot.capture_id}.json")
    if not isinstance(manifest, CapturedManifest):
        raise ValueError("extraction snapshot references unavailable evidence")
    if manifest.source_id != snapshot.source_id:
        raise ValueError("extraction snapshot and capture sources differ")
    if manifest.content_sha256 != snapshot.content_sha256:
        raise ValueError("extraction snapshot and capture hashes differ")
    verify_capture(manifest, storage_root)
    return manifest


def _capture_for_content(
    source_id: str, digest: str, manifest_dir: Path, storage_root: Path
) -> CapturedManifest | None:
    captures: list[CapturedManifest] = []
    for path in manifest_dir.glob("capture-*.json"):
        manifest = read_capture_manifest(path)
        if (
            isinstance(manifest, CapturedManifest)
            and manifest.source_id == source_id
            and manifest.content_sha256 == digest
        ):
            verify_capture(manifest, storage_root)
            captures.append(manifest)
    return max(captures, key=lambda item: (item.retrieved_at, item.id), default=None)


def _event_payload(
    *,
    source_id: str,
    checked_at: datetime,
    status: str,
    content_changed: bool | None,
    capture_id: str | None,
    snapshot_id: str | None,
    previous_snapshot_id: str | None,
    diff: list[DecisionDiff],
    error: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_id": source_id,
        "checked_at": _json_timestamp(checked_at),
        "status": status,
        "content_changed": content_changed,
        "capture_id": capture_id,
        "snapshot_id": snapshot_id,
        "previous_snapshot_id": previous_snapshot_id,
        "diff": [item.model_dump(mode="json") for item in diff],
        "error": error,
    }


def _write_event(event: RefreshEvent, directory: Path) -> RefreshEvent:
    _write_model(event, directory / f"{event.id}.json")
    return event


def _write_model(model: BaseModel, path: Path) -> None:
    write_immutable_record(path, canonical_json_bytes(model.model_dump(mode="json")))


def _record_id(kind: str, source_id: str, timestamp: datetime, payload: object) -> str:
    stamp = timestamp.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{kind}-{source_id}-{stamp}-{evidence_fingerprint(payload)[:12]}"


def _json_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _validate_identified[T: ExtractionSnapshot | RefreshEvent](path: Path, model: T) -> T:
    if path.name != f"{model.id}.json":
        raise ValueError("record filename does not match its identity")
    payload = model.model_dump(mode="json", exclude={"id"})
    expected = evidence_fingerprint(payload)[:12]
    if not model.id.endswith(f"-{expected}"):
        raise ValueError("record identity does not match its content")
    return model


@contextmanager
def _source_lock(refresh_dir: Path, source_id: str):
    lock_dir = Path(tempfile.gettempdir()) / "seattle-election-guide-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    history_key = hashlib.sha256(str(refresh_dir.resolve()).encode()).hexdigest()[:16]
    lock_path = lock_dir / f"{history_key}-{source_id}.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
