"""Deterministic source extraction with no implicit candidate inference."""

from __future__ import annotations

import io
import re
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader

from election_guide.collection.models import AdapterDecision, AdapterSpec
from election_guide.inventory.models import Inventory
from election_guide.normalization.matching import eligible_race_ids
from election_guide.sources.models import SourceRegistry
from election_guide.validation import media_type_essence


class ExtractionError(ValueError):
    """Raised when reviewed extraction rules no longer match the source exactly."""


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0
        self.hidden_stack: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        hidden = self.hidden_depth > 0 or _html_element_is_hidden(tag, attrs)
        if hidden and tag not in _HTML_VOID_TAGS:
            self.hidden_depth += 1
        if tag not in _HTML_VOID_TAGS:
            self.hidden_stack.append(hidden)
        if not hidden and tag in {"br", "p", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.hidden_depth and tag in {"p", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")
        if self.hidden_stack and self.hidden_stack.pop():
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def validate_adapter(spec: AdapterSpec, inventory: Inventory, registry: SourceRegistry) -> None:
    """Validate every configured canonical ID and source relationship."""
    source = next((item for item in registry.sources if item.id == spec.source_id), None)
    if source is None:
        raise ValueError(f"adapter has unknown source {spec.source_id!r}")
    if source.discovery.status != "published":
        raise ValueError(f"adapter source {spec.source_id!r} has no published discovery")
    if source.discovery.media_type is None:
        raise ValueError(f"adapter source {spec.source_id!r} has no discovered media type")
    discovered_type = media_type_essence(source.discovery.media_type)
    kind_matches = {
        "static_html": discovered_type in {"text/html", "application/xhtml+xml"},
        "dynamic_html": discovered_type in {"text/html", "application/xhtml+xml"},
        "pdf": discovered_type == "application/pdf",
        "image": discovered_type.startswith("image/"),
    }[spec.adapter_kind]
    if not kind_matches:
        raise ValueError(
            f"adapter kind {spec.adapter_kind!r} conflicts with discovered media type "
            f"{discovered_type!r}"
        )
    eligible = eligible_race_ids(spec.source_id, inventory, registry)
    races = {race.id: race for race in inventory.races}
    for rule in spec.rules:
        race = races.get(rule.race_id)
        if race is None:
            raise ValueError(f"adapter rule has unknown race {rule.race_id!r}")
        if rule.race_id not in eligible:
            raise ValueError(f"adapter rule {rule.race_id!r} is outside source eligibility")
        known_choices = {choice.id for choice in race.choices}
        unknown = set(rule.candidate_ids) - known_choices
        if unknown:
            raise ValueError(
                f"adapter rule {rule.race_id!r} has unknown candidate IDs: {sorted(unknown)}"
            )


def extract_decisions(
    spec: AdapterSpec,
    artifact: bytes,
    *,
    media_type: str,
    ocr_text: str | None = None,
    ocr_confidence: str | None = None,
) -> list[AdapterDecision]:
    """Extract only the decisions explicitly represented by a reviewed adapter."""
    text, requires_review, confidence = _artifact_text(
        spec,
        artifact,
        media_type=media_type,
        ocr_text=ocr_text,
        ocr_confidence=ocr_confidence,
    )
    decisions: list[AdapterDecision] = []
    covered = list(re.finditer(spec.decision_pattern, text, flags=re.IGNORECASE | re.MULTILINE))
    covered_excerpts = [" ".join(match.group(0).split()) for match in covered]
    if not covered_excerpts:
        raise ExtractionError("complete adapter detected no decision lines")
    rule_excerpts: list[str] = []
    for rule in spec.rules:
        matches = list(re.finditer(rule.pattern, text, flags=re.IGNORECASE | re.MULTILINE))
        if len(matches) > 1:
            raise ExtractionError(
                f"rule {rule.race_id!r} matched {len(matches)} times; expected at most once"
            )
        if not matches:
            continue
        excerpt = " ".join(matches[0].group(0).split())
        rule_excerpts.append(excerpt)
        decisions.append(
            AdapterDecision(
                race_id=rule.race_id,
                status=rule.status,
                candidate_ids=rule.candidate_ids,
                evidence_excerpt=excerpt,
                evidence_locator=rule.evidence_locator,
                requires_review=requires_review,
                extraction_confidence=confidence,
            )
        )
    if sorted(covered_excerpts) != sorted(rule_excerpts):
        raise ExtractionError(
            "complete adapter coverage does not match its configured decision rules "
            f"({len(covered_excerpts)} detected, {len(rule_excerpts)} configured)"
        )
    return sorted(decisions, key=lambda item: item.race_id)


def _artifact_text(
    spec: AdapterSpec,
    artifact: bytes,
    *,
    media_type: str,
    ocr_text: str | None,
    ocr_confidence: str | None,
) -> tuple[str, bool, str]:
    kind = spec.adapter_kind
    if kind in {"static_html", "dynamic_html"}:
        if ocr_text is not None or ocr_confidence is not None:
            raise ExtractionError("HTML extraction does not accept OCR inputs")
        if media_type.split(";", 1)[0].strip().lower() not in {
            "text/html",
            "application/xhtml+xml",
        }:
            raise ExtractionError(f"{kind} adapter requires HTML")
        parser = _VisibleTextParser()
        parser.feed(artifact.decode("utf-8"))
        parser.close()
        return _normalized_lines("".join(parser.parts)), True, "0.99"
    if kind == "pdf":
        if ocr_text is not None or ocr_confidence is not None:
            raise ExtractionError("PDF extraction does not accept OCR inputs")
        if media_type.split(";", 1)[0].strip().lower() != "application/pdf":
            raise ExtractionError("PDF adapter requires application/pdf")
        try:
            pages = [page.extract_text() or "" for page in PdfReader(io.BytesIO(artifact)).pages]
        except Exception as error:
            raise ExtractionError(f"PDF text extraction failed: {error}") from error
        return _normalized_lines("\n".join(pages)), False, "1"
    if not media_type.split(";", 1)[0].strip().lower().startswith("image/"):
        raise ExtractionError("image adapter requires an image media type")
    if media_type.split(";", 1)[0].strip().lower() == "image/svg+xml":
        if ocr_text is not None or ocr_confidence is not None:
            raise ExtractionError("SVG extraction does not accept OCR inputs")
        try:
            root = ElementTree.fromstring(artifact)
        except ElementTree.ParseError as error:
            raise ExtractionError(f"SVG text extraction failed: {error}") from error
        return _normalized_lines("\n".join(_visible_svg_text(root))), True, "0.99"
    if ocr_text is None or ocr_confidence is None:
        raise ExtractionError("raster image extraction requires OCR text and confidence")
    if re.fullmatch(r"(?:0|1|0\.[0-9]{1,6})", ocr_confidence) is None:
        raise ExtractionError("OCR confidence must be an exact decimal from 0 to 1")
    return _normalized_lines(ocr_text), True, ocr_confidence


def _normalized_lines(value: str) -> str:
    return "\n".join(line for raw in value.splitlines() if (line := " ".join(raw.split())))


def read_artifact(path: Path) -> bytes:
    """Read a bounded local artifact used by the refresh CLI."""
    size = path.stat().st_size
    if size == 0:
        raise ValueError("collection artifact cannot be empty")
    if size > 25 * 1024 * 1024:
        raise ValueError("collection artifact exceeds the 25 MiB limit")
    return path.read_bytes()


_HTML_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_HIDDEN_TAGS = {"script", "style", "template", "noscript", "svg"}
_HIDDEN_SVG_TAGS = {
    "clipPath",
    "defs",
    "desc",
    "mask",
    "metadata",
    "pattern",
    "script",
    "style",
    "symbol",
    "title",
}


def _html_element_is_hidden(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
    attributes = {name.casefold(): value for name, value in attrs}
    style = (attributes.get("style") or "").casefold().replace(" ", "")
    return (
        tag in _HIDDEN_TAGS
        or "hidden" in attributes
        or (attributes.get("aria-hidden") or "").casefold() == "true"
        or "display:none" in style
        or "visibility:hidden" in style
        or "content-visibility:hidden" in style
    )


def _visible_svg_text(element: ElementTree.Element, parent_visible: bool = True) -> list[str]:
    local_tag = element.tag.rsplit("}", 1)[-1]
    style = element.attrib.get("style", "").casefold().replace(" ", "")
    visible = parent_visible and not (
        local_tag in _HIDDEN_SVG_TAGS
        or element.attrib.get("display", "").casefold() == "none"
        or element.attrib.get("visibility", "").casefold() == "hidden"
        or element.attrib.get("aria-hidden", "").casefold() == "true"
        or "display:none" in style
        or "visibility:hidden" in style
    )
    parts: list[str] = []
    if visible and element.text:
        parts.append(element.text)
    for child in element:
        parts.extend(_visible_svg_text(child, visible))
        if visible and child.tail:
            parts.append(child.tail)
    return parts
