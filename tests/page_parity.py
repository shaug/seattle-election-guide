"""The audited pages, as the Node markup-parity tests consume them.

docs/FRONTEND.md § Rendering requires that a lit-html template rendered with
audited data produce the region the Jinja template rendered. The two renderers
run in different languages, so the audited side is committed as a fixture and
the Node tests diff against it, exactly as the lens engine's parity fixture is
committed for the client scorer.

Each fixture is the rendered page with two assets removed: the stylesheet, which
no markup comparison reads, and the bundled entry script, which a Node DOM must
not run. What remains is the server's markup and the payload element the client
renders from — the two halves the rule is about.

Issue #238 committed the Comparisons page here first (`compare_parity.py`, which
shares this module's stripping); issue #248 added the guide and the sources
editor when their lens regions moved to lit.

Regenerate with::

    uv run python -m tests.page_parity
"""

from __future__ import annotations

import re
from pathlib import Path

from election_guide.publication.models import PublicationRace, PublicationViewModel
from election_guide.rendering import context, read_rendering_configuration, render_html_document
from election_guide.rendering.documents import render_race_document, render_sources_document
from election_guide.rendering.shell import race_page_path
from tests.test_personalization import _bundle  # pyright: ignore[reportPrivateUsage]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "js" / "fixtures"
GUIDE_PAGE_PATH = FIXTURE_DIR / "guide-audited-page.html"
SOURCES_PAGE_PATH = FIXTURE_DIR / "sources-audited-page.html"
RACE_PAGE_PREFIX = "race-audited-page-"
RENDERING_CONFIG = PROJECT_ROOT / "config" / "rendering" / "guide.yaml"

# Fixed so the fixtures are a function of the committed dataset alone.
PUBLIC_SITE_URL = "https://seattleelections.guide"
PROJECT_URL = "https://github.com/shaug/seattle-election-guide"
ELECTION_ID = "wa-2026-primary"

# The addresses the fixtures' relative links resolve against, which are the
# pages the audited documents are published at. The Node harness resolves both
# sides against them, so a server's absolute path and a client's relative one
# compare as the link they are.
GUIDE_PAGE_URL = f"{PUBLIC_SITE_URL}/e/{ELECTION_ID}/"
SOURCES_PAGE_URL = f"{GUIDE_PAGE_URL}sources/"

_STYLE = re.compile(r"<style>.*?</style>", re.DOTALL)
_MODULE_SCRIPT = re.compile(r'<script type="module">.*?</script>', re.DOTALL)


def strip_for_parity(rendered: str) -> str:
    """Remove what a markup comparison must not read or run.

    The payload element is asserted rather than assumed: it is what the client
    renders from, so a fixture without one would make the whole comparison
    vacuous (docs/FRONTEND.md, The data contract).
    """
    stripped = _STYLE.sub("<style></style>", rendered)
    stripped = _MODULE_SCRIPT.sub("", stripped)
    if "data-client-payload" not in stripped:
        raise AssertionError(
            "the audited fixture lost its payload element; the client renders from it "
            "(docs/FRONTEND.md, The data contract)."
        )
    return stripped


def published_view_model() -> PublicationViewModel:
    """The published view model, with the lens policy as the release ships it."""
    return _bundle().view_model


def build_audited_guide_page() -> str:
    """Render the endorsements guide and strip what a markup comparison must not run."""
    return strip_for_parity(
        render_html_document(published_view_model(), read_rendering_configuration(RENDERING_CONFIG))
    )


def build_audited_sources_page() -> str:
    """Render the sources editor and strip what a markup comparison must not run."""
    return strip_for_parity(
        render_sources_document(published_view_model(), public_site_url=PUBLIC_SITE_URL)
    )


def build_audited_race_page(race_id: str) -> str:
    """Render one race page and strip what a markup comparison must not run."""
    return strip_for_parity(
        render_race_document(
            published_view_model(),
            race_id,
            public_site_url=PUBLIC_SITE_URL,
            project_url=PROJECT_URL,
        )
    )


def race_page_url(race_id: str) -> str:
    """The address one race fixture's relative links resolve against."""
    return f"{PUBLIC_SITE_URL}{race_page_path(ELECTION_ID, race_id)}"


def race_page_fixture_path(race_id: str) -> Path:
    return FIXTURE_DIR / f"{RACE_PAGE_PREFIX}{race_id}.html"


def race_rendering_features(
    race: PublicationRace,
    sources: dict[str, object],
) -> frozenset[str]:
    """Which branches of the race page's markup this race actually exercises.

    A race page is ~60KB stripped, so committing one per race would put two
    megabytes of fixture in the tree for a comparison that only needs each
    *shape* once. This names the shapes; `race_parity_fixture_ids` picks the
    fewest races that show all of them.

    Only reachable branches are listed. The published ballot carries no
    Insufficient grade, no absent share, no low fill, and no unverified cell, so
    those four are covered by the hand-built view models in
    `race-detail.test.mjs` instead — the same division the guide's own parity
    test makes for the Insufficient card foot.
    """
    published = {key: value for key, value in sources.items()}
    cells = context.tallying_source_cells(race, published)  # pyright: ignore[reportArgumentType]
    features = {
        "tie" if len(race.support_leader_candidate_ids) > 1 else "sole_leader",
    }
    if context.has_no_majority(race):
        features.add("no_majority")
    if any(cell.state == "multi_endorsement" for cell in cells):
        features.add("split")
    if any(cell.evidence_url is None for cell in cells):
        features.add("no_receipt")
    if len(context.candidate_endorsement_groups(race)) > 2:
        features.add("many_candidates")
    for group in ("no_endorsement", "unverified", "not_covered", "not_applicable"):
        if context.source_cell_group_count(race, published, group):  # pyright: ignore[reportArgumentType]
            features.add(f"group_{group}")
    return frozenset(features)


def race_parity_fixture_ids(view_model: PublicationViewModel) -> list[str]:
    """The fewest races whose pages show every reachable markup branch.

    A greedy cover over `race_rendering_features`, taking the race that adds the
    most uncovered shapes and breaking ties by race id, so the selection is a
    function of the committed dataset rather than someone's choice. New data that
    introduces a shape adds a fixture; data that retires one drops it, and
    `tests/test_rendering.py` fails until the committed files match.
    """
    sources = {source.id: source for source in view_model.sources}
    features = {
        race.id: race_rendering_features(race, sources)  # pyright: ignore[reportArgumentType]
        for section in view_model.sections
        for race in section.races
    }
    uncovered = set[str]().union(*features.values())
    chosen: list[str] = []
    while uncovered:
        race_id = min(
            features, key=lambda candidate: (-len(features[candidate] & uncovered), candidate)
        )
        uncovered -= features[race_id]
        chosen.append(race_id)
        del features[race_id]
    return sorted(chosen)


def write_audited_pages() -> list[Path]:
    """Write the committed fixtures."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    GUIDE_PAGE_PATH.write_text(build_audited_guide_page(), encoding="utf-8")
    SOURCES_PAGE_PATH.write_text(build_audited_sources_page(), encoding="utf-8")
    written = [GUIDE_PAGE_PATH, SOURCES_PAGE_PATH]
    for race_id in race_parity_fixture_ids(published_view_model()):
        path = race_page_fixture_path(race_id)
        path.write_text(build_audited_race_page(race_id), encoding="utf-8")
        written.append(path)
    # A shape that stops being reachable must take its fixture with it, or the
    # Node suite would keep diffing a page the renderer no longer produces.
    for stale in sorted(FIXTURE_DIR.glob(f"{RACE_PAGE_PREFIX}*.html")):
        if stale not in written:
            stale.unlink()
    return written


if __name__ == "__main__":
    for path in write_audited_pages():
        print(f"wrote {path}")
