"""Shared validation for provenance-bearing metadata."""

import re
from urllib.parse import parse_qsl, unquote_plus, urlsplit

from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)
MEDIA_TYPE_TOKEN = r"[A-Za-z0-9!#$%&'*+.^_`|~-]+"
MEDIA_TYPE_QUOTED_VALUE = r'"(?:\\[\t -~]|[^\x00-\x1f\x7f"\\])*"'
MEDIA_TYPE_PATTERN = re.compile(
    rf"{MEDIA_TYPE_TOKEN}/{MEDIA_TYPE_TOKEN}"
    rf"(?:[ \t]*;[ \t]*{MEDIA_TYPE_TOKEN}[ \t]*=[ \t]*"
    rf"(?:{MEDIA_TYPE_TOKEN}|{MEDIA_TYPE_QUOTED_VALUE}))*"
)
MEDIA_TYPE_PARAMETER_PATTERN = re.compile(
    rf"[ \t]*;[ \t]*(?P<name>{MEDIA_TYPE_TOKEN})[ \t]*=[ \t]*"
    rf"(?:{MEDIA_TYPE_TOKEN}|{MEDIA_TYPE_QUOTED_VALUE})"
)
SENSITIVE_URL_PARAMETER_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "awsaccesskeyid",
    "client_secret",
    "code",
    "credential",
    "googleaccessid",
    "id_token",
    "jwt",
    "key",
    "password",
    "passwd",
    "secret",
    "session_token",
    "sig",
    "signature",
    "token",
}
SENSITIVE_URL_PARAMETER_SUFFIXES = (
    "_api_key",
    "_apikey",
    "_credential",
    "_key",
    "_password",
    "_secret",
    "_signature",
    "_token",
)
SENSITIVE_URL_PARAMETER_NAMES_COLLAPSED = {
    re.sub(r"[^a-z0-9]", "", name) for name in SENSITIVE_URL_PARAMETER_NAMES
}
SENSITIVE_URL_PARAMETER_SUFFIXES_COLLAPSED = tuple(
    re.sub(r"[^a-z0-9]", "", suffix) for suffix in SENSITIVE_URL_PARAMETER_SUFFIXES
)


def validated_http_url(value: str) -> str:
    """Return a normalized HTTP(S) URL without embedded credentials."""
    try:
        url = HTTP_URL_ADAPTER.validate_python(value)
    except ValidationError as error:
        raise ValueError("must be an absolute HTTP(S) URL") from error
    if url.username is not None or url.password is not None:
        raise ValueError("official URLs cannot contain credentials")
    normalized = str(url)
    split = urlsplit(normalized)
    _reject_credential_parameters([split.query, split.fragment, split.fragment.partition("?")[2]])
    return normalized


def validated_media_type(value: str) -> str:
    """Return a normalized, nonempty MIME type."""
    normalized = value.strip()
    if not MEDIA_TYPE_PATTERN.fullmatch(normalized):
        raise ValueError("media type must be a nonempty MIME type")
    essence, separator, parameters = normalized.partition(";")
    names: set[str] = set()
    remaining = separator + parameters if separator else ""
    position = 0
    while position < len(remaining):
        match = MEDIA_TYPE_PARAMETER_PATTERN.match(remaining, position)
        if match is None:
            raise ValueError("media type must use valid MIME parameters")
        name = match.group("name").lower()
        if name in names:
            raise ValueError(f"media type repeats parameter {name!r}")
        names.add(name)
        position = match.end()
    return essence.lower() + (separator + parameters if separator else "")


def media_type_essence(value: str) -> str:
    """Return the case-insensitive MIME type without parameters."""
    return value.partition(";")[0].strip().lower()


def _reject_credential_parameters(initial_components: list[str]) -> None:
    pending = [component for component in initial_components if component]
    inspected: set[str] = set()
    while pending:
        component = pending.pop()
        if component in inspected:
            continue
        inspected.add(component)
        if len(inspected) > 256:
            raise ValueError("official URL parameter nesting is too deep to validate safely")
        variants = _decoded_variants(component)
        pending.extend(variant for variant in variants[1:] if variant not in inspected)
        for variant in variants:
            try:
                parameters = parse_qsl(
                    variant,
                    keep_blank_values=True,
                    max_num_fields=128,
                )
            except ValueError as error:
                raise ValueError(
                    "official URL has too many parameters to validate safely"
                ) from error
            for name, parameter_value in parameters:
                if _is_sensitive_parameter_name(name):
                    raise ValueError("official URLs cannot contain credential parameters")
                nested = urlsplit(parameter_value)
                pending.extend(
                    item
                    for item in (
                        nested.query,
                        nested.fragment,
                        nested.fragment.partition("?")[2],
                    )
                    if item
                )
                nested_name, separator, _ = parameter_value.lstrip("?&").partition("=")
                if separator and _is_sensitive_parameter_name(nested_name):
                    pending.append(parameter_value)


def _decoded_variants(value: str) -> list[str]:
    variants = [value]
    for _ in range(8):
        decoded = unquote_plus(variants[-1])
        if decoded == variants[-1]:
            return variants
        variants.append(decoded)
    if unquote_plus(variants[-1]) != variants[-1]:
        raise ValueError("official URL parameter encoding is too deep to validate safely")
    return variants


def _is_sensitive_parameter_name(name: str) -> bool:
    normalized_name = name.lower().replace("-", "_")
    collapsed_name = re.sub(r"[^a-z0-9]", "", name.lower())
    return (
        normalized_name in SENSITIVE_URL_PARAMETER_NAMES
        or normalized_name.endswith(SENSITIVE_URL_PARAMETER_SUFFIXES)
        or normalized_name.startswith("x_amz_")
        or normalized_name.startswith("x_goog_")
        or collapsed_name in SENSITIVE_URL_PARAMETER_NAMES_COLLAPSED
        or collapsed_name.endswith(SENSITIVE_URL_PARAMETER_SUFFIXES_COLLAPSED)
        or collapsed_name.startswith("xamz")
        or collapsed_name.startswith("xgoog")
    )
