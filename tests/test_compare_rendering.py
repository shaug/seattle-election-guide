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

PROJECT_ROOT = Path(__file__).parents[1]


def _enabled_view_model() -> PublicationViewModel:
    view_model = _bundle().view_model
    return view_model.model_copy(
        update={
            "comparisons": view_model.comparisons.model_copy(
                update={"policy": ComparisonsPolicy(enabled=True)}
            )
        }
    )


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
        "a1e06e05b29202f3a0d146111ef150a2e8078142a9104ea614638b59a23c4020"
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
            rf'<tr data-comparison-race="{re.escape(display.race_id)}">(.*?)</tr>',
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
            assert (
                f'data-column-signal="{source.code}"\n'
                f'                data-cell-kind="{expected_kind}"\n'
                f"                data-leading-pick-ids='{json.dumps(expected_ids)}'" in row
            )
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
