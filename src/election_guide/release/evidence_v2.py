"""Bounded, lossless compressed evidence framing, independent of GitHub writes."""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import re
import zlib
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from election_guide.release.automation_models import Producer, Sha256
from election_guide.serialization import canonical_json_bytes

MARKER = "<!-- release-evidence-v2 "
MAX_COMMENT_CHARS = 60000
MAX_REPORTS = 16
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_COMPRESSED_BYTES = 4 * 1024 * 1024
PART_BYTES = 32768
MAX_PARTS = 128
REPORT_NAME = re.compile(r"[A-Za-z0-9_.-]{1,100}")


class EnvelopeMarker(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["2.0"] = "2.0"
    encoding: Literal["gzip+base64"] = "gzip+base64"
    producer: Producer
    release_version: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,200}$")
    phase: Literal["publication", "deployment"]
    state: Literal["published", "verified", "failed", "superseded", "deployment_paused"]
    group: Sha256
    kind: Literal["v2-envelope", "v2-part", "v2-seal"] = "v2-envelope"
    part: int = Field(default=1, ge=1, le=MAX_PARTS)
    count: int = Field(default=1, ge=1, le=MAX_PARTS)
    compressed_bytes: int = Field(ge=1, le=MAX_COMPRESSED_BYTES)
    compressed_sha256: Sha256
    uncompressed_bytes: int = Field(ge=1, le=MAX_TOTAL_BYTES)
    uncompressed_sha256: Sha256
    part_sha256: Sha256


class EnvelopeRef(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: int = Field(gt=0)
    part: int = Field(ge=1, le=MAX_PARTS)
    sha256: Sha256


class EnvelopeSeal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["2.0"] = "2.0"
    parts: tuple[EnvelopeRef, ...] = Field(min_length=1, max_length=MAX_PARTS)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate compressed evidence JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError(f"nonfinite compressed evidence JSON: {value}")


def _json(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("invalid compressed evidence UTF-8 JSON") from error


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("compressed evidence requires a JSON object")
    return cast(dict[str, Any], value)


def _files(files: dict[str, bytes]) -> None:
    if not 1 <= len(files) <= MAX_REPORTS or "receipt.json" not in files:
        raise ValueError("compressed evidence report count or receipt is invalid")
    for name, content in files.items():
        if (
            REPORT_NAME.fullmatch(name) is None
            or name in {".", ".."}
            or type(content) is not bytes
            or len(content) > MAX_REPORT_BYTES
        ):
            raise ValueError("compressed evidence report name or size exceeds bound")
        if canonical_json_bytes(_json(content)) != content:
            raise ValueError("compressed evidence requires original canonical UTF-8 JSON")


def encode_envelope(files: dict[str, bytes]) -> bytes:
    """Compress canonical report text without normalizing its original bytes."""
    _files(files)
    data = canonical_json_bytes(
        {
            "schema_version": "2.0",
            "files": {
                name: {"content": content.decode("utf-8"), "sha256": _sha(content)}
                for name, content in files.items()
            },
        }
    )
    if len(data) > MAX_TOTAL_BYTES:
        raise ValueError("compressed evidence envelope exceeds decoded bound")
    output = io.BytesIO()
    # GzipFile emits an OS-independent header without a filename or clock.
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as sink:
        sink.write(data)
    compressed = output.getvalue()
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise ValueError("compressed evidence exceeds compressed bound")
    return compressed


def _checked(marker: EnvelopeMarker) -> EnvelopeMarker:
    return EnvelopeMarker.model_validate(marker.model_dump())


def decode_envelope(payload: bytes, marker: EnvelopeMarker) -> dict[str, bytes]:
    marker = _checked(marker)
    if (
        len(payload) > MAX_COMPRESSED_BYTES
        or len(payload) != marker.compressed_bytes
        or _sha(payload) != marker.compressed_sha256
        or marker.uncompressed_bytes > MAX_TOTAL_BYTES
    ):
        raise ValueError("compressed evidence size or hash conflicts")
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        data = decoder.decompress(payload, MAX_TOTAL_BYTES + 1)
    except zlib.error as error:
        raise ValueError("invalid compressed evidence gzip") from error
    if (
        len(data) > MAX_TOTAL_BYTES
        or len(data) != marker.uncompressed_bytes
        or not decoder.eof
        or decoder.unused_data
        or decoder.unconsumed_tail
        or _sha(data) != marker.uncompressed_sha256
    ):
        raise ValueError("compressed evidence expansion, length or trailing data conflicts")
    value = _object(_json(data))
    if set(value) != {"schema_version", "files"} or value["schema_version"] != "2.0":
        raise ValueError("invalid compressed evidence envelope")
    wire_files = _object(value["files"])
    if not 1 <= len(wire_files) <= MAX_REPORTS:
        raise ValueError("compressed evidence report count exceeds bound")
    files: dict[str, bytes] = {}
    for name, raw_record in wire_files.items():
        record = _object(raw_record)
        if set(record) != {"content", "sha256"} or not isinstance(record["content"], str):
            raise ValueError("invalid compressed evidence report")
        content = record["content"].encode("utf-8")
        if _sha(content) != record["sha256"]:
            raise ValueError("compressed evidence original report hash conflicts")
        files[name] = content
    _files(files)
    if _sha(files["receipt.json"]) != marker.group:
        raise ValueError("compressed evidence operation digest conflicts")
    return files


def _piece(marker: EnvelopeMarker, payload: bytes) -> None:
    if (
        marker.part > marker.count
        or marker.count > MAX_PARTS
        or _sha(payload) != marker.part_sha256
    ):
        raise ValueError("compressed evidence part identity or hash conflicts")
    if marker.kind == "v2-envelope":
        if (
            marker.part != 1
            or marker.count != 1
            or len(payload) != marker.compressed_bytes
            or _sha(payload) != marker.compressed_sha256
        ):
            raise ValueError("atomic compressed evidence identity conflicts")
    elif marker.kind == "v2-part":
        if len(payload) > PART_BYTES or not payload:
            raise ValueError("compressed evidence part exceeds bound")
    elif marker.part != 1 or len(payload) > MAX_COMMENT_CHARS:
        raise ValueError("compressed evidence seal exceeds bound")


def _body(marker: EnvelopeMarker, payload: bytes) -> str:
    producer = marker.producer
    return (
        f"Release {marker.release_version}: {marker.phase}/{marker.state}. "
        f"[Run {producer.run_id}/{producer.run_attempt}]"
        f"(https://github.com/{producer.repository}/actions/runs/{producer.run_id}).\n"
        "<details>\n<summary>Compressed release evidence v2</summary>\n\n"
        + base64.b64encode(payload).decode("ascii")
        + "\n</details>\n"
        + MARKER
        + json.dumps(marker.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        + " -->"
    )


def render_envelope(marker: EnvelopeMarker, payload: bytes) -> str:
    marker = _checked(marker)
    _piece(marker, payload)
    body = _body(marker, payload)
    if len(body) >= MAX_COMMENT_CHARS:
        raise ValueError("compressed evidence framing exceeds comment bound")
    return body


def decode_comment(body: str) -> tuple[EnvelopeMarker, bytes]:
    if len(body) >= MAX_COMMENT_CHARS:
        raise ValueError("compressed evidence comment exceeds bound")
    lines = body.splitlines()
    if len(lines) != 7 or not lines[-1].startswith(MARKER) or not lines[-1].endswith(" -->"):
        raise ValueError("invalid compressed evidence framing")
    marker = EnvelopeMarker.model_validate(_json(lines[-1][len(MARKER) : -4].encode()))
    try:
        payload = base64.b64decode(lines[4], validate=True)
    except ValueError as error:
        raise ValueError("invalid compressed evidence base64") from error
    if render_envelope(marker, payload) != body:
        raise ValueError("conflicting compressed evidence framing")
    return marker, payload


def envelope_parts(
    marker: EnvelopeMarker, payload: bytes
) -> tuple[tuple[EnvelopeMarker, bytes], ...]:
    marker = _checked(marker)
    _piece(marker, payload)
    if len(_body(marker, payload)) < MAX_COMMENT_CHARS:
        return ((marker, payload),)
    chunks = tuple(payload[i : i + PART_BYTES] for i in range(0, len(payload), PART_BYTES))
    if not 1 <= len(chunks) <= MAX_PARTS:
        raise ValueError("compressed evidence multipart count exceeds bound")
    parts = tuple(
        (
            marker.model_copy(
                update={
                    "kind": "v2-part",
                    "part": i + 1,
                    "count": len(chunks),
                    "part_sha256": _sha(data),
                }
            ),
            data,
        )
        for i, data in enumerate(chunks)
    )
    for part, data in parts:
        render_envelope(part, data)
    return parts


def assemble_envelope(
    marker: EnvelopeMarker,
    payload: bytes,
    comments: dict[int, tuple[EnvelopeMarker, bytes]],
) -> dict[str, bytes]:
    marker = _checked(marker)
    _piece(marker, payload)
    if marker.kind != "v2-seal":
        raise ValueError("multipart evidence requires a final seal")
    value = _json(payload)
    if canonical_json_bytes(value) != payload:
        raise ValueError("noncanonical compressed evidence seal")
    seal = EnvelopeSeal.model_validate_json(payload)
    if len(seal.parts) != marker.count or len({ref.id for ref in seal.parts}) != len(seal.parts):
        raise ValueError("missing or duplicate compressed evidence references")
    chunks: list[bytes] = []
    size = 0
    for index, ref in enumerate(seal.parts):
        found = comments.get(ref.id)
        if ref.part != index + 1 or found is None:
            raise ValueError("missing or unordered compressed evidence part")
        expected = marker.model_copy(
            update={"kind": "v2-part", "part": index + 1, "part_sha256": ref.sha256}
        )
        actual, data = found
        if actual != expected:
            raise ValueError("conflicting compressed evidence part identity")
        _piece(actual, data)
        size += len(data)
        if size > MAX_COMPRESSED_BYTES:
            raise ValueError("compressed evidence assembled size exceeds bound")
        chunks.append(data)
    return decode_envelope(b"".join(chunks), marker)
