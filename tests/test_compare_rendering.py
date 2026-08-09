"""Server-rendered comparisons page contract tests."""

from __future__ import annotations

import hashlib
import html
import json
import re
import tempfile
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlencode

import pytest

from election_guide.publication.comparisons import ComparisonsPolicy
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.context import ComparisonCellView, comparison_row_differs
from election_guide.rendering.documents import (
    render_comparison_document,
    render_html_document,
    render_sources_document,
)
from election_guide.results.models import RaceOutcome, RaceResults
from tests.compare_parity import (
    AUDITED_PAGE_PATH,
    build_audited_comparison_page,
)
from tests.compare_parity import enabled_view_model as _enabled_view_model
from tests.test_comparisons import _bundle  # pyright: ignore[reportPrivateUsage]
from tests.test_rendering import _evaluate_in_chrome  # pyright: ignore[reportPrivateUsage]
from tests.test_results import RACE_ID as RESULTS_RACE_ID
from tests.test_results import _valid_results  # pyright: ignore[reportPrivateUsage]

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_DIFFERENCE_ORACLE = PROJECT_ROOT / "tests/fixtures/comparison-default-differences.json"


def _comparison_table(rendered: str) -> str:
    """The server-rendered comparison table, apart from the rest of the page.

    The page inlines the bundled client modules, whose lit-html templates
    contain the same attribute names the table's markup does. A count over the
    whole document would see both, so assertions about what the server rendered
    read the table itself.
    """
    match = re.search(r'<table class="comparison-table".*?</table>', rendered, re.DOTALL)
    assert match is not None, "the comparisons page rendered no comparison table"
    return match.group(0)


def test_default_difference_oracle_matches_published_current_inputs() -> None:
    """Keep the hand-verified list independent of the client rowDiffers implementation."""
    view_model = _enabled_view_model()
    oracle = json.loads(DEFAULT_DIFFERENCE_ORACLE.read_text(encoding="utf-8"))
    displays = {display.race_id: display for display in view_model.comparisons.display_index}
    races = {race.race_id: race for race in view_model.personalization.races}

    observed: dict[str, dict[str, list[str]]] = {}
    for race_id, display in displays.items():
        race = races[race_id]
        leading = {"gall": list(display.baseline.leading_pick_ids)}
        for signal in ("strn", "stim"):
            if signal not in race.eligible_source_codes:
                leading[signal] = []
                continue
            cell = next(cell for cell in race.cells if cell.source_code == signal)
            leading[signal] = (
                [
                    candidate_id
                    for candidate_id in race.candidate_order
                    if candidate_id in cell.allocation
                ]
                if cell.state in {"endorsement", "multi_endorsement"}
                else []
            )
        reference = set(leading["gall"])
        if reference and any(
            bool(leading[signal]) and reference.isdisjoint(leading[signal])
            for signal in ("strn", "stim")
        ):
            observed[race_id] = leading

    expected = {item["race_id"]: item["leading_pick_ids"] for item in oracle["differing_races"]}
    assert observed == expected
    assert [displays[item["race_id"]].race_label for item in oracle["differing_races"]] == [
        item["race_label"] for item in oracle["differing_races"]
    ]


def test_committed_audited_page_fixture_matches_a_fresh_render() -> None:
    """The Node markup-parity check is only as good as the page it diffs against.

    docs/FRONTEND.md § Rendering requires the lit-html rendering of a region to
    be the region the Jinja template rendered. The Node side of that comparison
    reads a committed copy of the audited page, so a change to the Jinja
    template or to the published data has to land with a regenerated fixture —
    otherwise the parity test would keep passing against markup the site no
    longer serves.
    """
    committed = AUDITED_PAGE_PATH.read_text(encoding="utf-8")

    assert committed == build_audited_comparison_page(), (
        f"{AUDITED_PAGE_PATH.relative_to(PROJECT_ROOT)} is not what the renderer now "
        "produces, so the Node markup-parity test is diffing against a page that no longer "
        "exists. Regenerate it in this pull request with "
        "`uv run python -m tests.compare_parity` (docs/FRONTEND.md, Rendering)."
    )


def test_compare_document_server_renders_default_contract_snapshot() -> None:
    view_model = _enabled_view_model()
    rendered = render_comparison_document(
        view_model,
        public_site_url="https://seattleelections.guide",
        project_url="https://github.com/shaug/seattle-election-guide",
    )

    assert 'href="/e/wa-2026-primary/comparisons/" aria-current="page">Comparisons</a>' in rendered
    assert "<title>Comparisons — August 2026 Primary — Seattle Elections Guide</title>" in rendered
    assert '<header class="page-head">' in rendered
    assert '<p class="page-eyebrow">August 2026 Primary</p>' in rendered
    assert "<h1>Comparisons</h1>" in rendered
    assert 'data-election-day="2026-08-04"' in rendered
    assert "<b>Election day:</b> Tuesday, August 4, 2026" in rendered
    assert rendered.index(">Endorsements</a>") < rendered.index(">Comparisons</a>")
    assert rendered.index(">Sources</a>") < rendered.index(">Comparisons</a>")
    assert 'data-default-columns="gall,strn,stim"' in rendered
    # Counted over the table rather than the document: the page inlines the
    # bundled client modules, and the lit-html templates in them name the same
    # attributes they render (docs/FRONTEND.md, Rendering).
    table = _comparison_table(rendered)
    assert table.count("data-comparison-race=") == len(view_model.comparisons.display_index)
    assert table.count('data-column-signal="gall"') == len(view_model.comparisons.display_index) + 1
    assert table.count('data-column-signal="strn"') == len(view_model.comparisons.display_index) + 1
    assert table.count('data-column-signal="stim"') == len(view_model.comparisons.display_index) + 1
    assert "Endorsements side by side, surfacing tension." in rendered
    assert "You're starting with all sources" not in rendered
    assert 'name="description" content="Endorsements side by side, surfacing tension."' in rendered
    assert "audited all-sources" not in rendered
    assert '<div class="segmented-control">' in rendered
    assert "Audited baseline" not in rendered
    assert 'class="comparison-only-badge"' not in rendered
    assert "Each organization has equal weight" not in rendered
    assert 'class="comparison-legend"' not in rendered
    assert 'class="comparison-method"' not in rendered
    assert "≠" not in rendered
    assert 'class="comparison-share"' not in rendered
    assert "data-comparison-copy" not in rendered
    # Issue 192: Share is a masthead action now — it acts on the page you are
    # reading, while the footer keeps meta about the site.
    assert "data-footer-share" not in rendered
    assert "data-shell-share" in rendered
    # Wired by the bundled entry, which the template does nothing but invoke.
    assert "ComparePage.boot();" in rendered

    presets = re.search(r'<div class="comparison-presets".*?</div>', rendered, re.S)
    assert presets is not None
    links = re.findall(r'<a href="#([^"]+)">([^<]+)</a>', presets.group(0))
    assert [label for _, label in links] == [
        "The Stranger and The Times",
        "Labor and environment",
        "All sources and The Urbanist",
    ]
    assert [parse_qs(unescape(fragment))["cols"] for fragment, _ in links] == [
        ["strnstim"],
        ["GlabGenv"],
        ["gallurbn"],
    ]

    table = re.search(r'<table class="comparison-table".*?</table>', rendered, flags=re.DOTALL)
    assert table is not None
    normalized = re.sub(r"\s+", " ", unescape(table.group(0))).strip()
    assert hashlib.sha256(normalized.encode()).hexdigest() == (
        "7033b94d8eb04924540445b3b87b74a106962777bd664d63d9117139ab10faca"
    )
    static_head = re.search(r"<thead.*?</thead>", normalized)
    assert static_head is not None
    assert "Reference" not in static_head.group(0)
    assert "Maximum" not in static_head.group(0)

    payload_match = re.search(
        r'<script type="application/json" data-client-payload>(.*?)</script>',
        rendered,
        flags=re.DOTALL,
    )
    assert payload_match is not None
    payload = json.loads(payload_match.group(1))
    assert payload["default_columns"] == ["gall", "strn", "stim"]
    assert payload["personalization"] == view_model.personalization.model_dump(mode="json")
    assert payload["comparisons"] == view_model.comparisons.model_dump(mode="json")
    assert "function migrateCompareState" in rendered

    personalization_races = {race.race_id: race for race in view_model.personalization.races}
    sources = {source.id: source for source in view_model.personalization.sources}
    for display in view_model.comparisons.display_index:
        race_match = re.search(
            rf'<tr data-comparison-race="{re.escape(display.race_id)}"[^>]*>(.*?)</tr>',
            rendered,
            flags=re.DOTALL,
        )
        assert race_match is not None
        row = race_match.group(1)
        baseline_ids = json.dumps(display.baseline.leading_pick_ids)
        assert 'data-column-signal="gall"' in row
        assert 'data-cell-kind="baseline"' in row
        assert f"data-leading-pick-ids='{baseline_ids}'" in row
        assert f'data-share="{display.baseline.share}"' in row
        assert f'data-explicit-source-count="{display.baseline.explicit_source_count}"' in row

        labels = display.candidate_names or display.measure_response_labels
        for source_id in ("the-stranger", "seattle-times-editorial-board"):
            source = sources[source_id]
            if source.code not in personalization_races[display.race_id].eligible_source_codes:
                expected_kind = "outside_scope"
                expected_ids: list[str] = []
            else:
                cell = next(
                    cell
                    for cell in personalization_races[display.race_id].cells
                    if cell.source_code == source.code
                )
                if cell.state not in {"endorsement", "multi_endorsement"}:
                    expected_kind = "blank"
                    expected_ids = []
                else:
                    expected_kind = "comparison" if source.panel_role == "comparison" else "direct"
                    expected_ids = [
                        candidate_id
                        for candidate_id in personalization_races[display.race_id].candidate_order
                        if candidate_id in cell.allocation
                    ]
            assert f'data-column-signal="{source.code}"' in row
            assert f'data-cell-kind="{expected_kind}"' in row
            assert f"data-leading-pick-ids='{json.dumps(expected_ids)}'" in row
            for candidate_id in expected_ids:
                assert html.escape(labels[candidate_id]) in row

    guide = render_html_document(
        view_model,
        read_rendering_configuration(PROJECT_ROOT / "config/rendering/guide.yaml"),
    )
    sources_page = render_sources_document(
        view_model,
        public_site_url="https://seattleelections.guide",
    )
    for page in (guide, sources_page):
        assert 'href="/e/wa-2026-primary/comparisons/">Comparisons</a>' in page


def test_compare_document_refuses_disabled_policy() -> None:
    view_model = _bundle().view_model
    disabled = view_model.model_copy(
        update={
            "comparisons": view_model.comparisons.model_copy(
                update={"policy": ComparisonsPolicy(enabled=False)}
            )
        }
    )
    with pytest.raises(ValueError, match="release policy is disabled"):
        render_comparison_document(
            disabled,
            public_site_url="https://seattleelections.guide",
        )


def test_comparisons_payload_omits_certified_results_until_a_file_exists() -> None:
    """#288's own state gate: the client payload names no certified results at
    all -- not merely an empty `race_results` -- while `view_model.results` is
    `None`, exactly like every other results surface (docs/RESULTS.md,
    Rendering: "results render as a state, not an option")."""
    view_model = _enabled_view_model()
    assert view_model.results is None

    rendered = render_comparison_document(
        view_model,
        public_site_url="https://seattleelections.guide",
    )
    payload_match = re.search(
        r'<script type="application/json" data-client-payload>(.*?)</script>',
        rendered,
        flags=re.DOTALL,
    )
    assert payload_match is not None
    payload = json.loads(payload_match.group(1))
    assert payload["results_available"] is False
    assert payload["race_results"] == {}


def test_comparisons_payload_carries_certified_outcomes_for_candidate_races_only() -> None:
    """#288's own acceptance criterion (d): certified outcomes reach the
    client payload for the candidate race `tests.test_results._valid_results`
    certifies, and never for a measure race (out of scope pending #289),
    even when the results file explicitly certifies one too -- proving the
    measure exclusion is `race_results_view`'s own `race_type` gate
    (rendering/context.py), not merely an accident of the fixture naming no
    measure outcome."""
    measure_race_id = "seattle-proposition-1-library-levy"
    view_model = _enabled_view_model()
    assert any(
        display.race_id == measure_race_id for display in view_model.comparisons.display_index
    ), "fixture no longer includes the measure race this test excludes on purpose"

    with tempfile.TemporaryDirectory() as tmp_dir:
        results = _valid_results(Path(tmp_dir))
        # Extend the certified file with an outcome for the measure race too,
        # so a passing test proves the *type* gate, not just data absence.
        measure_outcomes = RaceResults(
            race_id=measure_race_id,
            ballots_counted=50000,
            outcomes=[
                RaceOutcome(
                    choice_id=f"{measure_race_id}--yes", votes=30000, share=0.6, advanced=True
                ),
                RaceOutcome(
                    choice_id=f"{measure_race_id}--no", votes=20000, share=0.4, advanced=False
                ),
            ],
        )
        results = results.model_copy(update={"races": [*results.races, measure_outcomes]})
        with_results = view_model.model_copy(update={"results": results})

        rendered = render_comparison_document(
            with_results,
            public_site_url="https://seattleelections.guide",
        )

    payload_match = re.search(
        r'<script type="application/json" data-client-payload>(.*?)</script>',
        rendered,
        flags=re.DOTALL,
    )
    assert payload_match is not None
    payload = json.loads(payload_match.group(1))
    assert payload["results_available"] is True
    assert measure_race_id not in payload["race_results"]
    outcomes = payload["race_results"][RESULTS_RACE_ID]
    assert [outcome["advanced"] for outcome in outcomes] == [True, True, False, False]
    assert [outcome["percentage_label"] for outcome in outcomes] == [
        "32.0%",
        "29.0%",
        "23.0%",
        "16.0%",
    ]
    assert {outcome["chip_label"] for outcome in outcomes if outcome["advanced"]} == {"Advances"}
    assert all(outcome["chip_label"] is None for outcome in outcomes if not outcome["advanced"])


def test_server_row_differences_are_relative_only_to_the_reference() -> None:
    def cell(*picks: str) -> ComparisonCellView:
        return ComparisonCellView(
            signal="test",
            kind="direct",
            choice_labels=picks,
            leading_pick_ids=picks,
        )

    assert comparison_row_differs((cell("a", "b"), cell("a"), cell("b"))) is False
    assert comparison_row_differs((cell("a"), cell("a", "b"), cell("b"))) is True
    assert comparison_row_differs((cell(), cell("a"), cell("b"))) is False


def _comparison_html_path(tmp_path: Path) -> Path:
    path = tmp_path / "compare.html"
    path.write_text(
        render_comparison_document(
            _enabled_view_model(),
            public_site_url="https://seattleelections.guide",
            project_url="https://github.com/shaug/seattle-election-guide",
        ),
        encoding="utf-8",
    )
    return path


def _comparison_html_path_with_results(tmp_path: Path) -> Path:
    """The comparisons page with a certified results file attached
    (docs/RESULTS.md, Rendering § The comparison view; #288) -- the same
    `tests.test_results._valid_results` fixture #286/#287's own certified-
    surface tests use, so this ticket's own test proves the column against
    the identical certified data those already-shipped surfaces render."""
    results_root = tmp_path / "results-evidence"
    results_root.mkdir()
    with_results = _enabled_view_model().model_copy(
        update={"results": _valid_results(results_root)}
    )
    path = tmp_path / "compare-with-results.html"
    path.write_text(
        render_comparison_document(
            with_results,
            public_site_url="https://seattleelections.guide",
            project_url="https://github.com/shaug/seattle-election-guide",
        ),
        encoding="utf-8",
    )
    return path


def _guide_html_path(tmp_path: Path) -> Path:
    path = tmp_path / "guide.html"
    path.write_text(
        render_html_document(
            _enabled_view_model(),
            read_rendering_configuration(PROJECT_ROOT / "config/rendering/guide.yaml"),
        ),
        encoding="utf-8",
    )
    return path


def test_guide_and_compare_render_the_shared_election_controls_composite() -> None:
    view_model = _enabled_view_model()
    guide = render_html_document(
        view_model,
        read_rendering_configuration(PROJECT_ROOT / "config/rendering/guide.yaml"),
    )
    compare = render_comparison_document(
        view_model,
        public_site_url="https://seattleelections.guide",
    )
    for rendered in (guide, compare):
        assert '<div class="sticky-header"' in rendered
        bar = re.search(
            r'<section class="[^"]*filter-control-bar[^"]*".*?</section>', rendered, re.S
        )
        assert bar is not None
        assert 'class="filter-select-control' in bar.group(0)
        assert 'class="filter-control-label"' in bar.group(0)
        assert 'class="filter-select"' in bar.group(0)
        assert 'class="filter-segmented-control' in bar.group(0)
        assert 'class="segmented-control"' in bar.group(0)
        assert 'class="filter-control-status' in bar.group(0)
        labels = re.findall(r'class="filter-control-label"[^>]*>([^<]+)', bar.group(0))
        assert labels == ["Ballot", "View", "Races"]

    macro_source = (
        PROJECT_ROOT / "src/election_guide/rendering/templates/_filter_controls.html.j2"
    ).read_text(encoding="utf-8")
    consumer_sources = [
        (PROJECT_ROOT / f"src/election_guide/rendering/templates/{name}").read_text(
            encoding="utf-8"
        )
        for name in ("guide.html.j2", "compare.html.j2")
    ]
    assert "macro election_controls" in macro_source
    assert all("election_controls(" in source for source in consumer_sources)
    for primitive in ("control_bar", "labeled_select", "segmented_radio", "control_status"):
        assert f"macro {primitive}" in macro_source
        assert all(f"{primitive}(" not in source for source in consumer_sources)

    base_css = (PROJECT_ROOT / "src/election_guide/rendering/templates/base.css").read_text(
        encoding="utf-8"
    )
    page_css = "\n".join(
        (PROJECT_ROOT / f"src/election_guide/rendering/templates/{name}").read_text(
            encoding="utf-8"
        )
        for name in ("guide.css", "compare.css")
    )
    for selector in (
        ".filter-control-bar",
        ".filter-select-control",
        ".filter-select",
        ".filter-segmented-control",
        ".filter-control-status",
    ):
        assert selector in base_css
        assert selector not in page_css
    assert ".sticky-header { position: sticky; top: 0; z-index: 5; }" in base_css
    assert ".sticky-header { position: static; }" in base_css
    assert ".sticky-header" not in page_css


@pytest.mark.parametrize("viewport_width", [1440, 900, 721, 390])
def test_guide_and_compare_shared_controls_have_the_same_composition_and_geometry(
    tmp_path: Path, viewport_width: int
) -> None:
    script = """
    (() => {
      const bar = document.querySelector('.filter-control-bar');
      const select = bar.querySelector('.filter-select');
      const label = bar.querySelector('.filter-control-label');
      const segmented = [...bar.querySelectorAll('.segmented-control')];
      const selected = segmented[0].querySelector('input:checked + span');
      const status = bar.querySelector('.filter-control-status');
      const styles = (element) => getComputedStyle(element);
      const barRect = bar.getBoundingClientRect();
      const selectRect = select.getBoundingClientRect();
      const statusRect = status.getBoundingClientRect();
      return JSON.stringify({
        roles: [...bar.children].map((child) => [...child.classList]
          .find((name) => name.startsWith('filter-'))),
        slotLabels: [...bar.querySelectorAll('.filter-control-label')]
          .map((item) => item.textContent.trim()),
        slotOptions: segmented.map((control) => [...control.querySelectorAll('span')]
          .map((item) => item.textContent.trim())),
        slotRects: [...bar.children].map((child) => {
          const rect = child.getBoundingClientRect();
          return [rect.left - barRect.left, rect.top - barRect.top, rect.width, rect.height];
        }),
        selectLabel: document.querySelector(`label[for="${select.id}"]`)?.textContent,
        statusInside: status?.parentElement === bar,
        barDisplay: styles(bar).display,
        barBackground: styles(bar).backgroundColor,
        barPaddingTop: styles(bar).paddingTop,
        barBorderBottom: styles(bar).borderBottomWidth,
        selectHeight: styles(select).height,
        selectPadding: styles(select).padding,
        selectRadius: styles(select).borderRadius,
        labelColor: styles(label).color,
        labelSize: styles(label).fontSize,
        labelWeight: styles(label).fontWeight,
        selectedBackground: styles(selected).backgroundColor,
        selectedColor: styles(selected).color,
        barLeft: barRect.left,
        barWidth: barRect.width,
        barHeight: barRect.height,
        selectTop: selectRect.top,
        selectBottom: selectRect.bottom,
        statusTop: statusRect.top,
        statusBottom: statusRect.bottom,
        statusHeight: statusRect.height,
        statusLineHeight: styles(status).lineHeight,
        statusWhiteSpace: styles(status).whiteSpace,
        statusFits: status.scrollWidth <= status.clientWidth + 1,
        allOptionsFit: segmented.flatMap((control) => [...control.querySelectorAll('span')])
          .every((item) => item.scrollWidth <= item.clientWidth + 1),
        outerWidth: document.documentElement.scrollWidth,
        viewportWidth: document.documentElement.clientWidth,
      });
    })()
    """
    guide = _evaluate_in_chrome(_guide_html_path(tmp_path), script, mobile_width=viewport_width)
    compare = _evaluate_in_chrome(
        _comparison_html_path(tmp_path), script, mobile_width=viewport_width
    )
    assert guide["roles"] == [
        "filter-select-control",
        "filter-segmented-control",
        "filter-segmented-control",
        "filter-control-status",
    ]
    assert compare["roles"] == guide["roles"]
    assert guide["slotLabels"] == compare["slotLabels"] == ["Ballot", "View", "Races"]
    assert guide["slotOptions"] == [["Full", "Compact"], ["All", "Contested"]]
    assert compare["slotOptions"] == [["Full", "Differing"], ["All", "Contested"]]
    assert guide["selectLabel"] == compare["selectLabel"] == "Ballot"
    assert guide["statusInside"] is compare["statusInside"] is True
    for key in (
        "barDisplay",
        "barBackground",
        "barPaddingTop",
        "barBorderBottom",
        "selectHeight",
        "selectPadding",
        "selectRadius",
        "labelColor",
        "labelSize",
        "labelWeight",
        "selectedBackground",
        "selectedColor",
    ):
        assert guide[key] == compare[key]
    assert guide["outerWidth"] == guide["viewportWidth"]
    assert compare["outerWidth"] == compare["viewportWidth"]
    assert abs(guide["barLeft"] - compare["barLeft"]) < 1
    assert abs(guide["barWidth"] - compare["barWidth"]) < 1
    # The status slot carries intentionally different live copy on each page, so
    # its text metrics may differ across browser/font environments. Compare the
    # three shared controls here; the status has its own placement constraints
    # below.
    for guide_rect, compare_rect in zip(
        guide["slotRects"][:3], compare["slotRects"][:3], strict=True
    ):
        for guide_value, compare_value in zip(guide_rect, compare_rect, strict=True):
            assert abs(guide_value - compare_value) < 1
    assert guide["allOptionsFit"] is True
    assert compare["allOptionsFit"] is True
    assert guide["statusWhiteSpace"] == compare["statusWhiteSpace"] == "nowrap"
    assert guide["statusFits"] is compare["statusFits"] is True
    if viewport_width > 720:
        assert abs(guide["barHeight"] - compare["barHeight"]) < 1
        for rendered in (guide, compare):
            assert rendered["statusTop"] < rendered["selectBottom"]
            assert rendered["statusBottom"] > rendered["selectTop"]
            assert (
                rendered["statusHeight"]
                <= float(rendered["statusLineHeight"].removesuffix("px")) * 1.5
            )


@pytest.mark.parametrize("viewport_width", [1440, 390])
def test_guide_and_compare_controls_share_the_scroll_placement_contract(
    tmp_path: Path, viewport_width: int
) -> None:
    script = """
    (async () => {
      const wrapper = document.querySelector('.sticky-header');
      const documentTop = wrapper.getBoundingClientRect().top + scrollY;
      window.scrollTo(0, documentTop + 100);
      await new Promise((resolve) => setTimeout(resolve, 80));
      const wrapperRect = wrapper.getBoundingClientRect();
      const barRect = wrapper.querySelector('.filter-control-bar').getBoundingClientRect();
      return JSON.stringify({
        position: getComputedStyle(wrapper).position,
        wrapperTop: wrapperRect.top,
        barTop: barRect.top,
        barBottom: barRect.bottom,
        visible: barRect.bottom > 0 && barRect.top < innerHeight,
        outerWidth: document.documentElement.scrollWidth,
        viewportWidth: document.documentElement.clientWidth,
      });
    })()
    """
    guide = _evaluate_in_chrome(_guide_html_path(tmp_path), script, mobile_width=viewport_width)
    compare = _evaluate_in_chrome(
        _comparison_html_path(tmp_path), script, mobile_width=viewport_width
    )
    assert guide["position"] == compare["position"]
    assert guide["outerWidth"] == guide["viewportWidth"]
    assert compare["outerWidth"] == compare["viewportWidth"]
    if viewport_width > 720:
        assert guide["position"] == "sticky"
        assert abs(guide["wrapperTop"]) < 1
        assert abs(compare["wrapperTop"]) < 1
        assert abs(guide["barTop"] - compare["barTop"]) < 1
        assert guide["visible"] is compare["visible"] is True
    else:
        assert guide["position"] == "static"
        assert abs(guide["wrapperTop"] + 100) < 1
        assert abs(compare["wrapperTop"] + 100) < 1
        assert abs(guide["barTop"] - compare["barTop"]) < 1
        assert guide["visible"] is compare["visible"]


@pytest.mark.parametrize("viewport_width", [1440, 838, 390])
def test_compare_table_headers_stack_below_controls_without_overlap(
    tmp_path: Path, viewport_width: int
) -> None:
    result = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (async () => {
          const controls = document.querySelector('[data-sticky-controls]');
          const table = document.querySelector('[data-comparison-table]');
          const header = document.querySelector('[data-comparison-head] th');
          const title = document.querySelector('[data-comparison-title="1"]');
          const tableTop = table.getBoundingClientRect().top + scrollY;
          window.scrollTo(0, tableTop + (innerWidth > 720 ? 320 : 0));
          await new Promise((resolve) => setTimeout(resolve, 80));
          title.focus();
          const controlsRect = controls.getBoundingClientRect();
          const headerRect = header.getBoundingClientRect();
          const titleRect = title.getBoundingClientRect();
          return JSON.stringify({
            controlsPosition: getComputedStyle(controls).position,
            controlsTop: controlsRect.top,
            controlsBottom: controlsRect.bottom,
            controlsHeight: controlsRect.height,
            measuredOffset: parseFloat(getComputedStyle(document.documentElement)
              .getPropertyValue('--sticky-controls-height')),
            headerPosition: getComputedStyle(header).position,
            headerTop: headerRect.top,
            headerBottom: headerRect.bottom,
            headerVisible: headerRect.bottom > 0 && headerRect.top < innerHeight,
            titleVisible: titleRect.bottom > 0 && titleRect.top < innerHeight,
            titleBelowControls: titleRect.top >= controlsRect.bottom - 1,
            outerWidth: document.documentElement.scrollWidth,
            viewportWidth: document.documentElement.clientWidth,
          });
        })()
        """,
        mobile_width=viewport_width,
    )
    assert result["outerWidth"] == result["viewportWidth"]
    assert abs(result["measuredOffset"] - result["controlsHeight"]) < 1
    assert result["headerVisible"] is True
    assert result["titleVisible"] is True
    if viewport_width > 720:
        assert result["controlsPosition"] == "sticky"
        assert result["headerPosition"] == "sticky"
        assert abs(result["controlsTop"]) < 1
        assert abs(result["headerTop"] - result["controlsBottom"]) < 1
        assert result["titleBelowControls"] is True
    else:
        assert result["controlsPosition"] == "static"
        assert result["headerPosition"] == "static"
        assert result["controlsBottom"] <= 0


def test_compare_client_enforces_picker_bounds_and_history(tmp_path: Path) -> None:
    html_path = _comparison_html_path(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const signals = () => [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal);
          const openPicker = (index) => {
            document.querySelector(`[data-comparison-title="${index}"]`).click();
            return document.querySelector(`[data-comparison-column="${index}"]`);
          };
          const initial = signals();
          const restingPickerCount = document.querySelectorAll('[data-comparison-column]').length;
          const firstPicker = openPicker(1);
          const pickerFocused = document.activeElement === firstPicker;
          const duplicateDisabled = [...firstPicker.options]
            .find((item) => item.value === initial[2]).disabled;
          const multiCategoryCopies = [...firstPicker.options]
            .filter((item) => item.value === 'wsto').length;
          firstPicker.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          await wait();
          const escapeRestoredTitle = document.activeElement
            === document.querySelector('[data-comparison-title="1"]');

          document.querySelector('[data-comparison-remove="2"]').click();
          await wait();
          const afterRemove = signals();
          const focusAfterRemove = document.activeElement?.dataset.comparisonTitle;
          const removeButtonsAtMinimum = document
            .querySelectorAll('[data-comparison-remove]').length;
          const addAtMinimum = document.querySelector('.comparison-column-add');
          const addAtMinimumEvidence = {
            text: addAtMinimum.textContent,
            ariaLabel: addAtMinimum.getAttribute('aria-label'),
            title: addAtMinimum.title,
            column: addAtMinimum.closest('[data-column-signal]').dataset.columnSignal,
          };
          const blurPicker = openPicker(1);
          addAtMinimum.focus();
          const blurClosed = !blurPicker.isConnected
            && !document.querySelector('[data-comparison-column="1"]')
            && document.activeElement === addAtMinimum;
          addAtMinimum.click();
          await wait();
          const afterAdd = signals();
          const addedPicker = document.querySelector('[data-comparison-column="2"]');
          const focusAfterAdd = document.activeElement === addedPicker;
          const addedPickerValue = addedPicker.value;
          const bodyCellCounts = [...document.querySelectorAll('[data-comparison-race]')]
            .map((row) => row.querySelectorAll('.comparison-cell').length);

          const picker = openPicker(1);
          const previous = picker.value;
          picker.value = 'Glab';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();
          const changed = signals();
          const focusAfterChange = document.activeElement?.dataset.comparisonTitle;
          const changedHash = location.hash;
          history.back();
          await wait();
          const afterBack = signals();
          history.forward();
          await wait();
          const afterForward = signals();
          return JSON.stringify({
            initial, duplicateDisabled, multiCategoryCopies, afterRemove,
            removeButtonsAtMinimum, afterAdd, previous, changed, changedHash,
            afterBack, afterForward, restingPickerCount, pickerFocused,
            escapeRestoredTitle, blurClosed, focusAfterRemove, focusAfterAdd,
            focusAfterChange, addAtMinimumEvidence, addedPickerValue, bodyCellCounts,
            hasAddAtMaximum: Boolean(document.querySelector('.comparison-column-add')),
            raceHeaderText: document.querySelector('[data-comparison-head] th').textContent,
            headTextAtMaximum: document.querySelector('[data-comparison-head]').innerText,
            referenceHasPickerAtRest: Boolean(document.querySelector(
              '[data-comparison-column="0"]',
            )),
            referenceHasTitle: Boolean(document.querySelector('[data-comparison-title="0"]')),
            referenceHasRemove: Boolean(document.querySelector('[data-comparison-remove="0"]')),
          });
        })()
        """,
    )
    assert result["initial"] == ["gall", "strn", "stim"]
    assert result["duplicateDisabled"] is True
    assert result["multiCategoryCopies"] == 2
    assert result["restingPickerCount"] == 0
    assert result["pickerFocused"] is True
    assert result["escapeRestoredTitle"] is True
    assert result["afterRemove"] == ["gall", "strn"]
    assert result["removeButtonsAtMinimum"] == 0
    assert result["focusAfterRemove"] == "1"
    assert result["addAtMinimumEvidence"] == {
        "text": "+",
        "ariaLabel": "Add comparison column",
        "title": "Add comparison column",
        "column": "strn",
    }
    assert result["blurClosed"] is True
    assert len(result["afterAdd"]) == 3
    assert len(set(result["afterAdd"])) == 3
    assert result["focusAfterAdd"] is True
    assert result["addedPickerValue"] == result["afterAdd"][2]
    assert set(result["bodyCellCounts"]) == {3}
    assert result["changed"] == ["gall", "Glab", result["afterAdd"][2]]
    assert "cols=gallGlab" in result["changedHash"]
    assert result["focusAfterChange"] == "1"
    assert result["afterBack"] == result["afterAdd"]
    assert result["afterForward"] == result["changed"]
    assert result["hasAddAtMaximum"] is False
    assert result["raceHeaderText"] == "Race"
    assert "Maximum" not in result["headTextAtMaximum"]
    assert "Reference" not in result["headTextAtMaximum"]
    assert result["referenceHasPickerAtRest"] is False
    assert result["referenceHasTitle"] is True
    assert result["referenceHasRemove"] is True


def test_compare_client_removes_the_first_column_and_promotes_the_next_reference(
    tmp_path: Path,
) -> None:
    html_path = _comparison_html_path(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const signals = () => [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal);
          const remove = document.querySelector('[data-comparison-remove="0"]');
          const removeLabel = remove.getAttribute('aria-label');
          remove.click();
          await wait();
          return JSON.stringify({
            removeLabel,
            afterRemove: signals(),
            hash: new URLSearchParams(location.hash.slice(1)).get('cols'),
            focusAfterRemove: document.activeElement?.dataset.comparisonTitle,
            promotedAgreement: document.querySelector(
              '[data-comparison-race] .comparison-cell[data-column-signal="strn"]',
            ).dataset.agreement,
            removeButtonsAtMinimum: document.querySelectorAll('[data-comparison-remove]').length,
          });
        })()
        """,
    )
    assert result == {
        "removeLabel": "Remove All sources",
        "afterRemove": ["strn", "stim"],
        "hash": "strnstim",
        "focusAfterRemove": "0",
        "promotedAgreement": "reference",
        "removeButtonsAtMinimum": 0,
    }


def test_compare_client_preserves_an_arbitrary_first_reference_from_a_legacy_fragment(
    tmp_path: Path,
) -> None:
    html_path = _comparison_html_path(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const preset = document.querySelector('.comparison-presets a');
          const parameters = new URLSearchParams(preset.hash.slice(1));
          parameters.set('cols', 'strnstim');
          location.hash = parameters.toString();
          await wait();
          const headings = [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal);
          const reference = document.querySelector(
            '[data-comparison-race] [data-column-signal="strn"]',
          );
          return JSON.stringify({
            headings,
            referenceAgreement: reference.dataset.agreement,
            referenceTitle: document.querySelector(
              '[data-column-signal="strn"] .comparison-column-title',
            ).textContent,
            removeTargets: [...document.querySelectorAll('[data-comparison-remove]')]
              .map((button) => button.dataset.comparisonRemove),
          });
        })()
        """,
    )
    assert result == {
        "headings": ["strn", "stim"],
        "referenceAgreement": "reference",
        "referenceTitle": "The Stranger Election Control Board",
        "removeTargets": [],
    }


def test_compare_client_swaps_the_reference_and_recomputes_relative_state(tmp_path: Path) -> None:
    html_path = _comparison_html_path(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const signals = () => [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal);
          const differingRows = () => [...document.querySelectorAll('[data-row-differs="true"]')]
            .map((row) => row.dataset.comparisonRace);
          const tintedRows = () => [...new Set([...document.querySelectorAll(
            '.comparison-cell[data-agreement="differ"]',
          )].map((cell) => cell.closest('[data-comparison-race]').dataset.comparisonRace))];
          const openReference = () => {
            document.querySelector('[data-comparison-title="0"]').click();
            return document.querySelector('[data-comparison-column="0"]');
          };

          const defaultRows = differingRows();
          const defaultStatus = document.querySelector('[data-comparison-status]').textContent;
          let picker = openReference();
          const pickerLabel = picker.getAttribute('aria-label');
          const initialPickerValue = picker.value;
          const allSourcesOptions = [...picker.options]
            .filter((option) => option.value === 'gall').length;
          const duplicateDisabled = [...picker.options]
            .find((option) => option.value === 'strn').disabled;
          picker.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          await wait();
          const escapeFocus = document.activeElement?.dataset.comparisonTitle;

          picker = openReference();
          document.querySelector('[data-comparison-title="1"]').focus();
          const blurClosed = !picker.isConnected
            && document.activeElement?.dataset.comparisonTitle === '1';

          picker = openReference();
          picker.value = 'Genv';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();
          const changedRows = differingRows();
          const changedTintedRows = tintedRows();
          const changedStatus = document.querySelector('[data-comparison-status]').textContent;
          const changedHash = location.hash;
          const focusAfterChange = document.activeElement?.dataset.comparisonTitle;
          const referenceAgreement = document.querySelector(
            '[data-comparison-race] .comparison-cell[data-column-signal="Genv"]',
          ).dataset.agreement;
          picker = openReference();
          const allSourcesAvailableAfterChange = ![...picker.options]
            .find((option) => option.value === 'gall').disabled;
          picker.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          await wait();

          history.back();
          await wait();
          const afterBack = signals();
          history.forward();
          await wait();
          const afterForward = signals();

          const configuredUrl = location.href;

          document.querySelector('[data-comparison-remove="2"]').click();
          await wait();
          return JSON.stringify({
            defaultRows, defaultStatus, pickerLabel, initialPickerValue, allSourcesOptions,
            duplicateDisabled, escapeFocus, blurClosed,
            changedRows, changedTintedRows, changedStatus, changedHash, focusAfterChange,
            referenceAgreement, allSourcesAvailableAfterChange, afterBack, afterForward,
            configuredUrl,
            afterRemove: signals(),
            visibleReferenceLabel: Boolean(document.querySelector(
              '[data-column-signal="Genv"] .comparison-column-label',
            )),
            referenceRemove: Boolean(document.querySelector('[data-comparison-remove="0"]')),
          });
        })()
        """,
    )
    assert result["pickerLabel"] == "Change reference, currently All sources"
    assert result["initialPickerValue"] == "gall"
    assert result["allSourcesOptions"] == 1
    assert result["duplicateDisabled"] is True
    assert result["escapeFocus"] == "0"
    assert result["blurClosed"] is True
    assert result["changedHash"].startswith("#cmp=1&cols=Genvstrnstim&")
    assert result["focusAfterChange"] == "0"
    assert result["referenceAgreement"] == "reference"
    assert result["allSourcesAvailableAfterChange"] is True
    assert result["changedRows"] == result["changedTintedRows"]
    assert result["changedRows"] != result["defaultRows"]
    assert result["changedStatus"] != result["defaultStatus"]
    assert result["afterBack"] == ["gall", "strn", "stim"]
    assert result["afterForward"] == ["Genv", "strn", "stim"]
    assert result["configuredUrl"].endswith(result["changedHash"])
    assert result["afterRemove"] == ["Genv", "strn"]
    assert result["visibleReferenceLabel"] is False
    assert result["referenceRemove"] is False

    restored = _evaluate_in_chrome(
        html_path,
        """
        (() => JSON.stringify({
          columns: [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal),
          referenceLabel: document.querySelector('[data-comparison-title="0"]')
            .getAttribute('aria-label'),
        }))()
        """,
        initial_url=result["configuredUrl"],
    )
    assert restored["columns"] == ["Genv", "strn", "stim"]
    assert restored["referenceLabel"] == "Change reference, currently Environment"


def test_compare_client_reports_a_guide_link_instead_of_ignoring_it(tmp_path: Path) -> None:
    """A lens link on this page is unreadable, and the reader is told so.

    The Node suite covers every decode, migration, and encode outcome against
    the audited fixture; this is the one that runs in a real browser, through
    the bundle the page actually ships, so the notice and the cleared address
    are proved where a reader would meet them (issue #243).
    """
    html_path = _comparison_html_path(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const referenceText = () => document.querySelector(
            '[data-comparison-race] [data-column-signal="gall"] .comparison-cell-picks',
          ).textContent;
          const before = referenceText();
          location.hash = 'lens=1&mode=a&panel=saved-panel&ph=abcdef123456';
          await wait();
          const notice = document.querySelector('[data-comparison-hidden-notice]');
          return JSON.stringify({
            before,
            after: referenceText(),
            columns: [...document.querySelectorAll(
              '[data-comparison-head] [data-column-signal]',
            )].map((heading) => heading.dataset.columnSignal),
            referenceInteractive: Boolean(document.querySelector(
              '[data-column-signal="gall"] [data-comparison-title="0"]',
            )),
            notice: notice.textContent,
            noticeHidden: notice.hidden,
            hash: location.hash,
          });
        })()
        """,
    )
    assert result == {
        "before": result["before"],
        "after": result["before"],
        "columns": ["gall", "strn", "stim"],
        "referenceInteractive": True,
        "notice": ("This comparison link could not be read, so the default comparison is shown."),
        "noticeHidden": False,
        "hash": "",
    }


def test_compare_client_migrates_stale_links_without_promoting_a_new_reference(
    tmp_path: Path,
) -> None:
    html_path = _comparison_html_path(tmp_path)
    current_url = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          const preset = document.querySelector('.comparison-presets a');
          return JSON.stringify(`${location.href.split('#')[0]}${preset.hash}`);
        })()
        """,
    )
    assert isinstance(current_url, str)
    stale_url = re.sub(
        r"(&data=)[^&]+",
        r"\1stale-data",
        current_url.replace("cols=gallstrnstim", "cols=strnstim"),
    )
    migrated = _evaluate_in_chrome(
        html_path,
        """
        (() => JSON.stringify({
          columns: [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal),
          referenceLabel: document.querySelector('[data-comparison-title="0"]')
            .getAttribute('aria-label'),
          notice: document.querySelector('[data-comparison-hidden-notice]').textContent,
          noticeHidden: document.querySelector('[data-comparison-hidden-notice]').hidden,
          hash: location.hash,
        }))()
        """,
        initial_url=stale_url,
    )
    assert migrated["columns"] == ["strn", "stim"]
    assert migrated["referenceLabel"] == (
        "Change reference, currently The Stranger Election Control Board"
    )
    assert migrated["notice"] == "This comparison link was updated for the current source list."
    assert migrated["noticeHidden"] is False
    assert "cols=strnstim" in migrated["hash"]
    assert "data=stale-data" not in migrated["hash"]

    missing_reference_url = stale_url.replace("cols=strnstim", "cols=zzzzstrn")
    fallback = _evaluate_in_chrome(
        html_path,
        """
        (() => JSON.stringify({
          columns: [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal),
          notice: document.querySelector('[data-comparison-hidden-notice]').textContent,
          noticeHidden: document.querySelector('[data-comparison-hidden-notice]').hidden,
          hash: location.hash,
        }))()
        """,
        initial_url=missing_reference_url,
    )
    assert fallback["columns"] == ["gall", "strn", "stim"]
    assert fallback["notice"] == (
        "This comparison link could not be restored completely, so the default comparison is shown."
    )
    assert fallback["noticeHidden"] is False
    assert "cols=gallstrnstim" in fallback["hash"]
    assert "cols=strn" not in fallback["hash"]

    traversed = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 250));
          const current = document.querySelector('.comparison-presets a').hash;
          const parameters = new URLSearchParams(current.slice(1));
          parameters.set('cols', 'zzzzstrn');
          parameters.set('data', 'stale-data');
          const stale = `#${parameters}`;
          history.replaceState({}, '', current);
          history.pushState({}, '', stale);
          history.pushState({}, '', current);
          history.back();
          await wait();
          return JSON.stringify({
            columns: [...document.querySelectorAll(
              '[data-comparison-head] [data-column-signal]',
            )].map((heading) => heading.dataset.columnSignal),
            notice: document.querySelector('[data-comparison-hidden-notice]').textContent,
            noticeHidden: document.querySelector('[data-comparison-hidden-notice]').hidden,
            hash: location.hash,
          });
        })()
        """,
    )
    assert traversed["columns"] == ["gall", "strn", "stim"]
    assert traversed["notice"] == fallback["notice"]
    assert traversed["noticeHidden"] is False
    assert "cols=gallstrnstim" in traversed["hash"]
    assert "data=stale-data" not in traversed["hash"]


def test_each_comparison_preset_clicks_and_loads_its_exact_ordered_columns(
    tmp_path: Path,
) -> None:
    html_path = _comparison_html_path(tmp_path)
    clicked = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const links = [...document.querySelectorAll('.comparison-presets a')];
          const results = [];
          for (const link of links) {
            link.click();
            await wait();
            results.push({
              label: link.textContent,
              hash: location.hash,
              columns: [...document.querySelectorAll(
                '[data-comparison-head] [data-column-signal]',
              )].map((heading) => heading.dataset.columnSignal),
            });
          }
          return JSON.stringify({
            hrefs: links.map((link) => link.getAttribute('href')),
            results,
          });
        })()
        """,
    )
    expected = [
        ("The Stranger and The Times", ["strn", "stim"]),
        ("Labor and environment", ["Glab", "Genv"]),
        ("All sources and The Urbanist", ["gall", "urbn"]),
    ]
    assert [(item["label"], item["columns"]) for item in clicked["results"]] == expected
    assert ["gall" in item["columns"] for item in clicked["results"]] == [False, False, True]

    for href, (_, columns) in zip(clicked["hrefs"], expected, strict=True):
        loaded = _evaluate_in_chrome(
            html_path,
            """
            (() => JSON.stringify({
              columns: [...document.querySelectorAll(
                '[data-comparison-head] [data-column-signal]',
              )].map((heading) => heading.dataset.columnSignal),
              hash: location.hash,
            }))()
            """,
            initial_url=f"{html_path.resolve().as_uri()}{href}",
        )
        assert loaded["columns"] == columns
        assert loaded["hash"] == href


def test_compare_client_presets_filters_and_url_round_trip(tmp_path: Path) -> None:
    html_path = _comparison_html_path(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const preset = document.querySelector('.comparison-presets a');
          const presetHref = preset.getAttribute('href');
          preset.click();
          await wait();
          const presetColumns = [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal);
          const historyBeforeFilters = history.length;
          document.querySelector('[data-comparison-contested]').click();
          await wait();
          const rowsBeforeDifferences = document
            .querySelectorAll('[data-comparison-race]').length;
          document.querySelector('[data-comparison-differences]').click();
          await wait();
          const historyAfterFilters = history.length;
          const rowCount = document.querySelectorAll('[data-comparison-race]').length;
          const configuredUrl = location.href;
            return JSON.stringify({
              presetHref, presetColumns, hash: location.hash, rowCount, configuredUrl,
              rowsBeforeDifferences, historyBeforeFilters, historyAfterFilters,
              status: document.querySelector('[data-comparison-status]').textContent,
              differencesChecked: document.querySelector('[data-comparison-differences]').checked,
              contestedChecked: document.querySelector('[data-comparison-contested]').checked,
            });
        })()
        """,
    )
    assert result["presetHref"].startswith("#cmp=1&cols=strnstim&")
    assert result["presetColumns"] == ["strn", "stim"]
    assert "races=contested" in result["hash"]
    assert "diff=1" in result["hash"]
    assert result["rowCount"] > 0
    assert result["rowCount"] < result["rowsBeforeDifferences"]
    assert result["historyAfterFilters"] == result["historyBeforeFilters"]
    assert re.fullmatch(r"\d+ of \d+ races shown · \d+ differ", result["status"])
    assert result["differencesChecked"] is True
    assert result["contestedChecked"] is True
    restored = _evaluate_in_chrome(
        html_path,
        """
        (() => JSON.stringify({
          columns: [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal),
          contested: document.querySelector('[data-comparison-contested]').checked,
          differing: document.querySelector('[data-comparison-differences]').checked,
          restoredHash: location.hash,
        }))()
        """,
        initial_url=result["configuredUrl"],
    )
    assert restored["columns"] == result["presetColumns"]
    assert restored["contested"] is True
    assert restored["differing"] is True
    assert restored["restoredHash"] == result["hash"]


def test_legacy_differing_and_contested_differences_fragments_restore_independent_controls(
    tmp_path: Path,
) -> None:
    html_path = _comparison_html_path(tmp_path)
    preset = _evaluate_in_chrome(
        html_path,
        """
        (() => JSON.stringify({
          hash: document.querySelector('.comparison-presets a').hash,
        }))()
        """,
    )["hash"]
    parameters = parse_qs(unescape(preset.removeprefix("#")))
    parameters["cols"] = ["gallstrnstim"]
    preset = f"#{urlencode(parameters, doseq=True)}"
    expression = """
    (() => JSON.stringify({
      differing: document.querySelector('[data-comparison-differences]').checked,
      full: document.querySelector('[data-comparison-full]').checked,
      contested: document.querySelector('[data-comparison-contested]').checked,
      allRaces: document.querySelector('[data-comparison-all-races]').checked,
      rowCount: document.querySelectorAll('[data-comparison-race]').length,
    }))()
    """
    differing = _evaluate_in_chrome(
        html_path,
        expression,
        initial_url=f"{html_path.resolve().as_uri()}{preset}&diff=1",
    )
    combined = _evaluate_in_chrome(
        html_path,
        expression,
        initial_url=f"{html_path.resolve().as_uri()}{preset}&diff=1&races=contested",
    )
    assert differing == {
        "differing": True,
        "full": False,
        "contested": False,
        "allRaces": True,
        "rowCount": 13,
    }
    assert combined["differing"] is True
    assert combined["full"] is False
    assert combined["contested"] is True
    assert combined["allRaces"] is False
    assert 0 < combined["rowCount"] <= differing["rowCount"]


def test_compare_client_labels_comparison_category_truthfully(tmp_path: Path) -> None:
    html_path = _comparison_html_path(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          document.querySelector('[data-comparison-title="1"]').click();
          const picker = document.querySelector('[data-comparison-column="1"]');
          const comparisonCategory = [...picker.options]
            .find((item) => item.value === 'Gcmp');
          picker.value = 'Gcmp';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          return JSON.stringify({
            optionLabel: comparisonCategory.textContent,
            coverageMetadata: Boolean(document.querySelector('.comparison-column-meta')),
            coverageText: document.querySelector('[data-comparison-head]').textContent
              .includes('Endorsed in'),
            referenceTitle: document.querySelector(
              '[data-column-signal="gall"] .comparison-column-title',
            ).textContent,
            referencePickerAtRest: Boolean(document.querySelector(
              '[data-comparison-column="0"]',
            )),
            referenceTitleLabel: document.querySelector('[data-comparison-title="0"]')
              .getAttribute('aria-label'),
          });
        })()
        """,
    )
    assert result["optionLabel"].endswith("(Comparison only)")
    assert result["coverageMetadata"] is False
    assert result["coverageText"] is False
    assert result["referenceTitle"] == "All sources"
    assert result["referencePickerAtRest"] is False
    assert result["referenceTitleLabel"] == "Change reference, currently All sources"


def test_compare_picker_offers_certified_result_only_once_a_file_exists(
    tmp_path: Path,
) -> None:
    """#288's own acceptance criterion (a): the picker names no "Certified
    result" option while no certified results file exists for the election,
    and offers exactly one once it does (docs/RESULTS.md, Rendering § The
    comparison view: "the column picker offers 'Certified result' only when
    the results file exists")."""
    without_results = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (() => {
          document.querySelector('[data-comparison-title="1"]').click();
          const picker = document.querySelector('[data-comparison-column="1"]');
          return JSON.stringify({
            options: [...picker.options].map((option) => option.value),
          });
        })()
        """,
    )
    assert "gres" not in without_results["options"]

    with_results = _evaluate_in_chrome(
        _comparison_html_path_with_results(tmp_path),
        """
        (() => {
          document.querySelector('[data-comparison-title="1"]').click();
          const picker = document.querySelector('[data-comparison-column="1"]');
          const resultOption = [...picker.options].find((option) => option.value === 'gres');
          return JSON.stringify({
            options: [...picker.options].map((option) => option.value),
            resultLabel: resultOption?.textContent,
          });
        })()
        """,
    )
    assert with_results["options"].count("gres") == 1
    assert with_results["resultLabel"] == "Certified result"


def test_compare_certified_result_never_reaches_the_reference_position(
    tmp_path: Path,
) -> None:
    """A result cell is never a `DataCell` (compare-signals.mjs `isDataCell`),
    so a "Certified result" reference column would make every other column's
    `cellAgreement` against it return `neutral` too -- silently breaking
    agreement/Differs for the whole row, not just this column's own (the
    excluded-from-agreement rule docs/RESULTS.md, Rendering § The comparison
    view actually asks for). The picker never offers it at the reference
    position, and a link or a column removal that would promote it there is
    refused by the same codec gate a link the codec cannot write always is."""
    html_path = _comparison_html_path_with_results(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));

          // The reference picker (index 0) never offers "Certified result".
          document.querySelector('[data-comparison-title="0"]').click();
          const referencePicker = document.querySelector('[data-comparison-column="0"]');
          const referenceOffersResult = [...referencePicker.options]
            .some((option) => option.value === 'gres');
          referencePicker.dispatchEvent(
            new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
          );
          await wait();

          // Put "Certified result" in the middle column, then remove the
          // reference column -- which would otherwise promote it to index 0.
          document.querySelector('[data-comparison-title="1"]').click();
          const middlePicker = document.querySelector('[data-comparison-column="1"]');
          middlePicker.value = 'gres';
          middlePicker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();
          const columnsBeforeRemove = [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal);
          const hashBeforeRemove = location.hash;

          document.querySelector('[data-comparison-remove="0"]').click();
          await wait();

          return JSON.stringify({
            referenceOffersResult,
            columnsBeforeRemove,
            columnsAfterRemove: [...document.querySelectorAll(
              '[data-comparison-head] [data-column-signal]',
            )].map((heading) => heading.dataset.columnSignal),
            hashUnchanged: location.hash === hashBeforeRemove,
            notice: document.querySelector('[data-comparison-hidden-notice]').textContent,
            noticeHidden: document.querySelector('[data-comparison-hidden-notice]').hidden,
          });
        })()
        """,
    )
    assert result["referenceOffersResult"] is False
    assert result["columnsBeforeRemove"][1] == "gres"
    # The removal that would have promoted "Certified result" to the
    # reference position never took: the columns and the address bar are
    # exactly what they were before the click, and the reader is told why.
    assert result["columnsAfterRemove"] == result["columnsBeforeRemove"]
    assert result["hashUnchanged"] is True
    assert result["notice"] == (
        "That change could not be put into a shareable link, so the comparison is unchanged."
    )
    assert result["noticeHidden"] is False


def test_compare_result_column_carries_no_agreement_and_never_affects_differs(
    tmp_path: Path,
) -> None:
    """#288's own acceptance criteria (b) and (c): the certified-result
    column's cells never tint agree/differ, never move a row's Differs
    marker, and speak the table's own language -- choice labels on the picks
    line, shares and certification status on the meta line
    (docs/RESULTS.md, Rendering § The comparison view). Exercised against
    `king-county-assessor`, the same race `tests.test_results._valid_results`
    certifies with the top two of four candidates advancing."""
    html_path = _comparison_html_path_with_results(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        f"""
        (async () => {{
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const rowDiffers = () => document.querySelector(
            '[data-comparison-race="{RESULTS_RACE_ID}"]',
          ).dataset.rowDiffers;
          const before = rowDiffers();

          document.querySelector('[data-comparison-title="1"]').click();
          const picker = document.querySelector('[data-comparison-column="1"]');
          picker.value = 'gres';
          picker.dispatchEvent(new Event('change', {{ bubbles: true }}));
          await wait();

          const cell = document.querySelector(
            '[data-comparison-race="{RESULTS_RACE_ID}"] [data-column-signal="gres"]',
          );
          return JSON.stringify({{
            before,
            after: rowDiffers(),
            cellKind: cell.dataset.cellKind,
            agreement: cell.dataset.agreement,
            picks: cell.querySelector('.comparison-cell-picks').textContent.trim(),
            meta: cell.querySelector('.comparison-cell-meta')?.textContent.trim(),
            columnTitle: document.querySelector(
              '[data-column-signal="gres"] .comparison-column-title',
            )?.textContent,
          }});
        }})()
        """,
    )
    assert result["cellKind"] == "result"
    assert result["agreement"] == "neutral"
    # Both advancing candidates in this primary, most-share-first.
    assert result["picks"] == "Dominique M Scarimbolo / Christopher Roberts"
    assert result["meta"] == "32.0% · 29.0% · Advances"
    # Adding the column changes no row's Differs marker -- the reference is
    # still `gall`, and the result column never enters that computation.
    assert result["after"] == result["before"]
    assert result["columnTitle"] == "Certified result"


def test_compare_client_mobile_budget_and_focus_have_layout_evidence(tmp_path: Path) -> None:
    html_path = _comparison_html_path(tmp_path)
    mobile = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          document.querySelector('[data-comparison-title="1"]').click();
          const picker = document.querySelector('[data-comparison-column="1"]');
          picker.value = 'eccd';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          const titleActions = [...document.querySelectorAll('[data-comparison-title]')];
          const focus = getComputedStyle(titleActions[1]);
          const tableElement = document.querySelector('[data-comparison-table]');
          const wrapElement = document.querySelector('[data-comparison-grid]');
          const table = tableElement.getBoundingClientRect();
          const wrap = wrapElement.getBoundingClientRect();
          const titles = [...document.querySelectorAll('.comparison-column-title')];
          const remove = document.querySelector('[data-comparison-remove="1"]');
          const firstRace = document.querySelector('[data-comparison-race]');
          const firstRaceCells = [...firstRace.querySelectorAll('.comparison-cell')];
          return JSON.stringify({
            visibleSignals: [...document.querySelectorAll(
              '[data-comparison-head] [data-column-signal]',
            )].map((heading) => heading.dataset.columnSignal),
            notice: document.querySelector('[data-comparison-hidden-notice]').textContent,
            noticeVisible: !document.querySelector('[data-comparison-hidden-notice]').hidden,
            configured: new URLSearchParams(location.hash.slice(1)).get('cols'),
            focusOutlineStyle: focus.outlineStyle,
            focusOutlineWidth: focus.outlineWidth,
            tableWidth: table.width,
            wrapWidth: wrap.width,
            outerWidth: document.documentElement.scrollWidth,
            viewportWidth: document.documentElement.clientWidth,
            wrapScrollWidth: wrapElement.scrollWidth,
            wrapClientWidth: wrapElement.clientWidth,
            wrapOverflowX: getComputedStyle(wrapElement).overflowX,
            rowDisplay: getComputedStyle(firstRace).display,
            cellDisplay: getComputedStyle(firstRaceCells[0]).display,
            cellLabels: firstRaceCells.map((cell) => cell.dataset.columnLabel),
            titleLabels: titleActions.map((title) => title.getAttribute('aria-label')),
            restingPickerCount: document.querySelectorAll('[data-comparison-column]').length,
            focusReturned: document.activeElement === titleActions[1],
            titlesFit: titles.every((title) => title.scrollWidth <= title.clientWidth),
            removeTitle: remove.title,
            removeWidth: remove.getBoundingClientRect().width,
            removeHeight: remove.getBoundingClientRect().height,
            headerBackground: getComputedStyle(
              document.querySelector('[data-column-signal="eccd"]'),
            ).backgroundColor,
            navyToken: (() => {
              const probe = document.createElement('i');
              probe.style.background = 'var(--navy)';
              document.body.append(probe);
              const value = getComputedStyle(probe).backgroundColor;
              probe.remove();
              return value;
            })(),
            raceControlDisplay: getComputedStyle(
              document.querySelector('[name="comparison-races"]').closest('.segmented-control'),
            ).display,
          });
        })()
        """,
        mobile_width=390,
    )
    desktop = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          document.querySelector('[data-comparison-title="1"]').click();
          const picker = document.querySelector('[data-comparison-column="1"]');
          picker.value = 'eccd';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          const titleTops = [...document.querySelectorAll('.comparison-column-title')]
            .map((title) => title.getBoundingClientRect().top);
          const wrap = document.querySelector('[data-comparison-grid]');
          const table = document.querySelector('[data-comparison-table]');
          return JSON.stringify({
            visibleSignals: [...document.querySelectorAll(
              '[data-comparison-head] [data-column-signal]',
            )].map((heading) => heading.dataset.columnSignal),
            noticeVisible: !document.querySelector('[data-comparison-hidden-notice]').hidden,
            titleTopSpread: Math.max(...titleTops) - Math.min(...titleTops),
            stickyHead: getComputedStyle(
              document.querySelector('[data-comparison-head] th'),
            ).position,
            wrapOverflowX: getComputedStyle(wrap).overflowX,
            wrapScrollWidth: wrap.scrollWidth,
            wrapClientWidth: wrap.clientWidth,
            tableWidth: table.getBoundingClientRect().width,
            wrapWidth: wrap.getBoundingClientRect().width,
            outerWidth: document.documentElement.scrollWidth,
            viewportWidth: document.documentElement.clientWidth,
            titlesFit: [...document.querySelectorAll('.comparison-column-title')]
              .every((title) => title.scrollWidth <= title.clientWidth),
          });
        })()
        """,
    )
    assert mobile["visibleSignals"] == ["gall", "eccd", "stim"]
    assert mobile["noticeVisible"] is False
    assert mobile["notice"] == ""
    assert mobile["configured"] == "galleccdstim"
    assert mobile["focusOutlineStyle"] != "none"
    assert float(mobile["focusOutlineWidth"].removesuffix("px")) > 0
    assert mobile["tableWidth"] > mobile["wrapWidth"]
    assert mobile["outerWidth"] == mobile["viewportWidth"]
    assert mobile["wrapScrollWidth"] > mobile["wrapClientWidth"]
    assert mobile["wrapOverflowX"] == "auto"
    assert mobile["rowDisplay"] == "table-row"
    assert mobile["cellDisplay"] == "table-cell"
    assert mobile["cellLabels"] == [
        "All sources",
        "Environment and Climate Caucus of the Washington State Democratic Party",
        "The Seattle Times Editorial Board",
    ]
    assert mobile["titleLabels"] == [
        "Change reference, currently All sources",
        (
            "Change Environment and Climate Caucus of the Washington State "
            "Democratic Party comparison"
        ),
        "Change The Seattle Times Editorial Board comparison",
    ]
    assert mobile["restingPickerCount"] == 0
    assert mobile["focusReturned"] is True
    assert mobile["titlesFit"] is True
    assert mobile["removeTitle"] == (
        "Remove Environment and Climate Caucus of the Washington State Democratic Party"
    )
    assert mobile["removeWidth"] >= 40
    assert mobile["removeHeight"] >= 40
    assert mobile["headerBackground"] == mobile["navyToken"]
    assert mobile["raceControlDisplay"] == "flex"
    assert desktop["visibleSignals"] == ["gall", "eccd", "stim"]
    assert desktop["noticeVisible"] is False
    assert desktop["titleTopSpread"] < 1
    assert desktop["stickyHead"] == "sticky"
    assert desktop["wrapOverflowX"] == "visible"
    assert desktop["wrapScrollWidth"] == desktop["wrapClientWidth"]
    assert desktop["tableWidth"] <= desktop["wrapWidth"] + 1
    assert desktop["outerWidth"] == desktop["viewportWidth"]
    assert desktop["titlesFit"] is True


@pytest.mark.parametrize("viewport_width", [390, 375, 320])
def test_mobile_comparison_scrolls_columns_while_preserving_context(
    tmp_path: Path, viewport_width: int
) -> None:
    result = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 180));
          await wait();
          const wrap = document.querySelector('[data-comparison-grid]');
          const table = document.querySelector('[data-comparison-table]');
          const hint = document.querySelector('[data-comparison-scroll-hint]');
          const headerCells = [...document.querySelectorAll('[data-comparison-head] th')];
          const row = document.querySelector('[data-comparison-race]');
          const section = document.querySelector('.comparison-section-heading th');
          const cells = [...row.children];
          const rects = () => ({
            wrap: wrap.getBoundingClientRect(),
            table: table.getBoundingClientRect(),
            race: cells[0].getBoundingClientRect(),
            reference: cells[1].getBoundingClientRect(),
            firstComparison: cells[2].getBoundingClientRect(),
            lastComparison: cells.at(-1).getBoundingClientRect(),
            section: section.getBoundingClientRect(),
          });
          const summarize = () => {
            const measured = rects();
            return {
              scrollLeft: wrap.scrollLeft,
              raceLeft: measured.race.left,
              raceRight: measured.race.right,
              referenceLeft: measured.reference.left,
              referenceRight: measured.reference.right,
              firstComparisonLeft: measured.firstComparison.left,
              firstComparisonRight: measured.firstComparison.right,
              lastComparisonLeft: measured.lastComparison.left,
              lastComparisonRight: measured.lastComparison.right,
              wrapLeft: measured.wrap.left,
              wrapRight: measured.wrap.right,
              tableLeft: measured.table.left,
              tableWidth: measured.table.width,
              sectionLeft: measured.section.left,
              sectionWidth: measured.section.width,
              headerRaceLeft: headerCells[0].getBoundingClientRect().left,
              headerReferenceLeft: headerCells[1].getBoundingClientRect().left,
              hintHidden: hint.hidden,
              hintText: hint.textContent,
              hintPosition: hint.dataset.scrollPosition,
            };
          };

          const before = summarize();
          wrap.scrollLeft = wrap.scrollWidth;
          wrap.dispatchEvent(new Event('scroll'));
          await wait();
          const after = summarize();

          const sourceHeader = document.querySelector(
            '[data-comparison-head] th:nth-child(3)',
          );
          const layout = {
            overflowX: getComputedStyle(wrap).overflowX,
            snapType: getComputedStyle(wrap).scrollSnapType,
            snapAlign: getComputedStyle(sourceHeader).scrollSnapAlign,
            regionLabel: wrap.getAttribute('aria-label'),
            tabIndexAtThree: wrap.tabIndex,
            rowDisplay: getComputedStyle(row).display,
            cellDisplay: getComputedStyle(cells[1]).display,
            racePosition: getComputedStyle(cells[0]).position,
            referencePosition: getComputedStyle(cells[1]).position,
            sourceHeaderPosition: getComputedStyle(sourceHeader).position,
            sourceHeaderTop: getComputedStyle(sourceHeader).top,
            raceHeaderPosition: getComputedStyle(headerCells[0]).position,
            referenceHeaderPosition: getComputedStyle(headerCells[1]).position,
            sectionPosition: getComputedStyle(section).position,
            sectionColspan: section.colSpan,
            outerWidth: document.documentElement.scrollWidth,
            viewportWidth: document.documentElement.clientWidth,
          };

          document.querySelector('[data-comparison-remove="2"]').click();
          await wait();
          const twoColumns = {
            hintHidden: hint.hidden,
            tabIndex: wrap.tabIndex,
            scrollWidth: wrap.scrollWidth,
            clientWidth: wrap.clientWidth,
          };
          return JSON.stringify({
            before,
            after,
            twoColumns,
            ...layout,
          });
        })()
        """,
        mobile_width=viewport_width,
    )

    assert result["overflowX"] == "auto"
    assert result["snapType"] == "x mandatory"
    assert result["snapAlign"] == "start"
    assert result["regionLabel"] == "Scrollable endorsement comparison"
    assert result["tabIndexAtThree"] == 0
    assert result["rowDisplay"] == "table-row"
    assert result["cellDisplay"] == "table-cell"
    assert result["racePosition"] == "sticky"
    assert result["referencePosition"] == "sticky"
    assert result["sourceHeaderPosition"] == "static"
    assert result["sourceHeaderTop"] == "auto"
    assert result["raceHeaderPosition"] == "static"
    assert result["referenceHeaderPosition"] == "static"
    assert result["sectionPosition"] == "static"
    assert result["sectionColspan"] == 4
    assert result["outerWidth"] == result["viewportWidth"]

    before = result["before"]
    after = result["after"]
    assert before["hintHidden"] is False
    assert before["hintText"] == "More columns →"
    assert before["hintPosition"] == "start"
    assert before["firstComparisonLeft"] >= before["referenceRight"] - 1
    assert before["firstComparisonRight"] <= before["wrapRight"] + 1
    assert abs(before["sectionLeft"] - before["tableLeft"]) < 1
    assert abs(before["sectionWidth"] - before["tableWidth"]) < 1

    assert after["scrollLeft"] > 0
    assert after["hintHidden"] is False
    assert after["hintText"] == "← More columns"
    assert after["hintPosition"] == "end"
    assert abs(after["raceLeft"] - before["raceLeft"]) < 1
    assert abs(after["referenceLeft"] - before["referenceLeft"]) < 1
    assert abs(after["headerRaceLeft"] - before["headerRaceLeft"]) < 1
    assert abs(after["headerReferenceLeft"] - before["headerReferenceLeft"]) < 1
    assert after["lastComparisonLeft"] >= after["referenceRight"] - 1
    assert after["lastComparisonRight"] <= after["wrapRight"] + 1
    assert after["sectionLeft"] < before["sectionLeft"]
    assert abs(after["sectionWidth"] - after["tableWidth"]) < 1

    assert result["twoColumns"] == {
        "hintHidden": True,
        "tabIndex": -1,
        "scrollWidth": result["twoColumns"]["clientWidth"],
        "clientWidth": result["twoColumns"]["clientWidth"],
    }


@pytest.mark.parametrize("viewport_width", [390, 320])
def test_mobile_lower_rows_keep_visible_source_identity(
    tmp_path: Path, viewport_width: int
) -> None:
    result = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (async () => {
          const rows = [...document.querySelectorAll('[data-comparison-race]')];
          const row = rows[Math.min(15, rows.length - 1)];
          const cells = [...row.querySelectorAll('.comparison-cell')];
          window.scrollTo(0, row.getBoundingClientRect().top + scrollY - (innerHeight / 2));
          await new Promise((resolve) => setTimeout(resolve, 80));
          const rowRect = row.getBoundingClientRect();
          const headers = [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )];
          return JSON.stringify({
            rowVisible: rowRect.bottom > 0 && rowRect.top < innerHeight,
            headersOffscreen: headers.every(
              (header) => header.getBoundingClientRect().bottom <= 0,
            ),
            labels: cells.map((cell) => ({
              expected: cell.dataset.columnLabel,
              visible: getComputedStyle(cell, '::before').content,
              display: getComputedStyle(cell, '::before').display,
            })),
            outerWidth: document.documentElement.scrollWidth,
            viewportWidth: document.documentElement.clientWidth,
          });
        })()
        """,
        mobile_width=viewport_width,
    )
    assert result["rowVisible"] is True
    assert result["headersOffscreen"] is True
    assert result["labels"]
    for label in result["labels"]:
        assert label["visible"].strip('"') == label["expected"]
        assert label["display"] == "block"
    assert result["outerWidth"] == result["viewportWidth"]


def test_comparison_columns_do_not_compress_below_the_supported_320px_floor(
    tmp_path: Path,
) -> None:
    result = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (() => {
          const wrap = document.querySelector('[data-comparison-grid]');
          const row = document.querySelector('[data-comparison-race]');
          const cells = [...row.children];
          return JSON.stringify({
            raceWidth: cells[0].getBoundingClientRect().width,
            sourceWidths: cells.slice(1).map((cell) => cell.getBoundingClientRect().width),
            racePosition: getComputedStyle(cells[0]).position,
            referencePosition: getComputedStyle(cells[1]).position,
            overflowX: getComputedStyle(wrap).overflowX,
            wrapScrollWidth: wrap.scrollWidth,
            wrapClientWidth: wrap.clientWidth,
            outerWidth: document.documentElement.scrollWidth,
            viewportWidth: document.documentElement.clientWidth,
          });
        })()
        """,
        mobile_width=280,
    )

    assert result["raceWidth"] == pytest.approx(80, abs=1)
    assert all(width == pytest.approx(101.6, abs=1) for width in result["sourceWidths"])
    assert result["racePosition"] == "sticky"
    assert result["referencePosition"] == "sticky"
    assert result["overflowX"] == "auto"
    assert result["wrapScrollWidth"] > result["wrapClientWidth"]
    assert result["outerWidth"] == result["viewportWidth"] == 280


@pytest.mark.parametrize("viewport_width", [1440, 900])
def test_compare_header_uses_one_compact_corner_action_geometry(
    tmp_path: Path, viewport_width: int
) -> None:
    result = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const capture = () => {
            const head = document.querySelector('[data-comparison-head]');
            const headerCells = [...head.querySelectorAll('th')];
            const raceCell = headerCells[0].getBoundingClientRect();
            const raceLabel = headerCells[0]
              .querySelector('.comparison-column-label').getBoundingClientRect();
            const cells = headerCells.slice(1).map((cell) => {
              const cellRect = cell.getBoundingClientRect();
              const title = cell.querySelector('.comparison-column-title');
              const titleRect = title.getBoundingClientRect();
              const action = cell.querySelector(
                '.comparison-column-remove, .comparison-column-add',
              );
              const icon = action?.querySelector('.comparison-column-action-icon');
              const iconRect = icon?.getBoundingClientRect();
              return {
                signal: cell.dataset.columnSignal,
                titleTop: titleRect.top,
                titleFits: title.scrollWidth <= title.clientWidth,
                actionType: action?.classList.contains('comparison-column-add')
                  ? 'add'
                  : (action ? 'remove' : null),
                iconTopInset: iconRect ? iconRect.top - cellRect.top : null,
                iconRightInset: iconRect ? cellRect.right - iconRect.right : null,
                iconOverlapsTitle: iconRect ? !(
                  iconRect.left >= titleRect.right || iconRect.right <= titleRect.left
                  || iconRect.top >= titleRect.bottom || iconRect.bottom <= titleRect.top
                ) : false,
              };
            });
            const titleTops = cells.map((cell) => cell.titleTop);
            return {
              height: head.getBoundingClientRect().height,
              stickyPosition: getComputedStyle(headerCells[0]).position,
              raceTopInset: raceLabel.top - raceCell.top,
              raceLeftInset: raceLabel.left - raceCell.left,
              titleTopSpread: Math.max(...titleTops) - Math.min(...titleTops),
              cells,
            };
          };

          const threeColumns = capture();
          document.querySelector('[data-comparison-remove="2"]').click();
          await wait();
          return JSON.stringify({ threeColumns, twoColumns: capture() });
        })()
        """,
        mobile_width=viewport_width,
    )

    for layout in (result["threeColumns"], result["twoColumns"]):
        assert layout["height"] < 80
        assert layout["stickyPosition"] == "sticky"
        assert layout["titleTopSpread"] < 1
        assert all(cell["titleFits"] for cell in layout["cells"])
        for cell in layout["cells"]:
            assert cell["iconOverlapsTitle"] is False
            if cell["actionType"] is None:
                continue
            assert abs(cell["iconTopInset"] - layout["raceTopInset"]) <= 4
            assert abs(cell["iconRightInset"] - layout["raceLeftInset"]) <= 4

    assert [cell["actionType"] for cell in result["threeColumns"]["cells"]] == [
        "remove",
        "remove",
        "remove",
    ]
    assert [cell["actionType"] for cell in result["twoColumns"]["cells"]] == [
        None,
        "add",
    ]


def test_compare_client_mobile_add_action_is_compact_and_opens_the_new_picker(
    tmp_path: Path,
) -> None:
    result = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          document.querySelector('[data-comparison-remove="2"]').click();
          await wait();
          const add = document.querySelector('.comparison-column-add');
          add.focus();
          const focus = getComputedStyle(add);
          const addRect = add.getBoundingClientRect();
          const wrap = document.querySelector('[data-comparison-grid]');
          const before = {
            text: add.textContent,
            ariaLabel: add.getAttribute('aria-label'),
            title: add.title,
            signal: add.closest('[data-column-signal]').dataset.columnSignal,
            width: addRect.width,
            height: addRect.height,
            focusOutlineStyle: focus.outlineStyle,
            focusOutlineWidth: focus.outlineWidth,
            raceText: document.querySelector('[data-comparison-head] th').textContent,
            headText: document.querySelector('[data-comparison-head]').innerText,
            outerWidth: document.documentElement.scrollWidth,
            viewportWidth: document.documentElement.clientWidth,
            wrapScrollWidth: wrap.scrollWidth,
            wrapClientWidth: wrap.clientWidth,
          };
          add.click();
          await wait();
          const picker = document.querySelector('[data-comparison-column="2"]');
          return JSON.stringify({
            before,
            pickerFocused: document.activeElement === picker,
            pickerValue: picker.value,
            visibleSignals: [...document.querySelectorAll(
              '[data-comparison-head] [data-column-signal]',
            )].map((heading) => heading.dataset.columnSignal),
            plusAtMaximum: Boolean(document.querySelector('.comparison-column-add')),
            bodyCellCounts: [...document.querySelectorAll('[data-comparison-race]')]
              .map((row) => row.querySelectorAll('.comparison-cell').length),
            outerWidth: document.documentElement.scrollWidth,
            viewportWidth: document.documentElement.clientWidth,
          });
        })()
        """,
        mobile_width=390,
    )
    assert result["before"]["text"] == "+"
    assert result["before"]["ariaLabel"] == "Add comparison column"
    assert result["before"]["title"] == "Add comparison column"
    assert result["before"]["signal"] == "strn"
    assert result["before"]["width"] >= 40
    assert result["before"]["height"] >= 40
    assert result["before"]["focusOutlineStyle"] != "none"
    assert float(result["before"]["focusOutlineWidth"].removesuffix("px")) > 0
    assert result["before"]["raceText"] == "Race"
    assert "Reference" not in result["before"]["headText"]
    assert "Maximum" not in result["before"]["headText"]
    assert result["before"]["outerWidth"] == result["before"]["viewportWidth"]
    assert result["before"]["wrapScrollWidth"] == result["before"]["wrapClientWidth"]
    assert result["pickerFocused"] is True
    assert result["pickerValue"] == result["visibleSignals"][2]
    assert len(result["visibleSignals"]) == 3
    assert result["plusAtMaximum"] is False
    assert set(result["bodyCellCounts"]) == {3}
    assert result["outerWidth"] == result["viewportWidth"]


@pytest.mark.parametrize("mobile_width", [None, 390])
def test_default_differences_match_fixed_oracle_with_visual_and_accessible_signals(
    tmp_path: Path, mobile_width: int | None
) -> None:
    oracle = json.loads(DEFAULT_DIFFERENCE_ORACLE.read_text(encoding="utf-8"))
    expected_ids = [item["race_id"] for item in oracle["differing_races"]]
    result = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const tokenBackground = (name) => {
            const probe = document.createElement('span');
            probe.style.background = `var(${name})`;
            document.body.append(probe);
            const color = getComputedStyle(probe).backgroundColor;
            probe.remove();
            return color;
          };
          const narrow = window.matchMedia('(max-width: 720px)').matches;
          const senator = document.querySelector(
            '[data-comparison-race="ld-32-state-senator"]',
          );
          const agree = senator.querySelector('[data-column-signal="strn"]');
          const differ = document.querySelector(
            narrow
              ? '[data-comparison-race="ld-32-state-representative-1"] [data-column-signal="strn"]'
              : '[data-comparison-race="ld-32-state-senator"] [data-column-signal="stim"]',
          );
          const reference = senator.querySelector('[data-column-signal="gall"]');
          const blank = document.querySelector(
            '[data-cell-kind="blank"][data-column-signal="strn"]',
          );
          const appearance = {
            agree: {
              state: agree.dataset.agreement,
              background: getComputedStyle(agree).backgroundColor,
              fontWeight: getComputedStyle(
                agree.querySelector('.comparison-cell-picks'),
              ).fontWeight,
              token: tokenBackground('--tone-agree-bg'),
              hasSignal: Boolean(agree.querySelector('.comparison-cell-signal')),
            },
            differ: {
              state: differ.dataset.agreement,
              background: getComputedStyle(differ).backgroundColor,
              fontWeight: getComputedStyle(
                differ.querySelector('.comparison-cell-picks'),
              ).fontWeight,
              borderLeftWidth: getComputedStyle(differ).borderLeftWidth,
              token: tokenBackground('--tone-differ-bg'),
              hasSignal: Boolean(differ.querySelector('.comparison-cell-signal')),
            },
            reference: {
              state: reference.dataset.agreement,
              background: getComputedStyle(reference).backgroundColor,
              fontWeight: getComputedStyle(
                reference.querySelector('.comparison-cell-picks'),
              ).fontWeight,
              hasSignal: Boolean(reference.querySelector('.comparison-cell-signal')),
            },
            blank: {
              state: blank.dataset.agreement,
              background: getComputedStyle(blank).backgroundColor,
              hasSignal: Boolean(blank.querySelector('.comparison-cell-signal')),
            },
            agreeMatchesReference: agree.querySelector('.comparison-cell-picks').textContent
              === reference.querySelector('.comparison-cell-picks').textContent,
          };
          document.querySelector('[data-comparison-title="2"]').click();
          const picker = document.querySelector('[data-comparison-column="2"]');
          picker.value = 'ld11';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();
          const outside = document.querySelector('[data-cell-kind="outside_scope"]');
          appearance.outside = {
            state: outside.dataset.agreement,
            background: getComputedStyle(outside).backgroundColor,
            hasSignal: Boolean(outside.querySelector('.comparison-cell-signal')),
          };
          document.querySelector('[data-comparison-title="2"]').click();
          const restoredPicker = document.querySelector('[data-comparison-column="2"]');
          restoredPicker.value = 'stim';
          restoredPicker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();
          const chipIds = [...document.querySelectorAll('[data-row-differs="true"]')]
            .map((row) => row.dataset.comparisonRace);
          document.querySelector('[data-comparison-differences]').click();
          await wait();
          return JSON.stringify({
            filteredIds: [...document.querySelectorAll('[data-comparison-race]')]
              .map((row) => row.dataset.comparisonRace),
            chipIds,
            status: document.querySelector('[data-comparison-status]').textContent,
            statusLive: document.querySelector('[data-comparison-status]')
              .getAttribute('aria-live'),
            visibleSignals: [...document.querySelectorAll(
              '[data-comparison-head] [data-column-signal]',
            )].map((heading) => heading.dataset.columnSignal),
            hiddenNotice: document.querySelector('[data-comparison-hidden-notice]').textContent,
            differsLabel: senator.querySelector('.comparison-race-differs').textContent,
            differsCarrierCount: senator.querySelectorAll('.comparison-race-differs').length,
            senatorStillShown: Boolean(document.querySelector(
              '[data-comparison-race="ld-32-state-senator"]',
            )),
            ...appearance,
          });
        })()
        """,
        mobile_width=mobile_width,
    )
    assert result["filteredIds"] == expected_ids
    assert result["chipIds"] == expected_ids
    assert result["status"] == f"{len(expected_ids)} of 32 races shown · {len(expected_ids)} differ"
    assert result["statusLive"] == "polite"
    assert result["agree"] == {
        "state": "agree",
        "background": result["agree"]["token"],
        "fontWeight": "700",
        "token": result["agree"]["token"],
        "hasSignal": False,
    }
    assert result["agreeMatchesReference"] is True
    assert result["differ"] == {
        "state": "differ",
        "background": result["differ"]["token"],
        "fontWeight": "700",
        "borderLeftWidth": "0px",
        "token": result["differ"]["token"],
        "hasSignal": False,
    }
    assert result["reference"]["state"] == "reference"
    assert result["reference"]["fontWeight"] == "700"
    assert result["reference"]["background"] not in {
        result["agree"]["token"],
        result["differ"]["token"],
    }
    assert result["reference"]["hasSignal"] is False
    assert result["blank"]["state"] == "neutral"
    assert result["blank"]["background"] not in {
        result["agree"]["token"],
        result["differ"]["token"],
    }
    assert result["blank"]["hasSignal"] is False
    assert result["outside"]["state"] == "neutral"
    assert result["outside"]["background"] not in {
        result["agree"]["token"],
        result["differ"]["token"],
    }
    assert result["outside"]["hasSignal"] is False
    assert result["visibleSignals"] == ["gall", "strn", "stim"]
    assert result["hiddenNotice"] == ""
    assert result["senatorStillShown"] is True
    assert result["differsLabel"] == "Differs"
    assert result["differsCarrierCount"] == 1


@pytest.mark.parametrize("mobile_width", [None, 390])
def test_agreement_tones_recompute_when_the_reference_changes(
    tmp_path: Path, mobile_width: int | None
) -> None:
    result = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const tokenBackground = (name) => {
            const probe = document.createElement('span');
            probe.style.background = `var(${name})`;
            document.body.append(probe);
            const color = getComputedStyle(probe).backgroundColor;
            probe.remove();
            return color;
          };
          const raceId = 'ld-32-state-representative-1';
          const beforeRace = document.querySelector(`[data-comparison-race="${raceId}"]`);
          const beforeCell = beforeRace.querySelector('[data-column-signal="strn"]');
          const before = {
            state: beforeCell.dataset.agreement,
            background: getComputedStyle(beforeCell).backgroundColor,
            fontWeight: getComputedStyle(
              beforeCell.querySelector('.comparison-cell-picks'),
            ).fontWeight,
            rowDiffers: beforeRace.dataset.rowDiffers,
            differsText: beforeRace.querySelector('.comparison-race-differs').textContent,
          };

          document.querySelector('[data-comparison-title="0"]').click();
          const picker = document.querySelector('[data-comparison-column="0"]');
          picker.value = 'Genv';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();

          const afterRace = document.querySelector(`[data-comparison-race="${raceId}"]`);
          const reference = afterRace.querySelector('[data-column-signal="Genv"]');
          const agree = afterRace.querySelector('[data-column-signal="strn"]');
          return JSON.stringify({
            before,
            after: {
              state: agree.dataset.agreement,
              background: getComputedStyle(agree).backgroundColor,
              fontWeight: getComputedStyle(
                agree.querySelector('.comparison-cell-picks'),
              ).fontWeight,
              matchesReference: agree.querySelector('.comparison-cell-picks').textContent
                === reference.querySelector('.comparison-cell-picks').textContent,
              rowDiffers: afterRace.dataset.rowDiffers,
              differsLabelPresent: Boolean(afterRace.querySelector('.comparison-race-differs')),
            },
            reference: {
              state: reference.dataset.agreement,
              background: getComputedStyle(reference).backgroundColor,
              fontWeight: getComputedStyle(
                reference.querySelector('.comparison-cell-picks'),
              ).fontWeight,
            },
            agreeToken: tokenBackground('--tone-agree-bg'),
            differToken: tokenBackground('--tone-differ-bg'),
          });
        })()
        """,
        mobile_width=mobile_width,
    )
    assert result["before"] == {
        "state": "differ",
        "background": result["differToken"],
        "fontWeight": "700",
        "rowDiffers": "true",
        "differsText": "Differs",
    }
    assert result["after"] == {
        "state": "agree",
        "background": result["agreeToken"],
        "fontWeight": "700",
        "matchesReference": True,
        "rowDiffers": "false",
        "differsLabelPresent": False,
    }
    assert result["reference"]["state"] == "reference"
    assert result["reference"]["fontWeight"] == "700"
    assert result["reference"]["background"] not in {
        result["agreeToken"],
        result["differToken"],
    }


def test_coendorsement_intersection_and_blank_are_not_differences(tmp_path: Path) -> None:
    result = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          document.querySelector('[data-comparison-remove="2"]').click();
          await wait();
          document.querySelector('[data-comparison-title="1"]').click();
          const picker = document.querySelector('[data-comparison-column="1"]');
          picker.value = 'kcdm';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();
          const coendorsement = document.querySelector(
            '[data-comparison-race="ld-11-state-representative-1"]',
          );
          const coendorsementCell = coendorsement.querySelector('[data-column-signal="kcdm"]');
          const coendorsementResult = {
            agreement: coendorsementCell.dataset.agreement,
            background: getComputedStyle(coendorsementCell).backgroundColor,
            picks: coendorsementCell.querySelector('.comparison-cell-picks').textContent,
            rowDiffers: coendorsement.dataset.rowDiffers,
          };
          const probe = document.createElement('span');
          probe.style.background = 'var(--tone-agree-bg)';
          document.body.append(probe);
          const agreeToken = getComputedStyle(probe).backgroundColor;
          probe.remove();
          document.querySelector('[data-comparison-title="1"]').click();
          const nextPicker = document.querySelector('[data-comparison-column="1"]');
          nextPicker.value = 'stim';
          nextPicker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();
          const blank = document.querySelector('[data-comparison-race="us-house-9"]');
          return JSON.stringify({
            coendorsementResult,
            agreeToken,
            blankAgreement: blank.querySelector('[data-column-signal="stim"]').dataset.agreement,
            blankRowDiffers: blank.dataset.rowDiffers,
          });
        })()
        """,
    )
    assert result["coendorsementResult"] == {
        "agreement": "agree",
        "background": result["agreeToken"],
        "picks": "Ashley Fedan / David Hackney",
        "rowDiffers": "false",
    }
    assert result["blankAgreement"] == "neutral"
    assert result["blankRowDiffers"] == "false"


def test_all_agree_and_no_match_empty_states_are_distinct_and_resettable(tmp_path: Path) -> None:
    all_agree = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          document.querySelector('[data-comparison-remove="2"]').click();
          await wait();
          document.querySelector('[data-comparison-title="1"]').click();
          const picker = document.querySelector('[data-comparison-column="1"]');
          picker.value = 's775';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();
          document.querySelector('[data-comparison-differences]').click();
          await wait();
          const message = document.querySelector('.comparison-empty p').textContent;
          const resetLabel = document.querySelector('.comparison-reset').textContent;
          document.querySelector('.comparison-reset').click();
          await wait();
          return JSON.stringify({
            message, resetLabel,
            rowsAfterReset: document.querySelectorAll('[data-comparison-race]').length,
            differencesChecked: document.querySelector('[data-comparison-differences]').checked,
          });
        })()
        """,
    )
    assert all_agree["message"].startswith("These signals agree in every race they share")
    assert all_agree["resetLabel"] == "Show all rows"
    assert all_agree["rowsAfterReset"] == 32
    assert all_agree["differencesChecked"] is False

    no_match_path = _comparison_html_path(tmp_path)
    no_match_html = no_match_path.read_text(encoding="utf-8")
    no_match_path.write_text(
        re.sub(r'"contested_race_ids": \[[^]]*\]', '"contested_race_ids": []', no_match_html),
        encoding="utf-8",
    )
    no_match = _evaluate_in_chrome(
        no_match_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          document.querySelector('[data-comparison-contested]').click();
          await wait();
          const message = document.querySelector('.comparison-empty p').textContent;
          const resetLabel = document.querySelector('.comparison-reset').textContent;
          document.querySelector('.comparison-reset').click();
          await wait();
          return JSON.stringify({
            message, resetLabel,
            rowsAfterReset: document.querySelectorAll('[data-comparison-race]').length,
            contestedChecked: document.querySelector('[data-comparison-contested]').checked,
          });
        })()
        """,
    )
    assert no_match["message"] == "No races match the current filters."
    assert no_match["resetLabel"] == "Reset filters"
    assert no_match["rowsAfterReset"] == 32
    assert no_match["contestedChecked"] is False
