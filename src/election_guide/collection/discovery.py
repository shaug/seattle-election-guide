"""Bounded official index traversal and original article custody."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from pydantic import AwareDatetime, Field, model_validator

from election_guide.collection.http import fetch_http
from election_guide.collection.verification import SourcePolicy, VerificationModel
from election_guide.evidence.models import (
    SHA256_PATTERN,
    SOURCE_ID_PATTERN,
    CaptureRequest,
    evidence_fingerprint,
)
from election_guide.evidence.storage import (
    read_capture_manifest,
    record_capture,
    write_immutable_record,
)
from election_guide.serialization import canonical_json_bytes, read_json


class DiscoveryAudit(VerificationModel):
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    checked_at: AwareDatetime
    articles: list[str] = Field(min_length=1, max_length=100)
    listed: list[str] = Field(min_length=1, max_length=100)
    captures: list[str] = Field(min_length=1, max_length=140)
    comparison_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_articles(self) -> DiscoveryAudit:
        for url in [*self.articles, *self.listed]:
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "www.sgn.org"
                or not re.fullmatch(r"/story/[0-9]+/", parsed.path)
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("discovery audit requires clean official story identities")
        if len(set(self.articles)) != len(self.articles) or not set(self.listed) <= set(
            self.articles
        ):
            raise ValueError("discovery audit has contradictory article membership")
        return self


class PublicationParser(HTMLParser):
    """Read actual links and the article heading, rather than executing a page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: set[str] = set()
        self.heading: list[str] = []
        self.in_heading = False
        self.heading_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.links.add(str(attributes["href"]))
        if tag == "h1":
            self.in_heading = True
            self.heading_count += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self.in_heading = False

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.heading.append(data)


def discover_publication(
    policy: SourcePolicy,
    root: Path,
    storage: Path,
    checked_at: datetime,
) -> bytes:
    """Revisit known articles and discover every newer article up to a reviewed boundary.

    A missing boundary, changed pagination, unknown heading, or inaccessible
    article fails the check. It cannot truncate discovery into a zero diff.
    """
    if not policy.index_url or not policy.article_pattern or not policy.index_boundary:
        raise ValueError("incomplete index policy")
    host = urlsplit(policy.index_url).netloc
    captures: list[str] = []
    total = 0

    def fetch(url: str) -> tuple[bytes, PublicationParser]:
        nonlocal total
        if urlsplit(url).netloc != host or urlsplit(url).scheme != "https":
            raise ValueError("index link leaves the official HTTPS host")
        artifact = fetch_http(url)
        if (
            urlsplit(artifact.canonical_url).netloc != host
            or urlsplit(artifact.canonical_url).scheme != "https"
        ):
            raise ValueError("index response leaves the official host")
        if artifact.media_type.split(";", 1)[0] not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("index or article is not HTML")
        total += len(artifact.content)
        if total > 64 * 1024 * 1024:
            raise ValueError("publication discovery exceeds its total byte bound")
        path = storage.parent / "discovery-input.html"
        path.write_bytes(artifact.content)
        request = CaptureRequest(
            source_id=policy.source_id,
            requested_url=url,
            canonical_url=artifact.canonical_url,
            title="Official endorsement discovery input",
            retrieved_at=checked_at,
            media_type=artifact.media_type,
            capture_method="static_html",
            http_status=artifact.status,
            redirect_chain=artifact.redirect_chain,
            redistribution="restricted",
            redistribution_note="Committed only as authenticated ciphertext.",
        )
        manifest = read_capture_manifest(record_capture(request, path, storage, root / "manifests"))
        captures.append(manifest.id)
        parser = PublicationParser()
        parser.feed(artifact.content.decode("utf-8"))
        parser.close()
        return artifact.content, parser

    known: set[str] = set()
    for path in root.glob("discovery/*.json"):
        record = read_json(path)
        if record["source_id"] == policy.source_id:
            known.update(record["articles"])
    discovered: set[str] = set()
    visited: set[str] = set()
    url = policy.index_url
    for _ in range(40):
        if url in visited:
            raise ValueError("publication pagination loops")
        visited.add(url)
        _, page = fetch(url)
        links = {urljoin(url, item) for item in page.links}
        articles = {
            item
            for item in links
            if re.search(policy.article_pattern, unquote(item), re.IGNORECASE)
        }
        for article in articles:
            if urlsplit(article).netloc != host or urlsplit(article).scheme != "https":
                raise ValueError("article discovery leaves the official HTTPS host")
            identifier = re.search(r"/story/[0-9]+/", article)
            if identifier is None:
                raise ValueError("official article URL has no stable story identity")
            discovered.add(f"https://{host}{identifier.group(0)}")
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
            raise ValueError("publication boundary was not reached through unambiguous pagination")
        url = next_pages[0]
    else:
        raise ValueError("publication discovery reached the 40-page bound before its boundary")
    articles = sorted(known | discovered)
    if not articles or len(articles) > 100:
        raise ValueError("publication discovery requires one to 100 articles")
    headings: list[str] = []
    article_hashes: dict[str, str] = {}
    for article in articles:
        raw, page = fetch(article)
        if page.heading_count != 1:
            raise ValueError("endorsement article must have exactly one heading")
        title = " ".join("".join(page.heading).split())
        if not title.casefold().startswith("sgn endorsements"):
            raise ValueError("known endorsement article no longer has an endorsement heading")
        headings.append(f"<p>{html.escape(title)}</p>")
        article_hashes[article] = hashlib.sha256(raw).hexdigest()
    # This is an explicitly derived comparison artifact. Original HTTP bytes
    # and response metadata remain in the separate encrypted captures above.
    comparison = {"articles": article_hashes, "listed": sorted(discovered)}
    body = (
        "<html><body>"
        + "".join(headings)
        + f"<!--{evidence_fingerprint(comparison)}--></body></html>"
    ).encode()
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
