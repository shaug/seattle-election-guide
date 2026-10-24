"""Finite TRU WordPress discovery, with full original HTML and known image custody."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit

from pydantic import AwareDatetime, Field, model_validator

from election_guide.collection import discovery
from election_guide.collection.discovery import (
    DiscoveryAudit,
    PublicationCollector,
    PublicationParser,
)
from election_guide.collection.verification import VerificationModel
from election_guide.evidence.models import (
    CAPTURE_ID_PATTERN,
    CapturedManifest,
    ObservedManifest,
    evidence_fingerprint,
)
from election_guide.evidence.storage import read_capture_manifest, write_immutable_record
from election_guide.serialization import canonical_json_bytes, read_json

TRU_HOME = "https://transitriders.org/"
TRU_CURRENT = TRU_HOME + "2026-general-election-endorsements/"
TRU_BOUNDARY = TRU_HOME + "transit-riders-union-2026-general-election-endorsements/"
TRU_IMAGE = (
    "https://transitriders.sfo3.digitaloceanspaces.com/transitriders.org/wp-content/uploads/"
    "2026/10/17022007/TRU_November_2026_General_Endorsements-1024x581.jpg"
)


def validate_tru_article(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "transitriders.org"
        or parsed.query
        or parsed.fragment
        or re.fullmatch(r"/[a-z0-9]+(?:-[a-z0-9]+)*/", parsed.path) is None
        or "2026-general-election-endorsements" not in parsed.path
    ):
        raise ValueError("TRU requires a clean official current-general article identity")


def archive_number(url: str) -> int:
    if url == TRU_HOME:
        return 1
    parsed = urlsplit(url)
    match = re.fullmatch(r"/page/([1-9][0-9]*)/", parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "transitriders.org"
        or parsed.query
        or parsed.fragment
        or match is None
        or int(match[1]) < 2
    ):
        raise ValueError("TRU archive requires the official root or a clean numbered page")
    return int(match[1])


def current_title(text: str) -> bool:
    return (
        re.fullmatch(
            r"(?:transit riders union )?2026 general election endorsements(?:[: \u2013-].+)?",
            " ".join(text.split()).casefold(),
        )
        is not None
    )


class TruParser(PublicationParser):
    """Read WordPress post identities, designated next links and scoped article content."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, set[str]]] = []
        self.entries: list[tuple[str, list[tuple[str, str]]]] = []
        self.entry_headings: list[str] = []
        self.bookmarks: list[tuple[str, str]] = []
        self.next_links: set[str] = set()
        self.article_count = 0
        self.content_count = 0
        self.content: list[str] = []
        self.images: list[str] = []
        self.scoped_heading: list[str] = []
        self.scoped_heading_count = 0
        self.href: str | None = None
        self.anchor: list[str] = []
        self.bookmark = False
        self.void = {
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

    def inside(self, tag: str, css: str) -> bool:
        return any(name == tag and css in classes for name, classes in self.stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "article":
            if any(name == "article" for name, _ in self.stack):
                raise ValueError("TRU has nested publication articles")
            self.article_count += 1
            self.entry_headings = []
            self.bookmarks = []
        if tag not in self.void:
            self.stack.append((tag, classes))
        if (
            tag == "h1"
            and "entry-title" in classes
            and self.inside("article", "category-endorsements")
        ):
            self.scoped_heading_count += 1
        if (
            tag == "div"
            and "entry-content" in classes
            and self.inside("article", "category-endorsements")
        ):
            self.content_count += 1
        if tag == "img" and self.inside("div", "entry-content"):
            self.images.append(attributes.get("src") or "")
        if tag == "a":
            self.href = attributes.get("href")
            self.anchor = []
            self.bookmark = "bookmark" in (attributes.get("rel") or "").split() and self.inside(
                "h2", "entry-title"
            )
            if self.inside("nav", "paging-navigation") and (
                {"next", "page-numbers"} <= classes or self.inside("div", "nav-previous")
            ):
                self.next_links.add(self.href or "")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.anchor.append(data)
        if self.inside("article", "category-endorsements"):
            if self.inside("h2", "entry-title"):
                self.entry_headings.append(data)
            if self.inside("h1", "entry-title"):
                self.scoped_heading.append(data)
            if self.inside("div", "entry-content"):
                self.content.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.void:
            return
        if tag == "a":
            if self.bookmark:
                self.bookmarks.append((self.href or "", " ".join("".join(self.anchor).split())))
            self.href = None
            self.bookmark = False
        if tag == "article" and self.inside("article", "category-endorsements"):
            self.entries.append((" ".join("".join(self.entry_headings).split()), self.bookmarks))
        # Reject broken publication structure; HTML void elements never enter the stack.
        if not self.stack or self.stack[-1][0] != tag:
            raise ValueError("TRU publication has malformed element structure")
        self.stack.pop()

    def close(self) -> None:
        super().close()
        if self.stack:
            raise ValueError("TRU publication has unclosed elements")


class TruDiscoveryObligation(VerificationModel):
    """Learned current-general membership, never a successful check or approval."""

    schema_version: Literal["1.0"] = "1.0"
    source_id: Literal["transit-riders-union"] = "transit-riders-union"
    election_id: Literal["wa-2026-general"] = "wa-2026-general"
    checked_at: AwareDatetime
    articles: list[str] = Field(min_length=1, max_length=100)
    capture_id: str = Field(pattern=CAPTURE_ID_PATTERN)

    @model_validator(mode="after")
    def validate_articles(self) -> TruDiscoveryObligation:
        if self.checked_at.year != 2026 or len(set(self.articles)) != len(self.articles):
            raise ValueError("TRU obligations require unique current-election articles")
        for url in self.articles:
            validate_tru_article(url)
        return self


def read_tru_discovery_obligation(path: Path) -> TruDiscoveryObligation:
    record = read_json(path)
    obligation = TruDiscoveryObligation.model_validate(record)
    if path.stem != evidence_fingerprint(record):
        raise ValueError("TRU obligation identity contradicts its content")
    manifest = read_capture_manifest(
        path.parent.parent / "manifests" / f"{obligation.capture_id}.json"
    )
    if (
        not isinstance(manifest, (CapturedManifest, ObservedManifest))
        or manifest.source_id != obligation.source_id
        or manifest.capture_method != "static_html"
        or manifest.retrieved_at != obligation.checked_at
        or manifest.redistribution != "restricted"
        or manifest.canonical_url != manifest.requested_url
        or manifest.http_status != 200
        or not manifest.media_type
        or manifest.media_type.split(";", 1)[0] not in {"text/html", "application/xhtml+xml"}
    ):
        raise ValueError("TRU obligation lacks its original official archive capture")
    archive_number(manifest.requested_url)
    return obligation


def discover_tru_publication(
    root: Path,
    storage: Path,
    checked_at: datetime,
    *,
    retention: Literal["retain_original", "facts_only"] = "retain_original",
) -> bytes:
    """Observe complete archives/articles/image; extract only the designated reviewed article."""
    if checked_at.year != 2026:
        raise ValueError("TRU discovery is bound to the reviewed 2026 general election")
    collector = PublicationCollector(
        "transit-riders-union", "transitriders.org", root, storage, checked_at, retention=retention
    )
    known = {TRU_CURRENT, TRU_BOUNDARY}
    for path in root.glob("discovery/*.json"):
        record = read_json(path)
        if record["source_id"] == "transit-riders-union":
            known.update(DiscoveryAudit.model_validate(record).articles)
    for path in root.glob("discovery-obligations/*.json"):
        if read_json(path)["source_id"] == "transit-riders-union":
            known.update(read_tru_discovery_obligation(path).articles)
    listed: set[str] = set()
    indexes: dict[str, str] = {}
    url = TRU_HOME
    for _ in range(40):
        number = archive_number(url)
        parser = TruParser()
        raw, _ = collector.fetch(url, parser)
        if not parser.entries:
            raise ValueError("TRU archive has no identifiable endorsement posts")
        learned: set[str] = set()
        for title, links in parser.entries:
            if not title or len(links) != 1 or links[0][1] != title:
                raise ValueError("TRU archive post lacks one identifiable bookmark heading")
            if current_title(title):
                article_url = urljoin(url, links[0][0])
                validate_tru_article(article_url)
                learned.add(article_url)
            elif re.search(r"2026.*general.*endorse", title, re.I):
                raise ValueError("TRU current-general title requires review")
        if len(known | listed | learned) > 100:
            raise ValueError("TRU discovery exceeds its 100-article bound")
        newly_learned = sorted(learned - known - listed)
        if newly_learned:
            obligation = TruDiscoveryObligation(
                checked_at=checked_at, articles=newly_learned, capture_id=collector.captures[-1]
            ).model_dump(mode="json")
            write_immutable_record(
                root / "discovery-obligations" / f"{evidence_fingerprint(obligation)}.json",
                canonical_json_bytes(obligation),
            )
        listed.update(learned)
        indexes[url] = hashlib.sha256(raw).hexdigest()
        next_urls = {urljoin(url, item) for item in parser.next_links}
        if len(next_urls) > 1:
            raise ValueError("TRU archive has competing next-page identities")
        for next_url in next_urls:
            if archive_number(next_url) != number + 1:
                raise ValueError("TRU archive pagination must increase by one")
        if TRU_BOUNDARY in learned:
            break
        if len(next_urls) != 1:
            raise ValueError("TRU archive did not reach its reviewed September boundary")
        url = next_urls.pop()
    else:
        raise ValueError("TRU discovery reached its 40-page bound before the boundary")
    articles = sorted(known | listed)
    hashes: dict[str, str] = {}
    designated: bytes | None = None
    for url in articles:
        validate_tru_article(url)
        parser = TruParser()
        raw, _ = collector.fetch(url, parser)
        if (
            parser.article_count != 1
            or parser.scoped_heading_count != 1
            or not current_title("".join(parser.scoped_heading))
            or parser.content_count != 1
            or not "".join(parser.content).strip()
        ):
            raise ValueError(
                "TRU article requires one current-general publication and nonempty content"
            )
        hashes[url] = hashlib.sha256(raw).hexdigest()
        if url == TRU_CURRENT:
            if parser.images.count(TRU_IMAGE) != 1:
                raise ValueError(
                    "TRU designated publication no longer links its exact required image"
                )
            designated = raw
    # The exact linked asset consumes the same transport, custody and aggregate budgets.
    artifact = discovery.fetch_http(TRU_IMAGE)
    if (
        artifact.status != 200
        or artifact.canonical_url != TRU_IMAGE
        or artifact.media_type.split(";", 1)[0] != "image/jpeg"
    ):
        raise ValueError("TRU meaningful image changed identity or media type")
    collector.retain(TRU_IMAGE, artifact, "image")
    comparison = {
        "articles": hashes,
        "listed": sorted(listed),
        "indexes": indexes,
        "assets": {TRU_IMAGE: hashlib.sha256(artifact.content).hexdigest()},
    }
    if designated is None:
        raise ValueError("TRU designated extraction publication is missing")
    body = designated + f"<!--{evidence_fingerprint(comparison)}-->".encode()
    if len(body) > 25 * 1024 * 1024:
        raise ValueError("TRU derived comparison exceeds the 25 MiB artifact limit")
    audit = DiscoveryAudit(
        source_id="transit-riders-union",
        checked_at=checked_at,
        articles=articles,
        listed=sorted(listed),
        captures=collector.captures,
        assets=[TRU_IMAGE],
        comparison_sha256=hashlib.sha256(body).hexdigest(),
    ).model_dump(mode="json")
    write_immutable_record(
        root / "discovery" / f"{evidence_fingerprint(audit)}.json", canonical_json_bytes(audit)
    )
    return body


def validate_tru_audit(
    audit: DiscoveryAudit, manifests: dict[str, CapturedManifest | ObservedManifest]
) -> None:
    """Bind successful membership to real same-check originals and its derived comparison."""
    if (
        audit.checked_at.year != 2026
        or not {TRU_CURRENT, TRU_BOUNDARY} <= set(audit.articles)
        or len(set(audit.listed)) != len(audit.listed)
        or len(set(audit.captures)) != len(audit.captures)
    ):
        raise ValueError("TRU audit has contradictory current-election membership")
    originals: dict[str, CapturedManifest | ObservedManifest] = {}
    for identifier in audit.captures:
        manifest = manifests[identifier]
        if (
            manifest.source_id != audit.source_id
            or manifest.retrieved_at != audit.checked_at
            or manifest.canonical_url != manifest.requested_url
            or manifest.http_status != 200
            or manifest.requested_url in originals
        ):
            raise ValueError("TRU audit input contradicts its original source, time or identity")
        if manifest.requested_url == TRU_IMAGE:
            if (
                manifest.capture_method != "image"
                or not manifest.media_type
                or manifest.media_type.split(";", 1)[0] != "image/jpeg"
            ):
                raise ValueError("TRU audit lacks its original meaningful image")
        else:
            if (
                manifest.capture_method != "static_html"
                or not manifest.media_type
                or manifest.media_type.split(";", 1)[0]
                not in {"text/html", "application/xhtml+xml"}
            ):
                raise ValueError("TRU audit requires original HTML captures")
            if manifest.requested_url not in audit.articles:
                archive_number(manifest.requested_url)
        originals[manifest.requested_url] = manifest
    if not {TRU_HOME, TRU_IMAGE, *audit.articles} <= originals.keys():
        raise ValueError("TRU audit lacks complete original publication inputs")
    if not any(
        item.source_id == audit.source_id
        and item.retrieved_at <= audit.checked_at
        and item.capture_method == "manual_upload"
        and item.http_status is None
        and item.content_sha256 == audit.comparison_sha256
        for item in manifests.values()
    ):
        raise ValueError("TRU audit lacks its derived comparison provenance")
