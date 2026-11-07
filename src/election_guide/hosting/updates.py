"""Compare served election pages and require accompanying published Updates."""

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urljoin, urlsplit

from pydantic import model_validator

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
_VERIFICATION_CLOCK = re.compile(
    r"([Ll]ast checked )(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r" (?:[1-9]|[12][0-9]|3[01]), (?:[1-9]|1[0-2]):[0-5][0-9]:[0-5][0-9]"
    r" [ap]\.m\. P[SD]T\b"
)


class ElectionUpdatesSnapshot(HostingModel):
    pages: dict[str, str]
    entries: list[tuple[str, str]]
    information_pages: dict[str, str] | None = None


class UpdatesSnapshot(HostingModel):
    schema_version: Literal["1.0", "2.0", "3.0", "4.0", "5.0"] = "5.0"
    canonical_origin: str
    elections: dict[str, ElectionUpdatesSnapshot]

    @model_validator(mode="after")
    def validate_information_policy(self) -> "UpdatesSnapshot":
        if self.schema_version != "1.0" and any(
            election.information_pages is None
            or election.information_pages.keys() != election.pages.keys()
            for election in self.elections.values()
        ):
            raise ValueError("Updates information policy requires every served page fingerprint")
        return self


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
            if tag == "link" and "stylesheet" in (attributes.get("rel") or "").lower().split()
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

    def _append_text(self, kind: str, data: str) -> None:
        if self.tokens and self.tokens[-1][0] == kind:
            self.tokens[-1] = (kind, self.tokens[-1][1] + data)
        else:
            self.tokens.append((kind, data))

    def handle_data(self, data: str) -> None:
        if self._inside("audit-site"):
            return
        if any(element in {"pre", "textarea"} for element, _ in self.stack):
            self._append_text("literal-text", data)
            return
        tag, attrs = self.stack[-1] if self.stack else ("", {})
        if tag == "script" and "data-client-payload" in attrs:
            payload = json.loads(data)
            # This is an input identity, including observation-only refreshes.
            # Every actual client field remains compared, including panel hashes.
            payload.pop("data_version", None)
            self.tokens.append(("payload", payload))
            return
        if tag in {"script", "style"}:
            self._append_text("literal-text", data)
        elif data:
            self._append_text("audit-data-text" if self._inside("audit-data") else "text", data)


def _block_boundary(token: Any) -> bool:
    return token[0] in {"start", "end"} and token[1] in _BLOCK


def _without_layout_whitespace(tokens: list[Any]) -> list[Any]:
    normalized: list[Any] = []
    for index, token in enumerate(tokens):
        if token[0] in {"text", "audit-data-text"}:
            # Comments can split a text node into callbacks. Collapse whitespace
            # only after joining those fragments, preserving visible boundaries.
            value = re.sub(r"[ \t\r\n\f]+", " ", token[1])
            if token[0] == "audit-data-text":
                value = re.sub(r"\bData updated \d{4}-\d{2}-\d{2}\b", "Data updated BUILD", value)
                if re.fullmatch(r"[0-9a-f]{12}", value):
                    value = "DATA_VERSION"
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


def _election_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep semantic inputs used to display endorsements, coverage and results.

    Page controls, query capabilities and URL limits are software contracts.
    Verification timestamps are provenance freshness, not new election facts.
    """
    keys = {
        "panel_id",
        "panel_hash",
        "sources",
        "categories",
        "scoring",
        "races",
        "race",
        "personalization",
    }
    freshness = {
        "data_version",
        "captured_at",
        "checked_at",
        "reviewed_at",
        "last_checked_at",
        "schema_version",
        "maximum_url_characters",
        "url_schema_version",
    }

    def factual(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: factual(item)
                for key, item in cast(dict[str, Any], value).items()
                if key not in freshness
            }
        if isinstance(value, list):
            return [factual(item) for item in cast(list[Any], value)]
        return value

    return factual({key: value for key, value in payload.items() if key in keys})


_RESULT_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
_RESULT_DAY = r"(?:[1-9]|[12][0-9]|3[01])"
_RESULT_CLOCK = (
    rf"{_RESULT_MONTH} {_RESULT_DAY}, (?:[1-9]|1[0-2]):[0-5][0-9]:[0-5][0-9] "
    r"(?:a|p)\.m\. (?:PST|PDT)"
)
_RESULT_DATE = rf"{_RESULT_MONTH} {_RESULT_DAY}, [0-9]{{4}}"


class _InformationContent(_PageContent):
    """Read actual election text/evidence and payload facts, independent of paint/code.

    Existing served pages already identify their data regions; no candidate-only
    marker can exempt a historical baseline. Complete assets are still verified.
    """

    def __init__(
        self,
        evidence_source_commit: str | None = None,
        *,
        verification_clocks: bool = True,
        result_clock_placement: bool = False,
    ) -> None:
        super().__init__()
        self.evidence_source_commit = evidence_source_commit
        self.verification_clocks = verification_clocks
        self.payload: list[str] | None = None
        self.result_clock_placement = result_clock_placement
        self.result_depth: int | None = None
        self.result_status: str | None = None
        self.result_clocks: list[tuple[str, str]] = []
        self.result_legacy_export = False
        self.result_notices: dict[int, str] = {}

    def _resolve_result_notices(self) -> None:
        if not self.result_notices:
            return
        omit = (
            self.result_legacy_export
            and self.result_status == "Unofficial"
            and len(self.result_clocks) == 1
            and self.result_clocks[0][0] == "export"
            and len(self.result_notices) == 1
        )
        start = max(0, min(self.result_notices) - 1)
        resolved: list[Any] = []
        for index, token in enumerate(self.tokens[start:], start=start):
            if index in self.result_notices:
                if omit:
                    continue
                token = ("text", self.result_notices[index])
            if resolved and token[0] == resolved[-1][0] == "text":
                resolved[-1] = ("text", resolved[-1][1] + token[1])
            else:
                resolved.append(token)
        self.tokens[start:] = resolved

    def _result_clock_text(self, data: str) -> str:
        """Keep exact clock facts independent of their approved badge/provenance position."""
        text = data.strip()
        if self._inside("race-results-status"):
            old = re.fullmatch(
                rf"(Unofficial|Certified) · (Export generated )?({_RESULT_CLOCK}|{_RESULT_DATE})",
                text,
            )
            if old is not None:
                status, export, clock = old.groups()
                kind = "certified" if status == "Certified" else "export" if export else "count"
                valid = _RESULT_DATE if kind == "certified" else _RESULT_CLOCK
                if re.fullmatch(valid, clock) and not (status == "Certified" and export):
                    self.result_status = status
                    self.result_clocks.append((kind, clock))
                    self.result_legacy_export = kind == "export"
                    return status
            elif text in {"Unofficial", "Certified"}:
                self.result_status = text
        elif self._inside("race-results-provenance"):
            if self.result_status == "Certified":
                certified = re.fullmatch(rf"Certified on ({_RESULT_DATE})", text)
                if certified is not None:
                    self.result_clocks.append(("certified", certified[1]))
                    return ""
            elif self.result_status == "Unofficial":
                if text == "Count timestamp not provided ·":
                    self.result_notices[len(self.tokens)] = data
                    self.tokens.append(("result-count-notice", data))
                    return ""
                if text.endswith(" ·"):
                    clocks = [
                        re.fullmatch(rf"(Count updated|Export generated) ({_RESULT_CLOCK})", part)
                        for part in text.removesuffix(" ·").split(" · ")
                    ]
                    if clocks and all(clocks):
                        for clock in clocks:
                            assert clock is not None
                            kind = "count" if clock[1] == "Count updated" else "export"
                            self.result_clocks.append((kind, clock[2]))
                        return ""
        return data

    def _information(self) -> bool:
        if any(
            tag in {"head", "script", "style", "footer", "nav", "button", "select", "option", "svg"}
            for tag, _ in self.stack
        ):
            return False
        if any(
            self._inside(name)
            for name in {
                "site-band",
                "sticky-header",
                "page-head",
                "audit-data",
                "audit-site",
                "filter-control-bar",
                "state-action-strip",
            }
        ):
            return False
        return (
            any(tag == "main" for tag, _ in self.stack)
            or self._inside("race-detail-certified-result")
            or self._inside("election-day")
        )

    def handle_decl(self, decl: str) -> None:
        pass

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag not in _VOID:
            self.stack.append((tag, attributes))
        if tag == "script" and "data-client-payload" in attributes:
            self.payload = []
        if not self._information():
            return
        if (
            self.result_clock_placement
            and self.result_depth is None
            and "race-results" in (attributes.get("class") or "").split()
        ):
            self.result_depth = len(self.stack)
            self.result_status = None
            self.result_clocks = []
            self.result_legacy_export = False
            self.result_notices = {}
        if tag in _BLOCK:
            self._append_text("text", " ")
        facts = {
            key: value
            for key, value in attrs
            if key
            in {
                "href",
                "data-publication-race-id",
                "data-contested",
                "data-race-detail-source-code",
                "data-source-state",
                "data-source-role",
                "data-source-group",
                "data-endorsed-candidate-id",
            }
            or key.startswith("data-election-")
        }
        href = facts.get("href")
        if (
            href is not None
            and self.evidence_source_commit is not None
            and self._inside("race-results")
        ):
            original = re.fullmatch(
                r"https://github\.com/shaug/seattle-election-guide/blob/"
                + re.escape(self.evidence_source_commit)
                + r"/data/evidence/official/sha256/([0-9a-f]{2})/([0-9a-f]{64})",
                href,
            )
            if original is not None and original[1] == original[2][:2]:
                facts["href"] = "sha256-official-original:" + original[2]
        if facts:
            self.tokens.append(("facts", facts))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.payload is not None:
            self.tokens.append(("payload", _election_payload(json.loads("".join(self.payload)))))
            self.payload = None
        if self._information() and tag in _BLOCK:
            self._append_text("text", " ")
        if self.result_depth == len(self.stack) and self.stack[-1][0] == tag:
            self._resolve_result_notices()
            if self.result_clocks:
                self.tokens.append(("result-clocks", sorted(self.result_clocks)))
            self.result_depth = None
            self.result_status = None
            self.result_clocks = []
            self.result_notices = {}
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.payload is not None:
            self.payload.append(data)
        elif self._information():
            literal = any(tag in {"pre", "textarea"} for tag, _ in self.stack)
            if self.result_depth is not None and not literal:
                data = self._result_clock_text(data)
            if (
                not self.verification_clocks
                and not literal
                and self._inside("race-results")
                and any(
                    tag == "span" and attrs.get("data-preliminary-recency")
                    for tag, attrs in self.stack
                )
            ):
                data = _VERIFICATION_CLOCK.sub(r"\1VERIFICATION_TIME", data)
            self._append_text(
                "literal-text" if literal else "text",
                data,
            )


def _information_content(
    site: Path,
    name: str,
    *,
    evidence_source_commit: str | None = None,
    verification_clocks: bool = True,
    result_clock_placement: bool = False,
) -> bytes:
    parser = _InformationContent(
        evidence_source_commit,
        verification_clocks=verification_clocks,
        result_clock_placement=result_clock_placement,
    )
    parser.feed((site / name).read_text(encoding="utf-8"))
    parser.close()
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
            if tag in {"p", "time"} and "corrections-date" in classes:
                self.field = "date"
            elif tag == "strong" or "corrections-headline" in classes:
                self.field = "headline"

    def handle_data(self, data: str) -> None:
        if self.field == "date":
            self.date += data
        elif self.field == "headline":
            self.headline += data

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "time", "strong", "h2"}:
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


def build_updates_snapshot(
    site: Path, *, schema_version: Literal["1.0", "2.0", "3.0", "4.0", "5.0"] = "5.0"
) -> UpdatesSnapshot:
    """Derive a durable content baseline from the verified pages that actually ship."""
    manifest = read_verified_deployment(site)
    return UpdatesSnapshot(
        schema_version=schema_version,
        canonical_origin=manifest.canonical_origin,
        elections={
            election.election_id: ElectionUpdatesSnapshot(
                pages={
                    name: hashlib.sha256(_page_content(site, name, manifest)).hexdigest()
                    for name in sorted(_pages(manifest, election.election_id))
                },
                entries=sorted(_entries(site, manifest, election.election_id)),
                information_pages=(
                    None
                    if schema_version == "1.0"
                    else {
                        name: hashlib.sha256(
                            _information_content(
                                site,
                                name,
                                evidence_source_commit=election.git_commit
                                if schema_version in {"3.0", "4.0", "5.0"}
                                else None,
                                verification_clocks=schema_version not in {"4.0", "5.0"},
                                result_clock_placement=schema_version == "5.0",
                            )
                        ).hexdigest()
                        for name in sorted(_pages(manifest, election.election_id))
                    }
                ),
            )
            for election in manifest.elections
        },
    )


def verify_updates_snapshot(site: Path) -> None:
    """A hash-valid stale snapshot is still invalid evidence about the staged pages."""
    stored = UpdatesSnapshot.model_validate(read_json(site / UPDATES_SNAPSHOT))
    rebuilt = build_updates_snapshot(site, schema_version=stored.schema_version)
    if stored != rebuilt:
        raise ValueError("Updates snapshot differs from staged election pages")


def compare_updates_snapshots(
    published: UpdatesSnapshot, proposed: UpdatesSnapshot
) -> dict[str, Any]:
    """Require a fresh served entry for each election whose page fingerprints changed."""
    if published.schema_version != "5.0" or proposed.schema_version != "5.0":
        raise ValueError(
            "Updates snapshot policy differs; verify original baseline pages before upgrading"
        )
    if published.canonical_origin != proposed.canonical_origin:
        raise ValueError("baseline and candidate canonical origins differ")
    elections: dict[str, Any] = {}
    empty = ElectionUpdatesSnapshot(pages={}, entries=[], information_pages={})
    for election in sorted(published.elections.keys() | proposed.elections.keys()):
        old = published.elections.get(election, empty)
        new = proposed.elections.get(election, empty)
        old_pages, new_pages = old.information_pages, new.information_pages
        if old_pages is None or new_pages is None:
            raise ValueError("Updates information policy has no verified page fingerprints")
        changed = old_pages.keys() ^ new_pages.keys()
        changed.update(
            page
            for page in old_pages.keys() & new_pages.keys()
            if old_pages[page] != new_pages[page]
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
