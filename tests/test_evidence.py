import errno
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pytest
import yaml
from pydantic import ValidationError

import election_guide.evidence.storage as evidence_storage
from election_guide.evidence.manual import (
    import_manual_entry,
    read_manual_draft,
    validate_manual_draft,
)
from election_guide.evidence.models import (
    MAX_PUBLIC_TRANSCRIPTION_CHARS,
    CapturedManifest,
    CaptureRequest,
    ManualEntryDraft,
    UnavailableManifest,
    UnavailableRequest,
)
from election_guide.evidence.storage import (
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
    changed = request.model_copy(update={"title": "A later historical title"})
    changed_path = record_capture(changed, input_path, storage_root, manifest_dir)

    assert changed_path != original
    assert len(list(manifest_dir.glob("*.json"))) == 2


def test_same_second_captures_with_distinct_metadata_keep_distinct_history(tmp_path: Path) -> None:
    request = _capture_request().model_copy(
        update={"retrieved_at": datetime(2026, 7, 19, 12, 0, 0, 1, tzinfo=UTC)}
    )
    later = request.model_copy(
        update={"retrieved_at": datetime(2026, 7, 19, 12, 0, 0, 2, tzinfo=UTC)}
    )

    first = record_capture(
        request, FIXTURES / "static.html", tmp_path / "snapshots", tmp_path / "manifests"
    )
    second = record_capture(
        later, FIXTURES / "static.html", tmp_path / "snapshots", tmp_path / "manifests"
    )

    assert first != second


@pytest.mark.parametrize(
    "field",
    [
        "requested_url",
        "canonical_url",
        "title",
        "capture_method",
        "media_type",
        "redistribution",
        "redistribution_note",
    ],
)
def test_captured_manifest_identity_binds_public_provenance(tmp_path: Path, field: str) -> None:
    manifest_path = record_capture(
        _capture_request(),
        FIXTURES / "static.html",
        tmp_path / "snapshots",
        tmp_path / "manifests",
    )
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    replacements: dict[str, object] = {
        "requested_url": "https://attacker.example/tampered",
        "canonical_url": "https://attacker.example/tampered",
        "title": "Altered title",
        "capture_method": "manual_upload",
        "media_type": "text/html; charset=utf-8",
        "redistribution": "restricted",
        "redistribution_note": "Altered policy decision.",
    }
    raw[field] = replacements[field]
    if field in {"requested_url", "canonical_url"}:
        raw["requested_url"] = replacements["requested_url"]
        raw["canonical_url"] = replacements["canonical_url"]
    tampered = tmp_path / f"tampered-{field}.json"
    tampered.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="record hash prefix"):
        read_capture_manifest(tampered)


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


def test_unavailable_source_may_record_unknown_canonical_url(tmp_path: Path) -> None:
    raw: dict[str, Any] = read_yaml(FIXTURES / "unavailable-request.yaml")
    raw.pop("canonical_url")

    request = UnavailableRequest.model_validate(raw)
    manifest = read_capture_manifest(record_unavailable(request, tmp_path / "manifests"))

    assert isinstance(manifest, UnavailableManifest)
    assert manifest.canonical_url is None


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


def test_manifest_reader_rejects_recomputed_identity_under_old_filename(tmp_path: Path) -> None:
    manifest_path = record_capture(
        _capture_request(),
        FIXTURES / "static.html",
        tmp_path / "snapshots",
        tmp_path / "manifests",
    )
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["title"] = "Recomputed tampered title"
    payload = {key: value for key, value in raw.items() if key not in {"id", "availability"}}
    prefix = raw["id"].rsplit("-", 1)[0]
    raw["id"] = f"{prefix}-{evidence_storage.evidence_fingerprint(payload)[:12]}"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="filename does not match its identity"):
        read_capture_manifest(manifest_path)


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


def test_manual_entry_rejects_manifest_filename_alias(tmp_path: Path) -> None:
    storage_root = tmp_path / "snapshots"
    manifest_dir = tmp_path / "manifests"
    manifest_path = record_capture(
        _capture_request(), FIXTURES / "static.html", storage_root, manifest_dir
    )
    manifest = read_capture_manifest(manifest_path)
    alias_id = manifest.id[:-12] + "f" * 12
    shutil.copyfile(manifest_path, manifest_dir / f"{alias_id}.json")
    draft_path = _manual_draft_path(tmp_path, alias_id)

    with pytest.raises(ValueError, match="filename does not match its identity"):
        import_manual_entry(draft_path, manifest_dir, storage_root, tmp_path / "review")


def test_manual_entry_cannot_predate_capture(tmp_path: Path) -> None:
    storage_root = tmp_path / "snapshots"
    manifest_dir = tmp_path / "manifests"
    manifest = read_capture_manifest(
        record_capture(_capture_request(), FIXTURES / "static.html", storage_root, manifest_dir)
    )
    raw: dict[str, Any] = read_yaml(FIXTURES / "manual-entry.yaml")
    raw["capture_id"] = manifest.id
    raw["entered_at"] = "2026-07-19T11:59:00Z"
    raw["reviewed_at"] = "2026-07-19T11:59:30Z"
    draft = ManualEntryDraft.model_validate(raw)

    with pytest.raises(ValueError, match="cannot predate its evidence capture"):
        validate_manual_draft(draft, manifest_dir, storage_root)


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


def test_pending_manual_review_rejects_completed_review_note() -> None:
    raw: dict[str, Any] = read_yaml(FIXTURES / "manual-entry.yaml")
    raw.update(
        {
            "review_status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
            "review_note": "Claims verification is already complete.",
        }
    )

    with pytest.raises(ValidationError, match="cannot carry completed review metadata"):
        ManualEntryDraft.model_validate(raw)


@pytest.mark.parametrize(
    "field",
    ["evidence_locator", "transcription", "reviewer", "reviewed_by", "review_note"],
)
def test_manual_entry_rejects_blank_audit_text(field: str) -> None:
    raw: dict[str, Any] = read_yaml(FIXTURES / "manual-entry.yaml")
    raw[field] = " \t "

    with pytest.raises(ValidationError, match="cannot be blank"):
        ManualEntryDraft.model_validate(raw)


def test_manual_entry_limits_public_transcription_to_a_short_excerpt() -> None:
    raw: dict[str, Any] = read_yaml(FIXTURES / "manual-entry.yaml")
    raw["transcription"] = "x" * (MAX_PUBLIC_TRANSCRIPTION_CHARS + 1)

    with pytest.raises(ValidationError, match="at most 4000 characters"):
        ManualEntryDraft.model_validate(raw)


@pytest.mark.parametrize("field", ["evidence_locator", "review_note"])
def test_manual_entry_limits_all_public_prose_fields(field: str) -> None:
    raw: dict[str, Any] = read_yaml(FIXTURES / "manual-entry.yaml")
    raw[field] = "x" * 10_000

    with pytest.raises(ValidationError, match="at most"):
        ManualEntryDraft.model_validate(raw)


def test_capture_models_reject_incoherent_method_metadata() -> None:
    with pytest.raises(ValidationError, match="pdf capture requires application/pdf"):
        _capture_request(capture_method="pdf", media_type="text/html")

    with pytest.raises(ValidationError, match="direct captures require an HTTP status"):
        _capture_request(http_status=None)

    with pytest.raises(ValidationError, match="requires a 2xx HTTP status"):
        _capture_request(http_status=302)


@pytest.mark.parametrize(
    ("capture_method", "media_type"),
    [
        ("static_html", "Text/HTML; charset=UTF-8"),
        ("pdf", "Application/PDF; version=1.7"),
    ],
)
def test_capture_models_accept_parameterized_case_insensitive_media_types(
    capture_method: str, media_type: str
) -> None:
    request = _capture_request(capture_method=capture_method, media_type=media_type)

    assert request.media_type is not None
    assert request.media_type.split(";", 1)[0].islower()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/page?access_token=secret",
        "https://example.org/page?client_secret=secret",
        "https://example.org/page?refresh_token=secret",
        "https://example.org/page?session_token=secret",
        "https://example.org/page?clientSecret=secret",
        "https://example.org/#/callback?accessToken=secret",
        "https://example.org/#/callback?refreshToken=secret",
        "https://example.org/page?credential=secret",
        "https://example.org/page?X-Amz-Signature=secret",
        "https://example.org/page#token=secret",
        "https://example.org/#/callback?access_token=secret",
        (
            "https://example.org/redirect?next=https%3A%2F%2Fauth.example%2Fcallback"
            "%3Faccess_token%3Dsecret"
        ),
        (
            "https://example.org/redirect?next=https%3A%2F%2Fstore.example%2Fobject"
            "%3FX-Amz-Signature%3Dsecret"
        ),
    ],
)
def test_capture_models_reject_credential_bearing_public_urls(url: str) -> None:
    raw = _capture_request().model_dump()
    raw.update({"requested_url": url, "canonical_url": url})

    with pytest.raises(ValidationError, match="credential parameters"):
        CaptureRequest.model_validate(raw)


def test_capture_models_reject_deeply_nested_and_double_encoded_credentials() -> None:
    credential_url = "https://auth.example/callback?access_token=secret"
    deeply_nested = credential_url
    for _ in range(5):
        deeply_nested = f"https://example.org/redirect?next={quote_plus(deeply_nested)}"
    double_encoded = f"https://example.org/redirect?next={quote_plus(quote_plus(credential_url))}"

    for url in (deeply_nested, double_encoded):
        raw = _capture_request().model_dump()
        raw.update({"requested_url": url, "canonical_url": url})
        with pytest.raises(ValidationError, match="credential parameters"):
            CaptureRequest.model_validate(raw)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/search?q=code",
        "https://example.org/search?q=token",
        "https://example.org/search?category=authorization",
    ],
)
def test_capture_models_accept_sensitive_words_as_ordinary_parameter_values(url: str) -> None:
    raw = _capture_request().model_dump()
    raw.update({"requested_url": url, "canonical_url": url})

    request = CaptureRequest.model_validate(raw)

    assert request.requested_url.startswith("https://example.org/search?")


@pytest.mark.parametrize(
    "media_type",
    [
        "text/html; charset=utf-8\nX-Evil: yes",
        'text/html; x="unterminated',
    ],
)
def test_capture_models_reject_malformed_media_type_parameters(media_type: str) -> None:
    with pytest.raises(ValidationError, match="nonempty MIME type"):
        _capture_request(media_type=media_type)


def test_capture_models_reject_duplicate_case_insensitive_media_type_parameters() -> None:
    with pytest.raises(ValidationError, match="repeats parameter 'charset'"):
        _capture_request(media_type="text/html; charset=utf-8; CHARSET=latin1")


@pytest.mark.parametrize(
    ("capture_method", "media_type", "fixture"),
    [
        ("pdf", "application/pdf", "static.html"),
        ("image", "image/png", "static.html"),
        ("manual_upload", "application/pdf", "endorsement-card.svg"),
        ("manual_upload", "image/png", "static.html"),
    ],
)
def test_capture_rejects_bytes_that_contradict_declared_type(
    tmp_path: Path, capture_method: str, media_type: str, fixture: str
) -> None:
    with pytest.raises(ValueError, match="capture bytes"):
        record_capture(
            _capture_request(capture_method=capture_method, media_type=media_type),
            FIXTURES / fixture,
            tmp_path / "snapshots",
            tmp_path / "manifests",
        )


def test_capture_rejects_mp4_bytes_claiming_to_be_avif(tmp_path: Path) -> None:
    mp4 = tmp_path / "video.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42")

    with pytest.raises(ValueError, match="do not match declared media type 'image/avif'"):
        record_capture(
            _capture_request(capture_method="image", media_type="image/avif"),
            mp4,
            tmp_path / "snapshots",
            tmp_path / "manifests",
        )


def test_restricted_capture_rejects_unignored_repository_paths(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    input_path = repository / "local-page.html"
    input_path.write_text("restricted", encoding="utf-8")

    with pytest.raises(ValueError, match="input inside the repository"):
        record_capture(
            _capture_request(capture_method="manual_upload", redistribution="restricted"),
            input_path,
            tmp_path / "outside-storage",
            repository / "manifests",
        )


def test_restricted_capture_requires_ignored_repository_storage(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)

    with pytest.raises(ValueError, match="storage inside the repository must be Git-ignored"):
        record_capture(
            _capture_request(redistribution="restricted"),
            FIXTURES / "static.html",
            repository / "public-storage",
            tmp_path / "manifests",
        )


def test_restricted_capture_accepts_nonexistent_ignored_storage_root(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    (repository / ".gitignore").write_text("snapshots/\n", encoding="utf-8")

    output = record_capture(
        _capture_request(redistribution="restricted"),
        FIXTURES / "static.html",
        repository / "snapshots",
        tmp_path / "manifests",
    )

    assert output.is_file()


def test_restricted_capture_rejects_index_only_input(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    input_path = repository / "restricted-page.html"
    input_path.write_text("restricted", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", str(input_path)], check=True)

    with pytest.raises(ValueError, match="must already be committed or Git-ignored"):
        record_capture(
            _capture_request(capture_method="manual_upload", redistribution="restricted"),
            input_path,
            tmp_path / "snapshots",
            tmp_path / "manifests",
        )


@pytest.mark.parametrize("stage_modification", [False, True])
def test_restricted_capture_rejects_modified_committed_input(
    tmp_path: Path, stage_modification: bool
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    input_path = repository / "capture.html"
    input_path.write_text("project-owned fixture", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", str(input_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.org",
            "commit",
            "--quiet",
            "-m",
            "test fixture",
        ],
        check=True,
    )
    input_path.write_text("restricted third-party page", encoding="utf-8")
    if stage_modification:
        subprocess.run(["git", "-C", str(repository), "add", str(input_path)], check=True)

    with pytest.raises(ValueError, match="must already be committed or Git-ignored"):
        record_capture(
            _capture_request(capture_method="manual_upload", redistribution="restricted"),
            input_path,
            tmp_path / "snapshots",
            tmp_path / "manifests",
        )


@pytest.mark.parametrize("index_flag", ["--assume-unchanged", "--skip-worktree"])
def test_restricted_capture_checks_actual_bytes_despite_hidden_index_flags(
    tmp_path: Path, index_flag: str
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    input_path = repository / "capture.html"
    input_path.write_text("project-owned fixture", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", str(input_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.org",
            "commit",
            "--quiet",
            "-m",
            "test fixture",
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repository), "update-index", index_flag, str(input_path)],
        check=True,
    )
    input_path.write_text("restricted third-party page", encoding="utf-8")

    with pytest.raises(ValueError, match="must already be committed or Git-ignored"):
        record_capture(
            _capture_request(capture_method="manual_upload", redistribution="restricted"),
            input_path,
            tmp_path / "snapshots",
            tmp_path / "manifests",
        )


def test_artifact_staging_does_not_follow_shared_symlink(tmp_path: Path) -> None:
    storage_root = tmp_path / "snapshots"
    outside = tmp_path / "outside"
    storage_root.mkdir()
    outside.mkdir()
    (storage_root / ".staging").symlink_to(outside, target_is_directory=True)

    record_capture(
        _capture_request(),
        FIXTURES / "static.html",
        storage_root,
        tmp_path / "manifests",
    )

    assert not list(outside.iterdir())


@pytest.mark.parametrize(
    "prefix",
    [
        b"\xef\xbb\xbf",
        b"<!-- generated fixture -->\n",
        b"<!DOCTYPE svg>\n",
    ],
)
def test_svg_signature_validation_accepts_standard_document_prefixes(
    tmp_path: Path, prefix: bytes
) -> None:
    svg = tmp_path / "fixture.svg"
    svg.write_bytes(prefix + b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')

    output = record_capture(
        _capture_request(capture_method="image", media_type="image/svg+xml"),
        svg,
        tmp_path / "snapshots",
        tmp_path / "manifests",
    )

    assert output.is_file()


def test_immutable_install_falls_back_when_hard_links_are_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unsupported_link(source: Path, destination: Path) -> None:
        raise OSError(errno.ENOTSUP, "hard links unsupported")

    monkeypatch.setattr(evidence_storage.os, "link", unsupported_link)
    storage_root = tmp_path / "snapshots"
    manifest_path = record_capture(
        _capture_request(), FIXTURES / "static.html", storage_root, tmp_path / "manifests"
    )
    manifest = read_capture_manifest(manifest_path)

    verify_capture(manifest, storage_root)
    assert (
        record_capture(
            _capture_request(), FIXTURES / "static.html", storage_root, tmp_path / "manifests"
        )
        == manifest_path
    )


def test_pdf_fixture_has_a_resolvable_cross_reference_table() -> None:
    payload = (FIXTURES / "endorsements.pdf").read_bytes()
    marker = payload.rsplit(b"startxref\n", 1)

    assert len(marker) == 2
    offset = int(marker[1].splitlines()[0])
    assert payload[offset:].startswith(b"xref\n")


def test_yaml_rejects_merge_keys_and_semantic_duplicates(tmp_path: Path) -> None:
    merge = tmp_path / "merge.yaml"
    merge.write_text("base: &base\n  reviewer: attacker\nentry:\n  <<: *base\n", encoding="utf-8")
    duplicate = tmp_path / "semantic-duplicate.yaml"
    duplicate.write_text("true: first\nTrue: second\n", encoding="utf-8")

    with pytest.raises(yaml.YAMLError, match="merge keys are not allowed"):
        read_yaml(merge)
    with pytest.raises(yaml.YAMLError, match="duplicate mapping key"):
        read_yaml(duplicate)


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
