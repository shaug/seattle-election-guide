"""Server-rendered comparisons page contract tests."""

from __future__ import annotations

import hashlib
import html
import json
import re
from html import unescape
from pathlib import Path

import pytest

from election_guide.publication.comparisons import ComparisonsPolicy
from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.renderer import (
    read_rendering_configuration,
    render_comparison_document,
    render_html_document,
    render_sources_document,
)
from tests.test_comparisons import _bundle  # pyright: ignore[reportPrivateUsage]
from tests.test_rendering import _evaluate_in_chrome  # pyright: ignore[reportPrivateUsage]

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_DIFFERENCE_ORACLE = PROJECT_ROOT / "tests/fixtures/comparison-default-differences.json"


def _enabled_view_model() -> PublicationViewModel:
    view_model = _bundle().view_model
    return view_model.model_copy(
        update={
            "comparisons": view_model.comparisons.model_copy(
                update={"policy": ComparisonsPolicy(enabled=True)}
            )
        }
    )


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
        data_sets = [set(picks) for picks in leading.values() if picks]
        if any(
            left.isdisjoint(right)
            for index, left in enumerate(data_sets)
            for right in data_sets[index + 1 :]
        ):
            observed[race_id] = leading

    expected = {item["race_id"]: item["leading_pick_ids"] for item in oracle["differing_races"]}
    assert observed == expected
    assert [displays[item["race_id"]].race_label for item in oracle["differing_races"]] == [
        item["race_label"] for item in oracle["differing_races"]
    ]


def test_compare_document_server_renders_default_contract_snapshot() -> None:
    view_model = _enabled_view_model()
    rendered = render_comparison_document(
        view_model,
        public_site_url="https://seattleelections.guide",
        project_url="https://github.com/shaug/seattle-election-guide",
        pdf_filename="Seattle_Election_Guide.pdf",
    )

    assert 'href="/e/wa-2026-primary/compare/" aria-current="page">Compare</a>' in rendered
    assert 'data-default-columns="gall,strn,stim"' in rendered
    assert rendered.count("data-comparison-race=") == len(view_model.comparisons.display_index)
    assert (
        rendered.count('data-column-signal="gall"') == len(view_model.comparisons.display_index) + 1
    )
    assert (
        rendered.count('data-column-signal="strn"') == len(view_model.comparisons.display_index) + 1
    )
    assert (
        rendered.count('data-column-signal="stim"') == len(view_model.comparisons.display_index) + 1
    )
    assert "Shown for comparison; never counted toward the scores." in rendered
    assert (
        "Each organization has equal weight; multi-candidate endorsements split one point."
        in rendered
    )

    table = re.search(r'<table class="comparison-table".*?</table>', rendered, flags=re.DOTALL)
    assert table is not None
    normalized = re.sub(r"\s+", " ", unescape(table.group(0))).strip()
    assert hashlib.sha256(normalized.encode()).hexdigest() == (
        "9422da29b50aa452268e6dc35e3a75b2655954186fbbeec1444ede453f91c9c0"
    )

    payload_match = re.search(
        r'<script type="application/json" id="comparison-bindings" '
        r"data-comparison-bindings>(.*?)</script>",
        rendered,
        flags=re.DOTALL,
    )
    assert payload_match is not None
    payload = json.loads(payload_match.group(1))
    assert payload["default_columns"] == ["gall", "strn", "stim"]
    assert payload["personalization"] == view_model.personalization.model_dump(mode="json")
    assert payload["comparisons"] == view_model.comparisons.model_dump(mode="json")

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
        read_rendering_configuration(PROJECT_ROOT / "config/rendering/pdf.yaml"),
    )
    sources_page = render_sources_document(
        view_model,
        public_site_url="https://seattleelections.guide",
    )
    for page in (guide, sources_page):
        assert 'href="/e/wa-2026-primary/compare/">Compare</a>' in page


def test_compare_document_refuses_disabled_policy() -> None:
    with pytest.raises(ValueError, match="release policy is disabled"):
        render_comparison_document(
            _bundle().view_model,
            public_site_url="https://seattleelections.guide",
        )


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


def test_compare_client_enforces_picker_bounds_and_history(tmp_path: Path) -> None:
    html_path = _comparison_html_path(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          const signals = () => [...document.querySelectorAll('[data-comparison-column]')]
            .map((picker) => picker.value);
          const initial = signals();
          const firstPicker = document.querySelector('[data-comparison-column="0"]');
          const duplicateDisabled = [...firstPicker.options]
            .find((item) => item.value === initial[1]).disabled;
          const multiCategoryCopies = [...firstPicker.options]
            .filter((item) => item.value === 'wsto').length;

          document.querySelector('[data-comparison-remove="2"]').click();
          await wait();
          const afterRemove = signals();
          const removeButtonsAtMinimum = document
            .querySelectorAll('[data-comparison-remove]').length;
          document.querySelector('.comparison-column-add').click();
          await wait();
          const afterAdd = signals();

          const picker = document.querySelector('[data-comparison-column="1"]');
          const previous = picker.value;
          picker.value = 'Glab';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();
          const changed = signals();
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
            afterBack, afterForward,
            hasAddAtMaximum: Boolean(document.querySelector('.comparison-column-add')),
          });
        })()
        """,
    )
    assert result["initial"] == ["gall", "strn", "stim"]
    assert result["duplicateDisabled"] is True
    assert result["multiCategoryCopies"] == 2
    assert result["afterRemove"] == ["gall", "strn"]
    assert result["removeButtonsAtMinimum"] == 0
    assert len(result["afterAdd"]) == 3
    assert len(set(result["afterAdd"])) == 3
    assert result["changed"] == ["gall", "Glab", result["afterAdd"][2]]
    assert "cols=gallGlab" in result["changedHash"]
    assert result["afterBack"] == result["afterAdd"]
    assert result["afterForward"] == result["changed"]
    assert result["hasAddAtMaximum"] is False


def test_compare_client_presets_filters_and_copy_link_round_trip(tmp_path: Path) -> None:
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
          const presetColumns = [...document.querySelectorAll('[data-comparison-column]')]
            .map((picker) => picker.value);
          const historyBeforeFilters = history.length;
          document.querySelector('[data-comparison-contested]').click();
          await wait();
          const rowsBeforeDifferences = document
            .querySelectorAll('[data-comparison-race]').length;
          document.querySelector('[data-comparison-differences]').click();
          await wait();
          const historyAfterFilters = history.length;
          const rowCount = document.querySelectorAll('[data-comparison-race]').length;
          const beforeCopy = location.href;
          let copied = null;
          Object.defineProperty(navigator, 'share', { value: undefined, configurable: true });
          Object.defineProperty(navigator, 'clipboard', {
            value: { writeText: async (value) => { copied = value; } }, configurable: true,
          });
          document.querySelector('[data-comparison-copy]').click();
          await wait();
            return JSON.stringify({
              presetHref, presetColumns, hash: location.hash, rowCount, beforeCopy, copied,
              rowsBeforeDifferences, historyBeforeFilters, historyAfterFilters,
              status: document.querySelector('[data-comparison-status]').textContent,
              copyStatus: document.querySelector('[data-comparison-copy-status]').textContent,
              differencesPressed: document.querySelector('[data-comparison-differences]')
              .getAttribute('aria-pressed'),
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
    assert result["copied"] == result["beforeCopy"]
    assert re.fullmatch(r"\d+ of \d+ races shown · \d+ differ", result["status"])
    assert result["copyStatus"] == "Link copied."
    assert result["differencesPressed"] == "true"


def test_compare_client_labels_comparison_category_truthfully(tmp_path: Path) -> None:
    html_path = _comparison_html_path(tmp_path)
    result = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          const picker = document.querySelector('[data-comparison-column="0"]');
          const comparisonCategory = [...picker.options]
            .find((item) => item.value === 'Gcmp');
          picker.value = 'Gcmp';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          const meta = document.querySelector('.comparison-column-meta');
          const gall = [...document.querySelectorAll('[data-comparison-column="1"] option')]
            .find((item) => item.value === 'gall');
          return JSON.stringify({
            optionLabel: comparisonCategory.textContent,
            coverage: meta.textContent,
            allSourcesDisabledInSibling: gall.disabled,
          });
        })()
        """,
    )
    assert result["optionLabel"].endswith("(Comparison only)")
    assert result["coverage"] == "Comparison only · never counted"
    assert result["allSourcesDisabledInSibling"] is False


def test_compare_client_mobile_budget_and_focus_have_layout_evidence(tmp_path: Path) -> None:
    html_path = _comparison_html_path(tmp_path)
    mobile = _evaluate_in_chrome(
        html_path,
        """
        (() => {
          const pickers = [...document.querySelectorAll('[data-comparison-column]')];
          pickers[0].focus();
          const focus = getComputedStyle(pickers[0]);
          const table = document.querySelector('[data-comparison-table]').getBoundingClientRect();
          const wrap = document.querySelector('[data-comparison-grid]').getBoundingClientRect();
          return JSON.stringify({
            visibleSignals: pickers.map((picker) => picker.value),
            notice: document.querySelector('[data-comparison-hidden-notice]').textContent,
            noticeVisible: !document.querySelector('[data-comparison-hidden-notice]').hidden,
            configured: new URLSearchParams(location.hash.slice(1)).get('cols'),
            focusOutlineStyle: focus.outlineStyle,
            focusOutlineWidth: focus.outlineWidth,
            tableWidth: table.width,
            wrapWidth: wrap.width,
          });
        })()
        """,
        mobile_width=390,
    )
    desktop = _evaluate_in_chrome(
        html_path,
        """
        (() => JSON.stringify({
          visibleSignals: [...document.querySelectorAll('[data-comparison-column]')]
            .map((picker) => picker.value),
          noticeVisible: !document.querySelector('[data-comparison-hidden-notice]').hidden,
        }))()
        """,
    )
    assert mobile["visibleSignals"] == ["gall", "strn"]
    assert mobile["noticeVisible"] is True
    assert "1 configured column hidden" in mobile["notice"]
    assert mobile["configured"] is None
    assert mobile["focusOutlineStyle"] != "none"
    assert float(mobile["focusOutlineWidth"].removesuffix("px")) > 0
    assert mobile["tableWidth"] >= mobile["wrapWidth"]
    assert desktop["visibleSignals"] == ["gall", "strn", "stim"]
    assert desktop["noticeVisible"] is False


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
          const baseline = senator.querySelector('[data-column-signal="gall"]');
          const blank = document.querySelector(
            '[data-cell-kind="blank"][data-column-signal="strn"]',
          );
          const appearance = {
            agree: {
              state: agree.dataset.agreement,
              background: getComputedStyle(agree).backgroundColor,
              token: tokenBackground('--tone-agree-bg'),
              visible: agree.querySelector('.comparison-cell-signal').textContent,
              accessible: agree.querySelector('.visually-hidden').textContent,
            },
            differ: {
              state: differ.dataset.agreement,
              background: getComputedStyle(differ).backgroundColor,
              token: tokenBackground('--tone-differ-bg'),
              visible: differ.querySelector('.comparison-cell-signal').textContent,
              accessible: differ.querySelector('.visually-hidden').textContent,
            },
            baseline: {
              state: baseline.dataset.agreement,
              background: getComputedStyle(baseline).backgroundColor,
              hasSignal: Boolean(baseline.querySelector('.comparison-cell-signal')),
            },
            blank: {
              state: blank.dataset.agreement,
              background: getComputedStyle(blank).backgroundColor,
              hasSignal: Boolean(blank.querySelector('.comparison-cell-signal')),
            },
          };
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
            visibleSignals: [...document.querySelectorAll('[data-comparison-column]')]
              .map((picker) => picker.value),
            hiddenNotice: document.querySelector('[data-comparison-hidden-notice]').textContent,
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
        "token": result["agree"]["token"],
        "visible": "Agrees",
        "accessible": "Agrees with baseline.",
    }
    assert result["differ"] == {
        "state": "differ",
        "background": result["differ"]["token"],
        "token": result["differ"]["token"],
        "visible": "≠ Differs",
        "accessible": "Differs from baseline.",
    }
    assert result["baseline"]["state"] == "baseline"
    assert result["baseline"]["background"] not in {
        result["agree"]["token"],
        result["differ"]["token"],
    }
    assert result["baseline"]["hasSignal"] is False
    assert result["blank"]["state"] == "neutral"
    assert result["blank"]["background"] not in {
        result["agree"]["token"],
        result["differ"]["token"],
    }
    assert result["blank"]["hasSignal"] is False
    if mobile_width is None:
        assert result["visibleSignals"] == ["gall", "strn", "stim"]
    else:
        assert result["visibleSignals"] == ["gall", "strn"]
        assert "remains configured and counted" in result["hiddenNotice"]
        assert result["senatorStillShown"] is True


def test_coendorsement_intersection_and_blank_are_not_differences(tmp_path: Path) -> None:
    result = _evaluate_in_chrome(
        _comparison_html_path(tmp_path),
        """
        (async () => {
          const wait = () => new Promise((resolve) => setTimeout(resolve, 120));
          document.querySelector('[data-comparison-remove="2"]').click();
          await wait();
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
            picks: coendorsementCell.querySelector('.comparison-cell-picks').textContent,
            rowDiffers: coendorsement.dataset.rowDiffers,
          };
          picker.value = 'stim';
          picker.dispatchEvent(new Event('change', { bubbles: true }));
          await wait();
          const blank = document.querySelector('[data-comparison-race="us-house-9"]');
          return JSON.stringify({
            coendorsementResult,
            blankAgreement: blank.querySelector('[data-column-signal="stim"]').dataset.agreement,
            blankRowDiffers: blank.dataset.rowDiffers,
          });
        })()
        """,
    )
    assert result["coendorsementResult"] == {
        "agreement": "agree",
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
          const picker = document.querySelector('[data-comparison-column="1"]');
          picker.value = 'wslc';
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
            differencesPressed: document.querySelector('[data-comparison-differences]')
              .getAttribute('aria-pressed'),
          });
        })()
        """,
    )
    assert all_agree["message"].startswith("These signals agree in every race they share")
    assert all_agree["resetLabel"] == "Show all rows"
    assert all_agree["rowsAfterReset"] == 32
    assert all_agree["differencesPressed"] == "false"

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
            contestedPressed: document.querySelector('[data-comparison-contested]')
              .getAttribute('aria-pressed'),
          });
        })()
        """,
    )
    assert no_match["message"] == "No races match the current filters."
    assert no_match["resetLabel"] == "Reset filters"
    assert no_match["rowsAfterReset"] == 32
    assert no_match["contestedPressed"] == "false"
