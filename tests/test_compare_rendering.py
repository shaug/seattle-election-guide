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
    ComparisonCellView,
    _comparison_row_differs,  # pyright: ignore[reportPrivateUsage]
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
    assert "Put any sources side by side and see where they agree" in rendered
    assert "audited all-sources" not in rendered
    assert '<div class="segmented-control">' in rendered
    assert "Audited baseline" not in rendered
    assert 'class="comparison-only-badge"' not in rendered
    assert "Each organization has equal weight" not in rendered
    assert 'class="comparison-legend"' not in rendered
    assert 'class="comparison-method"' not in rendered
    assert "≠" not in rendered

    table = re.search(r'<table class="comparison-table".*?</table>', rendered, flags=re.DOTALL)
    assert table is not None
    normalized = re.sub(r"\s+", " ", unescape(table.group(0))).strip()
    assert hashlib.sha256(normalized.encode()).hexdigest() == (
        "37d7b85afc5f36d8a02fa1f9b24216f8e69759b10f5eb9beabf64432e1588421"
    )
    static_head = re.search(r"<thead.*?</thead>", normalized)
    assert static_head is not None
    assert "Reference" not in static_head.group(0)
    assert "Maximum" not in static_head.group(0)

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


def test_server_row_differences_are_relative_only_to_the_reference() -> None:
    def cell(*picks: str) -> ComparisonCellView:
        return ComparisonCellView(
            signal="test",
            kind="direct",
            choice_labels=picks,
            leading_pick_ids=picks,
        )

    assert _comparison_row_differs((cell("a", "b"), cell("a"), cell("b"))) is False
    assert _comparison_row_differs((cell("a"), cell("a", "b"), cell("b"))) is True
    assert _comparison_row_differs((cell(), cell("a"), cell("b"))) is False


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
    assert result["referenceHasRemove"] is False


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

          let copied = null;
          Object.defineProperty(navigator, 'share', { value: undefined, configurable: true });
          Object.defineProperty(navigator, 'clipboard', {
            value: { writeText: async (value) => { copied = value; } }, configurable: true,
          });
          document.querySelector('[data-comparison-copy]').click();
          await wait();

          document.querySelector('[data-comparison-remove="2"]').click();
          await wait();
          return JSON.stringify({
            defaultRows, defaultStatus, pickerLabel, initialPickerValue, allSourcesOptions,
            duplicateDisabled, escapeFocus, blurClosed,
            changedRows, changedTintedRows, changedStatus, changedHash, focusAfterChange,
            referenceAgreement, allSourcesAvailableAfterChange, afterBack, afterForward, copied,
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
    assert result["copied"].endswith(result["changedHash"])
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
        initial_url=result["copied"],
    )
    assert restored["columns"] == ["Genv", "strn", "stim"]
    assert restored["referenceLabel"] == "Change reference, currently Environment"


def test_compare_client_ignores_lens_state_and_keeps_its_default_reference(tmp_path: Path) -> None:
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
          return JSON.stringify({
            before,
            after: referenceText(),
            columns: [...document.querySelectorAll(
              '[data-comparison-head] [data-column-signal]',
            )].map((heading) => heading.dataset.columnSignal),
            referenceInteractive: Boolean(document.querySelector(
              '[data-column-signal="gall"] [data-comparison-title="0"]',
            )),
          });
        })()
        """,
    )
    assert result == {
        "before": result["before"],
        "after": result["before"],
        "columns": ["gall", "strn", "stim"],
        "referenceInteractive": True,
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
          const presetColumns = [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal);
          const historyBeforeFilters = history.length;
          document.querySelector('[data-comparison-contested]').click();
          await wait();
          const rowsBeforeDifferences = document
            .querySelectorAll('[data-comparison-race]').length;
          document.querySelector('[data-comparison-contested-differences]').click();
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
              differencesChecked: document.querySelector(
                '[data-comparison-contested-differences]',
              ).checked,
              shareSeparated: !document.querySelector('[data-comparison-copy]')
                .closest('.comparison-controls'),
          });
        })()
        """,
    )
    assert result["presetHref"].startswith("#cmp=1&cols=gallstrnstim&")
    assert result["presetColumns"] == ["gall", "strn", "stim"]
    assert "races=contested" in result["hash"]
    assert "diff=1" in result["hash"]
    assert result["rowCount"] > 0
    assert result["rowCount"] < result["rowsBeforeDifferences"]
    assert result["historyAfterFilters"] == result["historyBeforeFilters"]
    assert result["copied"] == result["beforeCopy"]
    assert re.fullmatch(r"\d+ of \d+ races shown · \d+ differ", result["status"])
    assert result["copyStatus"] == "Link copied."
    assert result["differencesChecked"] is True
    assert result["shareSeparated"] is True
    restored = _evaluate_in_chrome(
        html_path,
        """
        (() => JSON.stringify({
          columns: [...document.querySelectorAll(
            '[data-comparison-head] [data-column-signal]',
          )].map((heading) => heading.dataset.columnSignal),
          contested: document.querySelector('[data-comparison-contested-differences]').checked,
          copiedHash: location.hash,
        }))()
        """,
        initial_url=result["copied"],
    )
    assert restored["columns"] == result["presetColumns"]
    assert restored["contested"] is True
    assert restored["copiedHash"] == result["hash"]


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
            copyTag: document.querySelector('[data-comparison-copy]').tagName,
            titlesFit: titles.every((title) => title.scrollWidth <= title.clientWidth),
            removeTitle: remove.title,
            removeWidth: remove.getBoundingClientRect().width,
            removeHeight: remove.getBoundingClientRect().height,
            headerBackground: getComputedStyle(
              document.querySelector('[data-column-signal="eccd"]'),
            ).backgroundColor,
            whiteToken: (() => {
              const probe = document.createElement('i');
              probe.style.background = 'var(--white)';
              document.body.append(probe);
              const value = getComputedStyle(probe).backgroundColor;
              probe.remove();
              return value;
            })(),
            raceControlColumns: getComputedStyle(
              document.querySelector('.comparison-race-filters .segmented-control'),
            ).gridTemplateColumns,
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
    assert mobile["tableWidth"] <= mobile["wrapWidth"] + 1
    assert mobile["outerWidth"] == mobile["viewportWidth"]
    assert mobile["wrapScrollWidth"] == mobile["wrapClientWidth"]
    assert mobile["wrapOverflowX"] == "visible"
    assert mobile["rowDisplay"] == "block"
    assert mobile["cellDisplay"] == "grid"
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
    assert mobile["copyTag"] == "BUTTON"
    assert mobile["titlesFit"] is True
    assert mobile["removeTitle"] == (
        "Remove Environment and Climate Caucus of the Washington State Democratic Party"
    )
    assert mobile["removeWidth"] >= 40
    assert mobile["removeHeight"] >= 40
    assert mobile["headerBackground"] == mobile["whiteToken"]
    assert len(mobile["raceControlColumns"].split()) == 2
    assert desktop["visibleSignals"] == ["gall", "eccd", "stim"]
    assert desktop["noticeVisible"] is False
    assert desktop["titleTopSpread"] < 1
    assert desktop["stickyHead"] == "sticky"
    assert desktop["wrapOverflowX"] == "visible"
    assert desktop["wrapScrollWidth"] == desktop["wrapClientWidth"]
    assert desktop["tableWidth"] <= desktop["wrapWidth"] + 1
    assert desktop["outerWidth"] == desktop["viewportWidth"]
    assert desktop["titlesFit"] is True


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
          const transparent = 'rgba(0, 0, 0, 0)';
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
              token: tokenBackground('--tone-agree-bg'),
              hasSignal: Boolean(agree.querySelector('.comparison-cell-signal')),
            },
            differ: {
              state: differ.dataset.agreement,
              background: getComputedStyle(differ).backgroundColor,
              borderLeftWidth: getComputedStyle(differ).borderLeftWidth,
              token: tokenBackground('--tone-differ-bg'),
              hasSignal: Boolean(differ.querySelector('.comparison-cell-signal')),
            },
            reference: {
              state: reference.dataset.agreement,
              background: getComputedStyle(reference).backgroundColor,
              hasSignal: Boolean(reference.querySelector('.comparison-cell-signal')),
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
            visibleSignals: [...document.querySelectorAll(
              '[data-comparison-head] [data-column-signal]',
            )].map((heading) => heading.dataset.columnSignal),
            hiddenNotice: document.querySelector('[data-comparison-hidden-notice]').textContent,
            differsLabel: senator.querySelector('.comparison-race-differs').textContent,
            differsCarrierCount: senator.querySelectorAll('.comparison-race-differs').length,
            transparent,
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
        "background": result["transparent"],
        "token": result["agree"]["token"],
        "hasSignal": False,
    }
    assert result["differ"] == {
        "state": "differ",
        "background": result["differ"]["token"],
        "borderLeftWidth": "0px",
        "token": result["differ"]["token"],
        "hasSignal": False,
    }
    assert result["reference"]["state"] == "reference"
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
    assert result["visibleSignals"] == ["gall", "strn", "stim"]
    assert result["hiddenNotice"] == ""
    assert result["senatorStillShown"] is True
    assert result["differsLabel"] == "Differs"
    assert result["differsCarrierCount"] == 1


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
            picks: coendorsementCell.querySelector('.comparison-cell-picks').textContent,
            rowDiffers: coendorsement.dataset.rowDiffers,
          };
          document.querySelector('[data-comparison-title="1"]').click();
          const nextPicker = document.querySelector('[data-comparison-column="1"]');
          nextPicker.value = 'stim';
          nextPicker.dispatchEvent(new Event('change', { bubbles: true }));
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
          document.querySelector('[data-comparison-title="1"]').click();
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
