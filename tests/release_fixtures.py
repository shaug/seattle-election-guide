"""Small independent artifact-policy inputs; full publication builds stay integration tests."""

from pathlib import Path

from election_guide.publication.models import PublicationViewModel
from election_guide.serialization import read_json

MINIMAL_VIEW_MODEL = Path(__file__).parent / "fixtures/release/minimal-publication-view-model.json"


def minimal_publication_view_model(
    *, source_registry_hash: str | None = None
) -> PublicationViewModel:
    payload = read_json(MINIMAL_VIEW_MODEL)
    payload["schema_version"] = "1.9" if source_registry_hash is None else "1.14"
    if source_registry_hash is None:
        payload["metadata"].pop("source_registry_hash", None)
    else:
        payload["metadata"]["source_registry_hash"] = source_registry_hash
    return PublicationViewModel.model_validate(payload)
