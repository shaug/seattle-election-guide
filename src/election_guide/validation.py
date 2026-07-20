"""Shared validation for provenance-bearing metadata."""

import re

from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)
MEDIA_TYPE_PATTERN = re.compile(
    r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(?:\s*;\s*[^;=\s]+=[^;]+)*"
)


def validated_http_url(value: str) -> str:
    """Return a normalized HTTP(S) URL without embedded credentials."""
    try:
        url = HTTP_URL_ADAPTER.validate_python(value)
    except ValidationError as error:
        raise ValueError("must be an absolute HTTP(S) URL") from error
    if url.username is not None or url.password is not None:
        raise ValueError("official URLs cannot contain credentials")
    return str(url)


def validated_media_type(value: str) -> str:
    """Return a normalized, nonempty MIME type."""
    normalized = value.strip()
    if not MEDIA_TYPE_PATTERN.fullmatch(normalized):
        raise ValueError("media type must be a nonempty MIME type")
    return normalized
