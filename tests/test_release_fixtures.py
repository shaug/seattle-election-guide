"""Small artifact-policy inputs remain fully typed and independent (#651)."""

from tests.release_fixtures import minimal_publication_view_model


def test_release_policy_fixture_contains_one_complete_contest() -> None:
    view = minimal_publication_view_model(source_registry_hash="c" * 64)
    assert [race.id for section in view.sections for race in section.races] == [
        "king-county-assessor"
    ]
    assert view.metadata.election_id == "wa-2026-primary"
    assert view.metadata.published_race_count == 1
    assert view.metadata.source_registry_hash == "c" * 64
    assert [race.race_id for race in view.personalization.races] == ["king-county-assessor"]


def test_release_policy_fixture_does_not_share_mutable_state() -> None:
    first = minimal_publication_view_model()
    first.sections[0].races[0].race_label = "Mutated private fixture"
    first.personalization.sources.clear()
    second = minimal_publication_view_model()
    assert second.sections[0].races[0].race_label == "King County Assessor"
    assert second.personalization.sources
    assert second.metadata.source_registry_hash is None
