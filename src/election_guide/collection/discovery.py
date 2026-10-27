"""Bounded official index traversal and original article custody."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urljoin, urlsplit

from pydantic import AwareDatetime, Field, model_validator

from election_guide.collection.http import HttpArtifact, fetch_http
from election_guide.collection.models import PublicationReviewRequired
from election_guide.collection.verification import SourcePolicy, VerificationModel
from election_guide.evidence.models import (
    CAPTURE_ID_PATTERN,
    SHA256_PATTERN,
    SOURCE_ID_PATTERN,
    CapturedManifest,
    CaptureRequest,
    ObservedManifest,
    evidence_fingerprint,
)
from election_guide.evidence.storage import (
    read_capture_manifest,
    record_capture,
    record_observation,
    write_immutable_record,
)
from election_guide.serialization import canonical_json_bytes, read_json

# Exact reviewed current article; retain membership after index rotation.
SGN_ARTICLES = ("https://www.sgn.org/story/171425/",)

UFCW_INDEX = "https://ufcw3000.org/endorsements"
UFCW_ARTICLES = (
    "https://ufcw3000.org/news/2026/10/15/ufcw-3000-executive-board-unanimously-rejects-i-638-and-i-001-endorses-no-hate-campaign",
    "https://ufcw3000.org/news/2026/10/15/ufcw-3000-executive-board-unanimously-rejects-i-645-endorses-no-vote",
)


def validate_ufcw_article(url: str) -> None:
    parsed = urlsplit(url)
    match = re.fullmatch(
        r"/news/([0-9]{4})/([0-9]{1,2})/([0-9]{1,2})/[a-z0-9]+(?:-[a-z0-9]+)*", parsed.path
    )
    if (
        parsed.scheme != "https"
        or parsed.netloc != "ufcw3000.org"
        or parsed.query
        or parsed.fragment
        or match is None
    ):
        raise ValueError("UFCW discovery requires a clean official dated article URL")
    date(*(int(part) for part in match.groups()))


class DiscoveryAudit(VerificationModel):
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    checked_at: AwareDatetime
    articles: list[str] = Field(min_length=1, max_length=100)
    listed: list[str] = Field(max_length=100)
    captures: list[str] = Field(min_length=1, max_length=140)
    comparison_sha256: str = Field(pattern=SHA256_PATTERN)
    assets: list[str] = Field(default_factory=list, max_length=1)

    @model_validator(mode="after")
    def validate_articles(self) -> DiscoveryAudit:
        if self.assets:
            from election_guide.collection.tru_discovery import TRU_IMAGE

            if self.source_id != "transit-riders-union" or self.assets != [TRU_IMAGE]:
                raise ValueError("only the exact reviewed TRU image is supported")
        if self.source_id == "transit-riders-union" and not self.assets:
            raise ValueError("TRU discovery requires its meaningful image")
        for url in [*self.articles, *self.listed]:
            parsed = urlsplit(url)
            if self.source_id == "ufcw-3000":
                validate_ufcw_article(url)
            elif self.source_id == "transit-riders-union":
                from election_guide.collection.tru_discovery import validate_tru_article

                validate_tru_article(url)
            elif (
                self.source_id != "seattle-gay-news"
                or parsed.scheme != "https"
                or parsed.netloc != "www.sgn.org"
                or not re.fullmatch(r"/story/[0-9]+/", parsed.path)
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("discovery audit requires clean official story identities")
        if self.source_id == "seattle-gay-news" and not self.listed:
            raise ValueError("SGN discovery requires listed articles")
        if len(set(self.articles)) != len(self.articles) or not set(self.listed) <= set(
            self.articles
        ):
            raise ValueError("discovery audit has contradictory article membership")
        return self


class SgnDiscoveryObligation(VerificationModel):
    """Validated story membership, independent of pagination or article success."""

    schema_version: Literal["1.0"] = "1.0"
    source_id: Literal["seattle-gay-news"] = "seattle-gay-news"
    checked_at: AwareDatetime
    articles: list[str] = Field(min_length=1, max_length=100)
    capture_id: str = Field(pattern=CAPTURE_ID_PATTERN)

    @model_validator(mode="after")
    def validate_articles(self) -> SgnDiscoveryObligation:
        for url in self.articles:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "www.sgn.org"
                or re.fullmatch(r"/story/[0-9]+/", parsed.path) is None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("SGN obligations require clean official story identities")
        if len(set(self.articles)) != len(self.articles):
            raise ValueError("SGN obligations require unique articles")
        return self


def read_sgn_discovery_obligation(path: Path) -> SgnDiscoveryObligation:
    record = read_json(path)
    obligation = SgnDiscoveryObligation.model_validate(record)
    if path.stem != evidence_fingerprint(record):
        raise ValueError("SGN obligation identity contradicts its content")
    manifest = read_capture_manifest(
        path.parent.parent / "manifests" / f"{obligation.capture_id}.json"
    )
    requested = urlsplit(manifest.requested_url)
    canonical = urlsplit(manifest.canonical_url or "")
    if (
        not isinstance(manifest, (CapturedManifest, ObservedManifest))
        or manifest.source_id != obligation.source_id
        or manifest.capture_method != "static_html"
        or manifest.retrieved_at != obligation.checked_at
        or manifest.redistribution != "restricted"
        or requested.scheme != "https"
        or requested.netloc != "www.sgn.org"
        or requested.path != "/ch/News/Seattle"
        or requested.fragment
        or (requested.query and re.fullmatch(r"start=[0-9]+", requested.query) is None)
        or canonical.scheme != "https"
        or canonical.netloc != "www.sgn.org"
        or not manifest.media_type
        or manifest.media_type.split(";", 1)[0] not in {"text/html", "application/xhtml+xml"}
    ):
        raise ValueError("SGN obligation lacks its official index observation")
    return obligation


class UfcwDiscoveryObligation(VerificationModel):
    """Validated landing-page membership, independent of collection success."""

    schema_version: Literal["1.0"] = "1.0"
    source_id: Literal["ufcw-3000"] = "ufcw-3000"
    checked_at: AwareDatetime
    articles: list[str] = Field(min_length=1, max_length=100)
    capture_id: str = Field(pattern=CAPTURE_ID_PATTERN)

    @model_validator(mode="after")
    def validate_articles(self) -> UfcwDiscoveryObligation:
        for url in self.articles:
            validate_ufcw_article(url)
            if int(urlsplit(url).path.split("/")[2]) != self.checked_at.year:
                raise ValueError("UFCW discovery obligations require current-year articles")
        if len(set(self.articles)) != len(self.articles):
            raise ValueError("UFCW discovery obligations require unique articles")
        return self


def read_ufcw_discovery_obligation(path: Path) -> UfcwDiscoveryObligation:
    record = read_json(path)
    obligation = UfcwDiscoveryObligation.model_validate(record)
    if path.stem != evidence_fingerprint(record):
        raise ValueError("UFCW discovery obligation identity contradicts its content")
    manifest = read_capture_manifest(
        path.parent.parent / "manifests" / f"{obligation.capture_id}.json"
    )
    if (
        not isinstance(manifest, (CapturedManifest, ObservedManifest))
        or manifest.source_id != obligation.source_id
        or manifest.requested_url != UFCW_INDEX
        or manifest.capture_method != "static_html"
        or manifest.retrieved_at != obligation.checked_at
        or manifest.redistribution != "restricted"
        or urlsplit(manifest.canonical_url).scheme != "https"
        or urlsplit(manifest.canonical_url).netloc != "ufcw3000.org"
    ):
        raise ValueError("UFCW discovery obligation lacks its original official landing capture")
    return obligation


class PublicationParser(HTMLParser):
    """Read actual links and the article heading, rather than executing a page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: set[str] = set()
        self.endorsement_links: set[str] = set()
        self.link_href: str | None = None
        self.link_text: list[str] = []
        self.heading: list[str] = []
        self.in_heading = False
        self.heading_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a":
            self.link_href = attributes.get("href")
            self.link_text = []
            if self.link_href:
                self.links.add(self.link_href)
        if tag == "h1" or (
            tag == "h2"
            and {"mb-3", "font-weight-bold"} <= set((attributes.get("class") or "").split())
        ):
            self.in_heading = True
            self.heading_count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            title = " ".join("".join(self.link_text).split())
            if self.link_href and title.casefold().startswith("sgn endorsements"):
                self.endorsement_links.add(self.link_href)
            self.link_href = None
            self.link_text = []
        if tag in {"h1", "h2"}:
            self.in_heading = False

    def handle_data(self, data: str) -> None:
        if self.link_href:
            self.link_text.append(data)
        if self.in_heading:
            self.heading.append(data)


class PublicationCollector:
    """Bounded HTML GETs with the original HTTP capture metadata and private bytes."""

    def __init__(
        self,
        source_id: str,
        host: str,
        root: Path,
        storage: Path,
        checked_at: datetime,
        *,
        retention: Literal["retain_original", "facts_only"] = "retain_original",
    ) -> None:
        if retention not in {"retain_original", "facts_only"}:
            raise ValueError("unknown publication retention mode")
        self.retention = retention
        self.source_id = source_id
        self.host = host
        self.root = root
        self.storage = storage
        self.checked_at = checked_at
        self.captures: list[str] = []
        self.total = 0

    def fetch(
        self, url: str, parser: PublicationParser | None = None
    ) -> tuple[bytes, PublicationParser]:
        if urlsplit(url).netloc != self.host or urlsplit(url).scheme != "https":
            raise ValueError("index link leaves the official HTTPS host")
        artifact = fetch_http(url)
        if (
            urlsplit(artifact.canonical_url).netloc != self.host
            or urlsplit(artifact.canonical_url).scheme != "https"
        ):
            raise ValueError("index response leaves the official host")
        if self.source_id == "transit-riders-union" and (
            artifact.canonical_url != url or artifact.status != 200
        ):
            raise ValueError(
                "TRU response changes the requested identity or complete-response status"
            )
        if self.source_id == "ufcw-3000" and url != UFCW_INDEX:
            validate_ufcw_article(artifact.canonical_url)
        if artifact.media_type.split(";", 1)[0] not in {"text/html", "application/xhtml+xml"}:
            raise PublicationReviewRequired("parse", "index or article is not HTML")
        if not artifact.content:
            raise PublicationReviewRequired(
                "incomplete_publication", "publication response is empty"
            )
        self.retain(url, artifact, "static_html")
        parser = parser or PublicationParser()
        try:
            parser.feed(artifact.content.decode("utf-8"))
            parser.close()
        except UnicodeError as error:
            raise PublicationReviewRequired(
                "parse", "publication text is not valid UTF-8"
            ) from error
        return artifact.content, parser

    def retain(
        self, url: str, artifact: HttpArtifact, method: Literal["static_html", "image"]
    ) -> None:
        """Retain one real bounded response; assets share the publication budgets."""
        if len(self.captures) >= 140:
            raise PublicationReviewRequired(
                "incomplete_publication", "publication discovery exceeds its combined capture bound"
            )
        self.total += len(artifact.content)
        if self.total > 64 * 1024 * 1024:
            raise PublicationReviewRequired(
                "incomplete_publication", "publication discovery exceeds its total byte bound"
            )
        path = self.storage.parent / "discovery-input.html"
        path.write_bytes(artifact.content)
        request = CaptureRequest(
            source_id=self.source_id,
            requested_url=url,
            canonical_url=artifact.canonical_url,
            title="Official endorsement discovery input",
            retrieved_at=self.checked_at,
            media_type=artifact.media_type,
            capture_method=method,
            http_status=artifact.status,
            redirect_chain=artifact.redirect_chain,
            redistribution="restricted",
            redistribution_note=(
                "Public observation; original response bytes are transient."
                if self.retention == "facts_only"
                else "Committed only as authenticated ciphertext."
            ),
        )
        manifest = read_capture_manifest(
            record_observation(request, path, self.root / "manifests")
            if self.retention == "facts_only"
            else record_capture(request, path, self.storage, self.root / "manifests")
        )
        self.captures.append(manifest.id)


def discover_publication(
    policy: SourcePolicy,
    root: Path,
    storage: Path,
    checked_at: datetime,
    *,
    retention: Literal["retain_original", "facts_only"] = "retain_original",
) -> bytes:
    """Revisit known articles and discover every newer article up to a reviewed boundary.

    A missing boundary, changed pagination, unknown heading, or inaccessible
    article fails the check. It cannot truncate discovery into a zero diff.
    """
    if not policy.index_url or not policy.article_pattern or not policy.index_boundary:
        raise ValueError("incomplete index policy")
    host = urlsplit(policy.index_url).netloc
    collector = PublicationCollector(
        policy.source_id, host, root, storage, checked_at, retention=retention
    )
    fetch = collector.fetch
    captures = collector.captures

    known: set[str] = set(SGN_ARTICLES)
    for path in root.glob("discovery/*.json"):
        record = read_json(path)
        if record["source_id"] == policy.source_id:
            known.update(DiscoveryAudit.model_validate(record).articles)
    for path in root.glob("discovery-obligations/*.json"):
        if read_json(path)["source_id"] == policy.source_id:
            known.update(read_sgn_discovery_obligation(path).articles)
    discovered: set[str] = set()
    index_hashes: dict[str, str] = {}
    visited: set[str] = set()
    url = policy.index_url
    for _ in range(40):
        if url in visited:
            raise PublicationReviewRequired(
                "incomplete_publication", "publication pagination loops"
            )
        visited.add(url)
        raw, page = fetch(url)
        index_hashes[url] = hashlib.sha256(raw).hexdigest()
        links = {urljoin(url, item) for item in page.links}
        articles = {
            item
            for item in links
            if re.search(policy.article_pattern, unquote(item), re.IGNORECASE)
        } | {urljoin(url, item) for item in page.endorsement_links}
        for article in sorted(articles):
            if urlsplit(article).netloc != host or urlsplit(article).scheme != "https":
                raise ValueError("article discovery leaves the official HTTPS host")
            identifier = re.search(r"/story/[0-9]+/", article)
            if identifier is None:
                raise PublicationReviewRequired(
                    "parse", "official article URL has no stable story identity"
                )
            canonical = f"https://{host}{identifier.group(0)}"
            if len(known | discovered | {canonical}) > 100:
                raise PublicationReviewRequired(
                    "incomplete_publication", "publication discovery exceeds its 100-article bound"
                )
            if canonical not in known | discovered:
                obligation = SgnDiscoveryObligation(
                    checked_at=checked_at, articles=[canonical], capture_id=captures[-1]
                ).model_dump(mode="json")
                write_immutable_record(
                    root / "discovery-obligations" / f"{evidence_fingerprint(obligation)}.json",
                    canonical_json_bytes(obligation),
                )
            discovered.add(canonical)
        if any(item.startswith(policy.index_boundary) for item in links):
            break
        next_pages = sorted(
            item
            for item in links
            if urlsplit(item).path == urlsplit(policy.index_url).path
            and "start=" in urlsplit(item).query
            and item not in visited
        )
        if len(next_pages) != 1:
            raise PublicationReviewRequired(
                "incomplete_publication",
                "publication boundary was not reached through unambiguous pagination",
            )
        url = next_pages[0]
    else:
        raise PublicationReviewRequired(
            "incomplete_publication",
            "publication discovery reached the 40-page bound before its boundary",
        )
    articles = sorted(known | discovered)
    if not articles or len(articles) > 100:
        raise PublicationReviewRequired(
            "incomplete_publication", "publication discovery requires one to 100 articles"
        )
    headings: list[str] = []
    article_hashes: dict[str, str] = {}
    for article in articles:
        raw, page = fetch(article)
        if page.heading_count != 1:
            raise PublicationReviewRequired(
                "parse", "endorsement article must have exactly one heading"
            )
        title = " ".join("".join(page.heading).split())
        if not title.casefold().startswith("sgn endorsements"):
            raise PublicationReviewRequired(
                "conflicting_evidence",
                "known endorsement article no longer has an endorsement heading",
            )
        headings.append(f"<p>{html.escape(title)}</p>")
        article_hashes[article] = hashlib.sha256(raw).hexdigest()
    # This derived comparison binds article/body and index fingerprints to
    # their independently identified HTTP observation metadata.
    comparison = {
        "articles": article_hashes,
        "listed": sorted(discovered),
        "indexes": index_hashes,
    }
    body = (
        "<html><body>"
        + "".join(headings)
        + f"<!--{evidence_fingerprint(comparison)}--></body></html>"
    ).encode()
    if len(body) > 25 * 1024 * 1024:
        raise PublicationReviewRequired(
            "incomplete_publication", "SGN derived comparison exceeds the 25 MiB artifact limit"
        )
    record = {
        "source_id": policy.source_id,
        "checked_at": checked_at.isoformat(),
        "articles": articles,
        "listed": sorted(discovered),
        "captures": captures,
        "comparison_sha256": hashlib.sha256(body).hexdigest(),
    }
    DiscoveryAudit.model_validate(record)
    write_immutable_record(
        root / "discovery" / f"{evidence_fingerprint(record)}.json", canonical_json_bytes(record)
    )
    return body


class UfcwParser(PublicationParser):
    """Recognize Squarespace article content and relevant landing-page links."""

    def __init__(self) -> None:
        super().__init__()
        self.article_depth = 0
        self.content_depth = 0
        self.content: list[str] = []
        self.relevant_links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        super().handle_starttag(tag, attrs)
        classes = set((dict(attrs).get("class") or "").split())
        if tag == "article":
            self.article_depth += 1
        # Layout/navigation h1 elements do not identify the publication.
        if tag == "h1" and (not self.article_depth or "entry-title" not in classes):
            self.heading_count -= 1
            self.in_heading = False
        if (
            tag == "div"
            and self.article_depth
            and (self.content_depth or "sqs-html-content" in classes)
        ):
            self.content_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.link_href:
            text = " ".join(self.link_text)
            if re.search(
                r"endorse|vote\s+no|reject.{0,100}\b(?:i[- ]?[0-9]|initiative)",
                unquote(self.link_href) + " " + text,
                re.I,
            ):
                self.relevant_links.add(self.link_href)
        super().handle_endtag(tag)
        if tag == "div" and self.content_depth:
            self.content_depth -= 1
        if tag == "article":
            self.article_depth -= 1

    def handle_data(self, data: str) -> None:
        super().handle_data(data)
        if self.content_depth:
            self.content.append(data)


def discover_ufcw_publication(
    root: Path,
    storage: Path,
    checked_at: datetime,
    *,
    retention: Literal["retain_original", "facts_only"] = "retain_original",
) -> bytes:
    """Capture the landing page and bounded current-cycle/previously known articles."""
    collector = PublicationCollector(
        "ufcw-3000", "ufcw3000.org", root, storage, checked_at, retention=retention
    )
    page = UfcwParser()
    raw, _ = collector.fetch(UFCW_INDEX, page)
    listed: set[str] = set()
    for link in page.relevant_links:
        url = urljoin(UFCW_INDEX, link)
        # Scan this finite index only; unrelated news and past-cycle links
        # do not open a historical crawl. Relevant invalid URLs fail closed.
        if not re.search(r"/news/" + str(checked_at.year) + r"/", unquote(url)):
            continue
        validate_ufcw_article(url)
        listed.add(url)
    known: set[str] = set(UFCW_ARTICLES)
    for path in root.glob("discovery/*.json"):
        record = read_json(path)
        if record["source_id"] == "ufcw-3000":
            audit = DiscoveryAudit.model_validate(record)
            known.update(audit.articles)
    for path in root.glob("discovery-obligations/*.json"):
        if read_json(path)["source_id"] == "ufcw-3000":
            known.update(read_ufcw_discovery_obligation(path).articles)
    articles = sorted(known | listed)
    if len(articles) > 100:
        raise PublicationReviewRequired(
            "incomplete_publication", "UFCW discovery exceeds its 100-article bound"
        )
    # Learning membership does not assert that any article was collected or
    # compared. Its index observation survives collection failure so a later
    # runner must retry these URLs after link rotation.
    newly_listed = sorted(listed - known)
    if newly_listed:
        obligation = UfcwDiscoveryObligation(
            checked_at=checked_at, articles=newly_listed, capture_id=collector.captures[0]
        ).model_dump(mode="json")
        write_immutable_record(
            root / "discovery-obligations" / f"{evidence_fingerprint(obligation)}.json",
            canonical_json_bytes(obligation),
        )
    hashes: dict[str, str] = {}
    for url in articles:
        validate_ufcw_article(url)
        article = UfcwParser()
        content, _ = collector.fetch(url, article)
        if (
            article.heading_count != 1
            or not "".join(article.heading).strip()
            or not "".join(article.content).strip()
        ):
            raise PublicationReviewRequired(
                "parse", "UFCW article requires one publication heading and nonempty body"
            )
        hashes[url] = hashlib.sha256(content).hexdigest()
    # Extract only the existing reviewed landing-page facts. The digest binds
    # every complete original article, including unrecognized/withdrawn wording.
    comparison = {
        "articles": hashes,
        "listed": sorted(listed),
        "indexes": {UFCW_INDEX: hashlib.sha256(raw).hexdigest()},
    }
    body = raw + f"<!--{evidence_fingerprint(comparison)}-->".encode()
    if len(body) > 25 * 1024 * 1024:
        raise PublicationReviewRequired(
            "incomplete_publication", "UFCW derived comparison exceeds the 25 MiB artifact limit"
        )
    record = {
        "source_id": "ufcw-3000",
        "checked_at": checked_at.isoformat(),
        "articles": articles,
        "listed": sorted(listed),
        "captures": collector.captures,
        "comparison_sha256": hashlib.sha256(body).hexdigest(),
    }
    DiscoveryAudit.model_validate(record)
    write_immutable_record(
        root / "discovery" / f"{evidence_fingerprint(record)}.json", canonical_json_bytes(record)
    )
    return body
