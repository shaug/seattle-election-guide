"""Compare served election pages and require accompanying published Updates."""

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

from election_guide.hosting.models import DeploymentManifest, HostingModel
from election_guide.serialization import canonical_json_bytes, read_json

_VOID = frozenset(
    [
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
    ]
)
_BLOCK = frozenset(
    [
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "head",
        "header",
        "hr",
        "html",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    ]
)
UPDATES_SNAPSHOT = "updates-snapshot.json"


class ElectionUpdatesSnapshot(HostingModel):
    pages: dict[str, str]
    entries: list[tuple[str, str]]


class UpdatesSnapshot(HostingModel):
    schema_version: Literal["1.0"] = "1.0"
    canonical_origin: str
    elections: dict[str, ElectionUpdatesSnapshot]


def read_verified_deployment(site: Path) -> DeploymentManifest:
    """Check the complete artifact tree before using any of its page bytes."""
    site = site.resolve()
    manifest = DeploymentManifest.model_validate(read_json(site / "deployment-manifest.json"))
    actual = {
        p.relative_to(site).as_posix()
        for p in site.rglob("*")
        if p.is_file() and p.relative_to(site).as_posix() != "deployment-manifest.json"
    }
    if actual != set(manifest.assets):
        raise ValueError(f"deployment asset set differs from manifest: {site}")
    for name, digest in manifest.assets.items():
        path = site / name
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise ValueError(f"deployment asset is a symlink: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"deployment asset hash mismatch: {name}")
    for election in manifest.elections:
        if f"e/{election.election_id}/index.html" not in manifest.assets:
            raise ValueError(f"deployment lacks aggregate page: {election.election_id}")
    return manifest


class _PageContent(HTMLParser):
    """Keep markup, CSS and code; normalize only known build provenance."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict[str, str | None]]] = []
        self.tokens: list[Any] = []
        self.references: set[str] = set()

    def _inside(self, class_name: str) -> bool:
        return any(class_name in (attrs.get("class") or "").split() for _, attrs in self.stack)

    def handle_decl(self, decl: str) -> None:
        self.tokens.append(("declaration", decl))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        reference = (
            attributes.get("src")
            if tag == "script"
            else attributes.get("href")
            if tag == "link" and attributes.get("rel") == "stylesheet"
            else None
        )
        if reference:
            self.references.add(reference)
        if tag not in _VOID:
            self.stack.append((tag, dict(attrs)))
        if not self._inside("audit-site"):
            self.tokens.append(("start", tag, sorted(attrs)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self._inside("audit-site"):
            self.tokens.append(("end", tag))
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._inside("audit-site"):
            return
        if any(element in {"pre", "textarea"} for element, _ in self.stack):
            self.tokens.append(("literal-text", data))
            return
        tag, attrs = self.stack[-1] if self.stack else ("", {})
        if tag == "script" and "data-client-payload" in attrs:
            payload = json.loads(data)
            # This is an input identity, including observation-only refreshes.
            # Every actual client field remains compared, including panel hashes.
            payload.pop("data_version", None)
            self.tokens.append(("payload", payload))
            return
        if tag not in {"script", "style"}:
            # HTML collapses ASCII whitespace, but a word boundary at an inline
            # tag and a non-breaking space can both change the displayed text.
            data = re.sub(r"[ \t\r\n\f]+", " ", data)
            if self._inside("audit-data"):
                data = re.sub(r"\bData updated \d{4}-\d{2}-\d{2}\b", "Data updated BUILD", data)
                if re.fullmatch(r"[0-9a-f]{12}", data):
                    data = "DATA_VERSION"
        if data:
            self.tokens.append(("text", data))


def _block_boundary(token: Any) -> bool:
    return token[0] in {"start", "end"} and token[1] in _BLOCK


def _without_layout_whitespace(tokens: list[Any]) -> list[Any]:
    normalized: list[Any] = []
    for index, token in enumerate(tokens):
        if token[0] == "text":
            value = token[1]
            if index == 0 or _block_boundary(tokens[index - 1]):
                value = value.lstrip(" ")
            if index == len(tokens) - 1 or _block_boundary(tokens[index + 1]):
                value = value.rstrip(" ")
            if not value:
                continue
            token = ("text", value)
        normalized.append(token)
    return normalized


def _page_content(site: Path, name: str, manifest: DeploymentManifest) -> bytes:
    parser = _PageContent()
    parser.feed((site / name).read_text(encoding="utf-8"))
    parser.close()
    for reference in sorted(parser.references):
        url = urlsplit(urljoin(f"{manifest.canonical_origin}/{name}", reference))
        asset = url.path.lstrip("/")
        if (
            f"{url.scheme}://{url.netloc}" != manifest.canonical_origin
            or asset not in manifest.assets
        ):
            raise ValueError(f"unverifiable client asset on {name}: {reference}")
        parser.tokens.append(("client-asset", reference, manifest.assets[asset]))
    return canonical_json_bytes(_without_layout_whitespace(parser.tokens))


class _Entries(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: set[tuple[str, str]] = set()
        self.active = False
        self.field: str | None = None
        self.date = ""
        self.headline = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if tag == "article" and "corrections-entry" in classes:
            self.active = True
            self.date = self.headline = ""
        if self.active:
            if tag == "p" and "corrections-date" in classes:
                self.field = "date"
            elif tag == "strong":
                self.field = "headline"

    def handle_data(self, data: str) -> None:
        if self.field == "date":
            self.date += data
        elif self.field == "headline":
            self.headline += data

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "strong"}:
            self.field = None
        if tag == "article" and self.active:
            key = (" ".join(self.date.split()), " ".join(self.headline.split()))
            if not all(key) or key in self.entries:
                raise ValueError("published Updates contains an invalid or duplicate entry")
            self.entries.add(key)
            self.active = False


def _entries(site: Path, manifest: DeploymentManifest, election: str) -> set[tuple[str, str]]:
    name = f"e/{election}/updates/index.html"
    if name not in manifest.assets:
        return set()
    parser = _Entries()
    parser.feed((site / name).read_text(encoding="utf-8"))
    parser.close()
    if parser.active or not parser.entries:
        raise ValueError(f"published Updates has no complete entries: {name}")
    return parser.entries


def _pages(manifest: DeploymentManifest, election: str) -> set[str]:
    root = f"e/{election}/"
    return {
        name
        for name in manifest.assets
        if name == root + "index.html"
        or re.fullmatch(re.escape(root) + r"races/[^/]+/index\.html", name)
    }


def build_updates_snapshot(site: Path) -> UpdatesSnapshot:
    """Derive a durable content baseline from the verified pages that actually ship."""
    manifest = read_verified_deployment(site)
    return UpdatesSnapshot(
        canonical_origin=manifest.canonical_origin,
        elections={
            election.election_id: ElectionUpdatesSnapshot(
                pages={
                    name: hashlib.sha256(_page_content(site, name, manifest)).hexdigest()
                    for name in sorted(_pages(manifest, election.election_id))
                },
                entries=sorted(_entries(site, manifest, election.election_id)),
            )
            for election in manifest.elections
        },
    )


def verify_updates_snapshot(site: Path) -> None:
    """A hash-valid stale snapshot is still invalid evidence about the staged pages."""
    stored = UpdatesSnapshot.model_validate(read_json(site / UPDATES_SNAPSHOT))
    if stored != build_updates_snapshot(site):
        raise ValueError("Updates snapshot differs from staged election pages")


def compare_updates_snapshots(
    published: UpdatesSnapshot, proposed: UpdatesSnapshot
) -> dict[str, Any]:
    """Require a fresh served entry for each election whose page fingerprints changed."""
    if published.canonical_origin != proposed.canonical_origin:
        raise ValueError("baseline and candidate canonical origins differ")
    elections: dict[str, Any] = {}
    empty = ElectionUpdatesSnapshot(pages={}, entries=[])
    for election in sorted(published.elections.keys() | proposed.elections.keys()):
        old = published.elections.get(election, empty)
        new = proposed.elections.get(election, empty)
        changed = old.pages.keys() ^ new.pages.keys()
        changed.update(
            page
            for page in old.pages.keys() & new.pages.keys()
            if old.pages[page] != new.pages[page]
        )
        before, after = set(old.entries), set(new.entries)
        fresh = after - before
        # Rewriting a date/headline must not masquerade as an additional entry.
        retained = before <= after
        passed = not changed or (bool(fresh) and retained)
        elections[election] = {
            "result": "pass" if passed else "fail",
            "changed_pages": ["/" + page for page in sorted(changed)],
            "new_entries": [{"date": day, "headline": headline} for day, headline in sorted(fresh)],
            "previous_entry_identities_retained": retained,
            "updates_path": f"/e/{election}/updates/",
        }
    return {
        "schema_version": "1.0",
        "result": "pass" if all(e["result"] == "pass" for e in elections.values()) else "fail",
        "elections": elections,
    }


def check_updates(baseline: Path, candidate: Path) -> dict[str, Any]:
    """Offline comparison against a retained, verified successful production artifact."""
    try:
        published = build_updates_snapshot(baseline)
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot verify published baseline: {error}") from error
    report = compare_updates_snapshots(published, build_updates_snapshot(candidate))
    report["baseline_manifest_sha256"] = hashlib.sha256(
        (baseline / "deployment-manifest.json").read_bytes()
    ).hexdigest()
    report["candidate_manifest_sha256"] = hashlib.sha256(
        (candidate / "deployment-manifest.json").read_bytes()
    ).hexdigest()
    return report
