from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from html import escape, unescape
from pathlib import Path
from stat import S_IMODE
from typing import Any, cast
from urllib.parse import urlencode

import pytest
from PIL import Image
from pydantic import ValidationError
from websocket import create_connection  # pyright: ignore[reportUnknownVariableType]

from election_guide.publication import build_publication_bundle
from election_guide.publication.builder import (
    reprojected_comparisons,
    reprojected_personalization,
)
from election_guide.publication.models import (
    PublicationComparison,
    PublicationRace,
    PublicationViewModel,
    SourceCell,
)
from election_guide.publication.personalization import (
    PersonalizationCategory,
    PersonalizationSource,
)
from election_guide.rendering import (
    build_rendered_guide,
    read_rendering_configuration,
    render_html_document,
    validate_rendered_guide,
)
from election_guide.rendering.browser import (
    _CdpSocket,  # pyright: ignore[reportPrivateUsage]
    _terminate_process,  # pyright: ignore[reportPrivateUsage]
    _wait_for_devtools_endpoint,  # pyright: ignore[reportPrivateUsage]
    find_chrome,
    render_screenshot,
)
from election_guide.rendering.bundler import TEMPLATE_DIR, bundle_entry
from election_guide.rendering.context import (
    candidate_endorsement_groups,
    has_no_majority,
    race_detail_accessible_summary,
    race_detail_support_summary,
    screen_support_summary,
    screen_support_summary_compact,
    source_cell_detail_label,
    source_cell_group,
)
from election_guide.rendering.documents import render_sources_document, template_environment
from election_guide.rendering.models import RenderingValidationReport
from election_guide.rendering.payload import CLIENT_PAYLOAD_SCHEMA_VERSION, GuidePayload
from election_guide.rendering.shell import (
    HOW_TO_VOTE_HREF,
    election_day_banner_html,
    election_names,
)
from election_guide.scoring import score_dataset
from election_guide.serialization import canonical_json_bytes, read_json, read_yaml
from election_guide.sources.registry import read_source_registry
from tests.page_parity import (
    GUIDE_PAGE_PATH,
    SOURCES_PAGE_PATH,
    build_audited_guide_page,
    build_audited_sources_page,
)
from tests.test_personalization import (
    _bundle as _production_bundle,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_publication import (
    _publication_dataset,  # pyright: ignore[reportPrivateUsage]
    _snapshot_store,  # pyright: ignore[reportPrivateUsage]
)
from tests.test_scoring import (
    NOW,
    _configuration,  # pyright: ignore[reportPrivateUsage]
)

PROJECT_ROOT = Path(__file__).parent.parent
RENDERING_CONFIG = PROJECT_ROOT / "config/rendering/guide.yaml"
# The one payload element every page publishes (docs/FRONTEND.md, The data
# contract). The whole opening tag, so the selector inside the inlined bundle
# is not mistaken for a second element.
PAYLOAD_ELEMENT = '<script type="application/json" data-client-payload>'
DARWIN_VISUAL_BASELINES = {
    "desktop": [
        0.382,
        0.593,
        0.613,
        0.422,
        0.149,
        0.190,
        0.184,
        0.129,
        0.071,
        0.065,
        0.068,
        0.069,
        0.078,
        0.106,
        0.097,
        0.089,
    ],
    # UI polish round 5.1 (issue 177): the hero deck is gone and the source
    # strip is always present, shifting the narrow layout while preserving its
    # overall visual density.
    "mobile": [
        0.503,
        0.495,
        0.507,
        0.537,
        0.346,
        0.356,
        0.133,
        0.135,
        0.128,
        0.170,
        0.118,
        0.067,
        0.098,
        0.115,
        0.084,
        0.039,
    ],
}
LINUX_VISUAL_BASELINES = {
    "desktop": [
        0.390,
        0.603,
        0.613,
        0.422,
        0.152,
        0.178,
        0.180,
        0.129,
        0.071,
        0.059,
        0.058,
        0.071,
        0.068,
        0.067,
        0.069,
        0.071,
    ],
    # UI polish round 5.1 (issue 177): values carry the same per-index delta
    # measured on a real macOS run of this fixture (there is no equivalent
    # real Linux measurement available in this environment); if CI reports
    # different exact values, replace these with its own.
    "mobile": [
        0.515,
        0.512,
        0.525,
        0.540,
        0.340,
        0.339,
        0.132,
        0.141,
        0.106,
        0.128,
        0.116,
        0.077,
        0.076,
        0.056,
        0.067,
        0.052,
    ],
}
APPROVED_VISUAL_BASELINES_BY_PLATFORM = {
    "darwin": DARWIN_VISUAL_BASELINES,
    "linux": LINUX_VISUAL_BASELINES,
}


def test_canonical_names_use_structured_future_election_data() -> None:
    seed = cast(
        dict[str, Any],
        read_yaml(PROJECT_ROOT / "tests/fixtures/initialization/wa-2027-seattle-general.yaml"),
    )
    election = cast(dict[str, Any], seed["election"])
    assert election["name"] == "Fixture 2027 Seattle Municipal General Election"
    assert election_names(
        str(election["election_date"]),
        cast(str, election["election_type"]),
        cast(str, election["state"]),
    ) == ("November 2027 General", "November 2, 2027 Washington general")
    assert election_names(
        str(election["election_date"]),
        None,
        None,
        legacy_name=cast(str, election["name"]),
        election_id=cast(str, election["id"]),
    ) == ("November 2027 General", "November 2, 2027 Washington general")


def _render_shell(source: str, **context: object) -> str:
    """Render a snippet against the real template environment.

    Issue 241 moved the shell grammar from Python builders in `shell.py` into
    `_shell.html.j2`'s macros, so these tests drive it the way a page does —
    through the same environment, with the same globals and autoescaping.
    """
    return template_environment().from_string(source).render(**context)


def _page_head(title: str, tagline: str = "A tagline.", **options: object) -> str:
    return _render_shell(
        "{% call shell.page_head(title, eyebrow=eyebrow, mode=mode) %}" + tagline + "{% endcall %}",
        title=title,
        eyebrow=options.get("eyebrow"),
        mode=options.get("mode", "plain"),
    )


def test_page_head_names_the_page_and_puts_the_election_in_the_eyebrow() -> None:
    """Issue 192: one head for every page. The h1 is the page's own name and
    the eyebrow is the election, so the two read as one name and the strongest
    identity on screen keeps its size and position across page types."""
    head = _page_head("Comparisons", "Put any sources side by side.", eyebrow="August 2026 Primary")

    assert '<p class="page-eyebrow">August 2026 Primary</p>' in head
    assert "<h1>Comparisons</h1>" in head
    assert '<header class="page-head">' in head


def test_page_head_omits_the_eyebrow_on_election_agnostic_pages() -> None:
    """Presence follows the page's kind: the absence of an eyebrow is the only
    marker an agnostic page needs, so no extra mechanism is spent on it."""
    head = _page_head("How this works", "How this guide works.")

    assert "page-eyebrow" not in head
    assert "<h1>How this works</h1>" in head


def test_extended_page_head_is_the_one_exception_primacy_buys() -> None:
    """The dial (R3): the masthead's navy runs through the head on the page the
    brand lockup links to. It bends no other rule — the eyebrow's mint-on-navy
    and the title's white are the ground-relative colors already prescribed."""
    extended = _page_head(
        "Endorsements", "Distilled.", eyebrow="August 2026 Primary", mode="extended"
    )
    plain = _page_head("Sources", "Choose.", eyebrow="August 2026 Primary")

    assert '<header class="page-head extended">' in extended
    assert '<header class="page-head">' in plain


def test_page_head_takes_its_pages_reading_measure_when_it_has_one() -> None:
    """A head above a book-measure column sits on that column, so its tagline
    never outruns the prose beneath it."""
    measured = _page_head("Guide archive", "Every guide stays up.", mode="measured")

    assert '<header class="page-head narrow">' in measured
    assert '<div class="narrow-main">' in measured


def test_page_head_escapes_its_names_and_anything_interpolated_into_its_tagline() -> None:
    """The head's escaping asymmetry, restated for the Jinja shell (issue 241).

    It used to be a naming convention: `tagline_html` was not escaped and its
    caller owned the escape, which is why `_about_html` had to pass
    `html.escape(...)`. The tagline is now the caller's `{% call %}` block, so
    the asymmetry is structural rather than advisory — markup authored in a
    template is markup, and a *value* interpolated into it is escaped like any
    other. Issue 192 review finding cor-1 asked that this be explicit, not that
    it be removed: taglines still carry entities in the guide's copy and real
    links on the 404.
    """
    head = _render_shell(
        "{% call shell.page_head(title, eyebrow=eyebrow) %}"
        'Read <a href="/e/">the archive</a>. {{ untrusted }}'
        "{% endcall %}",
        title="Sources <script>",
        eyebrow="A & B",
        untrusted='<script>alert("x")</script>',
    )

    assert "<h1>Sources &lt;script&gt;</h1>" in head
    assert "A &amp; B" in head
    # Authored markup reaches the page as markup...
    assert 'Read <a href="/e/">the archive</a>.' in head
    # ...and an interpolated value does not.
    assert "<script>alert" not in head
    assert "&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt;" in head


def test_election_day_banner_states_a_truth_that_survives_the_election() -> None:
    """Every guide is a frozen file that cannot know today's date, so the server
    writes a tense-neutral statement — true before and after the election — and
    the script escalates or rewrites it. A reader without JavaScript is never
    told something false, whichever era they arrive in."""
    banner = election_day_banner_html("2026-08-04")

    assert 'data-election-day="2026-08-04"' in banner
    assert "<b>Election day:</b> Tuesday, August 4, 2026" in banner
    # No verb tense to go stale, and the date in both the long and short forms
    # the script needs so it never has to reformat a date itself.
    assert "Election day is" not in banner
    assert 'data-election-day-short="Tuesday, August 4"' in banner
    assert HOW_TO_VOTE_HREF in banner


def test_shared_site_band_names_the_methodology_path_for_what_it_does() -> None:
    band = _render_shell(
        "{{ shell.band(guide_href='/e/wa-2026-primary/',"
        " sources_href='/e/wa-2026-primary/sources/',"
        " about_href='/about/', current='about') }}"
    )

    assert ">How this works</a>" in band
    assert ">About</a>" not in band
    assert 'href="/about/" aria-current="page"' in band


def test_shared_site_band_orders_nav_by_dependency() -> None:
    """Reading order follows what each page depends on: the guide is the
    destination, Sources is what feeds it, Comparisons is a view derived from
    those sources, and How this works explains all three.

    This reverses the order issue 197 shipped, which put Comparisons second.
    """
    band = _render_shell(
        "{{ shell.band(guide_href='/e/wa-2026-primary/',"
        " sources_href='/e/wa-2026-primary/sources/',"
        " compare_href='/e/wa-2026-primary/comparisons/') }}"
    )

    assert band.index(">Endorsements</a>") < band.index(">Sources</a>")
    assert band.index(">Sources</a>") < band.index(">Comparisons</a>")
    assert band.index(">Comparisons</a>") < band.index(">How this works</a>")


def test_html_uses_one_view_model_for_screen_print_filters_and_evidence(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path)
    gap_source = next(source for source in view_model.sources if source.endorsement_count == 0)
    gap_source.contribution_status = "coverage_gap"
    gap_source.coverage_gap_status = "not_found"
    gap_source.coverage_gap_note = "The official site did not publish endorsement results."
    view_model.metadata.contributing_source_count -= 1
    view_model.metadata.coverage_gap_count += 1
    view_model = _revalidated(view_model)
    configuration = read_rendering_configuration(RENDERING_CONFIG)

    html = render_html_document(view_model, configuration)

    # Against the rendered markup, not the whole document: since issue #248 the
    # client carries its own copy of this wording, and the renderer inlines the
    # bundle into the page, so a whole-document search would be satisfied by
    # guide-lens.mjs and would stop constraining this template. The personalized
    # wording is no longer server markup at all — the lens-only twin that used
    # to carry it is retired — and is asserted client-side instead, in
    # `tests/js/guide-lens.test.mjs`.
    body = html.split("</style>", 1)[1].split('<script type="module">', 1)[0]
    assert "Too few endorsements to measure agreement." in body
    assert "Too few endorsements to measure agreement among your selected sources." not in body
    assert "Too few explicit endorsements" not in html

    # Issue 108 acceptance: a coverage-gap source has zero endorsements and was
    # never selectable on the sources page's own tree, so the guide's lens
    # bindings (which drive its "Viewing N of M sources" total) must exclude
    # it too, exactly like the sources page's own contribution_status filter.
    gap_code = next(
        source.code for source in view_model.personalization.sources if source.id == gap_source.id
    )
    bindings = _client_payload(html)
    assert gap_code not in {source["code"] for source in bindings["sources"]}

    races = [race for section in view_model.sections for race in section.races]
    source_by_id = {source.id: source for source in view_model.sources}
    source_code_by_id = {source.id: source.code for source in view_model.personalization.sources}
    category_label_by_key = {
        category.category: category.label for category in view_model.methodology.source_categories
    }
    assert html.count('data-publication-race-id="') == len(races)
    assert all(f'data-publication-race-id="{race.id}"' in html for race in races)
    assert "@media print" in html
    assert "@media (max-width: 720px)" in html
    assert 'id="race-filter"' in html
    assert 'input type="radio" name="ballot-view" value="full" checked><span>Full</span>' in html
    assert 'input type="radio" name="ballot-view" value="compact"><span>Compact</span>' in html
    assert (
        'input type="radio" name="race-set" value="complete" id="complete-filter" checked'
        "><span>All</span>" in html
    )
    assert (
        'input type="radio" name="race-set" value="contested" id="contested-filter"'
        "><span>Contested</span>" in html
    )
    assert "contested-control" not in html
    assert html.count('data-contested="') == len(races)
    assert "Full race detail" not in html
    assert 'aria-labelledby="race-label-' in html
    assert html.count('<a class="race-card-primary"') == len(races)
    assert html.count('aria-label="View endorsements for ') == len(races)
    assert '<option value="Legislative District 43">Legislative District 43</option>' in html
    # The filter behavior ships in the bundled guide-filters.mjs now rather than
    # in an inline script (issue #239); the shipped page must still carry it.
    assert "card.dataset.filterTokens" in html
    assert 'card.dataset.contested === "true"' in html
    assert "matchesScope && matchesContest" in html
    assert 'query.set("view", "compact")' in html
    assert '<label class="filter-control-label" for="race-filter">Ballot</label>' in html
    assert "Show races" not in html
    assert 'query.set("races", "contested")' in html
    assert 'query.set("filter", state.scope)' in html
    assert "syncFromUrl();" in html
    assert "html.compact-ballot-mode .race-grid { grid-template-columns: repeat(4" in html
    # Phones keep two compact columns so Compact stays visibly denser than
    # Full on mobile (issue 115, item F23).
    assert (
        "html.compact-ballot-mode .race-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }"
        in html
    )
    assert "> View endorsements" not in html
    assert html.count('<dialog class="race-detail-dialog"') == len(races)
    assert html.count("August 2026 Primary · Endorsements") == len(races)
    assert html.count('data-copy-race-link="') == len(races)
    assert html.count('title="Share this race"') == len(races)
    assert html.count('title="Close"') == len(races)
    assert ">Share link</button>" not in html
    assert ">Close</button>" not in html
    assert "Source details" not in html
    assert "Open source evidence" not in html
    assert "Race source audit" not in html
    for race in races:
        assert f'id="race-{race.id}"' in html
        assert html.count(f'href="#race-{race.id}" data-race-detail-link') == 1
        trigger_start = html.index(f'<a class="race-card-primary" href="#race-{race.id}"')
        trigger_end = html.index("</a>", trigger_start)
        trigger_html = html[trigger_start:trigger_end]
        assert f'id="race-label-{race.id}"' in trigger_html
        contested_value = "true" if race.is_contested else "false"
        assert f'data-contested="{contested_value}"' in html[trigger_start - 300 : trigger_start]
        assert 'data-display-role="recommendation"' in trigger_html
        assert 'data-display-role="share"' in trigger_html
        assert 'data-display-role="support"' in trigger_html
        dialog_start = html.index(f'id="race-detail-{race.id}"')
        assert trigger_end < dialog_start
        # Issue 124: the per-race Times comparison is gone from the card
        # entirely. Only the lens's own "All sources" reference bar remains
        # at the card foot.
        card_foot_html = html[trigger_end:dialog_start]
        assert 'data-display-role="comparison"' not in card_foot_html
        assert "screen-comparisons" not in card_foot_html
        assert "data-comparison-lens" not in card_foot_html
        dialog_end = html.index("</dialog>", dialog_start)
        dialog_html = html[dialog_start:dialog_end]
        assert (
            f'aria-labelledby="race-detail-election-{race.id} race-detail-title-{race.id}"'
            in dialog_html
        )
        assert f'id="race-detail-election-{race.id}"' in dialog_html
        assert "race-detail-overview" not in dialog_html
        assert "race-detail-category-groups" not in dialog_html
        assert "data-race-detail-category=" not in dialog_html
        assert f'id="copy-race-status-{race.id}"' in dialog_html
        assert 'role="status"' in dialog_html
        assert 'aria-live="polite" data-copy-race-status' in dialog_html
        assert f'aria-describedby="copy-race-status-{race.id}"' in dialog_html
        assert race.recommendation_label in dialog_html
        assert race_detail_accessible_summary(race) in dialog_html
        assert race_detail_support_summary(race) in dialog_html
        endorsement_groups = candidate_endorsement_groups(race)
        candidate_positions = [
            dialog_html.index(f'data-race-detail-candidate-id="{group.candidate_id}"')
            for group in endorsement_groups
        ]
        assert candidate_positions == sorted(candidate_positions)
        source_counts = [group.source_count for group in endorsement_groups]
        assert source_counts == sorted(source_counts, reverse=True)
        for group in endorsement_groups:
            assert group.candidate_label in dialog_html
            assert (
                dialog_html.count(f'data-endorsed-candidate-id="{group.candidate_id}"')
                == group.source_count
            )

        def _cell_row_count(cell: SourceCell, race: PublicationRace = race) -> int:
            if source_cell_group(cell, race, source_by_id[cell.source_id]) == "candidate":
                return len(cell.candidate_ids)
            return 1

        # Issue 124: a comparison source contributes no row, no badge, and no
        # candidate section to the guide's race detail.
        tallying_cells = [
            cell
            for cell in race.source_cells
            if source_by_id[cell.source_id].panel_role != "comparison"
        ]
        expected_row_count = sum(_cell_row_count(cell) for cell in tallying_cells)
        assert dialog_html.count('data-race-detail-source-code="') == expected_row_count
        assert dialog_html.count('data-source-group="') == expected_row_count
        assert dialog_html.count('class="race-detail-category-badge') == expected_row_count
        assert "race-detail-comparison-badge" not in dialog_html
        expected_co_endorsement_rows = sum(
            len(cell.candidate_ids) for cell in tallying_cells if cell.state == "multi_endorsement"
        )
        assert dialog_html.count(">Co-endorsed</span>") == expected_co_endorsement_rows
        for state in ("not_covered", "not_applicable"):
            missing_count = sum(
                source_cell_group(cell, race, source_by_id[cell.source_id]) == state
                for cell in tallying_cells
            )
            if not missing_count:
                continue
            noun = "source" if missing_count == 1 else "sources"
            if state == "not_covered":
                summary = f"{missing_count} {noun} did not cover this race"
            else:
                verb = "was" if missing_count == 1 else "were"
                summary = f"{missing_count} {noun} {verb} outside this district"
            assert summary in dialog_html
        for cell in race.source_cells:
            group = source_cell_group(cell, race, source_by_id[cell.source_id])
            source = source_by_id[cell.source_id]
            code = source_code_by_id[cell.source_id]
            if source.panel_role == "comparison":
                assert f'data-race-detail-source-code="{code}"' not in dialog_html
                continue
            expected_occurrences = len(cell.candidate_ids) if group == "candidate" else 1
            assert (
                dialog_html.count(f'data-race-detail-source-code="{code}"') == expected_occurrences
            )
            assert f'data-source-state="{cell.state}"' in dialog_html
            assert category_label_by_key[source.category] in dialog_html
            detail_label = source_cell_detail_label(cell, race, group)
            if detail_label is not None:
                assert detail_label in dialog_html
            if cell.evidence_url is not None:
                assert f'href="{cell.evidence_url}"' in dialog_html
    assert "No endorsement" in html
    assert "Made no endorsement" not in html
    assert "Needs verification" in html
    # Issue 124: every guide-side trace of the per-race Times comparison is
    # gone. The Times itself stays listed in the evidence panel, so the check
    # below is for the retired treatment, not the source.
    assert "Comparison only" not in html
    assert "never counted toward the tally" not in html
    assert 'data-race-detail-group="comparison"' not in html
    assert "race-detail-source-row-comparison" not in html
    assert "Times comparison" not in html
    assert "print-times-pick" not in html
    assert "screen-comparisons" not in html
    assert "show-times" not in html
    assert "See which groups line up with the leading choice" not in html
    assert "race-detail-description-" not in html
    # The dialog's routing ships in the bundled guide-dialog.mjs now rather than
    # in an inline classic script (issue #239), and reaches `location` only
    # through the codec-owned router in lens-route.mjs.
    assert "raceDetail: target" in html
    assert "history.pushState(state" in html
    assert "history.back()" in html
    assert "target.showModal()" in html
    assert 'dialog.addEventListener("cancel"' in html
    assert 'window.addEventListener("popstate"' in html
    assert 'window.addEventListener("hashchange"' in html
    assert "navigator.clipboard?.writeText" in html
    assert "const link = new URL(window.location.href);" in html
    # Issue 142: the dialog's own Share link no longer overwrites the whole
    # hash with the bare race id — it rewrites only the `race` segment of
    # whatever fragment is already live, so an active personalized selection
    # survives the share. Issue #239 made that rewrite the codec's
    # `withRaceTarget` rather than a second hand-parse of the hash.
    assert "link.hash = withRaceTarget(window.location.hash, target);" in html
    assert "Consensus among explicitly endorsing sources" in html
    assert "Seattle Times" in html
    assert "August 2026 Primary" in html
    assert "Seattle Elections Guide" in html
    # L54: the hero states the election, not the brand (the band carries the
    # brand instead); the kicker states the exact election day; the old
    # hero-meta block ("Election ..." + "N races") is gone.
    # Issue 192: the head names the page and the eyebrow names the election, on
    # every page alike. The old "ELECTION DAY · AUGUST 4" kicker is gone — that
    # fact belongs to the election-day banner, which can retire itself once the
    # election has passed, as permanent chrome never could.
    assert '<p class="page-eyebrow">August 2026 Primary</p>' in html
    assert "<h1>Endorsements</h1>" in html
    assert 'class="hero-kicker"' not in html
    assert 'class="hero-meta"' not in html
    assert 'data-election-day="2026-08-04"' in html
    canonical_url = f"{configuration.public_site_url}/e/{view_model.metadata.election_id}/"
    assert f'<link rel="canonical" href="{canonical_url}">' in html
    assert f'<meta property="og:url" content="{canonical_url}">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    # Issue 192 (R5): the guide page's no-page-segment title exception is
    # retired, so every election-scoped page shares one title grammar.
    document_title = "Endorsements — August 2026 Primary — Seattle Elections Guide"
    assert f'<meta property="og:title" content="{document_title}">' in html
    assert f'<meta name="twitter:title" content="{document_title}">' in html
    assert f"<title>{document_title}</title>" in html
    assert f'<meta name="twitter:description" content="{configuration.subject}">' in html
    # Shared footer (UI polish round 5, item M71): one icon action cluster with
    # Share, Contact, GitHub, and How this works. Issue 193 retired the
    # generated PDF edition, so the cluster no longer offers a Printable PDF.
    assert '<footer class="site-footer">' in html
    footer_start = html.index('<footer class="site-footer">')
    footer_end = html.index("</footer>", footer_start)
    footer_html = html[footer_start:footer_end]
    assert "Printable PDF" not in html
    assert ".pdf" not in footer_html
    assert 'href="mailto:seattle-elections@dobravoda.dev" aria-label="Contact"' in footer_html
    assert f'href="{configuration.project_url}"' in footer_html
    assert 'aria-label="Source and audit files on GitHub (opens in a new tab)"' in footer_html
    # Web band: the GitHub action plus the audit line's code-revision link.
    # Issue 193 removed the hidden print audit and its two extra linked dates.
    assert footer_html.count(configuration.project_url) == 2
    assert 'href="/about/" aria-label="How this works" title="How this works"' in footer_html
    assert 'class="site-footer-link"' not in footer_html
    assert "About &amp; FAQ" not in footer_html
    # Issue 192: Share moved to the masthead — actions on the page belong there,
    # while the footer keeps meta about the site.
    assert "data-footer-share" not in footer_html
    assert "navigator.share" in html
    assert "shareOrCopyLink" in html
    # The bundled entry is what wires it now; the page's whole share contract is
    # the masthead control plus the one entry invocation (docs/FRONTEND.md).
    assert "data-shell-share" in html
    assert "GuidePage.boot();" in html
    assert '<div class="site-footer-audit">' in footer_html
    assert "Data updated" in footer_html
    assert "Site updated" in footer_html
    assert f"Panel {view_model.metadata.source_panel_id}" in footer_html
    assert f"({view_model.metadata.source_panel_hash[:12]})" in footer_html
    assert f">{view_model.metadata.git_commit[:12]}</a>" in footer_html
    assert ">AGREES<" not in html
    assert ">DIFFERENT PICK<" not in html
    assert ">NO PICK<" not in html
    assert f"{view_model.metadata.captured_source_count} represented sources" not in html
    assert f"{view_model.metadata.unresolved_review_count} unresolved reviews" not in html
    assert "Coverage note:" not in html
    assert "Category representation and support" not in html
    assert 'data-display-role="grade"' not in html
    assert 'id="methodology"' not in html
    assert 'class="sources-summary"' not in html
    assert 'href="/about/"' in html
    assert "How the consensus works" not in html
    assert "Verify the guide" not in html
    assert "Build and audit details" not in html
    assert configuration.project_url in html
    # Issue 124: the audited comparison records stay published, but nothing
    # the guide renders may quote them any more, on screen or in print.
    comparisons = [comparison for race in races for comparison in race.comparisons]
    assert comparisons
    for comparison in comparisons:
        # "Times" alone (the not-covered status) also names a font family in
        # the stylesheet, so only the distinctive labels are asserted absent.
        if comparison.print_status_label != "Times":
            assert comparison.print_status_label not in html
        assert comparison.voter_accessible_label not in html
        assert comparison.badge_label not in html
    assert (
        ".screen-race-result { display: grid; grid-template-columns: minmax(0, 1fr) 11rem;" in html
    )
    assert "grid-template-columns: minmax(0, 1fr) 11rem" in html
    # Nothing here restates the caption row's track. A string assertion cannot
    # fail for the reason it is written down, as this change learned twice; that
    # track is measured by test_the_support_caption_stays_on_one_line_beside_the_name.
    assert (
        ".screen-meter { display: flex; align-items: center; justify-content: flex-start;" in html
    )
    assert "linear-gradient(to right, var(--teal) 0 var(--meter-fill)" in html
    assert "html.compact-ballot-mode .screen-meter { width: 100%; height: 1.6rem; }" in html
    assert "text-align: left;" in html
    assert ".comparison-status { font-weight: 700; }" not in html
    assert (
        ".lens-comparison-agrees { "
        "border-left-color: var(--tone-agree-border); background: var(--tone-agree-bg);" in html
    )
    # Issue 193 retired the generated PDF edition, and with it the guide's
    # second rendering of its own data: the print source panel and the
    # detailed-edition source directory. The Sources page owns that listing
    # now, so the guide carries no publication-source or coverage-gap rows.
    assert 'data-publication-source-id="' not in html
    assert 'data-coverage-gap-source-id="' not in html
    assert 'class="print-guide"' not in html
    assert "print-race" not in html
    assert "--print-sans" not in html
    assert "centerPrintInk" not in html
    assert "detailed-edition" not in html
    # What survives is one print stylesheet over the page the reader sees.
    assert "@media print {" in html
    assert ".state-action-strip, .sticky-header, .filter-control-bar { display: none" in html
    assert "html .race-grid, html.compact-ballot-mode .race-grid" in html
    assert 'style="--meter-fill: ' in html


def test_no_majority_uses_the_exact_unrounded_share_across_the_card_and_dialog(
    tmp_path: Path,
) -> None:
    view_model = _view_model(tmp_path)
    configuration = read_rendering_configuration(RENDERING_CONFIG)
    target = next(
        race
        for section in view_model.sections
        for race in section.races
        if race.winner_share is not None
    )
    target.winner_share = "1/2"
    target.percentage_whole = 50
    target.percentage_label = "50%"

    assert has_no_majority(target) is True
    html = render_html_document(view_model, configuration)
    card_start = html.index(f'data-publication-race-id="{target.id}"')
    card_end = html.index("</article>", card_start)
    card_html = html[card_start:card_end]
    assert re.search(r'<p class="no-majority-pill"[^>]*>No majority</p>', card_html)
    assert 'class="screen-meter meter-no-majority"' in card_html
    assert "No majority · Leading choice" in card_html
    assert 'class="race-detail-meter meter-no-majority"' in card_html
    assert "No majority. Consensus among explicitly endorsing sources: 50%" in card_html

    target.winner_share = "5001/10000"
    assert has_no_majority(target) is False
    above_half_html = render_html_document(view_model, configuration)
    above_half_card_start = above_half_html.index(f'data-publication-race-id="{target.id}"')
    above_half_card_end = above_half_html.index("</article>", above_half_card_start)
    above_half_card = above_half_html[above_half_card_start:above_half_card_end]
    assert re.search(r'<p class="no-majority-pill" hidden[^>]*>No majority</p>', above_half_card)
    assert 'class="screen-meter meter-no-majority"' not in above_half_card
    assert "No majority · Leading choice" not in above_half_card


def test_the_no_majority_pill_sits_under_the_name_and_displaces_nothing(
    tmp_path: Path,
) -> None:
    """M63: the pill qualifies the pick, so it hangs under the name it applies to.

    The card's two rows carry the same shape — name over pill, meter over
    caption — which is only observable as geometry. Assert what that buys: the
    meter reads against the name's first line rather than its middle, the pill's
    left edge is the name's, the caption is flush to the meter, and the pill
    sits beside the caption rather than anywhere it could displace it. Compact
    stacks both rows into one column, and there the pill comes last.
    """
    view_model = _view_model(tmp_path)
    tied = next(
        race
        for section in view_model.sections
        for race in section.races
        if race.winner_share is not None
    )
    tied.winner_share = "1/2"
    tied.percentage_whole = 50
    tied.percentage_label = "50%"
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    expression = """
      (() => {
        const rows = () => [...document.querySelectorAll('.race-card')].map((card) => {
          const name = card.querySelector('h3');
          const meter = card.querySelector('.screen-meter');
          const caption = [...card.querySelectorAll('.support-line')]
            .find((line) => line.getClientRects().length);
          const pill = card.querySelector('.no-majority-pill:not([hidden])');
          if (!name || !meter || !caption) return null;
          const nameBox = name.getBoundingClientRect();
          const meterBox = meter.getBoundingClientRect();
          const pillBox = pill && pill.getClientRects().length
            ? pill.getBoundingClientRect() : null;
          const captionBox = caption.getBoundingClientRect();
          const context = caption.closest('.screen-race-context');
          return {
            pilled: Boolean(pillBox),
            captionFlush: Math.abs(captionBox.right - meterBox.right) <= 1,
            meterTopsWithName: Math.abs(meterBox.top - nameBox.top) <= 1,
            pillLeftWithName: pillBox === null
              || Math.abs(pillBox.left - nameBox.left) <= 1,
            // Its left edge alone survives a stretch, so measure the box against
            // its own text: deleting `justify-self` widens the pill to its whole
            // column while every edge assertion still passes.
            pillHugsText: pillBox === null || (() => {
              const text = document.createRange();
              text.selectNodeContents(pill);
              return pillBox.width - text.getBoundingClientRect().width < 40;
            })(),
            // Beside the caption in two columns, or after it in one — never
            // between the meter and the caption it belongs to.
            pillBesideCaption: pillBox === null
              || (pillBox.top < captionBox.bottom && pillBox.bottom > captionBox.top),
            pillAfterCaption: pillBox === null || pillBox.top >= captionBox.bottom - 1,
            contextColumns:
              getComputedStyle(context).gridTemplateColumns.split(' ').length,
            captionTop: Math.round(captionBox.top),
            captionHeight: Math.round(captionBox.height),
          };
        }).filter(Boolean);
        const full = rows();
        // The caption's row holds two items of different heights, so its
        // cross-axis alignment decides whether a pill appearing beside the
        // caption moves the caption. Suppress every pill and re-measure.
        const pills = [...document.querySelectorAll('.no-majority-pill:not([hidden])')];
        pills.forEach((pill) => { pill.hidden = true; });
        const fullWithoutPills = rows();
        pills.forEach((pill) => { pill.hidden = false; });
        document.documentElement.classList.add('compact-ballot-mode');
        const compact = rows();
        document.documentElement.classList.remove('compact-ballot-mode');
        return JSON.stringify({full, fullWithoutPills, compact});
      })()
    """

    measured = _evaluate_in_chrome(html_path, expression)
    full = measured["full"]
    assert any(card["pilled"] for card in full), "fixture must render a pill"
    assert any(not card["pilled"] for card in full), "fixture must render a card without one"

    assert all(card["meterTopsWithName"] for card in full)
    assert all(card["pillLeftWithName"] for card in full)
    assert all(card["pillHugsText"] for card in full)
    assert all(card["captionFlush"] for card in full)
    # Two columns in full view, so the pill sits beside the caption rather than
    # anywhere that could displace it.
    assert all(card["contextColumns"] == 2 for card in full)
    assert all(card["pillBesideCaption"] for card in full)
    # The pill shares the caption's row, so "beside" has to mean the caption did
    # not move to make room. (The meter is in the row above and cannot move at
    # all, which is why nothing here asserts that it didn't.)
    assert [card["captionTop"] for card in full] == [
        card["captionTop"] for card in measured["fullWithoutPills"]
    ]
    # ...and did not stretch to the pill's height either, which is the other way
    # a taller neighbour can reshape it.
    assert [card["captionHeight"] for card in full] == [
        card["captionHeight"] for card in measured["fullWithoutPills"]
    ]

    # Compact is one column, and there the pill comes after the caption. Note
    # what is NOT asserted: that hiding a pill leaves the meter where it was.
    # The pill is in the row below the meter in both renderers, so that holds by
    # construction and an assertion on it could never fail.
    compact = measured["compact"]
    assert any(card["pilled"] for card in compact)
    assert all(card["contextColumns"] == 1 for card in compact)
    assert all(card["pillAfterCaption"] for card in compact)


def test_the_support_caption_stays_on_one_line_beside_the_name(tmp_path: Path) -> None:
    """The caption shares the meter's column, and the column is sized to hold it.

    The caption runs wider than the meter, so its track carries `max-content`.
    Three arrangements were tried and rejected, and each fails a named assertion
    here: a fixed track wraps the caption (`oneLine`, and `allHugText` with it); a
    fixed track pinned with `white-space: nowrap` leaves the box narrower than its
    own text (`allHugText`); and no track at all drops the caption into an implicit
    one that absorbs the row's free space (`allHugText` again). `pageOverflow` is
    not one of those guards — no arrangement in this design's decision space makes
    the page wider than its viewport — it is the general no-overflow check.

    Nothing here asserts the caption clears the name. It cannot reach it: the two
    live in different rows of `.race-card-primary`, separated by that grid's gap,
    so an assertion about their glyphs would pass whatever the CSS said.
    """
    view_model = _view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    # The widest caption the card can hold is not the server's — the fixture's
    # own top out at a one-digit count, and the audited form is the shorter one
    # anyway. Once a lens selection diverges the client writes "Based on N of M
    # selected sources" (guide-format.mjs; its shape is pinned by the regex
    # assertions elsewhere in this file), with both counts bounded by the
    # registry's source count. Build that, so the width measured is the width
    # the reader can actually get.
    sources = len(read_source_registry(PROJECT_ROOT / "config/sources/default.yaml").sources)
    longest_caption = f"Based on {sources} of {sources} selected sources"
    assert len(longest_caption) > len(
        max(
            (screen_support_summary(race) for s in view_model.sections for race in s.races),
            key=len,
        )
    )
    expression = """
      (() => {
        const captions = [...document.querySelectorAll('.race-card')].map((card) => {
          const caption = [...card.querySelectorAll('.support-line')]
            .find((line) => line.getClientRects().length);
          if (!caption) return null;
          caption.textContent = LONGEST;
          const box = caption.getBoundingClientRect();
          const cardBox = card.getBoundingClientRect();
          return {
            // One line-box tall, not "as short as its neighbours" — if every
            // caption wrapped, a comparison between them would still pass.
            lines: box.height / parseFloat(getComputedStyle(caption).lineHeight),
            // The track is the caption's own width, so the box hugs its text.
            // Measured against the text's own rect, not scrollWidth, which for
            // a block box is just the box again. Without the sizing the caption
            // lands in an implicit auto track that absorbs the row's free space.
            hugsText: (() => {
              const text = document.createRange();
              text.selectNodeContents(caption);
              return Math.abs(box.width - text.getBoundingClientRect().width) <= 2;
            })(),
            insideCard: box.left >= cardBox.left - 1 && box.right <= cardBox.right + 1,
          };
        }).filter(Boolean);
        return JSON.stringify({
          measured: captions.length,
          oneLine: captions.every((c) => c.lines <= 1.05),
          allHugText: captions.every((c) => c.hugsText),
          allInsideCard: captions.every((c) => c.insideCard),
          pageOverflow: document.documentElement.scrollWidth
            > document.documentElement.clientWidth,
        });
      })()
    """.replace("LONGEST", json.dumps(longest_caption))

    screen = _evaluate_in_chrome(html_path, expression)
    phone = _evaluate_in_chrome(html_path, expression, mobile_width=320)
    # No band width here. The caption's own track is 185.77px at every screen
    # width, so 560px measured exactly what the default already does — the two
    # editions failed together under every control and separately under none —
    # and each Chrome launch is a real cost to a suite that already flakes under
    # load. 320px and print stay because each fails where the others pass.
    printed = _evaluate_in_chrome(html_path, expression, mobile_width=768, media="print")

    for edition in (screen, phone, printed):
        assert edition["measured"] > 0
        assert edition["oneLine"] is True
        assert edition["allInsideCard"] is True
        assert edition["pageOverflow"] is False

    # Only where the card is two columns: the caption's track is its own width,
    # so the box hugs the text. Below 480px the card is one column and the
    # caption spans it, which is the point of that layout, not a defect.
    for edition in (screen, printed):
        assert edition["allHugText"] is True
    assert phone["allHugText"] is False


def test_round4_card_anatomy_and_data_ink_cleanup(tmp_path: Path) -> None:
    """docs/UI_POLISH.md round-4 items I39/H38/H34/H36/H37/I40/I41/I42."""
    view_model = _view_model(tmp_path)
    configuration = read_rendering_configuration(RENDERING_CONFIG)
    races = [race for section in view_model.sections for race in section.races]

    # I41: below ~30% fill, the card meter's label guard renders after the
    # fill in muted ink instead of riding the (now too-narrow) colored fill.
    # Reuse an existing race that already has a support leader (only its own
    # share is overridden) so revalidation doesn't reject a share with no
    # leader.
    leading_race_id = next(race.id for race in races if race.percentage_whole is not None)
    low_fill_model = view_model.model_copy(deep=True)
    low_fill_race = next(
        race
        for section in low_fill_model.sections
        for race in section.races
        if race.id == leading_race_id
    )
    low_fill_race.winner_share = str(Fraction(25, 100))
    low_fill_race.percentage_label = "25%"
    low_fill_race.percentage_whole = 25
    low_fill_model = _revalidated(low_fill_model)
    low_fill_html = render_html_document(low_fill_model, configuration)
    meter_start = low_fill_html.index(f'id="race-{leading_race_id}"')
    meter_end = low_fill_html.index("</dialog>", meter_start)
    assert (
        'class="screen-meter meter-no-majority meter-low-fill"'
        in low_fill_html[meter_start:meter_end]
    )

    high_fill_model = view_model.model_copy(deep=True)
    high_fill_race = next(
        race
        for section in high_fill_model.sections
        for race in section.races
        if race.id == leading_race_id
    )
    high_fill_race.winner_share = str(Fraction(70, 100))
    high_fill_race.percentage_label = "70%"
    high_fill_race.percentage_whole = 70
    high_fill_model = _revalidated(high_fill_model)
    high_fill_html = render_html_document(high_fill_model, configuration)
    high_meter_start = high_fill_html.index(f'id="race-{leading_race_id}"')
    high_meter_end = high_fill_html.index("</dialog>", high_meter_start)
    assert "meter-low-fill" not in high_fill_html[high_meter_start:high_meter_end]

    # H34/I39: the default caption always renders both its full and compact
    # forms (a pure CSS toggle, mirroring the print edition's own full/compact
    # captions), directly under the meter row and ahead of the reference
    # block (the comparisons div) at the card foot.
    # Issue #248 retired the lens-only twins: one caption element carries the
    # audited text and, once a selection diverges, the personalized text, so
    # the markup no longer varies with the policy.
    html = render_html_document(view_model, configuration)
    for race in races:
        card_start = html.index(f'id="race-{race.id}"')
        card_end = html.index("</dialog>", card_start)
        card_html = html[card_start:card_end]
        full_caption = (
            f'<p class="support-line support-full" data-display-role="support"'
            f">{screen_support_summary(race)}</p>"
        )
        compact_caption = (
            f'<p class="support-line support-compact" data-display-role="support"'
            f">{screen_support_summary_compact(race)}</p>"
        )
        assert full_caption in card_html
        assert compact_caption in card_html
        assert card_html.index(full_caption) < card_html.index(compact_caption)
        assert "screen-comparisons" not in card_html
    assert ".support-compact { display: none; }" in html
    assert "html.compact-ballot-mode .support-full { display: none; }" in html
    assert "html.compact-ballot-mode .support-compact { display: block; }" in html

    # H38: no per-card "My sources" pill remains anywhere in the markup.
    assert "lens-card-badge" not in html
    assert "My sources</span>" not in html

    # H36: the category chip loses its pill chrome (plain muted text). Issue
    # 124 retired the comparison role badge along with the rows that carried it.
    assert (
        ".race-detail-category-badge { color: var(--muted); font-size: .68rem; "
        "font-weight: 600; text-align: right; }" in html
    )
    assert "race-detail-comparison-badge" not in html

    # I40: one meter chrome — the dialog meter now shares the card's own
    # border/track tokens instead of its former tone-agree border/white track.
    assert (
        ".race-detail-meter { display: flex; flex: 0 0 auto; align-items: center; "
        "justify-content: flex-start; width: 8.5rem; height: 1.8rem; overflow: hidden; "
        "border: 1px solid var(--line-strong); border-radius: 1rem; "
        "background: linear-gradient(to right, var(--teal) 0 var(--meter-fill), "
        "var(--meter-track) var(--meter-fill) 100%); }" in html
    )
    assert ".race-detail-meter-na { background: var(--meter-track); }" in html

    # I42: compact-mode race labels reserve consistent height so the
    # following name+meter block starts at the same offset in every card.
    assert "html.compact-ballot-mode .race-office { min-height: 2.3rem;" in html


def test_rendering_configuration_rejects_contract_drift() -> None:
    configuration = read_rendering_configuration(RENDERING_CONFIG)
    payload = configuration.model_dump(mode="json")
    payload["unexpected"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        type(configuration).model_validate(payload)

    for field in ("author", "subject"):
        blank = configuration.model_dump(mode="json")
        blank[field] = "   "
        with pytest.raises(ValidationError):
            type(configuration).model_validate(blank)

    coerced = configuration.model_dump(mode="json")
    coerced["desktop_width"] = "1440"
    with pytest.raises(ValidationError):
        type(configuration).model_validate(coerced)

    retired_pdf_key = configuration.model_dump(mode="json")
    retired_pdf_key["pdf_filename"] = "Guide.pdf"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        type(configuration).model_validate(retired_pdf_key)


def test_html_escapes_publication_text_and_filter_attributes(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path)
    payload = '<img src=x onerror="globalThis.pwned=1">'
    view_model.sources[0].name = payload
    view_model.sections[0].races[0].filter_tokens.append(payload)

    html = render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))

    assert payload not in html
    assert "&lt;img src=x onerror=&#34;globalThis.pwned=1&#34;&gt;" in html
    assert r"\u003cimg src=x onerror=\"globalThis.pwned=1\"\u003e" in html


def test_html_rejects_non_web_evidence_links(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path)
    endorsement_cell = next(
        cell
        for section in view_model.sections
        for race in section.races
        for cell in race.source_cells
        if cell.state in {"endorsement", "multi_endorsement"}
    )
    endorsement_cell.evidence_url = "javascript:alert(document.cookie)"

    with pytest.raises(ValueError, match=r"safe HTTP\(S\) URL"):
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))

    source_view_model = _view_model(tmp_path / "source")
    source_view_model.sources[0].evidence_url = "javascript:alert(document.cookie)"

    with pytest.raises(ValueError, match=r"safe HTTP\(S\) URL"):
        render_html_document(source_view_model, read_rendering_configuration(RENDERING_CONFIG))

    # A source's own receipt is rendered by the sources editor's tree and its
    # coverage-gap rows, so that renderer checks it too.
    with pytest.raises(ValueError, match=r"safe HTTP\(S\) URL"):
        render_sources_document(source_view_model, public_site_url="https://seattleelections.guide")

    cell_view_model = _view_model(tmp_path / "cell")
    cell = next(
        cell
        for section in cell_view_model.sections
        for race in section.races
        for cell in race.source_cells
        if cell.state in {"no_endorsement", "unavailable", "unverified"}
    )
    cell.evidence_url = "javascript:alert(document.cookie)"

    with pytest.raises(ValueError, match=r"safe HTTP\(S\) URL"):
        render_html_document(cell_view_model, read_rendering_configuration(RENDERING_CONFIG))


def test_nonempty_render_destination_is_preserved(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path / "fixture")
    view_model_path = tmp_path / "publication_view_model.json"
    view_model_path.write_bytes(canonical_json_bytes(view_model.model_dump(mode="json")))
    output_dir = tmp_path / "rendered"
    output_dir.mkdir()
    marker = output_dir / "keep.txt"
    marker.write_text("owned by another generation", encoding="utf-8")

    with pytest.raises(ValueError, match="must be absent or empty"):
        build_rendered_guide(view_model_path, RENDERING_CONFIG, output_dir)

    assert marker.read_text(encoding="utf-8") == "owned by another generation"


def _recommendation_tag_pattern(label: str) -> re.Pattern[str]:
    """Match a rendered recommendation `<h3>` around its exact label text."""
    return re.compile(
        r'(<h3 data-display-role="recommendation"[^>]*>)' + re.escape(label) + r"(</h3>)"
    )


def test_chromium_build_is_semantically_faithful_and_visually_safe(tmp_path: Path) -> None:
    view_model = _visual_view_model(_view_model(tmp_path / "fixture"))
    view_model_path = tmp_path / "publication_view_model.json"
    view_model_path.write_bytes(canonical_json_bytes(view_model.model_dump(mode="json")))

    rendered = build_rendered_guide(
        view_model_path,
        RENDERING_CONFIG,
        tmp_path / "rendered",
    )

    rendered_html = rendered.html_path.read_text(encoding="utf-8")
    assert view_model.metadata.source_panel_id in rendered_html
    assert view_model.metadata.source_panel_hash in rendered_html
    for percentage in (53, 64, 70, 100):
        assert f'style="--meter-fill: {percentage}%"' in rendered_html
    for tone in ("agrees", "differs", "not_covered"):
        assert f'class="comparison comparison-{tone}"' not in rendered_html
        assert f"print-times-pick-{tone}" not in rendered_html

    assert rendered.validation_report.passed
    assert len(rendered.screenshots) == 2
    report = RenderingValidationReport.model_validate(read_json(rendered.validation_path))
    assert report == rendered.validation_report
    vacuous = report.model_dump(mode="json")
    vacuous["checks"] = []
    with pytest.raises(ValidationError, match="each required check exactly once"):
        RenderingValidationReport.model_validate(vacuous)
    inconsistent = report.model_dump(mode="json")
    inconsistent["checks"][0]["passed"] = False
    with pytest.raises(ValidationError, match="summary does not match its checks"):
        RenderingValidationReport.model_validate(inconsistent)
    with Image.open(rendered.screenshots[0]) as desktop:
        assert desktop.size == (1440, 1200)
    with Image.open(rendered.screenshots[1]) as mobile:
        assert mobile.size == (390, 1200)
    assert S_IMODE((tmp_path / "rendered").stat().st_mode) == 0o755
    assert S_IMODE(rendered.html_path.stat().st_mode) == 0o644
    approved_baselines = APPROVED_VISUAL_BASELINES_BY_PLATFORM[sys.platform]
    artifact_paths = dict(zip(approved_baselines, rendered.screenshots, strict=True))
    observed_signatures = {
        label: _coarse_visual_signature(path) for label, path in artifact_paths.items()
    }
    for label, observed in observed_signatures.items():
        expected = approved_baselines[label]
        assert (
            sum(abs(left - right) for left, right in zip(observed, expected, strict=True)) / 16
            < 0.04
        ), f"{label}: observed signatures {observed_signatures}"
        assert (
            max(abs(left - right) for left, right in zip(observed, expected, strict=True)) < 0.12
        ), f"{label}: observed signatures {observed_signatures}"

    blank_screenshots: list[Path] = []
    for index, screenshot in enumerate(rendered.screenshots):
        with Image.open(screenshot) as source:
            blank = Image.new("RGB", source.size, "white")
        blank_path = tmp_path / f"blank-{index}.png"
        blank.save(blank_path)
        blank_screenshots.append(blank_path)
    blank_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        rendered.html_path,
        blank_screenshots,
    )
    responsive_check = next(
        check for check in blank_report.checks if check.id == "responsive-viewports"
    )
    assert not responsive_check.passed

    races = [race for section in view_model.sections for race in section.races]
    evidence_urls = [
        endorser.evidence_url
        for race in races
        for group in race.endorsement_groups
        for endorser in group.endorsers
    ]
    assert len(evidence_urls) >= 2
    mutated_html = tmp_path / "mutated.html"
    mutated_html.write_text(
        rendered.html_path.read_text(encoding="utf-8").replace(
            evidence_urls[0], evidence_urls[1], 1
        ),
        encoding="utf-8",
    )
    row_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        mutated_html,
        rendered.screenshots,
    )
    evidence_check = next(
        check for check in row_report.checks if check.id == "html-source-evidence"
    )
    assert not evidence_check.passed

    unexpected_link_html = tmp_path / "unexpected-link.html"
    unexpected_link_html.write_text(
        rendered.html_path.read_text(encoding="utf-8").replace(
            "</body>",
            '<a href="https://evil.example/phish">More evidence</a></body>',
            1,
        ),
        encoding="utf-8",
    )
    unexpected_link_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        unexpected_link_html,
        rendered.screenshots,
    )
    unexpected_link_check = next(
        check for check in unexpected_link_report.checks if check.id == "html-source-evidence"
    )
    assert not unexpected_link_check.passed

    canonical_html = rendered.html_path.read_text(encoding="utf-8")
    detail_race, detail_cell = next(
        (race, cell)
        for race in races
        for cell in race.source_cells
        if cell.evidence_url is not None
    )
    detail_source = next(
        source for source in view_model.sources if source.id == detail_cell.source_id
    )
    detail_source_code = next(
        source.code
        for source in view_model.personalization.sources
        if source.id == detail_cell.source_id
    )
    row_marker = f'<li data-race-detail-source-code="{detail_source_code}"'
    race_start = canonical_html.index(f'id="race-detail-{detail_race.id}"')
    row_start = canonical_html.index(row_marker, race_start)
    row_end = canonical_html.index("</li>", row_start) + len("</li>")
    canonical_row = canonical_html[row_start:row_end]
    malicious_duplicate = canonical_row.replace(
        "</li>", '<a href="https://evil.example/phish">Wrong evidence</a></li>'
    )
    duplicate_row_html = tmp_path / "duplicate-source-row.html"
    duplicate_row_html.write_text(
        canonical_html.replace(canonical_row, malicious_duplicate + canonical_row, 1),
        encoding="utf-8",
    )
    duplicate_row_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        duplicate_row_html,
        rendered.screenshots,
    )
    duplicate_row_check = next(
        check for check in duplicate_row_report.checks if check.id == "html-source-evidence"
    )
    assert not duplicate_row_check.passed

    race_with_alternative = next(race for race in races if race.alternatives)
    recommendation_pattern = _recommendation_tag_pattern(race_with_alternative.recommendation_label)
    replacement_label = race_with_alternative.alternatives[0].candidate_label
    wrong_recommendation_html = tmp_path / "wrong-recommendation.html"
    wrong_recommendation_html.write_text(
        recommendation_pattern.sub(
            lambda match: f"{match.group(1)}{replacement_label}{match.group(2)}",
            rendered.html_path.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )
    semantic_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        wrong_recommendation_html,
        rendered.screenshots,
    )
    semantic_check = next(
        check for check in semantic_report.checks if check.id == "html-display-values"
    )
    assert not semantic_check.passed

    wrong_detail_row = canonical_row.replace(
        f"<strong>{detail_source.name}</strong>", "<strong>Wrong organization</strong>", 1
    )
    assert wrong_detail_row != canonical_row
    endorsement_html = tmp_path / "wrong-endorsement-source.html"
    endorsement_html.write_text(
        canonical_html.replace(canonical_row, wrong_detail_row, 1),
        encoding="utf-8",
    )
    endorsement_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        endorsement_html,
        rendered.screenshots,
    )
    endorsement_check = next(
        check for check in endorsement_report.checks if check.id == "html-source-evidence"
    )
    assert not endorsement_check.passed

    source_group = next(
        group
        for group in (
            "leader",
            "alternative",
            "no_endorsement",
            "comparison",
            "unverified",
            "not_covered",
        )
        if f'data-source-group="{group}"' in canonical_row
    )
    wrong_group_html = tmp_path / "wrong-source-group.html"
    wrong_group_html.write_text(
        canonical_html.replace(
            canonical_row,
            canonical_row.replace(
                f'data-source-group="{source_group}"', 'data-source-group="wrong"', 1
            ),
            1,
        ),
        encoding="utf-8",
    )
    wrong_group_report = validate_rendered_guide(
        view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        wrong_group_html,
        rendered.screenshots,
    )
    wrong_group_check = next(
        check for check in wrong_group_report.checks if check.id == "html-source-evidence"
    )
    assert not wrong_group_check.passed

    recommendation_match = _recommendation_tag_pattern(
        race_with_alternative.recommendation_label
    ).search(rendered.html_path.read_text(encoding="utf-8"))
    assert recommendation_match is not None
    recommendation_element = recommendation_match.group(0)
    for index, replacement in enumerate(
        (
            recommendation_element.replace(
                "</h3>", f" / {race_with_alternative.alternatives[0].candidate_label}</h3>"
            ),
            recommendation_element + recommendation_element,
        )
    ):
        conflicting_html = tmp_path / f"conflicting-recommendation-{index}.html"
        conflicting_html.write_text(
            rendered.html_path.read_text(encoding="utf-8").replace(
                recommendation_element, replacement, 1
            ),
            encoding="utf-8",
        )
        conflicting_report = validate_rendered_guide(
            view_model,
            read_rendering_configuration(RENDERING_CONFIG),
            conflicting_html,
            rendered.screenshots,
        )
        conflicting_check = next(
            check for check in conflicting_report.checks if check.id == "html-display-values"
        )
        assert not conflicting_check.passed

    # Issue 124: no comparison bar is rendered any more, so the accessible-name
    # tampering below anchors on the share meter alone. The comparison record
    # is still published — its accessible label must simply never appear.
    accessible_race = next(race for race in races if race.comparisons)
    accessible_html = rendered.html_path.read_text(encoding="utf-8")
    assert accessible_race.comparisons[0].voter_accessible_label not in accessible_html

    share_label = (
        f"Consensus among explicitly endorsing sources: {accessible_race.percentage_label}"
    )
    # The card's own compact meter (`data-display-role="share"`) is the
    # element `html-display-values` actually keys its "share" comparison on;
    # anchored to it (rather than a bare 'role="img"') so the corruption
    # lands there and not on the shared footer/band's decorative brand-icon
    # svg, which also carries `role="img"` (item L54: the band's icon now
    # always renders, including on the guide page).
    share_meter_match = re.search(
        r'role="img"\s+data-display-role="share"\s+aria-label="' + re.escape(share_label) + '"',
        accessible_html,
    )
    assert share_meter_match is not None
    share_meter_original = share_meter_match.group(0)
    for index, (original, replacement) in enumerate(
        (
            (f'aria-label="{share_label}"', 'aria-label="Consensus among endorsers: 100%"'),
            (
                share_meter_original,
                share_meter_original.replace('role="img"', 'role="presentation"', 1),
            ),
        )
    ):
        assert original in accessible_html
        broken_share_html = tmp_path / f"broken-share-accessibility-{index}.html"
        broken_share_html.write_text(
            accessible_html.replace(original, replacement, 1),
            encoding="utf-8",
        )
        broken_share_report = validate_rendered_guide(
            view_model,
            read_rendering_configuration(RENDERING_CONFIG),
            broken_share_html,
            rendered.screenshots,
        )
        broken_share_check = next(
            check for check in broken_share_report.checks if check.id == "html-display-values"
        )
        assert not broken_share_check.passed

    unavailable_view_model = view_model.model_copy(deep=True)
    unavailable_race = unavailable_view_model.sections[0].races[0]
    unavailable_race.support_leader_candidate_ids = []
    unavailable_race.support_leader_candidate_labels = []
    unavailable_race.support_leader_label = "No leader"
    unavailable_race.recommendation_candidate_ids = []
    unavailable_race.recommendation_candidate_labels = []
    unavailable_race.recommendation_label = "Too few endorsements"
    unavailable_race.grade = "Insufficient"
    unavailable_race.winner_share = None
    unavailable_race.percentage_label = "—"
    unavailable_race.percentage_whole = None
    unavailable_view_model = _revalidated(unavailable_view_model)
    unavailable_html_text = render_html_document(
        unavailable_view_model, read_rendering_configuration(RENDERING_CONFIG)
    )
    unavailable_html = tmp_path / "unavailable-share.html"
    unavailable_html.write_text(unavailable_html_text, encoding="utf-8")
    unavailable_report = validate_rendered_guide(
        unavailable_view_model,
        read_rendering_configuration(RENDERING_CONFIG),
        unavailable_html,
        rendered.screenshots,
    )
    unavailable_html_check = next(
        check for check in unavailable_report.checks if check.id == "html-display-values"
    )
    assert unavailable_html_check.passed
    unavailable_label = "Consensus among explicitly endorsing sources: not available"
    # Same anchoring as the share-accessibility loop above: target the
    # card's own compact meter, not the first `role="img"` in the document
    # (now the shared band's brand icon, item L54).
    unavailable_meter_match = re.search(
        r'role="img"\s+data-display-role="share"\s+aria-label="'
        + re.escape(unavailable_label)
        + '"',
        unavailable_html_text,
    )
    assert unavailable_meter_match is not None
    unavailable_meter_original = unavailable_meter_match.group(0)
    for index, (original, replacement) in enumerate(
        (
            (f'aria-label="{unavailable_label}"', 'aria-label="Consensus among endorsers: 0%"'),
            (
                unavailable_meter_original,
                unavailable_meter_original.replace('role="img"', 'role="presentation"', 1),
            ),
        )
    ):
        assert original in unavailable_html_text
        broken_unavailable_html = tmp_path / f"broken-unavailable-accessibility-{index}.html"
        broken_unavailable_html.write_text(
            unavailable_html_text.replace(original, replacement, 1),
            encoding="utf-8",
        )
        broken_unavailable_report = validate_rendered_guide(
            unavailable_view_model,
            read_rendering_configuration(RENDERING_CONFIG),
            broken_unavailable_html,
            rendered.screenshots,
        )
        broken_unavailable_check = next(
            check for check in broken_unavailable_report.checks if check.id == "html-display-values"
        )
        assert not broken_unavailable_check.passed


def test_responsive_tablet_layout_renders(tmp_path: Path) -> None:
    view_model = _view_model(tmp_path / "fixture")
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )

    render_screenshot(
        html_path,
        tmp_path / "tablet.png",
        find_chrome(),
        width=768,
        height=1200,
        expected_race_count=sum(len(section.races) for section in view_model.sections),
        expected_source_count=sum(
            source.panel_role != "comparison" for source in view_model.sources
        ),
    )


def _dense_view_model(view_model: PublicationViewModel) -> PublicationViewModel:
    races = [race for section in view_model.sections for race in section.races]
    example = next(race for race in races if race.recommendation_candidate_labels)
    display = {
        "support_leader_candidate_ids": example.support_leader_candidate_ids,
        "support_leader_candidate_labels": example.support_leader_candidate_labels,
        "support_leader_label": example.support_leader_label,
        "recommendation_candidate_ids": example.recommendation_candidate_ids,
        "recommendation_candidate_labels": example.recommendation_candidate_labels,
        "recommendation_label": example.recommendation_label,
        "grade": example.grade,
        "winner_share": example.winner_share,
        "percentage_label": example.percentage_label,
        "percentage_whole": example.percentage_whole,
        "support_summary": example.support_summary,
        "explicit_endorsement_count": example.explicit_endorsement_count,
        "eligible_source_count": example.eligible_source_count,
        "source_coverage_count": example.source_coverage_count,
        "category_coverage_count": example.category_coverage_count,
        "category_breakdown": example.category_breakdown,
        "no_endorsement_count": example.no_endorsement_count,
        "missing_source_count": example.missing_source_count,
        "endorsement_groups": example.endorsement_groups,
        "alternatives": example.alternatives,
        "comparisons": example.comparisons,
        "warning_codes": example.warning_codes,
        "warning_messages": example.warning_messages,
        "source_cells": example.source_cells,
    }
    sections = [
        section.model_copy(
            update={"races": [race.model_copy(update=display) for race in section.races]}
        )
        for section in view_model.sections
    ]
    source_cells = [
        cell for section in sections for race in section.races for cell in race.source_cells
    ]
    sources = [
        source.model_copy(
            update={
                "endorsement_count": sum(
                    cell.source_id == source.id
                    and cell.state in {"endorsement", "multi_endorsement"}
                    for cell in source_cells
                ),
                "split_endorsement_count": sum(
                    cell.source_id == source.id and cell.state == "multi_endorsement"
                    for cell in source_cells
                ),
            }
        )
        for source in view_model.sources
    ]
    # Every race's candidates (endorsement groups, source cells) are stamped
    # from `example` above; its published lens candidate order must follow
    # the same substitution, or the personalization payload's own H30
    # invariant (every allocated candidate id is in `candidate_order`) would
    # reject the reprojected races below for referencing `example`'s
    # candidates under another race's original ballot order.
    example_candidate_order = next(
        race.candidate_order
        for race in view_model.personalization.races
        if race.race_id == example.id
    )
    personalization = view_model.personalization.model_copy(
        update={
            "races": [
                race.model_copy(update={"candidate_order": example_candidate_order})
                for race in view_model.personalization.races
            ]
        }
    )
    return _revalidated(
        view_model.model_copy(
            update={"sections": sections, "sources": sources, "personalization": personalization}
        )
    )


def _visual_view_model(view_model: PublicationViewModel) -> PublicationViewModel:
    visual = _dense_view_model(view_model)
    comparison_source_index = next(
        index for index, source in enumerate(visual.sources) if source.panel_role == "comparison"
    )
    template_source = next(
        source
        for source in visual.sources
        if source.panel_role == "consensus" and not source.overlap_group_ids
    )
    additional_sources = [
        template_source.model_copy(
            update={
                "id": f"visual-source-{index:02d}",
                "name": f"Regional Progressive Coalition and Community Action Network {index:02d}",
                "organization_url": f"https://example.com/visual-source-{index:02d}",
                "evidence_url": f"https://example.com/visual-source-{index:02d}/endorsements",
                "endorsement_count": 0,
                "split_endorsement_count": 0,
            }
        )
        for index in range(1, 32)
    ]
    visual.sources[comparison_source_index:comparison_source_index] = additional_sources
    category = next(
        category
        for category in visual.methodology.source_categories
        if category.category == template_source.category
    )
    category.source_ids.extend(source.id for source in additional_sources)
    additional_cells = [
        SourceCell.model_validate(
            {
                "source_id": source.id,
                "state": "not_applicable",
                "candidate_ids": [],
                "candidate_labels": [],
                "allocation": {},
                "evidence_url": None,
                "evidence_locator": None,
                "confidence_warning": False,
            }
        )
        for source in additional_sources
    ]
    for section in visual.sections:
        for race in section.races:
            race.source_cells[comparison_source_index:comparison_source_index] = additional_cells
    visual.metadata.source_count += len(additional_sources)
    visual.metadata.captured_source_count += len(additional_sources)
    visual.metadata.contributing_source_count += len(additional_sources)
    races = [race for section in visual.sections for race in section.races]
    source_id = races[0].comparisons[0].source_id
    races[0].comparisons = [
        PublicationComparison.model_validate(
            {
                "source_id": source_id,
                "status": "agrees",
                "badge_label": "AGREES",
                "candidate_ids": races[0].recommendation_candidate_ids,
                "candidate_labels": races[0].recommendation_candidate_labels,
            }
        )
    ]
    races[1].comparisons = [
        PublicationComparison.model_validate(
            {
                "source_id": source_id,
                "status": "differs",
                "badge_label": "DIFFERENT PICK",
                "candidate_ids": ["toshiko-grace-hasegawa"],
                "candidate_labels": ["Toshiko Grace Hasegawa"],
            }
        )
    ]
    races[2].comparisons = [
        PublicationComparison.model_validate(
            {
                "source_id": source_id,
                "status": "not_covered",
                "badge_label": "NOT COVERED",
                "candidate_ids": [],
                "candidate_labels": [],
            }
        )
    ]
    for race, percentage in zip(races[:4], (53, 64, 70, 100), strict=True):
        race.winner_share = str(Fraction(percentage, 100))
        race.percentage_label = f"{percentage}%"
        race.percentage_whole = percentage
    return _revalidated(visual)


def _coarse_visual_signature(path: Path) -> list[float]:
    with Image.open(path) as opened:
        image = opened.convert("RGB").resize(  # pyright: ignore[reportUnknownMemberType]
            (4, 4), Image.Resampling.BOX
        )
        signature: list[float] = []
        for y in range(4):
            for x in range(4):
                pixel = cast(tuple[int, int, int], image.getpixel((x, y)))
                signature.append(round(1 - sum(pixel) / (3 * 255), 3))
        return signature


def _view_model(root: Path) -> PublicationViewModel:
    dataset = _publication_dataset(root)
    snapshot_root = _snapshot_store(root, dataset)
    report = score_dataset(
        dataset,
        _configuration(),
        computed_at=NOW,
        allow_unresolved=True,
    )
    return build_publication_bundle(
        dataset,
        report,
        git_commit="render-fixture",
        snapshot_root=snapshot_root,
    ).view_model


def _client_payload(html: str) -> dict[str, Any]:
    """The page's one embedded JSON payload (docs/FRONTEND.md, The data contract)."""
    return json.loads(html.split(PAYLOAD_ELEMENT)[1].split("</script>")[0])


def _revalidated(view_model: PublicationViewModel) -> PublicationViewModel:
    """Revalidate a hand-built display model with a coherent lens payload.

    Layout fixtures synthesize extra panel sources, so this mints transport
    codes for them and reprojects the derived lens records before validating.
    """
    contract = view_model.personalization
    lens_by_id = {source.id: source for source in contract.sources}
    lens_sources: list[PersonalizationSource] = []
    for index, source in enumerate(view_model.sources):
        existing = lens_by_id.get(source.id)
        if existing is not None:
            lens_sources.append(existing)
            continue
        lens_sources.append(
            PersonalizationSource(
                id=source.id,
                code=f"x{index:03d}",
                panel_role=source.panel_role,
                selectable=True,
                reporting_category_id=source.category,
                selection_category_ids=[source.category],
                overlap_group_ids=source.overlap_group_ids,
            )
        )
    categories = [
        category.model_copy(
            update={
                "member_source_codes": sorted(
                    source.code
                    for source in lens_sources
                    if source.selectable and category.id in source.selection_category_ids
                )
                if category.selectable
                else []
            }
        )
        for category in contract.categories
    ]
    rebuilt = view_model.model_copy(
        update={
            "personalization": contract.model_copy(
                update={"sources": lens_sources, "categories": categories}
            )
        }
    )
    reprojected = reprojected_personalization(rebuilt)
    return PublicationViewModel.model_validate(
        reprojected_comparisons(reprojected).model_dump(mode="json")
    )


def _sources_tree_html(tmp_path: Path) -> str:
    """Render the reference guide the way the other rendering tests do."""
    return render_html_document(
        _view_model(tmp_path), read_rendering_configuration(RENDERING_CONFIG)
    )


def test_guide_has_no_orphaned_methodology_markup_css_or_js(tmp_path: Path) -> None:
    """Issue 109: the on-screen inline methodology disclosure, its CSS, and any
    JS that only existed to support it are gone from the guide entirely. The
    fixed print edition's own separate, always-printed "How to read this
    guide" page (a different section that predates and is independent of the
    removed on-screen disclosure) is untouched and keeps its own self-contained
    explanation, since a printed PDF cannot link out to /about/."""
    html = _sources_tree_html(tmp_path)
    assert 'id="methodology"' not in html
    assert "methodology-screen" not in html
    assert "methodology-panel" not in html
    assert "methodology-overlap" not in html


def test_the_guide_carries_no_times_comparison_at_all(tmp_path: Path) -> None:
    """Issue 124: the opt-in Times comparison is retired, not merely hidden.

    Issue 79 shipped it as a CSS-gated reveal driven by a `show-times` root
    class; nothing of that mechanism — the bars, the hidden race-detail rows,
    the two-count headings, or the class itself — survives.
    """
    html = _sources_tree_html(tmp_path)
    stylesheet = html.split("<style>")[1].split("</style>")[0]

    assert "show-times" not in html
    assert "screen-comparisons" not in html
    assert "data-times-hidden" not in html
    assert "data-times-only" not in html
    assert 'data-source-role="comparison"' not in stylesheet

    # Every group heading states one count, matching the rows it lists.
    detail = html.split('data-race-detail-group="no_endorsement"')[1].split("</section>")[0]
    listed = detail.count('data-race-detail-source-code="')
    assert f"{listed} source" in detail


def test_sources_tree_shell_exposes_no_dialog_and_keeps_controls_in_the_merged_section(
    tmp_path: Path,
) -> None:
    """Issue 97: the Customize dialog no longer exists anywhere in the page.
    Issue 108: the interactive sources tree itself is gone too — the guide
    keeps only a compact, non-interactive summary and a link to the
    dedicated sources page."""
    html = _sources_tree_html(tmp_path)
    controls = html.split('<section class="screen-controls filter-control-bar"')[1].split(
        "</section>"
    )[0]

    assert controls.count("<button") == 0
    assert "data-customize-open" not in html
    assert "customize-dialog" not in html
    assert "<dialog" in html  # the race-detail dialogs are unaffected

    assert 'id="sources"' not in html
    assert "data-sources-source" not in html
    assert "data-sources-comparison-status" not in html
    band = html.split('<div class="site-band">')[1].split("</div>")[0]
    assert "data-sources-link" in band


def test_sources_tree_shell_encodes_state_through_the_published_codec(tmp_path: Path) -> None:
    """The page reaches the codec through the bundler, not by restating it.

    Before the bundler this asserted the codec's source text appeared verbatim
    in the page, which is the paste-order arrangement issue #234 removed. The
    same guarantee now has two halves: the guide's entry imports the published
    codec, and the page inlines that entry's bundle byte for byte.
    """
    html = _sources_tree_html(tmp_path)
    codec = (TEMPLATE_DIR / "lens-url.mjs").read_text(encoding="utf-8")
    # The entry's own imports are the shell and the page wiring; issue #239 moved
    # the glue that reaches the codec into guide-client.mjs, one edge further
    # down the same import graph.
    client = (TEMPLATE_DIR / "guide-client.mjs").read_text(encoding="utf-8")

    assert "export function encodeLensFragment" in codec
    assert "from './lens-url.mjs'" in client
    assert bundle_entry("guide-entry.mjs", global_name="GuidePage") in html
    assert '<script type="application/json" data-client-payload>' in html
    assert "encodeLensFragment(" in html
    assert "decodeLensFragment(" in html


def test_the_guide_glue_reads_no_state_out_of_rendered_markup(tmp_path: Path) -> None:
    """docs/FRONTEND.md, The data contract: the DOM is write-only projection.

    The guide's module script used to recover three audited values by reading
    the dialog it had just been sent — the candidate display labels, the audited
    candidate order, and the audited accessible summary — and to translate a
    row's publication id into the transport code the payload speaks. Its
    *classic* script read two more: the race label for the share status, and the
    filter scope label for the status line. All six are contract now, so each
    former read is named here: a reintroduced one fails this test rather than
    surviving until a markup change silently moves the behavior.

    The whole client bundle is swept, not one script block. Issue #239 moved
    both blocks into modules, so the page's client code is the bundle the
    template inlines — which is where a reintroduced read would now live.
    """
    client = bundle_entry("guide-entry.mjs", global_name="GuidePage")

    for scrape in (
        # Candidate display labels, read off the dialog's own headings.
        ".race-detail-candidate-title h4",
        # The audited candidate order, captured from server-rendered DOM order.
        ".race-detail-outcomes > [data-race-detail-candidate-id]",
        # The audited accessible summary, captured verbatim for restore.
        '[data-race-detail-summary]")?.textContent',
        # The translation map between our own two identifier spaces.
        "codeBySourceId",
        # The race label for the share status (issue #239).
        '[data-display-role="race-label"]',
        # The filter scope label for the status line (issue #239).
        "selectedOptions",
    ):
        assert scrape not in client, scrape

    # Each one now comes from the payload, which publishes what the server
    # rendered rather than a second computation of it.
    html = _sources_tree_html(tmp_path)
    payload = GuidePayload.model_validate(_client_payload(html))
    assert payload.races
    # A race nobody endorsed renders no candidate sections, so it publishes no
    # candidates either; the two sides agree race by race.
    for race in payload.races:
        assert all(candidate.label for candidate in race.candidates)
        assert race.audited_accessible_summary
        dialog = html.split(f'id="race-detail-{race.race_id}"')[1].split("</dialog>")[0]
        rendered_order = re.findall(r'data-race-detail-candidate-id="([^"]+)"', dialog)
        assert rendered_order == [candidate.candidate_id for candidate in race.candidates]
        # The payload carries the text; the template escapes it on the way out
        # (`Rodney 'Star' Thornley` renders as `Rodney &#39;Star&#39; Thornley`).
        # Compare the decoded markup, so the two sides are held to the same text
        # rather than to one spelling of an entity.
        rendered_text = unescape(dialog)
        for candidate in race.candidates:
            assert f"<h4>{candidate.label}</h4>" in rendered_text
        assert race.audited_accessible_summary in rendered_text
    assert any(race.candidates for race in payload.races)

    # The two reads issue #239 removed, and where their values come from now.
    for race in payload.races:
        assert race.race_label
        card = html.split(f'id="race-{race.race_id}"')[1].split("</article>")[0]
        assert f'data-display-role="race-label">{escape(race.race_label, quote=False)}<' in card

    # One generator for the Ballot filter: the payload publishes exactly the
    # options the select renders, in the same order.
    select = html.split('<select class="filter-select" id="race-filter"')[1].split("</select>")[0]
    rendered = [
        (value, unescape(label))
        for value, label in re.findall(r'<option value="([^"]*)">([^<]*)</option>', select)
    ]
    assert rendered == [(scope.value, scope.label) for scope in payload.filter_scopes]

    # Where the Sources links point, so the module that appends the live lens
    # fragment is not told by the template. Root-relative, like every in-site
    # link, and the same path the rendered anchors carry.
    assert payload.sources_page_path.startswith("/e/")
    assert payload.sources_page_path.endswith("/sources/")
    assert f'href="{payload.sources_page_path}" data-sources-link' in html


def test_the_guide_publishes_exactly_one_payload_element(tmp_path: Path) -> None:
    """One payload element convention across pages (The data contract).

    The guide used to publish two — the lens bindings and, separately, the
    personalization contract — so a reader of the page had to know which held
    what. One element, one model, one schema version.
    """
    html = _sources_tree_html(tmp_path)

    assert html.count('<script type="application/json"') == 1
    assert html.count(PAYLOAD_ELEMENT) == 1
    payload = GuidePayload.model_validate(_client_payload(html))
    assert payload.schema_version == CLIENT_PAYLOAD_SCHEMA_VERSION
    assert payload.personalization is not None


def test_guide_head_carries_the_eyebrow_title_and_tagline(tmp_path: Path) -> None:
    """Issue 177: the live source count belongs to the persistent strip.

    Issue 192: the guide's bespoke hero became the shared page head. It is the
    brand-link target, so it takes the one exception that page buys — the
    masthead's navy runs through the head instead of stopping at the band.
    """
    html = _sources_tree_html(tmp_path)

    head = html.split('<header class="page-head extended">')[1].split("</header>")[0]
    assert 'class="page-eyebrow"' in head
    assert "<h1>Endorsements</h1>" in head
    assert 'class="page-tagline"' in head
    assert 'class="hero-deck"' not in head
    band = html.split('<div class="site-band">')[1].split("</div>")[0]
    assert '/sources/" data-sources-link' in band


def test_sources_links_carry_the_guides_current_fragment(tmp_path: Path) -> None:
    """Issue 108 acceptance criterion: the guide's Sources references must
    carry the guide's current live fragment, not just the bare page URL, so
    Cancel on the sources page can restore exactly what the reader was
    viewing.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    configuration = read_rendering_configuration(RENDERING_CONFIG)
    tallying_codes = sorted(
        source.code for source in view_model.personalization.sources if _tallying_selectable(source)
    )
    fragment = _lens_fragment(view_model, mode="s", source_codes=tuple(tallying_codes[1:]))
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, configuration),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (() => JSON.stringify({
          // The literal attribute, not the DOM-resolved URL: these links are
          // root-relative now (issue 192), so the resolved form depends on the
          // origin the page happens to be served from — which is exactly what
          // this link must not depend on.
          hrefs: [...document.querySelectorAll('[data-sources-link]')]
            .map((link) => link.getAttribute('href')),
        }))()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    expected_href = f"/e/{view_model.metadata.election_id}/sources/#{fragment}"
    assert result["hrefs"]
    assert all(href == expected_href for href in result["hrefs"])


def test_masthead_share_button_uses_web_share_then_falls_back_to_copy(tmp_path: Path) -> None:
    """Issue 66: the share action must degrade cleanly when the Web Share API,

    then the Clipboard API, are unavailable, without letting a declined share
    sheet clobber the status line with a spurious failure message.
    """
    html_path = tmp_path / "guide.html"
    html_path.write_text(_sources_tree_html(tmp_path), encoding="utf-8")
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const pause = () => new Promise((resolve) => setTimeout(resolve, 50));
          const button = document.querySelector('[data-shell-share]');
          const status = document.querySelector('[data-shell-share-status]');

          Object.defineProperty(navigator, 'share', {
            value: (details) => Promise.resolve(details),
            configurable: true,
          });
          button.click();
          await pause();
          const afterShare = status.textContent;

          status.textContent = 'SENTINEL';
          Object.defineProperty(navigator, 'share', {
            value: () => Promise.reject(
              Object.assign(new Error('cancelled'), { name: 'AbortError' })
            ),
            configurable: true,
          });
          button.click();
          await pause();
          const afterCancelledShare = status.textContent;

          Object.defineProperty(navigator, 'share', { value: undefined, configurable: true });
          Object.defineProperty(navigator, 'clipboard', {
            value: { writeText: async () => {} },
            configurable: true,
          });
          button.click();
          await pause();
          const afterClipboardCopy = status.textContent;

          // Headless Chrome over file:// has no clipboard permission or
          // focus/selection context to grant real execCommand('copy') either,
          // so stub it the same way the existing copy-link buttons already
          // do, to exercise the fallback branch deterministically.
          Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
          document.execCommand = () => true;
          button.click();
          await pause();
          const afterExecCommandCopy = status.textContent;

          return JSON.stringify({
            afterShare,
            afterCancelledShare,
            afterClipboardCopy,
            afterExecCommandCopy,
          });
        })()
        """,
    )
    assert result["afterShare"] == "Share menu opened."
    # A declined share sheet is not a failure and must not overwrite the status line.
    assert result["afterCancelledShare"] == "SENTINEL"
    assert result["afterClipboardCopy"] == "Link copied."
    assert result["afterExecCommandCopy"] == "Link copied."


def test_a_comparison_only_candidate_gets_no_section_at_all() -> None:
    """Issue 124: a candidate only the Seattle Times picked is not a guide choice.

    Issue 79 rendered its section and hid it behind `data-times-only`; now the
    section is never built, so nothing about that pick reaches the page.
    """
    view_model = _production_bundle().view_model
    html = render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))
    source_by_id = {source.id: source for source in view_model.sources}

    rendered_candidate_ids = {
        group.candidate_id
        for section in view_model.sections
        for race in section.races
        for group in candidate_endorsement_groups(race)
    }
    endorsed_candidate_ids = {
        group.candidate_id
        for section in view_model.sections
        for race in section.races
        for group in race.endorsement_groups
    }
    assert rendered_candidate_ids == endorsed_candidate_ids

    comparison_only_candidate_ids = {
        candidate_id
        for section in view_model.sections
        for race in section.races
        for cell in race.source_cells
        if source_by_id[cell.source_id].panel_role == "comparison"
        for candidate_id in cell.candidate_ids
    } - endorsed_candidate_ids
    # The production panel has at least one candidate only the comparison source
    # picked; confirm the assertion below is not vacuous.
    assert len(comparison_only_candidate_ids) > 0
    assert "data-times-only" not in html
    for candidate_id in comparison_only_candidate_ids:
        assert f'data-race-detail-candidate-id="{candidate_id}"' not in html


def _personalization_view_model(tmp_path: Path, *, enabled: bool) -> PublicationViewModel:
    """The customize fixture with the lens policy forced to `enabled`."""
    view_model = _view_model(tmp_path)
    policy = view_model.personalization.policy.model_copy(update={"enabled": enabled})
    view_model = view_model.model_copy(
        update={"personalization": view_model.personalization.model_copy(update={"policy": policy})}
    )
    return _revalidated(view_model)


def _personalization_enabled_view_model(tmp_path: Path) -> PublicationViewModel:
    """The customize fixture with the lens policy enabled, for issue 80's UI."""
    return _personalization_view_model(tmp_path, enabled=True)


def _personalization_disabled_view_model(tmp_path: Path) -> PublicationViewModel:
    """The customize fixture with the lens policy disabled.

    The release policy defaults to enabled (issue 82), but the disabled code
    path stays covered in case a future release ever needs to turn it back
    off.
    """
    return _personalization_view_model(tmp_path, enabled=False)


def _evaluate_in_chrome(
    html_path: Path,
    expression: str,
    *,
    mobile_width: int | None = None,
    initial_url: str | None = None,
    viewport: tuple[int, int] | None = None,
    media: str | None = None,
) -> dict[str, Any]:
    """Load one local file in headless Chrome and return one JSON object result.

    A minimal harness for the personalization flow: unlike render_screenshot's
    responsive-interaction probe, this only needs one page load and one script
    evaluation, so it does not share that function's screenshot-capture
    machinery. Pass mobile_width to emulate a narrow CSS viewport first, or
    viewport for an exact desktop-shaped one. Pass initial_url to navigate to
    an already-encoded shared link (query string and/or fragment) instead of
    the bare file, to exercise a load-time restore rather than an in-page
    transition. Pass media="print" to evaluate against the print stylesheet
    (issue 193: the browser's own print output is the printable edition, so
    that is the only place its rules can be measured).
    """
    chrome_path = find_chrome()
    profile = Path(tempfile.mkdtemp(prefix="election-guide-chrome-"))
    try:
        process = subprocess.Popen(
            [
                str(chrome_path),
                "--headless=new",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-extensions",
                "--hide-scrollbars",
                "--no-first-run",
                "--allow-file-access-from-files",
                f"--user-data-dir={profile}",
                "--remote-debugging-port=0",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            port, browser_path = _wait_for_devtools_endpoint(process, profile)
            websocket = create_connection(
                f"ws://127.0.0.1:{port}{browser_path}",
                timeout=30,
                suppress_origin=True,
                http_no_proxy=["127.0.0.1"],
            )
            try:
                cdp = _CdpSocket(websocket)
                target = cdp.command("Target.createTarget", {"url": "about:blank"})
                target_id = cast(str, target["targetId"])
                attached = cdp.command(
                    "Target.attachToTarget", {"targetId": target_id, "flatten": True}
                )
                session_id = cast(str, attached["sessionId"])
                cdp.command("Page.enable", session_id=session_id)
                if mobile_width is not None:
                    cdp.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": mobile_width,
                            "height": 780,
                            "deviceScaleFactor": 1,
                            "mobile": True,
                        },
                        session_id=session_id,
                    )
                elif viewport is not None:
                    cdp.command(
                        "Emulation.setDeviceMetricsOverride",
                        {
                            "width": viewport[0],
                            "height": viewport[1],
                            "deviceScaleFactor": 1,
                            "mobile": False,
                        },
                        session_id=session_id,
                    )
                cdp.command(
                    "Page.navigate",
                    {"url": initial_url or html_path.resolve().as_uri()},
                    session_id=session_id,
                )
                cdp.wait_event("Page.loadEventFired", session_id=session_id)
                if media is not None:
                    cdp.command(
                        "Emulation.setEmulatedMedia",
                        {"media": media},
                        session_id=session_id,
                    )
                evaluated = cdp.command(
                    "Runtime.evaluate",
                    {"expression": expression, "returnByValue": True, "awaitPromise": True},
                    session_id=session_id,
                )
                result = cast(dict[str, object], evaluated["result"])
                if "value" not in result:
                    raise ValueError(f"personalization evaluation failed: {evaluated}")
                return cast(dict[str, Any], json.loads(cast(str, result["value"])))
            finally:
                websocket.close()
        finally:
            _terminate_process(process)
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def test_printing_the_guide_suppresses_chrome_and_keeps_every_race_whole(
    tmp_path: Path,
) -> None:
    """Issue 193: the browser's own print output is the printable edition.

    Measured at the US Letter content box the `@page` margins leave (8.5in
    minus .55in per side, 11in minus .5in per side, at 96dpi), because a
    clipped column only shows up against a real page width.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    expected_races = sum(len(section.races) for section in view_model.sections)

    result = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          const display = (selector) => {
            const element = document.querySelector(selector);
            return element === null ? 'absent' : getComputedStyle(element).display;
          };
          const shown = (selector) => [...document.querySelectorAll(selector)]
            .filter((element) => element.getBoundingClientRect().height > 0).length;
          const cards = [...document.querySelectorAll('.race-card')];
          const pageWidth = document.documentElement.getBoundingClientRect().width;
          return JSON.stringify({
            band: display('.site-band'),
            controls: display('.screen-controls'),
            stickyHeader: display('.sticky-header'),
            skipLink: display('.skip-link'),
            footerActions: display('.site-footer-actions'),
            dialog: display('.race-detail-dialog'),
            pageHeadBackground:
              getComputedStyle(document.querySelector('.page-head')).backgroundColor,
            pageHeadTitle: shown('.page-head h1'),
            electionDay: display('.election-day'),
            gridColumnCount: getComputedStyle(document.querySelector('.race-grid'))
              .gridTemplateColumns.split(' ').length,
            visibleCards: shown('.race-card'),
            visibleRecommendations: shown('.race-card h3'),
            visibleMeters: shown('.screen-meter'),
            clippedCards: cards.filter((card) => card.scrollWidth > card.clientWidth + 1).length,
            overflowingElements: [...document.querySelectorAll('.screen-guide *')]
              .filter((element) => element.getBoundingClientRect().right > pageWidth + 1).length,
            horizontalScroll: document.documentElement.scrollWidth > pageWidth + 1,
            auditVisible: shown('.site-footer-audit') > 0,
          });
        })()
        """,
        viewport=(758, 960),
        media="print",
    )

    # Chrome suppressed: nothing the reader could only have used on screen.
    assert result["band"] == "none"
    assert result["controls"] == "none"
    assert result["stickyHeader"] == "none"
    assert result["skipLink"] == "none"
    assert result["footerActions"] == "none"
    assert result["dialog"] == "none"
    # The shared page head (issue 192) is the guide's navy extended variant on
    # screen; on paper it flattens onto white and keeps its title.
    assert result["pageHeadBackground"] == "rgb(255, 255, 255)"
    assert result["pageHeadTitle"] == 1
    # Slot 4 still states the election day, which a printed guide wants.
    assert result["electionDay"] != "none"
    # Races and recommendations intact.
    assert result["visibleCards"] == expected_races
    assert result["visibleRecommendations"] == expected_races
    assert result["visibleMeters"] == expected_races
    assert result["auditVisible"] is True
    # No clipped columns.
    assert result["gridColumnCount"] == 2
    assert result["clippedCards"] == 0
    assert result["overflowingElements"] == 0
    assert result["horizontalScroll"] is False


def test_phone_dialog_metrics_fit_the_longest_live_content_at_320px(tmp_path: Path) -> None:
    """Issue 150: the metrics column may wrap, but must never escape the dialog."""
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )

    result = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          const row = document.querySelector('.race-detail-candidate');
          const dialog = row.closest('.race-detail-dialog');
          row.querySelector('h4').textContent = 'Sharon Tomiko Santos / Kelabe Tewolde';
          const count = row.querySelector(
            '.race-detail-candidate-metrics > span[data-lens-hidden]'
          );
          count.textContent = '12 of 18 endorsing sources (co-endorsements split)';
          dialog.showModal();
          const box = (element) => element.getBoundingClientRect();
          const dialogBox = box(dialog);
          const meterBox = box(row.querySelector('.race-detail-meter[data-lens-hidden]'));
          const countBox = box(count);
          const titleBox = box(row.querySelector('.race-detail-candidate-title'));
          const actionBox = box(dialog.querySelector('.race-detail-actions'));
          const actionButtons = [...dialog.querySelectorAll('.race-detail-actions button')];
          return JSON.stringify({
            titleWidth: titleBox.width,
            meterWithin: meterBox.left >= dialogBox.left && meterBox.right <= dialogBox.right,
            countWithin: countBox.left >= dialogBox.left && countBox.right <= dialogBox.right,
            actionsWithin: actionBox.left >= dialogBox.left && actionBox.right <= dialogBox.right,
            actionSizes: actionButtons.map((button) => [box(button).width, box(button).height]),
          });
        })()
        """,
        mobile_width=320,
    )

    assert result["titleWidth"] >= 100
    assert result["meterWithin"] is True
    assert result["countWithin"] is True
    assert result["actionsWithin"] is True
    assert result["actionSizes"] == [[40, 40], [40, 40]]


@pytest.mark.parametrize("mobile_width", [320, 375, 414])
def test_phone_dialog_header_keeps_actions_beside_longest_race_title(
    tmp_path: Path, mobile_width: int
) -> None:
    """Issue 174: icon actions stay beside the wrapped title without a dead band."""
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )

    result = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          const dialog = document.querySelector('.race-detail-dialog');
          const header = dialog.querySelector('.race-detail-header');
          const titleBlock = header.firstElementChild;
          const title = titleBlock.querySelector('h3');
          const actions = header.querySelector('.race-detail-actions');
          title.textContent =
            'Seattle Proposition 1 — Property Tax Levy for Seattle Public Library';
          dialog.showModal();
          const box = (element) => element.getBoundingClientRect();
          const before = {
            header: box(header),
            titleBlock: box(titleBlock),
            title: box(title),
            actions: box(actions),
          };
          dialog.scrollTop = Math.min(160, dialog.scrollHeight - dialog.clientHeight);
          const after = box(header);
          return JSON.stringify({
            titleWraps: title.scrollHeight > parseFloat(getComputedStyle(title).lineHeight) * 1.5,
            actionsBesideTitle:
              before.actions.left >= before.titleBlock.right &&
              before.actions.top < before.title.bottom,
            headerHeightBefore: before.header.height,
            headerHeightAfter: after.height,
            headerTopBefore: before.header.top,
            headerTopAfter: after.top,
          });
        })()
        """,
        mobile_width=mobile_width,
    )

    assert result["titleWraps"] is True
    assert result["actionsBesideTitle"] is True
    assert result["headerHeightAfter"] == pytest.approx(result["headerHeightBefore"], abs=0.5)
    assert result["headerTopAfter"] == pytest.approx(result["headerTopBefore"], abs=0.5)


def test_no_majority_lens_state_appears_and_dissolves_with_the_selected_sources(
    tmp_path: Path,
) -> None:
    view_model = _personalization_enabled_view_model(tmp_path)
    source_code_by_id = {source.id: source.code for source in view_model.personalization.sources}
    split_code = source_code_by_id["washington-working-families-party"]
    majority_code = source_code_by_id["the-urbanist"]
    split_fragment = _lens_fragment(view_model, mode="s", source_codes=(split_code,))
    majority_fragment = _lens_fragment(
        view_model,
        mode="s",
        source_codes=tuple(sorted((split_code, majority_code))),
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )

    result = _evaluate_in_chrome(
        html_path,
        f"""
        (async () => {{
          const pause = () => new Promise((resolve) => setTimeout(resolve, 100));
          const card = document.querySelector('[data-publication-race-id="king-county-assessor"]');
          const snapshot = () => {{
            const meter = card.querySelector('[data-lens-result] .screen-meter');
            const pill = card.querySelector('[data-lens-context] .no-majority-pill');
            const kicker = card.querySelector('[data-race-detail-lens-kicker]:not([hidden])');
            return {{
              pillHidden: pill.hidden,
              amberMeter: meter.classList.contains('meter-no-majority'),
              accessibleName: meter.getAttribute('aria-label'),
              kicker: kicker?.textContent ?? null,
            }};
          }};
          await pause();
          const split = snapshot();
          window.location.hash = {json.dumps(majority_fragment)};
          await pause();
          return JSON.stringify({{ split, majority: snapshot() }});
        }})()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{split_fragment}",
    )

    assert result["split"] == {
        "pillHidden": False,
        "amberMeter": True,
        "accessibleName": "No majority. Consensus among explicitly endorsing sources: 50%",
        "kicker": "No majority · Tied for lead",
    }
    assert result["majority"]["pillHidden"] is True
    assert result["majority"]["amberMeter"] is False
    assert not result["majority"]["accessibleName"].startswith("No majority")
    assert result["majority"]["kicker"] == "Leading choice"


def test_full_race_card_stacks_name_and_meter_below_480px(tmp_path: Path) -> None:
    """Issue 151: full view stacks on phones without changing the 480px layout."""
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    expression = """
      (() => {
        const result = document.querySelector('.screen-race-result');
        result.querySelector('h3').textContent = 'Sharon Tomiko Santos / Kelabe Tewolde';
        const meter = result.querySelector('.screen-meter');
        const context = result.nextElementSibling;
        const resultBox = result.getBoundingClientRect();
        const meterBox = meter.getBoundingClientRect();
        return JSON.stringify({
          columns: getComputedStyle(result).gridTemplateColumns.split(' ').length,
          // The context row pins its pill and caption to explicit columns, so
          // one column here means both resets landed: without them the pinned
          // `grid-column: 2` opens an implicit second track and sits the caption
          // beside the pill instead of under it.
          contextColumns: getComputedStyle(context).gridTemplateColumns.split(' ').length,
          resultWidth: resultBox.width,
          meterWidth: meterBox.width,
          captionBelow: context.getBoundingClientRect().top >= resultBox.bottom,
        });
      })()
    """

    phone = _evaluate_in_chrome(html_path, expression, mobile_width=320)
    boundary = _evaluate_in_chrome(html_path, expression, mobile_width=480)

    assert phone["columns"] == 1
    assert phone["contextColumns"] == 1
    assert phone["meterWidth"] == pytest.approx(phone["resultWidth"], abs=1)
    assert phone["captionBelow"] is True
    assert boundary["columns"] == 2
    assert boundary["contextColumns"] == 2


def test_shared_footer_closes_short_viewport_and_follows_tall_content(tmp_path: Path) -> None:
    """Issue 152: the screen frame fills short pages without clipping tall ones."""
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    short = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          document.querySelector('.screen-sections').hidden = true;
          const footer = document.querySelector('.site-footer').getBoundingClientRect();
          const page = document.querySelector('.page').getBoundingClientRect();
          return JSON.stringify({
            footerBottom: footer.bottom,
            pageBottom: page.bottom,
            viewport: innerHeight,
          });
        })()
        """,
    )
    tall = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          const footer = document.querySelector('.site-footer').getBoundingClientRect();
          return JSON.stringify({footerBottom: footer.bottom, viewport: innerHeight});
        })()
        """,
    )

    assert short["footerBottom"] == pytest.approx(short["viewport"], abs=1)
    assert short["pageBottom"] == pytest.approx(short["viewport"], abs=1)
    assert tall["footerBottom"] > tall["viewport"]


def test_shared_footer_keeps_icons_on_row_one_and_provenance_full_width_on_squeeze(
    tmp_path: Path,
) -> None:
    """Issue 179: provenance changes rows without pushing down the icon cluster."""
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    expression = """
      (() => {
        const band = document.querySelector('.site-footer-band');
        const brand = band.querySelector('.site-footer-brand').getBoundingClientRect();
        const audit = band.querySelector('.site-footer-audit').getBoundingClientRect();
        const actions = band.querySelector('.site-footer-actions').getBoundingClientRect();
        const join = band.querySelector('.audit-join');
        const wordmark = band.querySelector('.site-footer-brand > span');
        return JSON.stringify({
          columns: getComputedStyle(band).gridTemplateColumns.split(' ').length,
          brandTop: brand.top,
          brandBottom: brand.bottom,
          brandRight: brand.right,
          actionsTop: actions.top,
          actionsBottom: actions.bottom,
          actionsLeft: actions.left,
          auditTop: audit.top,
          auditWidth: audit.width,
          bandWidth: band.getBoundingClientRect().width,
          joinDisplay: getComputedStyle(join).display,
          wordmarkDisplay: getComputedStyle(wordmark).display,
        });
      })()
    """

    wide = _evaluate_in_chrome(html_path, expression, mobile_width=1200)
    squeezed = _evaluate_in_chrome(html_path, expression, mobile_width=900)
    phone = _evaluate_in_chrome(html_path, expression, mobile_width=390)
    narrow_phone = _evaluate_in_chrome(html_path, expression, mobile_width=320)

    assert wide["columns"] == 3
    assert wide["auditTop"] < wide["brandBottom"]
    assert wide["joinDisplay"] == "none"
    assert squeezed["columns"] == 2
    assert squeezed["actionsTop"] < squeezed["brandBottom"]
    assert squeezed["actionsBottom"] > squeezed["brandTop"]
    assert squeezed["auditTop"] >= squeezed["brandBottom"]
    assert squeezed["auditWidth"] > squeezed["bandWidth"] * 0.85
    assert squeezed["joinDisplay"] == "inline"
    for narrow in (phone, narrow_phone):
        assert narrow["columns"] == 2
        assert narrow["wordmarkDisplay"] == "none"
        assert narrow["brandRight"] <= narrow["actionsLeft"]
        assert narrow["auditTop"] >= narrow["brandBottom"]


def _tallying_selectable(item: PersonalizationCategory | PersonalizationSource) -> bool:
    """Whether item is a selectable, tallying (non-comparison) category or
    source, for tests that specifically want a tallying-only item (e.g. moving
    a source between two tallying categories) rather than any selectable
    item, comparison included."""
    return item.selectable and item.panel_role != "comparison"


def test_personalization_is_invisible_while_the_policy_is_disabled(tmp_path: Path) -> None:
    """Issue 80/81: no tallying selection UI, no reset action, and no per-race
    lens presentation, while disabled. The full bindings payload stays present
    regardless (issue 124): the codec must still be able to recognize a
    pre-removal link's comparison token in order to ignore it.

    The stylesheet carries `[data-lens-only]`/`[data-lens-hidden]` selectors
    unconditionally (an unused selector is harmless with no matching markup),
    and since issue #239 so does the page's one bundle: the lens renderer's
    selectors are string literals in guide-lens.mjs whether or not a payload
    ever hands it a personalization contract. Both are inert without matching
    markup, which is what this sweeps for — the rendered markup only, between
    the stylesheet and the bundle.

    `data-lens-notice` is deliberately excluded from the marker list, and is
    asserted present below instead: since issue #239 a page with the lens
    switched off still has to report a fragment it could not read
    (docs/FRONTEND.md § State and URLs), so the notice element is no longer
    policy-gated.
    """
    view_model = _personalization_disabled_view_model(tmp_path)
    html = render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))
    body = html.split("</style>", 1)[1].split('<script type="module">', 1)[0]

    for marker in (
        "data-sources-reset",
        "data-sources-source",
        "data-sources-category-toggle",
        "data-lens-banner",
        "data-lens-only",
        "data-lens-hidden",
        "data-race-detail-lens",
        "data-lens-detail-summary",
        "data-lens-detail-audited",
        "data-lens-detail-sources",
        "data-comparison-lens",
        "data-race-detail-lens-kicker",
        "data-race-detail-lens-count",
        "data-race-detail-lens-meter",
        "data-race-detail-not-counted",
    ):
        assert marker not in body

    # The contract itself is withheld while the policy is disabled: nothing on
    # the page can rescore, so publishing it would ship a contract no code reads.
    assert _client_payload(html)["personalization"] is None
    # The payload notice is not lens furniture: a page with the lens switched
    # off still admits a payload, so it still has to be able to say when it
    # could not (docs/FRONTEND.md, The data contract). The lens notice is the
    # same argument for the fragment: an unreadable link is cleaned from the
    # address bar, and the rule requires the reader be told why (issue #239).
    assert "data-payload-notice" in body
    assert "data-lens-notice" in body

    # Issue #248: the sources page's tree is a lit region now, so the switch has
    # to reach the payload as well as the markup. An empty tree is what stops
    # the client taking the region over and rendering the checkboxes this
    # template deliberately withheld.
    sources_html = render_sources_document(
        view_model, public_site_url="https://seattleelections.guide"
    )
    sources_body = sources_html.split("</style>", 1)[1].split('<script type="module">', 1)[0]
    assert "data-sources-source=" not in sources_body
    assert "data-sources-category-toggle=" not in sources_body
    assert _client_payload(sources_html)["tree"] == []

    # Issue 124: the bindings still publish every category and source,
    # including the comparison one, so the codec can classify a pre-removal
    # link's token and drop it rather than reject the whole link.
    bindings = _client_payload(html)
    assert "comparison" in {item["panel_role"] for item in bindings["categories"]}
    assert "comparison" in {item["panel_role"] for item in bindings["sources"]}
    assert len(bindings["categories"]) == len(view_model.personalization.categories)


def test_a_comparison_token_is_inert_while_the_policy_is_disabled(
    tmp_path: Path,
) -> None:
    """Issue 124: a pre-removal link is not an error, even with no lens policy.

    Issue 96 made the Times toggle readable from an incoming fragment while
    personalization was disabled. Nothing acts on that token any more, so the
    only requirement left is that the link is neither rejected nor rewritten:
    the address bar keeps it verbatim and the page shows the audited guide.
    """
    view_model = _personalization_disabled_view_model(tmp_path)
    comparison_code = next(
        source.code
        for source in view_model.personalization.sources
        if source.panel_role == "comparison"
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    fragment = _lens_fragment(view_model, mode="s", source_codes=(comparison_code,))
    result = _evaluate_in_chrome(
        html_path,
        "JSON.stringify({hash: window.location.hash})",
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )

    assert result["hash"] == f"#{fragment}"


def test_personalization_ordinary_anchor_survives_initial_load_while_disabled(
    tmp_path: Path,
) -> None:
    """An initial load carrying a plain in-page anchor (e.g. the skip link's
    target) decodes the same way a malformed lens fragment would, but must
    survive untouched even while the personalization policy is disabled,
    matching the enabled branch's own exclusion for this exact case.
    """
    view_model = _personalization_disabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        "JSON.stringify({ hash: window.location.hash })",
        initial_url=f"{html_path.resolve().as_uri()}#guide-races",
    )
    assert result["hash"] == "#guide-races"


def test_personalization_bindings_include_every_selectable_category_and_source(
    tmp_path: Path,
) -> None:
    """Issue 97/108: every selectable tallying category/source, plus the
    comparison category/source (which predates and is independent of the
    tallying selection, per issue 96/97), still flows through the lens
    bindings payload even though the guide itself no longer renders any of
    it as an interactive tree — that tree now lives on the dedicated sources
    page (issue 107), which has its own equivalent coverage."""
    view_model = _personalization_enabled_view_model(tmp_path)
    html = render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG))
    contract = view_model.personalization

    selectable_categories = [item for item in contract.categories if _tallying_selectable(item)]
    selectable_sources = [item for item in contract.sources if _tallying_selectable(item)]
    assert len(selectable_categories) > 0
    assert len(selectable_sources) > 0

    bindings = _client_payload(html)
    assert len(bindings["categories"]) == len(contract.categories)
    assert len(bindings["sources"]) == len(contract.sources)
    assert {item["code"] for item in bindings["sources"]} == {
        source.code for source in contract.sources
    }
    assert {item["code"] for item in bindings["categories"]} == {
        category.code for category in contract.categories
    }


def test_personalization_initial_my_sources_matches_audited_consensus(tmp_path: Path) -> None:
    """Issue 80/97 acceptance criterion: the initial selection already equals
    the audited consensus. Issue 97 removed the audited/my-sources mode
    switch entirely, so there is no longer a mode to enter — every tallying
    source already counts and no comparison source counts, which is by
    definition the default (non-personalized) selection.

    Issue 108 removed the guide's own checkboxes entirely (module-scoped
    bindings inside the page's own `<script type="module">` were already not
    reachable from an injected Runtime.evaluate expression, since they are
    not global), so this observes the page's own computed summary/banner
    output rather than DOM checkbox state or calling scoreSelection from
    outside the page. The claim that scoring the full selectable panel
    reproduces the audited consensus exactly is lens-score.mjs's own tested
    contract (issue 77, "the full selectable panel reproduces the audited
    published consensus"); this test proves only that the page's initial
    render already reaches that full-panel selection, which is the part
    issue 80/97/108 own.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          summaryPresent: document.querySelector('[data-sources-summary-count]') !== null,
          personalized: document.documentElement.classList.contains('lens-personalized'),
          bannerHidden: document.querySelector('[data-lens-banner]').hidden,
          bannerText: document.querySelector('[data-lens-banner-status]').textContent,
        })
        """,
    )
    # The footer summary stays removed, but the live source state and edit path
    # are now always present in the sticky strip.
    assert result["summaryPresent"] is False
    assert result["personalized"] is False
    assert result["bannerHidden"] is False
    tallying_count = len(
        [source for source in view_model.personalization.sources if _tallying_selectable(source)]
    )
    assert result["bannerText"] == f"Counting all {tallying_count} sources."


def test_sources_strip_keeps_the_same_geometry_between_default_and_lens_states(
    tmp_path: Path,
) -> None:
    view_model = _personalization_enabled_view_model(tmp_path)
    tallying_codes = sorted(
        source.code for source in view_model.personalization.sources if _tallying_selectable(source)
    )
    fragment = _lens_fragment(view_model, mode="s", source_codes=tuple(tallying_codes[1:]))
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    expression = """
      (() => {
        const banner = document.querySelector('[data-lens-banner]');
        const sticky = document.querySelector('.sticky-header');
        return JSON.stringify({
          bannerHeight: banner.getBoundingClientRect().height,
          stickyHeight: sticky.getBoundingClientRect().height,
          bannerHidden: banner.hidden,
          bannerText: banner.querySelector('[data-lens-banner-status]').textContent,
        });
      })()
    """

    default = _evaluate_in_chrome(html_path, expression)
    personalized = _evaluate_in_chrome(
        html_path,
        expression,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )

    assert default["bannerHidden"] is False
    assert personalized["bannerHidden"] is False
    assert default["bannerText"] == f"Counting all {len(tallying_codes)} sources."
    assert personalized["bannerText"] == (
        f"Counting {len(tallying_codes) - 1} of {len(tallying_codes)} sources."
    )
    assert personalized["bannerHeight"] == pytest.approx(default["bannerHeight"], abs=0.5)
    assert personalized["stickyHeight"] == pytest.approx(default["stickyHeight"], abs=0.5)


def test_personalization_reactive_banner_appends_below_the_controls_not_over_them(
    tmp_path: Path,
) -> None:
    """Issue 103 acceptance criterion: with a non-default selection active,
    the reactive banner must stack below the sticky filter controls rather
    than covering them. Both were independently `position: sticky; top: 0`,
    which made them compete for the same stuck position; they must now share
    one sticky ancestor so normal document flow keeps them stacked.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    tallying_codes = sorted(
        source.code for source in view_model.personalization.sources if _tallying_selectable(source)
    )
    fragment = _lens_fragment(view_model, mode="s", source_codes=tuple(tallying_codes[1:]))
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          window.scrollTo(0, 2000);
          await new Promise((resolve) => setTimeout(resolve, 60));
          const controls = document.querySelector('.screen-controls');
          const banner = document.querySelector('[data-lens-banner]');
          const controlsRect = controls.getBoundingClientRect();
          const bannerRect = banner.getBoundingClientRect();
          return JSON.stringify({
            bannerHidden: banner.hidden,
            bannerBelowControls: bannerRect.top >= controlsRect.bottom - 1,
            bannerText: banner.querySelector('[data-lens-banner-status]').textContent,
            editSourcesHref: banner.querySelector('[data-sources-link]').href,
            background: getComputedStyle(banner).backgroundColor,
          });
        })()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["bannerHidden"] is False
    assert result["bannerBelowControls"] is True
    assert result["bannerText"].startswith("Counting ")
    assert result["editSourcesHref"].endswith(f"/sources/#{fragment}")
    assert result["background"] == "rgb(16, 42, 67)"


def test_race_detail_dialog_history_back_and_forward_restore_open_state(
    tmp_path: Path,
) -> None:
    """A race-detail dialog's own permalink is pushed as a distinct history
    entry (unrelated to source selection, which issue 108 removed from the
    guide's history entirely), so back()/forward() must still open and close
    the dialog correctly.
    """
    view_model = _view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const pause = () => new Promise((resolve) => setTimeout(resolve, 60));
          // A same-page history navigation is asynchronous in headless Chrome
          // and its exact settling time is not guaranteed, so poll for the
          // expected outcome instead of trusting a single fixed-length pause.
          const waitUntil = async (predicate, { timeoutMs = 2000, stepMs = 30 } = {}) => {
            const deadline = Date.now() + timeoutMs;
            while (Date.now() < deadline) {
              if (predicate()) return true;
              await new Promise((resolve) => setTimeout(resolve, stepMs));
            }
            return predicate();
          };
          const isOpen = () => document.querySelector('[data-race-detail-dialog][open]') !== null;
          const link = document.querySelector('[data-race-detail-link]');
          link.click();
          await waitUntil(isOpen);
          const openedHash = window.location.hash;
          const openedAfterPush = isOpen();

          history.back();
          await waitUntil(() => !isOpen());
          const closedAfterBack = !isOpen();
          const hashAfterBack = window.location.hash;

          history.forward();
          await waitUntil(isOpen);
          await pause();
          const openedAfterForward = isOpen();

          return JSON.stringify({
            openedHash,
            openedAfterPush,
            closedAfterBack,
            hashAfterBack,
            openedAfterForward,
          });
        })()
        """,
    )
    assert result["openedHash"] != ""
    assert result["openedAfterPush"] is True
    assert result["closedAfterBack"] is True
    assert result["hashAfterBack"] == ""
    assert result["openedAfterForward"] is True


def test_race_detail_dialog_preserves_an_active_lens_through_open_close_and_share(
    tmp_path: Path,
) -> None:
    """Issue 142 acceptance criteria: opening a race-detail dialog while a
    personalized lens is active must not clobber the lens out of the address
    bar. Both routing schemes share `window.location.hash` (the dialog's own
    permalink predates the lens by issues 62/73/86), so opening must compose
    rather than overwrite, closing must strip only the race segment, and the
    dialog's own "Share link" button must reproduce both the lens and the
    open race rather than whatever the bare per-race fragment used to be.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    tallying_codes = sorted(
        source.code for source in view_model.personalization.sources if _tallying_selectable(source)
    )
    personalized_codes = tallying_codes[1:]
    first_race_label = view_model.sections[0].races[0].race_label
    fragment = _lens_fragment(view_model, mode="s", source_codes=tuple(personalized_codes))
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          window.addEventListener('unhandledrejection', (event) => {
            window.__shareError = String(event.reason?.stack || event.reason);
          });
          const link = document.querySelector('[data-race-detail-link]');
          link.click();
          await pause(80);
          const hashAfterOpen = window.location.hash;

          Object.defineProperty(navigator, 'share', {
            value: async (payload) => { window.__shared = payload; },
            configurable: true,
          });
          const shareButton = document.querySelector('[data-copy-race-link]');
          shareButton.click();
          await pause(80);
          const nativeSharedLink = window.__shared?.url || null;
          const nativeSharedTitle = window.__shared?.title || null;

          Object.defineProperty(navigator, 'share', { value: undefined, configurable: true });
          Object.defineProperty(navigator, 'clipboard', {
            value: { writeText: async (text) => { window.__copied = text; } },
            configurable: true,
          });
          shareButton.click();
          await pause(80);
          const copiedLink = window.__copied;

          document.querySelector('[data-close-race-detail]').click();
          await pause(80);
          const hashAfterClose = window.location.hash;
          const isOpenAfterClose =
            document.querySelector('[data-race-detail-dialog][open]') !== null;

          return JSON.stringify({
            hashAfterOpen, nativeSharedLink, nativeSharedTitle, copiedLink,
            shareError: window.__shareError || null,
            hashAfterClose, isOpenAfterClose,
          });
        })()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["shareError"] is None, result["shareError"]
    assert "sel=" in result["hashAfterOpen"]
    assert "race=" in result["hashAfterOpen"]
    assert "sel=" in result["nativeSharedLink"]
    assert "race=" in result["nativeSharedLink"]
    assert result["nativeSharedTitle"] == first_race_label
    assert result["copiedLink"] == result["nativeSharedLink"]
    assert result["isOpenAfterClose"] is False
    assert "sel=" in result["hashAfterClose"]
    assert "race=" not in result["hashAfterClose"]


def test_race_detail_dialog_history_back_and_forward_preserve_an_active_lens(
    tmp_path: Path,
) -> None:
    """Issue 142 acceptance criterion 4, under the exact scenario this ticket
    exists to fix: back()/forward() must still open and close the
    race-detail dialog correctly while a personalized lens is active, and
    going back must restore the lens-only fragment (no stale race target)
    rather than clearing the hash outright, unlike the no-lens case covered
    by test_race_detail_dialog_history_back_and_forward_restore_open_state.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    tallying_codes = sorted(
        source.code for source in view_model.personalization.sources if _tallying_selectable(source)
    )
    personalized_codes = tallying_codes[1:]
    fragment = _lens_fragment(view_model, mode="s", source_codes=tuple(personalized_codes))
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const waitUntil = async (predicate, { timeoutMs = 2000, stepMs = 30 } = {}) => {
            const deadline = Date.now() + timeoutMs;
            while (Date.now() < deadline) {
              if (predicate()) return true;
              await new Promise((resolve) => setTimeout(resolve, stepMs));
            }
            return predicate();
          };
          const isOpen = () => document.querySelector('[data-race-detail-dialog][open]') !== null;
          const link = document.querySelector('[data-race-detail-link]');
          link.click();
          await waitUntil(isOpen);
          const openedHash = window.location.hash;

          history.back();
          await waitUntil(() => !isOpen());
          const hashAfterBack = window.location.hash;

          history.forward();
          await waitUntil(isOpen);
          const hashAfterForward = window.location.hash;
          const openedAfterForward = isOpen();

          return JSON.stringify({
            openedHash, hashAfterBack, hashAfterForward, openedAfterForward,
          });
        })()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert "sel=" in result["openedHash"] and "race=" in result["openedHash"]
    assert "sel=" in result["hashAfterBack"]
    assert "race=" not in result["hashAfterBack"]
    assert result["openedAfterForward"] is True
    assert "sel=" in result["hashAfterForward"] and "race=" in result["hashAfterForward"]


def test_race_detail_dialog_fragment_reload_restores_lens_and_reopens_dialog(
    tmp_path: Path,
) -> None:
    """Issue 142 acceptance criterion: a link produced while a race-detail
    dialog is open and a lens is active (a refresh, or a copied/shared URL)
    must restore both the personalized selection and the open dialog on
    load, not just one or the other.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    tallying_codes = sorted(
        source.code for source in view_model.personalization.sources if _tallying_selectable(source)
    )
    personalized_codes = tallying_codes[1:]
    fragment = _lens_fragment(view_model, mode="s", source_codes=tuple(personalized_codes))
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    opened = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          document.querySelector('[data-race-detail-link]').click();
          await pause(80);
          return JSON.stringify({ hash: window.location.hash });
        })()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    combined_hash = opened["hash"]
    reloaded = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          bannerHidden: document.querySelector('[data-lens-banner]').hidden,
          bannerText: document.querySelector('[data-lens-banner-status]').textContent,
          isOpen: document.querySelector('[data-race-detail-dialog][open]') !== null,
        })
        """,
        initial_url=f"{html_path.resolve().as_uri()}{combined_hash}",
    )
    assert reloaded["bannerHidden"] is False
    assert (
        reloaded["bannerText"]
        == f"Counting {len(personalized_codes)} of {len(tallying_codes)} sources."
    )
    assert reloaded["isOpen"] is True


def test_personalization_shared_link_restores_the_same_version_selection(tmp_path: Path) -> None:
    """Issue 80/97/108 scope: a link that already encodes a personalized
    selection must restore that exact selection on load — the only path
    left now that the guide has no interactive control of its own, since a
    shared/returned link's fragment is applied once, at script start
    (applySelection(lensState())).
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    tallying_codes = sorted(
        source.code for source in view_model.personalization.sources if _tallying_selectable(source)
    )
    expected_codes = tallying_codes[1:]
    fragment = _lens_fragment(view_model, mode="s", source_codes=tuple(expected_codes))
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    shared_url = f"{html_path.resolve().as_uri()}?edition=compact#{fragment}"
    result = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          bannerHidden: document.querySelector('[data-lens-banner]').hidden,
          bannerText: document.querySelector('[data-lens-banner-status]').textContent,
          search: window.location.search,
        })
        """,
        initial_url=shared_url,
    )
    assert result["bannerHidden"] is False
    assert (
        result["bannerText"] == f"Counting {len(expected_codes)} of {len(tallying_codes)} sources."
    )
    assert result["search"] == "?edition=compact"


# Issue 81: per-race personalized presentation and audited divergence.


def test_personalization_full_panel_selection_shows_no_divergent_comparison(tmp_path: Path) -> None:
    """Issue 81/97 acceptance criterion: an unchanged race stays free of
    redundant audited detail. Issue 97 derives "personalized" from whether
    the live selection differs from the full default panel
    (`isDefaultSelection()`), so the full selectable panel — every tallying
    checkbox checked, no comparison checkbox checked — is simply the page's
    own initial state and is never itself flagged personalized: those values
    would be numerically identical to audited by construction (issue 77's
    tested contract), so a distinct personalized label would add nothing.
    This verifies that plain, single audited detail is what actually shows
    on that initial state, not a duplicated or divergent comparison.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const cards = [...document.querySelectorAll('.race-card')];
          const personalized = document.documentElement.classList.contains('lens-personalized');
          // Issue #248: the reference bar is divergence-only markup now, so
          // the audited page renders no element at all rather than a hidden one.
          const anyComparisonShown = cards.some(
            (card) => card.querySelector('[data-lens-foot] .lens-comparison') !== null,
          );
          const firstCard = cards[0];
          return JSON.stringify({
            cardCount: cards.length,
            personalized,
            anyComparisonShown,
            recommendationText: firstCard
              .querySelector('[data-display-role="recommendation"]').textContent,
          });
        })()
        """,
    )
    assert result["cardCount"] > 0
    assert result["personalized"] is False
    assert result["anyComparisonShown"] is False
    assert result["recommendationText"] != ""


def test_personalization_divergent_race_discloses_a_compact_comparison_and_full_detail(
    tmp_path: Path,
) -> None:
    """Issue 81/97/108 acceptance criteria: every defined divergence dimension
    is detected from structured values, a divergent card shows a compact
    audited comparison, and the race detail panel discloses complete
    audited/personalized values, contributing sources, and inclusion
    reasons. Narrowing the real production panel to one category's own
    sources (via an incoming fragment naming only that category's member
    codes, the same shape a returned sources-page link would carry) is
    virtually certain to push some races below the minimum-explicit-sources
    threshold, diverging their recommendation state from the full default
    panel.
    """
    view_model = _production_bundle().view_model
    enabled_policy = view_model.personalization.policy.model_copy(update={"enabled": True})
    view_model = view_model.model_copy(
        update={
            "personalization": view_model.personalization.model_copy(
                update={"policy": enabled_policy}
            )
        }
    )
    first_category = next(
        category
        for category in view_model.personalization.categories
        if _tallying_selectable(category)
    )
    fragment = _lens_fragment(
        view_model, mode="s", source_codes=tuple(first_category.member_source_codes)
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    selected_codes_json = json.dumps(list(first_category.member_source_codes))
    result = _evaluate_in_chrome(
        html_path,
        f"""
        (async () => {{
          const selectedCodes = new Set({selected_codes_json});
          const shown = (el) => el !== null && getComputedStyle(el).display !== 'none';
          const cards = [...document.querySelectorAll('.race-card')];
          // The reference bar exists only on a card that diverges (issue #248).
          const bar = (card) => card.querySelector('[data-lens-foot] .lens-comparison');
          const divergent = cards.find((card) => bar(card) !== null);
          const unchanged = cards.find((card) => bar(card) === null);
          let detail = null;
          if (divergent) {{
            divergent.querySelector('[data-race-detail-link]').click();
            await new Promise((resolve) => setTimeout(resolve, 50));
            const dialog = divergent.querySelector('[data-race-detail-dialog]');
            // I56: the dialog's "My sources" summary section is deleted
            // outright; neither of its two query-only elements exists at all.
            const deletedElementsGone =
              dialog.querySelector('[data-lens-detail-summary]') === null
              && dialog.querySelector('[data-lens-detail-sources]') === null
              && dialog.querySelector('[data-race-detail-lens]') === null;
            const noMySourcesHeading = ![...dialog.querySelectorAll('h4')].some(
              (heading) => heading.textContent === 'My sources',
            );
            const cardShareText = divergent.querySelector(
              '[data-lens-result] .screen-meter strong',
            )?.textContent;
            const sections = [...dialog.querySelectorAll('[data-race-detail-candidate-id]')];
            // I56 hard invariant: every visible per-candidate meter equals the
            // card's own lens share — no quantity appears with two values.
            const visibleLensMeterShares = sections
              .map((section) => section.querySelector('[data-race-detail-lens-meter]'))
              .filter((meter) => shown(meter))
              .map((meter) => (
                meter.querySelector('[data-race-detail-lens-meter-text]')?.textContent
              ));
            // Every audited (pre-lens) count/meter/kicker in the dialog is
            // hidden while the lens is active — the personalized twin is the
            // only one visible.
            const auditedElementsHidden = sections.every((section) => (
              [...section.querySelectorAll('[data-lens-hidden]')].every((el) => !shown(el))
            ));
            // I56: an unselected source's row stays in place, visibly
            // de-emphasized and marked "Not counted"; a selected source's row
            // never carries that mark. Checked against every actual row
            // rather than merely asserting one exists either way.
            const rowMarkingCorrect = sections.every((section) => (
              [...section.querySelectorAll('[data-endorsed-candidate-id]')]
                .every((row) => {{
                  const badge = row.querySelector('[data-race-detail-not-counted]');
                  const marked = shown(badge);
                  return marked === !selectedCodes.has(row.dataset.raceDetailSourceCode);
                }})
            ));
            detail = {{
              deletedElementsGone,
              noMySourcesHeading,
              auditedHidden: dialog.querySelector('[data-lens-detail-audited]').hidden,
              auditedText: dialog.querySelector('[data-lens-detail-audited]').textContent,
              cardShareText,
              visibleLensMeterShares,
              auditedElementsHidden,
              rowMarkingCorrect,
              candidateSectionCount: sections.length,
            }};
          }}
          const divergentComparison = divergent === undefined ? null : bar(divergent);
          return JSON.stringify({{
            hasDivergent: divergent !== undefined,
            hasUnchanged: unchanged !== undefined,
            // H38: the caption itself carries the lens state now that the
            // per-card "My sources" pill is retired — no separate badge
            // element exists to query.
            divergentSupportText: divergent?.querySelector(
              '[data-lens-context] .support-full',
            )?.textContent,
            divergentSupportCompactText: divergent?.querySelector(
              '[data-lens-context] .support-compact',
            )?.textContent,
            divergentComparisonText: divergentComparison?.textContent,
            divergentComparisonRole: divergentComparison?.getAttribute('role'),
            divergentComparisonAriaLabel: divergentComparison?.getAttribute('aria-label'),
            divergentComparisonToned: Boolean(
              divergentComparison?.classList.contains('lens-comparison-differs')
              || divergentComparison?.classList.contains('lens-comparison-agrees'),
            ),
            unchangedComparisonAbsent: unchanged === undefined ? null : bar(unchanged) === null,
            detail,
          }});
        }})()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["hasDivergent"] is True, (
        "expected at least one production race to diverge from the full-panel audited baseline"
    )
    # H38: the caption carries the lens state — "Based on N of M selected
    # sources" — instead of a separate per-card "My sources" pill.
    assert re.match(r"Based on \d+ of \d+ selected sources", result["divergentSupportText"])
    assert re.match(r"\d+ of \d+ selected", result["divergentSupportCompactText"])
    assert "My sources" not in result["divergentSupportText"]
    assert "All sources:" in result["divergentComparisonText"]
    # Item G27: tone tint is never the sole agree/differ carrier — the bar is
    # a named group whose accessible label states the agreement in words.
    assert result["divergentComparisonRole"] == "group"
    assert result["divergentComparisonAriaLabel"].startswith(
        ("All sources agree with your selection.", "All sources differ from your selection.")
    )
    assert result["divergentComparisonToned"] is True
    detail = result["detail"]
    assert detail["deletedElementsGone"] is True
    assert detail["noMySourcesHeading"] is True
    assert detail["auditedHidden"] is False
    assert "All sources:" in detail["auditedText"]
    assert detail["candidateSectionCount"] > 0
    assert detail["auditedElementsHidden"] is True
    assert detail["rowMarkingCorrect"] is True
    # I56 hard invariant: no quantity appears with two values — every visible
    # per-candidate meter in the dialog equals the card's own lens share.
    assert detail["visibleLensMeterShares"], (
        "expected at least one visible personalized leader meter"
    )
    for share_text in detail["visibleLensMeterShares"]:
        assert share_text == detail["cardShareText"]
    if result["hasUnchanged"]:
        assert result["unchangedComparisonAbsent"] is True


def test_race_detail_dialog_reflects_the_active_lens_leader_not_the_audited_default(
    tmp_path: Path,
) -> None:
    """Ticket #141: five dialog defects found during epic #128's closeout
    acceptance sweep, exercised together against the exact live example the
    ticket itself reports — deselecting every `labor`-category source on
    `ld-11-state-representative-1` flips the leader from the audited default
    (David Hackney) to Ashley Fedan (67%), a genuine two-candidate leader
    change rather than a mere Insufficient-grade divergence.

    1. The candidate section DOM order follows the lens-personalized leader,
       not the audited default order baked into the server-rendered HTML.
    2. The confidence-flag UI is gone from every user-facing surface (the
       underlying `confidence_warning`/`warning_codes` data model is
       untouched elsewhere; this only checks presentation markers).
    3. The "All sources" reference bar renders immediately after the last
       candidate block, matching #131's own card-foot pattern.
    4. Only the currently-displayed leader's section ever shows a meter
       element; every other candidate section has none at all — not an
       empty, unfilled one.
    5. The dialog's aria-describedby summary is recomputed to state the
       personalized result, not left frozen at the audited default.
    """
    view_model = _production_bundle().view_model
    enabled_policy = view_model.personalization.policy.model_copy(update={"enabled": True})
    view_model = view_model.model_copy(
        update={
            "personalization": view_model.personalization.model_copy(
                update={"policy": enabled_policy}
            )
        }
    )
    labor_category = next(
        category for category in view_model.personalization.categories if category.id == "labor"
    )
    labor_members = set(labor_category.member_source_codes)
    contributing_ids = {
        source.id for source in view_model.sources if source.contribution_status == "contributing"
    }
    selection = tuple(
        source.code
        for source in view_model.personalization.sources
        if _tallying_selectable(source)
        and source.id in contributing_ids
        and source.code not in labor_members
    )
    fragment = _lens_fragment(view_model, mode="s", source_codes=selection)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    race_id_json = json.dumps("ld-11-state-representative-1")
    result = _evaluate_in_chrome(
        html_path,
        f"""
        (async () => {{
          const shown = (el) => el !== null && getComputedStyle(el).display !== 'none';
          const raceId = {race_id_json};
          const card = document.querySelector(`[data-publication-race-id="${{raceId}}"]`);
          const recommendation = card.querySelector(
            '[data-lens-result] [data-display-role="recommendation"]',
          )?.textContent;
          card.querySelector('[data-race-detail-link]').click();
          await new Promise((resolve) => setTimeout(resolve, 50));
          const dialog = card.querySelector('[data-race-detail-dialog]');
          const sections = [...dialog.querySelectorAll('[data-race-detail-candidate-id]')];
          const domOrder = sections.map((section) => section.dataset.raceDetailCandidateId);
          const leaderSection = sections.find(
            (section) => section.querySelector('[data-race-detail-lens-kicker]')?.hidden === false,
          );
          const meters = sections.map((section) => ({{
            candidateId: section.dataset.raceDetailCandidateId,
            meterShown: shown(section.querySelector('[data-race-detail-lens-meter]')),
          }}));
          const outcomes = dialog.querySelector('.race-detail-outcomes');
          const children = [...outcomes.children];
          const lastCandidateIndex = children
            .map((child) => child.hasAttribute('data-race-detail-candidate-id'))
            .lastIndexOf(true);
          const barIndex = children.findIndex(
            (child) => child.hasAttribute('data-lens-detail-audited'),
          );
          const summaryEl = document.getElementById(`race-detail-summary-${{raceId}}`);
          const summaryText = summaryEl?.textContent;
          return JSON.stringify({{
            recommendation,
            domOrder,
            leaderCandidateId: leaderSection?.dataset.raceDetailCandidateId,
            meters,
            barIndex,
            lastCandidateIndex,
            summaryText,
            confidenceMarkersPresent: document.body.innerHTML.includes('confidence-note')
              || document.body.innerHTML.includes('Confidence flag'),
          }});
        }})()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["recommendation"] == "Ashley Fedan", (
        "expected the crafted lens to flip the leader to Ashley Fedan, matching the ticket's "
        "own live example"
    )
    assert len(result["domOrder"]) >= 2
    # Item 1: DOM order follows the active lens leader.
    assert result["leaderCandidateId"] is not None
    assert result["domOrder"][0] == result["leaderCandidateId"]
    assert result["domOrder"][0].endswith("ashley-fedan")
    # Item 4: exactly the leader's section shows a meter; no other section
    # shows even an empty one.
    assert result["meters"], "expected at least one candidate section"
    for meter in result["meters"]:
        assert meter["meterShown"] == (meter["candidateId"] == result["leaderCandidateId"])
    # Item 3: the reference bar sits immediately after the last candidate
    # section, matching the card's own I39 foot placement.
    assert result["barIndex"] == result["lastCandidateIndex"] + 1
    # Item 2: no confidence-flag UI marker survives anywhere on the page.
    assert result["confidenceMarkersPresent"] is False
    # Item 5: the hidden accessible summary matches the displayed result.
    assert result["summaryText"].startswith("Ashley Fedan.")
    assert "David Hackney" not in result["summaryText"]


def test_personalization_compact_caption_shows_only_the_lens_short_form(tmp_path: Path) -> None:
    """H34 + H38 interaction: in compact mode, while a lens is active on a
    divergent race, exactly the short caption must be visible, and it must be
    carrying the lens's own text ("N of M selected") rather than the audited
    sentence.

    Issue #248 retired the lens-only caption twins, so there is one full
    caption and one compact caption per card and the only toggle left is the
    full/compact one (guide.css). What this proves is that the surviving pair
    still resolves the way it did when four elements were involved: the
    compact one visible, the full one not, and the visible text the lens's.
    """
    view_model = _production_bundle().view_model
    enabled_policy = view_model.personalization.policy.model_copy(update={"enabled": True})
    view_model = view_model.model_copy(
        update={
            "personalization": view_model.personalization.model_copy(
                update={"policy": enabled_policy}
            )
        }
    )
    first_category = next(
        category
        for category in view_model.personalization.categories
        if _tallying_selectable(category)
    )
    fragment = _lens_fragment(
        view_model, mode="s", source_codes=tuple(first_category.member_source_codes)
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const pause = () => new Promise((resolve) => setTimeout(resolve, 50));
          await pause();
          document.documentElement.classList.add('compact-ballot-mode');
          const cards = [...document.querySelectorAll('.race-card')];
          const divergent = cards.find(
            (card) => card.querySelector('[data-lens-foot] .lens-comparison') !== null,
          );
          const displayOf = (el) => (el ? getComputedStyle(el).display : null);
          const caption = (form) => divergent?.querySelector(
            `[data-lens-context] .support-line.support-${form}`,
          );
          return JSON.stringify({
            hasDivergent: divergent !== undefined,
            captionCount: divergent
              ? divergent.querySelectorAll('[data-lens-context] .support-line').length
              : null,
            fullDisplay: displayOf(caption('full')),
            compactDisplay: displayOf(caption('compact')),
            fullText: caption('full')?.textContent,
            compactText: caption('compact')?.textContent,
          });
        })()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["hasDivergent"] is True, (
        "expected at least one production race to diverge from the full-panel audited baseline"
    )
    # One caption per form, not two: the lens-only twins are gone.
    assert result["captionCount"] == 2
    assert result["fullDisplay"] == "none"
    assert result["compactDisplay"] == "block"
    assert re.match(r"\d+ of \d+ selected", result["compactText"])
    assert re.match(r"Based on \d+ of \d+ selected sources", result["fullText"])


def _lens_fragment(
    view_model: PublicationViewModel,
    *,
    mode: str,
    category_codes: tuple[str, ...] = (),
    source_codes: tuple[str, ...] = (),
    data_version: str | None = None,
    scoring_id: str | None = None,
) -> str:
    """Hand-encode a lens fragment in the exact parameter shape lens-url.mjs
    reads.

    Used only to construct a shared link the codec would never itself
    produce (a cross-version or malformed one), since there is no Python
    binding to call the JS codec directly.
    """
    contract = view_model.personalization
    selection = "".join(sorted({*category_codes, *source_codes}))
    params = {
        "lens": "2",
        "mode": mode,
        "panel": contract.panel_id,
        "ph": contract.panel_hash[:12],
        "data": data_version if data_version is not None else view_model.metadata.data_version,
        "scoring": scoring_id if scoring_id is not None else contract.scoring.configuration_id,
    }
    if selection:
        params["sel"] = selection
    return urlencode(params)


def test_personalization_stale_link_migrates_with_a_persistent_notice(tmp_path: Path) -> None:
    """Issue 81/97/108 acceptance criteria: a cross-version link that still
    resolves against the current panel is migrated, its migrated selection
    is applied, and a persistent explanation discloses the migration. Issue
    97 still reads a legacy categoryCodes-shaped fragment for backward
    compatibility even though it never writes one anymore, expanding it to
    that category's own member source codes on load — issue 108 removed the
    guide's checkboxes, so the expansion is observed through the lens
    banner's "Counting N of M sources." line rather than individual checkbox
    state (issue 115 removed the old always-visible footer summary count).
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    contract = view_model.personalization
    category = next(
        item
        for item in contract.categories
        if _tallying_selectable(item) and item.member_source_codes
    )
    tallying_count = sum(1 for source in contract.sources if _tallying_selectable(source))
    fragment = _lens_fragment(
        view_model,
        mode="s",
        category_codes=(category.code,),
        data_version="a-retired-data-version",
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          noticeHidden: document.querySelector('[data-lens-notice]').hidden,
          noticeText: document.querySelector('[data-lens-notice]').textContent,
          bannerText: document.querySelector('[data-lens-banner-status]').textContent,
        })
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["noticeHidden"] is False
    assert "migrated" in result["noticeText"]
    if len(category.member_source_codes) == tallying_count:
        # The migrated category expands to the full tallying panel, which is
        # by definition the default selection. The always-present banner
        # reports that audited state while the notice discloses the migration.
        assert result["bannerText"] == f"Counting all {tallying_count} sources."
    else:
        assert result["bannerText"] == (
            f"Counting {len(category.member_source_codes)} of {tallying_count} sources."
        )


def test_personalization_unresolvable_link_falls_back_to_audited_with_a_persistent_notice(
    tmp_path: Path,
) -> None:
    """Issue 81/97 acceptance criterion: a cross-version link whose category
    can no longer be resolved falls back to the audited consensus (the
    default full-panel selection) rather than a partial personalized score,
    with a persistent explanation.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    fragment = _lens_fragment(
        view_model,
        mode="s",
        category_codes=("Gzzz",),
        data_version="a-retired-data-version",
    )
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          noticeHidden: document.querySelector('[data-lens-notice]').hidden,
          noticeText: document.querySelector('[data-lens-notice]').textContent,
          personalized: document.documentElement.classList.contains('lens-personalized'),
        })
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["noticeHidden"] is False
    assert "could not be migrated" in result["noticeText"]
    assert result["personalized"] is False


def test_personalization_malformed_link_falls_back_to_audited_with_a_persistent_notice(
    tmp_path: Path,
) -> None:
    """Issue 81/97 acceptance criterion: an invalid link (an unknown token in
    an otherwise current-version fragment here) falls back to audited (the
    default full-panel selection) with a persistent explanation.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    fragment = _lens_fragment(view_model, mode="s", category_codes=("Gzzz",))
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          noticeHidden: document.querySelector('[data-lens-notice]').hidden,
          noticeText: document.querySelector('[data-lens-notice]').textContent,
          personalized: document.documentElement.classList.contains('lens-personalized'),
          hash: window.location.hash,
        })
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["noticeHidden"] is False
    assert "could not be read" in result["noticeText"]
    assert result["personalized"] is False
    # Issue 96 acceptance criterion: a link that must not be scored falls back
    # to a clean base URL rather than leaving the stale fragment in place.
    assert result["hash"] == ""


def test_personalization_prior_schema_link_falls_back_to_a_clean_base_url(
    tmp_path: Path,
) -> None:
    """Issue 96 acceptance criterion: a fragment written under the prior
    (Times-flag) schema version fails to decode under the new version and
    results in a clean base URL, not a stale or confusing address bar.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    fragment = _lens_fragment(view_model, mode="a").replace("lens=2", "lens=1") + "&times=1"
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        JSON.stringify({
          noticeHidden: document.querySelector('[data-lens-notice]').hidden,
          hash: window.location.hash,
        })
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["noticeHidden"] is False
    assert result["hash"] == ""


def test_personalization_ordinary_anchor_navigation_never_shows_a_lens_notice(
    tmp_path: Path,
) -> None:
    """The skip link decodes to the same `unrecognized_fragment` malformed
    status a corrupted lens link could, but a plain in-page anchor must
    never be mistaken for one: it must never show a lens notice.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          document.querySelector('.skip-link').click();
          await new Promise((resolve) => setTimeout(resolve, 30));
          return JSON.stringify({
            noticeHidden: document.querySelector('[data-lens-notice]').hidden,
            hash: window.location.hash,
          });
        })()
        """,
    )
    assert result["hash"] == "#guide-races"
    assert result["noticeHidden"] is True


def test_personalization_notice_clears_on_the_next_explicit_change(tmp_path: Path) -> None:
    """A persistent link explanation must not survive the reader's next
    genuine lens change — issue 108 removed the guide's own interactive
    controls, so the only such change left is a hashchange to a new valid
    lens fragment (returned from the dedicated sources page, or a browser
    back/forward), which still runs through the same clearLensNotice() path.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    fragment = _lens_fragment(view_model, mode="s", category_codes=("Gzzz",))
    next_fragment = _lens_fragment(view_model, mode="a")
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    result = _evaluate_in_chrome(
        html_path,
        f"""
        (async () => {{
          const pause = () => new Promise((resolve) => setTimeout(resolve, 60));
          const before = document.querySelector('[data-lens-notice]').hidden;
          window.location.hash = {next_fragment!r};
          await pause();
          return JSON.stringify({{
            before,
            afterHidden: document.querySelector('[data-lens-notice]').hidden,
          }});
        }})()
        """,
        initial_url=f"{html_path.resolve().as_uri()}#{fragment}",
    )
    assert result["before"] is False
    assert result["afterHidden"] is True


def test_a_pre_removal_shared_link_replays_with_its_comparison_token_ignored(
    tmp_path: Path,
) -> None:
    """Issue 124 acceptance criterion: the token is ignored, never rejected.

    A link written before the removal carried a real personalized selection
    plus a comparison token meaning "also show the Times." The comparison is
    gone, so that token now names nothing — but the rest of the link must
    still replay exactly, which is checked here against the very same link
    with the token removed.
    """
    view_model = _personalization_enabled_view_model(tmp_path)
    comparison_code = next(
        source.code
        for source in view_model.personalization.sources
        if source.panel_role == "comparison"
    )
    tallying_codes = sorted(
        source.code for source in view_model.personalization.sources if _tallying_selectable(source)
    )
    # Diverge from the default so the lens actually personalizes and renders
    # the card regions read below.
    personalized_codes = tallying_codes[1:]
    current_fragment = _lens_fragment(view_model, mode="s", source_codes=tuple(personalized_codes))
    legacy_fragment = _lens_fragment(
        view_model, mode="s", source_codes=(*personalized_codes, comparison_code)
    )
    assert legacy_fragment != current_fragment
    html_path = tmp_path / "guide.html"
    html_path.write_text(
        render_html_document(view_model, read_rendering_configuration(RENDERING_CONFIG)),
        encoding="utf-8",
    )
    probe = """
        JSON.stringify({
          hash: window.location.hash,
          personalized: document.documentElement.classList.contains('lens-personalized'),
          banner: document.querySelector('[data-lens-banner-status]')?.textContent ?? '',
          notice: document.querySelector('[data-lens-notice]:not([hidden])')?.textContent ?? '',
          sourcesHref: document.querySelector('[data-sources-link]')?.getAttribute('href') ?? '',
          cards: [...document.querySelectorAll('[data-publication-race-id]')].map((card) => [
            card.querySelector('[data-lens-result] [data-display-role="recommendation"]')
              ?.textContent,
            card.querySelector('[data-lens-result] .screen-meter strong')?.textContent,
            card.querySelector('[data-lens-context] .support-full')?.textContent,
          ].join('|')).join('||'),
        })
        """
    legacy = _evaluate_in_chrome(
        html_path, probe, initial_url=f"{html_path.resolve().as_uri()}#{legacy_fragment}"
    )
    current = _evaluate_in_chrome(
        html_path, probe, initial_url=f"{html_path.resolve().as_uri()}#{current_fragment}"
    )

    # Inert, not rejected: no fallback notice, no address-bar rewrite.
    assert legacy["notice"] == ""
    assert legacy["hash"] == f"#{legacy_fragment}"
    assert legacy["personalized"] is True
    # The token changes nothing, and is not carried onward to the sources page.
    assert {key: value for key, value in legacy.items() if key != "hash"} == {
        key: value for key, value in current.items() if key != "hash"
    }
    assert comparison_code not in legacy["sourcesHref"]


def test_committed_lens_page_fixtures_match_a_fresh_render() -> None:
    """The Node markup-parity checks are only as good as the pages they diff
    against.

    docs/FRONTEND.md § Rendering requires the lit-html rendering of a region to
    be the region the Jinja template rendered. The Node side of that comparison
    reads a committed copy of each audited page, so a change to a Jinja
    template or to the published data has to land with regenerated fixtures —
    otherwise the parity tests would keep passing against markup the site no
    longer serves.
    """
    for path, fresh in (
        (GUIDE_PAGE_PATH, build_audited_guide_page()),
        (SOURCES_PAGE_PATH, build_audited_sources_page()),
    ):
        assert path.read_text(encoding="utf-8") == fresh, (
            f"{path.relative_to(PROJECT_ROOT)} is not what the renderer now produces, so the "
            "Node markup-parity test is diffing against a page that no longer exists. "
            "Regenerate it in this pull request with `uv run python -m tests.page_parity` "
            "(docs/FRONTEND.md, Rendering)."
        )
