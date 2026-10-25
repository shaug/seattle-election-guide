"""Ballot applicability is independent of endorsements and presentation order."""

import json
from pathlib import Path

import pytest

from election_guide.inventory.models import Inventory
from election_guide.publication.ballot import build_ballot_membership


def test_rules_cover_the_inventory_without_assigning_order() -> None:
    inventory = Inventory.model_validate(
        json.loads(Path("data/normalized/wa-2026-general-inventory.json").read_text())
    )
    contract = build_ballot_membership(inventory)
    assert set(contract.races) == {race.id for race in inventory.races if race.publication_eligible}
    assert len({group.id for group in contract.groups}) == len(contract.groups)
    judicial = [group for group in contract.groups if group.mode == "membership"]
    assert len(judicial) == 2
    assert all(len(group.options) == 1 for group in judicial)
    shared = [rule for rule in contract.races.values() if rule.shared]
    assert shared
    assert all(rule.group_id is None for rule in shared)
    reversed_inventory = inventory.model_copy(update={"races": list(reversed(inventory.races))})
    assert build_ballot_membership(reversed_inventory).model_dump() == contract.model_dump()


def test_contract_rejects_missing_and_cross_group_references() -> None:
    import pytest
    from pydantic import ValidationError

    from election_guide.publication.ballot import BallotMembershipContract

    for rule in [
        {"jurisdiction_id": "ld1", "shared": False, "outside_target": False, "group_id": "missing"},
        {"jurisdiction_id": "ld2", "shared": False, "outside_target": False, "group_id": "ld"},
        {"jurisdiction_id": "ld1", "shared": True, "outside_target": False, "group_id": "ld"},
    ]:
        with pytest.raises(ValidationError):
            BallotMembershipContract.model_validate(
                {
                    "confirmation_label": "Confirm district",
                    "election_id": "test",
                    "geography_hash": None,
                    "inventory_notice": None,
                    "groups": [
                        {
                            "id": "ld",
                            "label": "District",
                            "mode": "district",
                            "options": [{"id": "ld1", "label": "District 1"}],
                        }
                    ],
                    "races": {"race": rule},
                }
            )


def test_reviewed_district_universe_does_not_depend_on_contests() -> None:
    inventory = Inventory.model_validate(
        json.loads(Path("data/normalized/wa-2026-general-inventory.json").read_text())
    )
    contract = build_ballot_membership(inventory)
    groups = {group.id: {option.id for option in group.options} for group in contract.groups}
    assert groups["city_council_district"] == {
        f"seattle-city-council-district-{number}" for number in range(1, 8)
    }
    assert groups["county_council_district"] == {
        f"county-council-district-{number}" for number in (1, 2, 4, 8)
    }
    assert "legislative-district-11" not in groups["legislative_district"]
    assert contract.races["ld-11-state-representative-1"].outside_target is True
    assert contract.races["ld-11-state-representative-1"].group_id is None
    assert contract.inventory_notice
    # Publication and scoring retain the original inventory; matching is a projection.
    assert any(race.jurisdiction_id == "legislative-district-11" for race in inventory.races)


def test_public_json_evidence_uses_the_capture_contract() -> None:
    from datetime import UTC, datetime

    import pytest
    from pydantic import ValidationError

    from election_guide.evidence.models import CaptureRequest

    request = {
        "source_id": "official-geography",
        "requested_url": "https://example.gov/districts",
        "canonical_url": "https://example.gov/districts",
        "retrieved_at": datetime(2026, 10, 24, tzinfo=UTC),
        "http_status": 200,
        "media_type": "application/json",
        "title": "Official district assignments",
        "capture_method": "json",
        "redistribution": "restricted",
        "redistribution_note": "Raw response local-only; normalized public facts retained.",
    }
    assert CaptureRequest.model_validate(request).capture_method == "json"
    with pytest.raises(ValidationError, match="JSON"):
        CaptureRequest.model_validate({**request, "media_type": "text/html"})


def test_geography_rejects_changed_evidence_and_duplicate_crosswalk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    import pytest

    from election_guide.inventory import geography

    config = json.loads(geography.CONFIGURATION.read_text())
    original_root = geography.ROOT
    for field in ("assignment_path", "city_crosswalk_path", "review_record"):
        destination = tmp_path / config[field]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((original_root / config[field]).read_bytes())
    configuration = tmp_path / "geography.json"
    configuration.write_text(json.dumps(config))
    monkeypatch.setattr(geography, "ROOT", tmp_path)
    monkeypatch.setattr(geography, "CONFIGURATION", configuration)
    assert geography.reviewed_geography("wa-2026-general") is not None
    review = tmp_path / config["review_record"]
    review.write_text(review.read_text() + " ")
    with pytest.raises(ValueError, match="hash changed"):
        geography.reviewed_geography("wa-2026-general")
    review.write_bytes((original_root / config["review_record"]).read_bytes())
    crosswalk = tmp_path / config["city_crosswalk_path"]
    crosswalk.write_text(crosswalk.read_text() + crosswalk.read_text().splitlines()[1] + "\n")
    config["city_crosswalk_sha256"] = hashlib.sha256(crosswalk.read_bytes()).hexdigest()
    configuration.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="unique precincts"):
        geography.reviewed_geography("wa-2026-general")


def test_public_visibility_projects_ballot_rules_but_retains_district_catalog() -> None:
    from election_guide.normalization.models import CanonicalDataset
    from election_guide.publication import build_publication_bundle
    from election_guide.publication.models import PublicationViewModel
    from election_guide.release.compiler import read_release_ledger
    from election_guide.scoring import read_scoring_configuration, score_dataset

    dataset = CanonicalDataset.model_validate_json(
        Path("data/normalized/wa-2026-general-canonical-dataset.json").read_bytes()
    )
    report = score_dataset(
        dataset,
        read_scoring_configuration(Path("config/scoring/default.yaml")),
        computed_at=read_release_ledger(
            Path("data/releases/wa-2026-general/source-decisions.yaml")
        ).data_as_of,
        allow_unresolved=True,
    )
    full = build_publication_bundle(
        dataset,
        report,
        git_commit="ballot-public-projection",
        snapshot_root=Path("data/releases/wa-2026-general/snapshots"),
    ).view_model
    before = full.model_dump_json()
    public = full.public_view()
    full_ids = [race.id for section in full.sections for race in section.races]
    public_ids = [race.id for section in public.sections for race in section.races]
    assert len(public_ids) < len(full_ids), "the fixture must exercise hidden contests"
    assert public_ids == [race_id for race_id in full_ids if race_id in set(public_ids)]
    assert full.ballot_membership is not None
    assert public.ballot_membership is not None
    assert set(public.ballot_membership.races) == set(public_ids)
    assert public.ballot_membership.groups == full.ballot_membership.groups
    assert public.ballot_membership.geography_hash == full.ballot_membership.geography_hash
    assert full.model_dump_json() == before, "visibility must preserve canonical audit inputs"
    assert public.public_view() == public
    assert PublicationViewModel.model_validate_json(public.model_dump_json()) == public


def test_primary_ballot_projection_obeys_the_shared_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from election_guide.publication.models import PublicationRace, PublicationViewModel
    from tests.test_comparisons import _bundle  # pyright: ignore[reportPrivateUsage]

    full: PublicationViewModel = _bundle().view_model
    assert full.metadata.election_type == "primary"
    original = full.model_dump_json()
    hidden = next(
        race for section in full.sections for race in section.races if not race.is_contested
    )
    original_selector = PublicationViewModel.is_race_visible

    def selector(view: PublicationViewModel, race: PublicationRace) -> bool:
        return race.id != hidden.id and original_selector(view, race)

    # The visibility owner tests confidence arithmetic. This consumer test
    # requires a primary publication to honor that API before geographic matching.
    monkeypatch.setattr(PublicationViewModel, "is_race_visible", selector)
    public = full.public_view()
    public_ids = {race.id for section in public.sections for race in section.races}
    assert hidden.id not in public_ids
    assert full.ballot_membership is not None
    assert public.ballot_membership is not None
    assert set(public.ballot_membership.races) == public_ids
    assert public.ballot_membership.groups == full.ballot_membership.groups
    assert full.model_dump_json() == original
    assert PublicationViewModel.model_validate_json(public.model_dump_json()) == public
