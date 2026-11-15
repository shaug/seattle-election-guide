"""Compressed evidence preserves original bytes and rejects hostile framing."""

from __future__ import annotations

import base64
import gzip
import hashlib
import importlib
import json
from typing import Any

import pytest

from election_guide.release.automation_models import Producer
from election_guide.serialization import canonical_json_bytes


def codec() -> Any:
    return importlib.import_module("election_guide.release.evidence_v2")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def files() -> dict[str, bytes]:
    return {
        "receipt.json": b'{\n  "state": "published"\n}\n',
        "observations.json": '{\n  "text": "日本語🗳\\n"\n}\n'.encode(),
    }


def marker(payload: bytes, originals: dict[str, bytes] | None = None) -> Any:
    originals = files() if originals is None else originals
    return codec().EnvelopeMarker(
        producer=Producer(
            repository="shaug/seattle-election-guide",
            source_sha="a" * 40,
            workflow_sha="b" * 40,
            run_id=123,
            run_attempt=1,
        ),
        release_version="2026-general.128",
        phase="publication",
        state="published",
        group=sha(originals["receipt.json"]),
        compressed_bytes=len(payload),
        compressed_sha256=sha(payload),
        uncompressed_bytes=len(gzip.decompress(payload)),
        uncompressed_sha256=sha(gzip.decompress(payload)),
        part_sha256=sha(payload),
    )


def test_codec_round_trips_original_unicode_bytes() -> None:
    original = files()
    payload = codec().encode_envelope(original)
    assert codec().decode_envelope(payload, marker(payload)) == original
    envelope = json.loads(gzip.decompress(payload))
    assert envelope["schema_version"] == "2.0"
    assert envelope["files"]["observations.json"] == {
        "content": '{\n  "text": "日本語🗳\\n"\n}\n',
        "sha256": sha(original["observations.json"]),
    }


def test_deterministic_gzip_header() -> None:
    first = codec().encode_envelope(files())
    second = codec().encode_envelope(dict(reversed(list(files().items()))))
    assert first == second
    assert first[:4] == b"\x1f\x8b\x08\x00"
    assert first[4:8] == b"\x00\x00\x00\x00"
    assert first[9] == 255  # platform-independent header, no original file name


@pytest.mark.parametrize("damage", ["truncated", "trailing", "concatenated", "corrupt"])
def test_codec_rejects_trailing_or_concatenated_gzip(damage: str) -> None:
    payload = codec().encode_envelope(files())
    damaged = {
        "truncated": payload[:-3],
        "trailing": payload + b"extra",
        "concatenated": payload + gzip.compress(b"{}", mtime=0),
        "corrupt": payload[:12] + bytes([payload[12] ^ 255]) + payload[13:],
    }[damage]
    expected = marker(payload).model_copy(
        update={"compressed_bytes": len(damaged), "compressed_sha256": sha(damaged)}
    )
    with pytest.raises(ValueError):
        codec().decode_envelope(damaged, expected)


def test_decode_rejects_expansion_over_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = gzip.compress(b"x" * 50000, mtime=0)
    expected = marker(codec().encode_envelope(files())).model_copy(
        update={
            "compressed_bytes": len(payload),
            "compressed_sha256": sha(payload),
            "uncompressed_bytes": 100,
        }
    )
    monkeypatch.setattr(codec(), "MAX_TOTAL_BYTES", 1000)
    with pytest.raises(ValueError):
        codec().decode_envelope(payload, expected)


def test_envelope_rejects_duplicate_json_keys() -> None:
    raw = b'{"schema_version":"2.0","files":{},"files":{}}'
    payload = gzip.compress(raw, mtime=0)
    with pytest.raises(ValueError, match="duplicate"):
        codec().decode_envelope(payload, marker(payload))


@pytest.mark.parametrize("damage", ["report_hash", "operation_digest", "content"])
def test_decode_rejects_report_hash_or_operation_digest_conflict(damage: str) -> None:
    payload = codec().encode_envelope(files())
    envelope = json.loads(gzip.decompress(payload))
    if damage == "report_hash":
        envelope["files"]["observations.json"]["sha256"] = "0" * 64
    elif damage == "content":
        envelope["files"]["observations.json"]["content"] += "\n"
    else:
        with pytest.raises(ValueError):
            codec().decode_envelope(payload, marker(payload).model_copy(update={"group": "f" * 64}))
        return
    payload = gzip.compress(canonical_json_bytes(envelope), mtime=0)
    with pytest.raises(ValueError):
        codec().decode_envelope(payload, marker(payload))


@pytest.mark.parametrize("damage", ["name", "count", "bytes", "noncanonical", "reserved_missing"])
def test_report_limits_fail_before_encoding(damage: str, monkeypatch: pytest.MonkeyPatch) -> None:
    original = files()
    if damage == "name":
        original["../outside.json"] = b"{}\n"
    elif damage == "count":
        original.update({f"report-{i}.json": b"{}\n" for i in range(16)})
    elif damage == "bytes":
        monkeypatch.setattr(codec(), "MAX_REPORT_BYTES", 10)
    elif damage == "noncanonical":
        original["observations.json"] = b'{"a": 1}'
    else:
        del original["receipt.json"]
    with pytest.raises(ValueError):
        codec().encode_envelope(original)


def test_comment_framing_roundtrip_and_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = codec().encode_envelope(files())
    expected = marker(payload)
    body = codec().render_envelope(expected, payload)
    assert "<details>" in body and "</details>" in body
    assert "2026-general.128" in body and "publication/published" in body
    assert "https://github.com/shaug/seattle-election-guide/actions/runs/123" in body
    assert base64.b64encode(payload).decode() in body
    assert codec().decode_comment(body) == (expected, payload)
    with pytest.raises(ValueError):
        codec().decode_comment(body + "\nextra")
    monkeypatch.setattr(codec(), "MAX_COMMENT_CHARS", len(body))
    with pytest.raises(ValueError):
        codec().render_envelope(expected, payload)


def multipart(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, bytes, dict[int, Any], dict[str, bytes]]:
    original = {
        **files(),
        "large.json": canonical_json_bytes(
            {"text": "".join(sha(str(i).encode()) for i in range(80))}
        ),
    }
    payload = codec().encode_envelope(original)
    root = marker(payload, original)
    monkeypatch.setattr(codec(), "MAX_COMMENT_CHARS", 2300)
    monkeypatch.setattr(codec(), "PART_BYTES", 512)
    parts = codec().envelope_parts(root, payload)
    assert len(parts) > 1
    comments = {100 + i: part for i, part in enumerate(parts)}
    refs = [{"id": i, "part": m.part, "sha256": sha(data)} for i, (m, data) in comments.items()]
    seal = canonical_json_bytes({"schema_version": "2.0", "parts": refs})
    seal_marker = root.model_copy(
        update={"kind": "v2-seal", "count": len(parts), "part_sha256": sha(seal)}
    )
    return seal_marker, seal, comments, original


def test_multipart_requires_exact_immutable_ids_and_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    root, seal, comments, original = multipart(monkeypatch)
    assert codec().assemble_envelope(root, seal, comments) == original
    for m, payload in comments.values():
        assert len(codec().render_envelope(m, payload)) < 2300


@pytest.mark.parametrize(
    "damage", ["missing", "duplicate_id", "wrong_hash", "wrong_producer", "order"]
)
def test_multipart_rejects_missing_duplicate_or_conflicting_parts(
    damage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, seal, comments, _ = multipart(monkeypatch)
    refs = json.loads(seal)
    if damage == "missing":
        del comments[min(comments)]
    elif damage == "duplicate_id":
        refs["parts"][1]["id"] = refs["parts"][0]["id"]
    elif damage == "wrong_hash":
        refs["parts"][0]["sha256"] = "0" * 64
    elif damage == "order":
        refs["parts"].reverse()
    else:
        first = min(comments)
        m, payload = comments[first]
        comments[first] = (
            m.model_copy(
                update={"producer": m.producer.model_copy(update={"source_sha": "c" * 40})}
            ),
            payload,
        )
    seal = canonical_json_bytes(refs)
    root = root.model_copy(update={"part_sha256": sha(seal)})
    with pytest.raises(ValueError):
        codec().assemble_envelope(root, seal, comments)


@pytest.mark.parametrize("name", [".", ".."])
def test_report_names_cannot_address_an_output_directory(name: str) -> None:
    original = {**files(), name: b"{}\n"}
    with pytest.raises(ValueError):
        codec().encode_envelope(original)


@pytest.mark.parametrize(
    "changes",
    [
        {"unexpected": "field"},
        {"schema_version": "1.0"},
        {"encoding": "gzip"},
        {"count": True},
        {"part": 0},
        {"compressed_bytes": 0},
        {"uncompressed_sha256": "not-a-digest"},
    ],
)
def test_marker_rejects_unknown_or_malformed_identity(changes: dict[str, Any]) -> None:
    payload = codec().encode_envelope(files())
    wire = {**marker(payload).model_dump(), **changes}
    with pytest.raises(ValueError):
        codec().EnvelopeMarker.model_validate(wire)


def test_comment_rejects_invalid_base64() -> None:
    payload = codec().encode_envelope(files())
    body = codec().render_envelope(marker(payload), payload)
    lines = body.splitlines()
    lines[4] = lines[4][:-1] + "$"
    with pytest.raises(ValueError):
        codec().decode_comment("\n".join(lines))


def test_compressed_budget_applies_to_encoding_and_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = codec().encode_envelope(files())
    expected = marker(payload)
    monkeypatch.setattr(codec(), "MAX_COMPRESSED_BYTES", len(payload) - 1)
    with pytest.raises(ValueError):
        codec().encode_envelope(files())
    with pytest.raises(ValueError):
        codec().decode_envelope(payload, expected)


def test_multipart_count_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, _, original = multipart(monkeypatch)
    payload = codec().encode_envelope(original)
    monkeypatch.setattr(codec(), "MAX_PARTS", 2)
    with pytest.raises(ValueError):
        codec().envelope_parts(marker(payload, original), payload)
