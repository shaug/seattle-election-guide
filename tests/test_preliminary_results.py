"""Offline preliminary admission; all counts and source IDs below are synthetic."""

import base64
import hashlib
import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.calendar.watch import read_repository_artifacts
from election_guide.cli import app
from election_guide.evidence.models import CaptureRequest, UnavailableRequest
from election_guide.evidence.storage import record_capture, record_unavailable
from election_guide.inventory.importer import read_inventory
from election_guide.publication.models import PublicationViewModel
from election_guide.rendering import context
from election_guide.rendering.browser import _CdpSocket  # pyright: ignore[reportPrivateUsage]
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import (
    render_comparison_document,
    render_html_document,
    render_race_document,
)
from election_guide.rendering.models import PagePresentation
from election_guide.results.loader import read_results, reject_committed_counting_status
from election_guide.results.models import PreliminaryElectionResults
from election_guide.results.validation import validate_results_inventory
from tests.address_lookup_fixtures import without_live_address_requests
from tests.test_precinct_rendering import general_view as general_view
from tests.test_rendering import (  # pyright: ignore[reportPrivateUsage]
    _client_payload,  # pyright: ignore[reportPrivateUsage]
    _evaluate_in_chrome,  # pyright: ignore[reportPrivateUsage]
    _race_card_html,  # pyright: ignore[reportPrivateUsage]
)

ROOT = Path(__file__).parents[1]
INVENTORY = ROOT / "data/normalized/wa-2026-general-inventory.json"


def preliminary_document() -> dict[str, Any]:
    """Whole synthetic inventory, not a production source/coverage admission."""
    inventory = read_inventory(INVENTORY)
    reference = "data/manifests/evidence/synthetic-preliminary.json"
    return {
        "schema_version": "1.1",
        "election_id": inventory.election.id,
        "status": "preliminary",
        "captures": [
            {
                "kind": "preliminary",
                "authority_id": "wa-secretary-of-state",
                "captured_at": "2026-11-04T05:00:00Z",
                "evidence": reference,
            }
        ],
        "races": [
            {
                "race_id": race.id,
                "jurisdiction_id": race.jurisdiction_id,
                "source_contest_id": f"synthetic-{race.id}",
                "coverage": "whole_jurisdiction",
                "coverage_evidence": reference,
                "authority_id": "wa-secretary-of-state",
                "authority": "Washington Secretary of State",
                "capture_evidence": reference,
                "reported_at": "2026-11-04T04:00:00Z",
                "reporting_complete": False,
                "ballots_counted": 100 * len(race.choices) + 20,
                "write_in_votes": 10,
                "outcomes": [{"choice_id": choice.id, "votes": 100} for choice in race.choices],
            }
            for race in inventory.races
        ],
    }


def read_document(tmp_path: Path, document: dict[str, Any]) -> PreliminaryElectionResults:
    path = tmp_path / "results.yaml"
    path.write_text(yaml.safe_dump(document))
    results = read_results(path)
    assert isinstance(results, PreliminaryElectionResults)
    return results


def test_whole_jurisdiction_count_so_far_is_admitted_without_certification(tmp_path: Path) -> None:
    results = read_document(tmp_path, preliminary_document())
    validate_results_inventory(results, read_inventory(INVENTORY))
    reject_committed_counting_status(results)
    assert results.status == "preliminary"
    assert len(results.races) == 52
    dumped = results.model_dump(mode="json")
    assert "certified_on" not in dumped
    assert "advanced" not in dumped["races"][0]["outcomes"][0]
    assert dumped["races"][0]["reporting_complete"] is False


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("coverage", "county_subset", "whole_jurisdiction"),
        ("reported_at", "2026-11-04T06:00:00Z", "count timestamp"),
        ("reported_at", "2026-11-04T04:00:00", "timezone"),
        ("authority_id", "king-county-elections", "authority"),
    ],
)
def test_unproved_scope_or_clock_cannot_become_preliminary_results(
    tmp_path: Path, field: str, value: str, match: str
) -> None:
    document = preliminary_document()
    document["races"][0][field] = value
    with pytest.raises(ValueError, match=match):
        read_document(tmp_path, document)


def test_missing_race_or_named_choice_cannot_masquerade_as_complete_results(tmp_path: Path) -> None:
    document = preliminary_document()
    missing_race = deepcopy(document)
    missing_race["races"].pop()
    with pytest.raises(ValueError, match="every inventory race"):
        validate_results_inventory(read_document(tmp_path, missing_race), read_inventory(INVENTORY))
    contested = next(race for race in document["races"] if len(race["outcomes"]) > 1)
    contested["outcomes"].pop()
    with pytest.raises(ValueError, match="every named ballot choice"):
        validate_results_inventory(read_document(tmp_path, document), read_inventory(INVENTORY))


def test_duplicate_or_winner_fields_are_not_preliminary_input(tmp_path: Path) -> None:
    document = preliminary_document()
    document["races"][0]["outcomes"][0]["advanced"] = True
    with pytest.raises(ValueError, match="Extra inputs"):
        read_document(tmp_path, document)


def test_preliminary_zero_count_and_write_ins_remain_separate(tmp_path: Path) -> None:
    document = preliminary_document()
    race = document["races"][0]
    race["ballots_counted"] = 0
    race["write_in_votes"] = 0
    for outcome in race["outcomes"]:
        outcome["votes"] = 0
    results = read_document(tmp_path, document)
    assert results.races[0].outcomes[0].votes == 0
    # Shares are derived from named counts; zero is not a fabricated 100%.
    assert "share" not in results.model_dump(mode="json")["races"][0]["outcomes"][0]


def test_unknown_reporting_completion_does_not_invalidate_whole_jurisdiction_counts(
    tmp_path: Path,
) -> None:
    document = preliminary_document()
    document["races"][0]["reporting_complete"] = None
    results = read_document(tmp_path, document)
    assert results.model_dump(mode="json")["races"][0]["reporting_complete"] is None


def test_preliminary_general_result_reuses_tally_without_calling_outcomes(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    results = read_document(tmp_path, preliminary_document())
    view = general_view.model_copy(update={"results": results})
    html = render_html_document(
        view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    )
    card = _race_card_html(html, "king-county-assessor")
    assert (
        '<span class="race-results-status race-results-status-preliminary">Unofficial</span>'
        in card
    )
    assert "Count updated Nov 3, 8:00:00 p.m. PST" in card

    assert card.count('class="race-results-row"') == 2
    assert card.count('style="width:50.0%"') == 2
    assert "220 ballots" in card
    assert "race-results-row-trailing" not in card
    assert "race-results-bar-aligned" not in card
    assert "race-results-bar-different" not in card
    assert "race-detail-result-chip" not in card
    assert "Unofficial results · counts may change" in html
    # County's scheduled certification date is not a proved statewide promise.
    assert "Results certify November 24" not in html


@pytest.mark.parametrize("votes", [(0, 0), (50, 50)])
def test_ambiguous_preliminary_counts_keep_neutral_meters(
    tmp_path: Path, general_view: PublicationViewModel, votes: tuple[int, int]
) -> None:
    document = preliminary_document()
    tally = next(r for r in document["races"] if r["race_id"] == "king-county-assessor")
    for row, count in zip(tally["outcomes"], votes, strict=True):
        row["votes"] = count
    tally["write_in_votes"] = 0
    tally["ballots_counted"] = sum(votes)
    view = general_view.model_copy(update={"results": read_document(tmp_path, document)})
    card = _race_card_html(
        render_html_document(
            view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        ),
        "king-county-assessor",
    )
    assert card.count('class="race-results-bar"') == 2
    assert "race-results-bar-aligned" not in card
    assert "race-results-bar-different" not in card
    assert "race-detail-result-chip" not in card


def _view_with_count_leader(
    tmp_path: Path,
    view: PublicationViewModel,
    votes: tuple[int, ...],
    recommended: tuple[int, ...] | None,
    *,
    write_ins: int = 0,
    race_id: str = "king-county-assessor",
) -> PublicationViewModel:
    race = next(r for section in view.sections for r in section.races if r.id == race_id)
    document = preliminary_document()
    tally = next(r for r in document["races"] if r["race_id"] == race_id)
    tally["outcomes"] = [
        {"choice_id": candidate.id, "votes": count}
        for candidate, count in zip(race.candidates, votes, strict=True)
    ]
    tally["write_in_votes"] = write_ins
    tally["ballots_counted"] = sum(votes) + write_ins
    updated = (
        race.model_copy(
            update={"recommendation_candidate_ids": [race.candidates[i].id for i in recommended]}
        )
        if recommended is not None
        else race
    )
    return view.model_copy(
        update={
            "results": read_document(tmp_path, document),
            "sections": [
                section.model_copy(
                    update={"races": [updated if r.id == race_id else r for r in section.races]}
                )
                for section in view.sections
            ],
        }
    )


@pytest.mark.parametrize(
    "votes,recommended,write_ins,expected",
    [
        ((60, 40), (0,), 0, ("aligned", None)),
        ((40, 60), (0,), 0, (None, "different")),
        ((40, 60), (0, 1), 0, (None, "aligned")),
        ((60, 40), (), 0, ("different", None)),
        ((60, 40), (1,), 0, ("different", None)),
        ((50, 50), (0, 1), 0, (None, None)),
        ((0, 0), (0,), 0, (None, None)),
        ((50001, 50000), (0,), 0, ("aligned", None)),
        ((60, 40), (0,), 59, ("aligned", None)),
        ((60, 40), (0,), 60, (None, None)),
        ((60, 40), (0,), 61, (None, None)),
    ],
)
def test_current_unofficial_leader_color_never_calls_an_outcome(
    tmp_path: Path,
    general_view: PublicationViewModel,
    votes: tuple[int, int],
    recommended: tuple[int, ...],
    write_ins: int,
    expected: tuple[str | None, str | None],
) -> None:
    view = _view_with_count_leader(tmp_path, general_view, votes, recommended, write_ins=write_ins)
    race = next(r for s in view.sections for r in s.races if r.id == "king-county-assessor")
    result = context.race_results_view(
        race, view.results, election_type="general", capture_urls=None
    )
    assert result is not None and result.preliminary
    rows = {row.candidate_id: row for row in result.outcomes}
    assert tuple(rows[c.id].meter_tone for c in race.candidates) == expected
    assert not any(row.advanced or row.chip_label for row in result.outcomes)
    if votes == (50001, 50000):
        assert [row.percentage_label for row in result.outcomes] == ["50.0%", "50.0%"]


@pytest.mark.parametrize(
    "race_id,election_type",
    [("king-county-assessor", "primary"), ("initiative-26-645", "general")],
)
def test_count_lead_does_not_invent_advancement_slots_or_measure_thresholds(
    tmp_path: Path, general_view: PublicationViewModel, race_id: str, election_type: str
) -> None:
    view = _view_with_count_leader(tmp_path, general_view, (60, 40), (0,), race_id=race_id)
    race = next(r for s in view.sections for r in s.races if r.id == race_id)
    result = context.race_results_view(
        race, view.results, election_type=election_type, capture_urls=None
    )
    assert result is not None
    assert [row.meter_tone for row in result.outcomes] == ["aligned", None]
    assert not any(row.advanced or row.chip_label for row in result.outcomes)


def test_submajority_current_leader_has_alignment_without_a_majority_claim(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    view = _view_with_count_leader(tmp_path, general_view, (40, 35), (0,))
    race = next(r for s in view.sections for r in s.races if r.id == "king-county-assessor")
    third = race.candidates[0].model_copy(
        update={"id": "synthetic-third-choice", "label": "Synthetic third choice"}
    )
    race = race.model_copy(update={"candidates": [*race.candidates, third]})
    assert isinstance(view.results, PreliminaryElectionResults)
    document = view.results.model_dump(mode="json")
    tally = next(r for r in document["races"] if r["race_id"] == race.id)
    tally["outcomes"].append({"choice_id": third.id, "votes": 25})
    tally["ballots_counted"] = 100
    result = context.race_results_view(
        race, read_document(tmp_path, document), election_type="general", capture_urls=None
    )
    assert result is not None
    assert [row.percentage_label for row in result.outcomes] == ["40.0%", "35.0%", "25.0%"]
    assert [row.meter_tone for row in result.outcomes] == ["aligned", None, None]
    assert not any(row.advanced or row.chip_label for row in result.outcomes)


@pytest.mark.parametrize(
    "votes,write_ins,expected",
    [(20, 0, "aligned"), (20, 19, "aligned"), (20, 20, None), (0, 0, None)],
)
def test_unopposed_preliminary_count_does_not_become_a_called_outcome(
    tmp_path: Path,
    general_view: PublicationViewModel,
    votes: int,
    write_ins: int,
    expected: str | None,
) -> None:
    original = next(r for s in general_view.sections for r in s.races if len(r.candidates) == 1)
    view = _view_with_count_leader(
        tmp_path, general_view, (votes,), (0,), race_id=original.id, write_ins=write_ins
    )
    race = next(r for s in view.sections for r in s.races if r.id == original.id)
    result = context.race_results_view(
        race, view.results, election_type="general", capture_urls=None
    )
    assert result is not None and len(result.outcomes) == 1
    assert result.outcomes[0].meter_tone == expected
    assert not result.outcomes[0].advanced and result.outcomes[0].chip_label is None


@pytest.mark.parametrize("missing", ["race", "choice"])
def test_missing_preliminary_data_cannot_manufacture_a_colored_leader(
    tmp_path: Path, general_view: PublicationViewModel, missing: str
) -> None:
    view = _view_with_count_leader(tmp_path, general_view, (60, 40), (0,))
    race = next(r for s in view.sections for r in s.races if r.id == "king-county-assessor")
    assert isinstance(view.results, PreliminaryElectionResults)
    document = view.results.model_dump(mode="json")
    if missing == "race":
        document["races"] = [r for r in document["races"] if r["race_id"] != race.id]
    else:
        next(r for r in document["races"] if r["race_id"] == race.id)["outcomes"].pop()
    results = read_document(tmp_path, document)
    with pytest.raises(ValueError, match=r"every inventory race|every named ballot choice"):
        validate_results_inventory(results, read_inventory(INVENTORY))
    result = context.race_results_view(race, results, election_type="general", capture_urls=None)
    if missing == "race":
        assert result is None
    else:
        assert result is not None
        assert all(row.meter_tone is None for row in result.outcomes)


def _view_with_alignment(
    tmp_path: Path, view: PublicationViewModel, tone: str
) -> PublicationViewModel:
    race = next(r for s in view.sections for r in s.races if r.id == "king-county-assessor")
    leading_index = next(
        i
        for i, candidate in enumerate(race.candidates)
        if (candidate.id in race.recommendation_candidate_ids) == (tone == "aligned")
    )
    votes = (60, 40) if leading_index == 0 else (40, 60)
    return _view_with_count_leader(tmp_path, view, votes, None)


@pytest.mark.parametrize("page", ["guide", "race"])
@pytest.mark.parametrize("tone", ["aligned", "different"])
def test_unofficial_leader_color_reaches_shared_pages_without_outcome_chrome(
    tmp_path: Path,
    general_view: PublicationViewModel,
    page: str,
    tone: str,
) -> None:
    view = _view_with_alignment(tmp_path, general_view, tone)
    config = read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    html = (
        render_html_document(view, config)
        if page == "guide"
        else render_race_document(
            view, "king-county-assessor", public_site_url=config.public_site_url
        )
    )
    markup = _race_card_html(html, "king-county-assessor") if page == "guide" else html
    tally, provenance = markup.split('<div class="race-results">', 1)[1].split(
        '<p class="race-results-provenance">', 1
    )
    block = tally + provenance.split("</p>", 1)[0]
    assert block.count(f'class="race-results-bar race-results-bar-{tone}"') == 1
    assert block.count('class="race-results-bar"') == 1
    assert 'style="width:60.0%"' in block and 'style="width:40.0%"' in block
    assert "Unofficial</span>" in block
    assert 'class="race-detail-result-chip"' not in block
    assert 'class="race-results-row race-results-row-trailing"' not in block
    assert "Count updated Nov 3, 8:00:00 p.m. PST" in block


@pytest.mark.parametrize("page", ["guide", "race"])
@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize(
    "tone,fill,remainder",
    [
        ("aligned", "rgb(8, 127, 115)", "rgb(206, 229, 227)"),
        ("different", "rgb(180, 101, 76)", "rgb(240, 224, 219)"),
    ],
)
def test_unofficial_leader_colors_in_the_browser(
    tmp_path: Path,
    general_view: PublicationViewModel,
    page: str,
    width: int,
    tone: str,
    fill: str,
    remainder: str,
) -> None:
    view = _view_with_alignment(tmp_path, general_view, tone)
    config = read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    html = (
        render_html_document(view, config)
        if page == "guide"
        else render_race_document(
            view, "king-county-assessor", public_site_url=config.public_site_url
        )
    )
    path = tmp_path / "unofficial-leader.html"
    path.write_text(without_live_address_requests(html))
    host = (
        "document.querySelector('[data-publication-race-id=\"king-county-assessor\"]')"
        if page == "guide"
        else "document"
    )

    def retain(cdp: _CdpSocket, session: str) -> None:
        if directory := os.environ.get("SEG_PRELIMINARY_METER_EVIDENCE_DIR"):
            target = Path(directory)
            target.mkdir(parents=True, exist_ok=True)
            prefix = f"{page}-{tone}-{width}"
            geometry = cdp.command(
                "Runtime.evaluate",
                {
                    "expression": """(async () => {
                      await document.fonts.ready;
                      const block = HOST.querySelector('.race-results');
                      block.scrollIntoView({block:'center'});
                      await new Promise(requestAnimationFrame);
                      await new Promise(requestAnimationFrame);
                      const rect = block.getBoundingClientRect();
                      return {top:rect.top,bottom:rect.bottom,height:innerHeight};
                    })()""".replace("HOST", host),
                    "awaitPromise": True,
                    "returnByValue": True,
                },
                session_id=session,
            )
            (target / f"{prefix}-geometry.json").write_text(json.dumps(geometry))
            version = cdp.command("Browser.getVersion", session_id=session)
            (target / f"{prefix}-version.json").write_text(json.dumps(version))
            shot = cdp.command("Page.captureScreenshot", {"format": "png"}, session_id=session)
            (target / f"{prefix}.png").write_bytes(base64.b64decode(shot["data"]))

    result = _evaluate_in_chrome(
        path,
        """(() => {
          const block = HOST.querySelector('.race-results');
          return JSON.stringify({
            status: block.querySelector('.race-results-status').textContent.trim(),
            rows: [...block.querySelectorAll('.race-results-row')].map(row => {
              const bar = row.querySelector('.race-results-bar');
              return { fill: getComputedStyle(bar.firstElementChild).backgroundColor,
                remainder: getComputedStyle(bar).backgroundColor,
                chip: !!row.querySelector('.race-detail-result-chip'),
                trailing: row.classList.contains('race-results-row-trailing') };
            }), overflow: document.documentElement.scrollWidth > innerWidth
          });
        })()""".replace("HOST", host),
        viewport=(width, 900),
        interact=retain,
    )
    if directory := os.environ.get("SEG_PRELIMINARY_METER_EVIDENCE_DIR"):
        (Path(directory) / f"{page}-{tone}-{width}-result.json").write_text(json.dumps(result))
    assert result["status"] == "Unofficial"
    assert result["rows"][0]["fill"] == fill
    assert result["rows"][0]["remainder"] == remainder
    assert len(result["rows"]) == 2
    assert result["rows"][1]["fill"] == "rgb(16, 42, 67)"
    assert result["rows"][1]["remainder"] == "rgb(237, 242, 244)"
    assert not any(row["chip"] or row["trailing"] for row in result["rows"])
    assert not result["overflow"]


@pytest.mark.parametrize("page", ["guide", "race"])
def test_preliminary_recency_uses_the_typed_page_payload(
    tmp_path: Path, general_view: PublicationViewModel, page: str
) -> None:
    view = general_view.model_copy(
        update={"results": read_document(tmp_path, preliminary_document())}
    )
    configuration = read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    html = (
        render_html_document(view, configuration)
        if page == "guide"
        else render_race_document(
            view, "king-county-assessor", public_site_url=configuration.public_site_url
        )
    )
    rows = _client_payload(html)["preliminary_recency"]
    row = next(item for item in rows if item["race_id"] == "king-county-assessor")
    assert row == {
        "race_id": "king-county-assessor",
        "checked_at": "2026-11-04T05:00:00Z",
        "checked_at_label": "Nov 3, 9:00:00 p.m. PST",
        "refresh_unavailable": False,
        "stale_after_seconds": 86400,
    }
    expected_ids = (
        {race.id for section in view.public_view().sections for race in section.races}
        if page == "guide"
        else {"king-county-assessor"}
    )
    assert {item["race_id"] for item in rows} == expected_ids
    assert len(rows) == len(expected_ids)
    assert 'data-preliminary-recency="king-county-assessor"' in html
    for attribute in (
        "data-preliminary-check-at",
        "data-preliminary-checked-label",
        "data-preliminary-refresh-failed",
        "data-preliminary-stale-after",
    ):
        assert attribute not in html


def test_failed_refresh_keeps_count_asof_and_later_success_clears_only_the_warning(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    document = preliminary_document()
    document["failed_refreshes"] = [
        {
            "authority_id": "wa-secretary-of-state",
            "checked_at": "2026-11-04T05:30:00Z",
            "evidence": "data/manifests/evidence/synthetic-unavailable.json",
        }
    ]
    metadata = general_view.metadata.model_copy(
        update={
            "generated_at": datetime(2026, 11, 4, 7, tzinfo=UTC),
        }
    )

    def rendered_card() -> str:
        view = general_view.model_copy(
            update={"results": read_document(tmp_path, document), "metadata": metadata}
        )
        assert view.metadata.data_as_of == general_view.metadata.data_as_of
        return _race_card_html(
            render_html_document(
                view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
            ),
            "king-county-assessor",
        )

    card = rendered_card()
    assert "Refresh unavailable · last checked Nov 3, 9:00:00 p.m. PST" in card
    assert "Count updated Nov 3, 8:00:00 p.m. PST" in card
    document["captures"][0]["captured_at"] = "2026-11-04T06:00:00Z"
    card = rendered_card()
    assert "Refresh unavailable" not in card
    assert "Last checked Nov 3, 10:00:00 p.m. PST" in card
    assert "Count updated Nov 3, 8:00:00 p.m. PST" in card


def test_preliminary_percentage_rounding_matches_the_existing_certified_convention(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    from election_guide.results.ingest import rank_tallies_into_outcomes

    inventory_race = next(
        item for item in read_inventory(INVENTORY).races if item.id == "king-county-assessor"
    )
    certified = rank_tallies_into_outcomes(
        [(inventory_race.choices[0].id, 129899), (inventory_race.choices[1].id, 70101)],
        {choice.id: choice.ballot_order for choice in inventory_race.choices},
        200000,
        top_count=1,
    )
    reference = next(item for item in certified if item.choice_id == inventory_race.choices[0].id)
    expected = f"{reference.share * 100:.1f}%"
    assert expected == "65.0%"
    document = preliminary_document()
    race = next(item for item in document["races"] if item["race_id"] == inventory_race.id)
    race["outcomes"][0]["votes"], race["outcomes"][1]["votes"] = 129899, 70101
    race["write_in_votes"], race["ballots_counted"] = 0, 200000
    view = general_view.model_copy(update={"results": read_document(tmp_path, document)})
    card = _race_card_html(
        render_html_document(
            view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        ),
        inventory_race.id,
    )
    assert expected in card


def test_preliminary_results_never_enable_the_certified_comparison_column(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    view = general_view.model_copy(
        update={"results": read_document(tmp_path, preliminary_document())}
    )
    html = render_comparison_document(view, public_site_url="https://seattleelections.guide")
    payload = _client_payload(html)
    assert payload["results_available"] is False
    assert payload["race_results"] == {}


def test_preliminary_file_does_not_satisfy_future_certified_ingestion(tmp_path: Path) -> None:
    directory = tmp_path / "results"
    directory.mkdir()
    (directory / "wa-2026-general.yaml").write_text(yaml.safe_dump(preliminary_document()))
    artifacts = read_repository_artifacts(
        manifest_dir=tmp_path / "manifests",
        refresh_dir=tmp_path / "refreshes",
        results_dir=directory,
    )
    assert "wa-2026-general" not in artifacts.ingested_election_ids


@pytest.mark.parametrize("page", ["guide", "race"])
@pytest.mark.parametrize("width", [320, 390, 1280])
@pytest.mark.parametrize("clock_basis", ["count", "export"])
def test_preliminary_general_result_is_readable_in_the_actual_application(
    tmp_path: Path, general_view: PublicationViewModel, page: str, width: int, clock_basis: str
) -> None:
    document = preliminary_document()
    if clock_basis == "export":
        target = next(r for r in document["races"] if r["race_id"] == "king-county-assessor")
        target["reported_at"] = None
        target["export_generated_at"] = "2026-11-04T04:15:00Z"
    view = general_view.model_copy(update={"results": read_document(tmp_path, document)})
    html = (
        render_html_document(
            view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
        )
        if page == "guide"
        else render_race_document(
            view, "king-county-assessor", public_site_url="https://seattleelections.guide"
        )
    )
    html = without_live_address_requests(html)
    path = tmp_path / f"preliminary-{page}-{width}.html"
    path.write_text(html)
    evidence_root = os.environ.get("SEG_RESULTS_EVIDENCE_DIR")
    case = Path(evidence_root) / f"{clock_basis}-{page}-{width}" if evidence_root else None
    if case is not None:
        case.mkdir(parents=True, exist_ok=True)
        (case / "application.html").write_text(html)

    def capture(cdp: _CdpSocket, session_id: str) -> None:
        if case is None:
            return
        version = cdp.command("Browser.getVersion")
        (case / "browser-version.json").write_text(json.dumps(version, indent=2))
        cdp.command(
            "Runtime.evaluate",
            {"expression": "document.fonts.ready", "awaitPromise": True},
            session_id=session_id,
        )
        image = cdp.command("Page.captureScreenshot", {"format": "png"}, session_id=session_id)
        (case / "top.png").write_bytes(base64.b64decode(str(image["data"])))
        cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    'document.querySelector(\'[data-publication-race-id="king-county-assessor"]'
                    " .race-results,.race-detail-certified-result .race-results')"
                    "?.scrollIntoView({block:'center'})"
                )
            },
            session_id=session_id,
        )
        image = cdp.command("Page.captureScreenshot", {"format": "png"}, session_id=session_id)
        (case / "tally.png").write_bytes(base64.b64decode(str(image["data"])))

    observed = _evaluate_in_chrome(
        path,
        """(async () => {
      await document.fonts.ready;
      const selector='[data-publication-race-id="king-county-assessor"]';
      const block=document.querySelector(selector+' .race-results')
        ??document.querySelector('.race-detail-certified-result .race-results');
      if(!block)return JSON.stringify({error:'missing result block'});
      const box=block.getBoundingClientRect();
      const rows=[...block.querySelectorAll('.race-results-row')].map(row=>{
        const name=row.querySelector('.race-results-name');
        const share=row.querySelector('.race-results-share');
        const bar=row.querySelector('.race-results-bar'),fill=bar.querySelector('i');
        const a=name.getBoundingClientRect(),b=share.getBoundingClientRect();
        return {name:name.textContent.trim(),percentage:share.textContent.trim(),
          color:getComputedStyle(name).color,weight:getComputedStyle(name).fontWeight,
          fillColor:getComputedStyle(fill).backgroundColor,
          fillRatio:fill.getBoundingClientRect().width/bar.getBoundingClientRect().width,
          readable:a.width>0&&a.right<=b.left+1&&a.height>=parseFloat(getComputedStyle(name).fontSize),
          inside:a.left>=box.left-1&&b.right<=box.right+1};
      });
      const badge=block.querySelector('.race-results-status'),r=badge.getBoundingClientRect();
      const banner=document.querySelector('.election-day'),t=document.createRange();
      t.selectNodeContents(banner);
      const text=t.getBoundingClientRect(),bb=banner.getBoundingClientRect();
      return JSON.stringify({viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,
        rows,provenance:block.querySelector('.race-results-provenance').textContent,
        status:badge.textContent,amber:getComputedStyle(badge).color,
        badgeInside:r.left>=box.left-1&&r.right<=box.right+1,
        bannerCentered:Math.abs((text.left+text.right)-(bb.left+bb.right))<4,
        outcomes:block.querySelectorAll('.race-detail-result-chip').length,
        trailing:block.querySelectorAll('.race-results-row-trailing').length});
    })()""",
        mobile_width=width if width < 720 else None,
        viewport=(width, 900) if width >= 720 else None,
        interact=capture,
    )
    if case is not None:
        (case / "observed.json").write_text(
            json.dumps(
                {
                    "input_sha256": hashlib.sha256(html.encode()).hexdigest(),
                    "method": (
                        "actual headless Chrome normal rendered application; "
                        "synthetic offline counts; GIS blocked"
                    ),
                    "observed": observed,
                },
                indent=2,
            )
        )
    assert "error" not in observed, observed
    assert observed["documentWidth"] <= observed["viewport"]
    assert observed["badgeInside"] is True
    assert observed["bannerCentered"] is True
    assert observed["status"] == "Unofficial"
    assert "Count timestamp not provided" not in observed["provenance"]
    if clock_basis == "export":
        assert "Export generated Nov 3, 8:15:00 p.m. PST" in observed["provenance"]
    else:
        assert "Count updated Nov 3, 8:00:00 p.m. PST" in observed["provenance"]
    assert observed["amber"] == "rgb(138, 75, 0)"
    assert observed["outcomes"] == observed["trailing"] == 0
    assert "220 ballots" in observed["provenance"]
    rows = observed["rows"]
    assert len(rows) == 2
    assert all(row["percentage"] == "50.0%" and row["readable"] and row["inside"] for row in rows)
    assert len({(row["color"], row["weight"], row["fillColor"]) for row in rows}) == 1
    assert all(row["fillRatio"] == pytest.approx(0.5, abs=0.01) for row in rows)


def captured_document(tmp_path: Path) -> dict[str, Any]:
    document = preliminary_document()
    artifact = tmp_path / "synthetic-official.json"
    artifact.write_text('{"fixture":"synthetic offline evidence"}')
    manifest = record_capture(
        CaptureRequest(
            source_id="wa-secretary-of-state",
            requested_url="https://example.org/synthetic-results",
            canonical_url="https://example.org/synthetic-results",
            retrieved_at=datetime(2026, 11, 4, 5, tzinfo=UTC),
            media_type="application/json",
            title="Synthetic test only",
            http_status=200,
            capture_method="manual_upload",
            redistribution="permitted",
            redistribution_note="Synthetic fixture, no official count claim.",
        ),
        artifact,
        tmp_path / "data/evidence/official",
        tmp_path / "data/manifests/evidence",
        repository_storage_root=tmp_path / "data/evidence/official",
    )
    reference = manifest.relative_to(tmp_path).as_posix()
    document["captures"][0]["evidence"] = reference
    for race in document["races"]:
        race["capture_evidence"] = reference
        race["coverage_evidence"] = reference
    registry = tmp_path / "config/authorities/default.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_bytes((ROOT / "config/authorities/default.yaml").read_bytes())
    return document


def test_preliminary_evidence_links_the_immutable_source_bytes_not_a_changing_feed(
    tmp_path: Path,
) -> None:
    from election_guide.results.loader import resolve_results_capture_urls
    from tests.test_results import _valid_results  # pyright: ignore[reportPrivateUsage]

    document = captured_document(tmp_path)
    manifest = json.loads((tmp_path / document["captures"][0]["evidence"]).read_text())
    urls = resolve_results_capture_urls(
        read_document(tmp_path, document),
        repository_root=tmp_path,
        source_commit="a" * 40,
        project_url="https://github.com/example/fixture",
    )
    expected = (
        "https://github.com/example/fixture/blob/"
        + "a" * 40
        + "/data/evidence/official/"
        + manifest["storage_reference"]
    )
    assert urls["king-county-assessor"] == expected
    assert "example.org/synthetic-results" not in urls.values()
    legacy = resolve_results_capture_urls(
        _valid_results(tmp_path / "legacy"),
        repository_root=tmp_path / "legacy",
        source_commit="a" * 40,
        project_url="https://github.com/example/fixture",
    )
    assert legacy == {"king-county-assessor": "https://example.org/results/certified"}


def test_preliminary_ingest_binds_source_ids_names_scope_and_original_vote_meaning(
    tmp_path: Path,
) -> None:
    from election_guide.results import build_preliminary_results
    from election_guide.results.ingest import resolve_ballot_choice

    inventory = read_inventory(INVENTORY)
    race = next(item for item in inventory.races if item.id == "king-county-assessor")
    # One-race inventory is a bounded producer fixture, NOT full General admission.
    fixture_inventory = inventory.model_copy(update={"races": [race], "coverage_checks": []})
    body = (ROOT / "tests/fixtures/results/wa-2026-general-historical-county.json").read_bytes()
    artifact = tmp_path / "historical-count-excerpt.json"
    artifact.write_bytes(body)
    reference = (
        record_capture(
            CaptureRequest(
                source_id="king-county-elections",
                requested_url="https://example.org/historical-fixture",
                canonical_url="https://example.org/historical-fixture",
                retrieved_at=datetime(2026, 11, 4, 5, tzinfo=UTC),
                media_type="application/json",
                title="Historical fixture, not current",
                capture_method="manual_upload",
                redistribution="permitted",
                redistribution_note="Historical excerpt for offline producer test.",
            ),
            artifact,
            tmp_path / "data/evidence/official",
            tmp_path / "data/manifests/evidence",
            repository_storage_root=tmp_path / "data/evidence/official",
        )
        .relative_to(tmp_path)
        .as_posix()
    )
    registry = tmp_path / "config/authorities/default.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_bytes((ROOT / "config/authorities/default.yaml").read_bytes())
    source = next(
        item for item in json.loads(body)["ballotItems"] if item["name"][0]["text"] == "Assessor"
    )
    binding = {
        "race_id": race.id,
        "jurisdiction_id": race.jurisdiction_id,
        "source_jurisdiction": "king-county-wa",
        "source_contest_id": source["id"],
        "coverage": "whole_jurisdiction",
        "source_contest_name": "Assessor",
        "capture_evidence": reference,
        "coverage_evidence": reference,
        "choices": [
            {
                "source_choice_id": option["id"],
                "source_name": option["name"][0]["text"],
                "choice_id": resolve_ballot_choice(option["name"][0]["text"], race).id,
            }
            for option in source["summaryResults"]["ballotOptions"]
            if not option["isWriteIn"]
        ],
    }
    plan = {
        "election_id": inventory.election.id,
        "sources": [
            {"authority_id": "king-county-elections", "format": "county", "evidence": reference}
        ],
        "races": [binding],
    }
    result = build_preliminary_results(plan, fixture_inventory, repository_root=tmp_path)
    assert result.status == "preliminary"
    assert result.races[0].votes_counted == 466113
    assert result.races[0].ballots_counted is None
    assert result.races[0].write_in_votes == 2416
    assert sorted(item.votes for item in result.races[0].outcomes) == [126531, 337166]
    assert result.races[0].reported_at is not None
    assert result.races[0].reported_at.isoformat() == "2026-11-04T04:12:12.419061+00:00"
    with pytest.raises(ValueError, match="every inventory race"):
        build_preliminary_results(plan, inventory, repository_root=tmp_path)
    mapping_path = tmp_path / "admission-map.yaml"
    mapping_path.write_text(yaml.safe_dump(plan))
    inventory_path = tmp_path / "one-race-fixture-inventory.json"
    inventory_path.write_text(fixture_inventory.model_dump_json())
    output_dir = tmp_path / "produced-results"
    argv = [
        "results",
        "ingest-preliminary",
        str(mapping_path),
        "--inventory-path",
        str(inventory_path),
        "--repository-root",
        str(tmp_path),
        "--output-dir",
        str(output_dir),
    ]
    command = CliRunner().invoke(app, argv)
    assert command.exit_code == 0, command.output
    output = output_dir / "wa-2026-general.yaml"
    assert read_results(output) == result
    # A certified file cannot be downgraded, even through a wrong election filename.
    certified_bytes = (ROOT / "data/results/wa-2026-primary.yaml").read_bytes()
    output.write_bytes(certified_bytes)
    command = CliRunner().invoke(app, argv)
    assert command.exit_code != 0
    assert "certified" in command.output
    assert output.read_bytes() == certified_bytes
    binding["source_jurisdiction"] = "washington"
    with pytest.raises(ValueError, match="jurisdiction"):
        build_preliminary_results(plan, fixture_inventory, repository_root=tmp_path)


def test_cli_selects_general_inventory_and_validates_real_capture_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = captured_document(tmp_path)
    inventory = tmp_path / "data/normalized/wa-2026-general-inventory.json"
    inventory.parent.mkdir(parents=True)
    inventory.write_bytes(INVENTORY.read_bytes())
    results_path = tmp_path / "results.yaml"
    results_path.write_text(yaml.safe_dump(document))
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["results", "validate", str(results_path)])
    assert result.exit_code == 0, result.output
    assert "wa-2026-general, preliminary, 52 races" in result.output
    document["captures"][0]["captured_at"] = "2026-11-04T05:01:00Z"
    results_path.write_text(yaml.safe_dump(document))
    result = CliRunner().invoke(app, ["results", "validate", str(results_path)])
    assert result.exit_code != 0
    assert "actual capture clock" in result.output


def test_server_preliminary_staleness_preserves_the_original_count_time(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    view = general_view.model_copy(
        update={
            "results": read_document(tmp_path, preliminary_document()),
            "metadata": general_view.metadata.model_copy(
                update={
                    "generated_at": datetime(2026, 11, 5, 5, tzinfo=UTC),
                }
            ),
        }
    )
    html = render_html_document(
        view, read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    )
    card = _race_card_html(html, "king-county-assessor")
    assert "Stale · last checked Nov 3, 9:00:00 p.m. PST" in card
    assert "Count updated Nov 3, 8:00:00 p.m. PST" in card
    assert "counting continues" not in html


@pytest.mark.parametrize("page", ["guide", "race"])
def test_historical_preliminary_presentation_ages_recency_without_changing_original_clocks(
    tmp_path: Path, general_view: PublicationViewModel, page: str
) -> None:
    document = preliminary_document()
    for tally in document["races"]:
        tally["export_generated_at"] = "2026-11-04T04:30:00Z"
    view = general_view.model_copy(
        update={
            "results": read_document(tmp_path, document),
            "metadata": general_view.metadata.model_copy(
                update={
                    "git_commit": "c" * 40,
                    "generated_at": datetime(2026, 11, 4, 5, tzinfo=UTC),
                    "results_capture_urls": {
                        "king-county-assessor": "https://example.test/original-count"
                    },
                }
            ),
        }
    )
    original = view.model_dump_json()
    presentation = PagePresentation(
        source_git_commit="a" * 40,
        generated_at=datetime(2026, 11, 6, 5, tzinfo=UTC),
        archive_git_commit="c" * 40,
        archive_release_version="test.1",
        release_manifest_sha256="d" * 64,
        publication_view_model_sha256=hashlib.sha256(original.encode()).hexdigest(),
    )
    configuration = read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    html = (
        render_html_document(view, configuration, presentation=presentation)
        if page == "guide"
        else render_race_document(
            view,
            "king-county-assessor",
            public_site_url=configuration.public_site_url,
            presentation=presentation,
        )
    )
    assert "Stale · last checked Nov 3, 9:00:00 p.m. PST" in html
    assert "Count updated Nov 3, 8:00:00 p.m. PST" in html
    assert "Export generated Nov 3, 8:30:00 p.m. PST" in html
    assert 'href="https://example.test/original-count"' in html
    assert "Nov 5, 9:00:00 p.m. PST" not in html
    assert "Advances" not in html and "Elected" not in html
    assert view.model_dump_json() == original


def test_preliminary_admission_requires_original_bytes_and_registered_authority(
    tmp_path: Path,
) -> None:
    from election_guide.results.validation import validate_results_evidence

    document = captured_document(tmp_path)
    results = read_document(tmp_path, document)
    manifest = json.loads((tmp_path / document["captures"][0]["evidence"]).read_text())
    original = tmp_path / "data/evidence/official" / manifest["storage_reference"]
    original.write_text("corrupted synthetic original")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_results_evidence(results, repository_root=tmp_path)


def test_failed_refresh_is_bound_to_the_actual_unavailable_record(tmp_path: Path) -> None:
    from election_guide.results.validation import validate_results_evidence

    document = captured_document(tmp_path)
    failure = record_unavailable(
        UnavailableRequest(
            source_id="wa-secretary-of-state",
            requested_url="https://example.org/synthetic-results",
            retrieved_at=datetime(2026, 11, 4, 6, tzinfo=UTC),
            http_status=403,
            redistribution="permitted",
            redistribution_note="Synthetic unavailable fixture, no live request.",
            unavailable_reason="Synthetic HTTP403; cause unknown.",
        ),
        tmp_path / "data/manifests/evidence",
    )
    document["failed_refreshes"] = [
        {
            "authority_id": "wa-secretary-of-state",
            "checked_at": "2026-11-04T06:00:00Z",
            "evidence": failure.relative_to(tmp_path).as_posix(),
        }
    ]
    original = deepcopy(document)
    original.pop("failed_refreshes")
    result_path = tmp_path / "results.yaml"
    result_path.write_text(yaml.safe_dump(original))
    command = CliRunner().invoke(
        app,
        [
            "results",
            "record-refresh-failure",
            str(result_path),
            str(failure),
            "--repository-root",
            str(tmp_path),
        ],
    )
    assert command.exit_code == 0, command.output
    recorded = read_results(result_path).model_dump(mode="json")
    assert recorded["failed_refreshes"][0]["checked_at"] == "2026-11-04T06:00:00Z"
    assert recorded["races"] == read_document(tmp_path, original).model_dump(mode="json")["races"]
    assert (
        recorded["captures"]
        == read_document(tmp_path, original).model_dump(mode="json")["captures"]
    )
    validate_results_evidence(read_document(tmp_path, document), repository_root=tmp_path)
    document["failed_refreshes"][0]["checked_at"] = "2026-11-04T06:01:00Z"
    with pytest.raises(ValueError, match="actual unavailable observation"):
        validate_results_evidence(read_document(tmp_path, document), repository_root=tmp_path)


def test_export_clock_keeps_missing_count_clock_and_approved_wording(
    tmp_path: Path, general_view: PublicationViewModel
) -> None:
    document = preliminary_document()
    row = next(r for r in document["races"] if r["race_id"] == "king-county-assessor")
    row["reported_at"] = None
    row["export_generated_at"] = "2026-11-04T04:15:00Z"
    row["vote_total_basis"] = "complete_choice_sum"
    row["ballots_counted"] = None
    row["votes_counted"] = sum(o["votes"] for o in row["outcomes"]) + row["write_in_votes"]
    results = read_document(tmp_path, document)
    assert next(r for r in results.races if r.race_id == "king-county-assessor").reported_at is None
    html = render_html_document(
        general_view.model_copy(update={"results": results}),
        read_rendering_configuration(ROOT / "config/rendering/guide.yaml"),
    )
    card = _race_card_html(html, "king-county-assessor")
    assert (
        '<span class="race-results-status race-results-status-preliminary">Unofficial</span>'
        in card
    )
    assert "<br>Export generated Nov 3, 8:15:00 p.m. PST · " in card
    assert "Count timestamp not provided" not in card
    assert "Certified ·" not in html


@pytest.mark.parametrize("page", ["guide", "race"])
@pytest.mark.parametrize("clocks", ["count", "export", "both"])
def test_available_result_clocks_share_the_bottom_line_without_crowding_the_badge(
    tmp_path: Path, general_view: PublicationViewModel, page: str, clocks: str
) -> None:
    document = preliminary_document()
    row = next(r for r in document["races"] if r["race_id"] == "king-county-assessor")
    if clocks == "export":
        row["reported_at"] = None
    if clocks in {"export", "both"}:
        row["export_generated_at"] = "2026-11-04T04:15:00Z"
    view = general_view.model_copy(
        update={
            "results": read_document(tmp_path, document),
            "metadata": general_view.metadata.model_copy(
                update={"generated_at": datetime(2026, 11, 4, 5, tzinfo=UTC)}
            ),
        }
    )
    configuration = read_rendering_configuration(ROOT / "config/rendering/guide.yaml")
    html = (
        render_html_document(view, configuration)
        if page == "guide"
        else render_race_document(
            view, "king-county-assessor", public_site_url=configuration.public_site_url
        )
    )
    block = _race_card_html(html, "king-county-assessor") if page == "guide" else html
    badge = block.split('class="race-results-status race-results-status-preliminary">', 1)[1]
    assert badge.split("</span>", 1)[0] == "Unofficial"
    provenance = block.split('class="race-results-provenance">', 1)[1].split("</p>", 1)[0]
    second_line = provenance.split("<br>", 1)[1]
    assert ("Count updated Nov 3, 8:00:00 p.m. PST" in second_line) == (clocks != "export")
    assert ("Export generated Nov 3, 8:15:00 p.m. PST" in second_line) == (clocks != "count")
    assert "Last checked Nov 3, 9:00:00 p.m. PST" in second_line
    assert "timestamp not provided" not in provenance


def test_generation_clock_cannot_follow_capture_or_replace_no_clock(tmp_path: Path) -> None:
    document = preliminary_document()
    document["races"][0]["reported_at"] = None
    with pytest.raises(ValueError, match="timestamp"):
        read_document(tmp_path, document)
    document["races"][0]["export_generated_at"] = "2026-11-04T06:00:00Z"
    with pytest.raises(ValueError, match="timestamp"):
        read_document(tmp_path, document)
