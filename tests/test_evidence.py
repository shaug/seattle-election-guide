import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from election_guide.evidence.manual import import_manual_entry, read_manual_draft
from election_guide.evidence.models import (
    CapturedManifest,
    CaptureRequest,
    ManualEntryDraft,
    UnavailableManifest,
    UnavailableRequest,
)
from election_guide.evidence.storage import (
    ImmutableRecordError,
    read_capture_manifest,
    record_capture,
    record_unavailable,
    verify_capture,
)
from election_guide.serialization import read_yaml

PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "evidence"


@pytest.mark.parametrize(
    ("filename", "capture_method", "media_type"),
    [
        ("static.html", "static_html", "text/html"),
        ("endorsements.pdf", "pdf", "application/pdf"),
        ("endorsement-card.svg", "image", "image/svg+xml"),
    ],
)
def test_direct_capture_paths_are_content_addressed_and_verifiable(
    tmp_path: Path,
    filename: str,
    capture_method: str,
    media_type: str,
) -> None:
    storage_root = tmp_path / "snapshots"
    manifest_dir = tmp_path / "manifests"
    request = _capture_request(capture_method=capture_method, media_type=media_type)

    manifest_path = record_capture(
        request,
        FIXTURES / filename,
        storage_root,
        manifest_dir,
    )
    manifest = read_capture_manifest(manifest_path)

    assert isinstance(manifest, CapturedManifest)
    assert manifest.id in manifest_path.name
    assert manifest.storage_scope == "local_only"
    assert manifest.storage_reference == (
        f"sha256/{manifest.content_sha256[:2]}/{manifest.content_sha256}"
    )
    assert (storage_root / manifest.storage_reference).read_bytes() == (
        FIXTURES / filename
    ).read_bytes()
    verify_capture(manifest, storage_root)


def test_capture_is_idempotent_but_manifest_history_is_immutable(tmp_path: Path) -> None:
    request = _capture_request()
    input_path = FIXTURES / "static.html"
    storage_root = tmp_path / "snapshots"
    manifest_dir = tmp_path / "manifests"

    original = record_capture(request, input_path, storage_root, manifest_dir)
    repeated = record_capture(request, input_path, storage_root, manifest_dir)

    assert repeated == original
    changed = request.model_copy(update={"title": "A conflicting historical title"})
    with pytest.raises(ImmutableRecordError, match="refusing to overwrite immutable record"):
        record_capture(changed, input_path, storage_root, manifest_dir)


def test_hash_verification_detects_modified_evidence(tmp_path: Path) -> None:
    storage_root = tmp_path / "snapshots"
    manifest_path = record_capture(
        _capture_request(),
        FIXTURES / "static.html",
        storage_root,
        tmp_path / "manifests",
    )
    manifest = read_capture_manifest(manifest_path)
    assert isinstance(manifest, CapturedManifest)

    (storage_root / manifest.storage_reference).write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="capture hash mismatch"):
        verify_capture(manifest, storage_root)


def test_unavailable_source_has_manifest_without_artifact(tmp_path: Path) -> None:
    request = UnavailableRequest.model_validate(read_yaml(FIXTURES / "unavailable-request.yaml"))

    manifest_path = record_unavailable(request, tmp_path / "manifests")
    manifest = read_capture_manifest(manifest_path)

    assert isinstance(manifest, UnavailableManifest)
    assert manifest.availability == "unavailable"
    assert "content_sha256" not in json.loads(manifest_path.read_text(encoding="utf-8"))
    verify_capture(manifest, tmp_path / "snapshots")

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["unavailable_reason"] = "tampered reason"
    tampered = tmp_path / "tampered-unavailable.json"
    tampered.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="metadata hash prefix"):
        read_capture_manifest(tampered)


def test_manifest_reader_rejects_identity_tampering(tmp_path: Path) -> None:
    manifest_path = record_capture(
        _capture_request(),
        FIXTURES / "static.html",
        tmp_path / "snapshots",
        tmp_path / "manifests",
    )
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["source_id"] = "the-urbanist"
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="capture ID must encode its source"):
        read_capture_manifest(tampered)


def test_manifest_reader_rejects_duplicate_json_fields(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"availability":"captured","availability":"unavailable"}', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON object key 'availability'"):
        read_capture_manifest(path)


def test_restricted_capture_manifest_does_not_embed_local_path_or_content(tmp_path: Path) -> None:
    storage_root = tmp_path / "private-snapshots"
    manifest_path = record_capture(
        _capture_request(redistribution="restricted"),
        FIXTURES / "static.html",
        storage_root,
        tmp_path / "public-manifests",
    )
    manifest_text = manifest_path.read_text(encoding="utf-8")

    assert str(storage_root) not in manifest_text
    assert "Fixture Candidate" not in manifest_text
    assert '"redistribution": "restricted"' in manifest_text
    assert '"storage_scope": "local_only"' in manifest_text


def test_manual_image_entry_imports_with_verified_capture(tmp_path: Path) -> None:
    storage_root = tmp_path / "snapshots"
    manifest_dir = tmp_path / "manifests"
    manifest_path = record_capture(
        _capture_request(
            capture_method="manual_upload",
            media_type="image/svg+xml",
            http_status=None,
            redistribution="restricted",
        ),
        FIXTURES / "endorsement-card.svg",
        storage_root,
        manifest_dir,
    )
    manifest = read_capture_manifest(manifest_path)
    draft_path = _manual_draft_path(tmp_path, manifest.id)

    output = import_manual_entry(
        draft_path,
        manifest_dir,
        storage_root,
        tmp_path / "review" / "manual",
    )
    record = json.loads(output.read_text(encoding="utf-8"))

    assert record["entry_method"] == "manual"
    assert record["capture_id"] == manifest.id
    assert record["reviewer"] == "fixture-reviewer"
    assert record["review_status"] == "verified"
    assert output == import_manual_entry(
        draft_path,
        manifest_dir,
        storage_root,
        tmp_path / "review" / "manual",
    )


def test_manual_entry_rejects_source_mismatch(tmp_path: Path) -> None:
    storage_root = tmp_path / "snapshots"
    manifest_dir = tmp_path / "manifests"
    manifest_path = record_capture(
        _capture_request(),
        FIXTURES / "static.html",
        storage_root,
        manifest_dir,
    )
    manifest = read_capture_manifest(manifest_path)
    draft_path = _manual_draft_path(tmp_path, manifest.id, source_id="the-urbanist")

    with pytest.raises(ValueError, match="does not match capture source"):
        import_manual_entry(draft_path, manifest_dir, storage_root, tmp_path / "review")


def test_manual_entry_rejects_evidence_type_mismatch(tmp_path: Path) -> None:
    storage_root = tmp_path / "snapshots"
    manifest_dir = tmp_path / "manifests"
    manifest = read_capture_manifest(
        record_capture(
            _capture_request(),
            FIXTURES / "static.html",
            storage_root,
            manifest_dir,
        )
    )
    draft_path = _manual_draft_path(tmp_path, manifest.id)

    with pytest.raises(ValueError, match="requires an image capture"):
        import_manual_entry(draft_path, manifest_dir, storage_root, tmp_path / "review")


def test_manual_entry_rejects_unavailable_capture(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifests"
    request = UnavailableRequest.model_validate(read_yaml(FIXTURES / "unavailable-request.yaml"))
    manifest = read_capture_manifest(record_unavailable(request, manifest_dir))
    draft_path = _manual_draft_path(
        tmp_path,
        manifest.id,
        source_id="seattle-times-editorial-board",
    )

    with pytest.raises(ValueError, match="requires captured evidence"):
        import_manual_entry(
            draft_path,
            manifest_dir,
            tmp_path / "snapshots",
            tmp_path / "review",
        )


def test_completed_manual_review_requires_audit_metadata() -> None:
    raw: dict[str, Any] = read_yaml(FIXTURES / "manual-entry.yaml")
    raw["reviewed_by"] = None

    with pytest.raises(ValidationError, match="requires reviewer and timestamp"):
        ManualEntryDraft.model_validate(raw)


def test_capture_models_reject_incoherent_method_metadata() -> None:
    with pytest.raises(ValidationError, match="pdf capture requires application/pdf"):
        _capture_request(capture_method="pdf", media_type="text/html")

    with pytest.raises(ValidationError, match="direct captures require an HTTP status"):
        _capture_request(http_status=None)


def _capture_request(
    *,
    capture_method: str = "static_html",
    media_type: str = "text/html",
    http_status: int | None = 200,
    redistribution: str = "permitted",
) -> CaptureRequest:
    return CaptureRequest.model_validate(
        {
            "source_id": "the-stranger",
            "requested_url": "https://example.org/endorsements",
            "canonical_url": "https://example.org/endorsements",
            "retrieved_at": datetime(2026, 7, 19, 12, tzinfo=UTC),
            "http_status": http_status,
            "media_type": media_type,
            "title": "Fixture 2026 Primary Endorsements",
            "capture_method": capture_method,
            "browser_required": capture_method == "browser",
            "redistribution": redistribution,
            "redistribution_note": "Original fixture content created for repository tests.",
        }
    )


def _manual_draft_path(
    tmp_path: Path,
    capture_id: str,
    *,
    source_id: str = "the-stranger",
) -> Path:
    raw: dict[str, Any] = read_yaml(FIXTURES / "manual-entry.yaml")
    raw["capture_id"] = capture_id
    raw["source_id"] = source_id
    output = tmp_path / f"manual-{source_id}.yaml"
    output.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    assert read_manual_draft(output).capture_id == capture_id
    return output
