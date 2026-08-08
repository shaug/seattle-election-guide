from pathlib import Path

import pytest
from pydantic import ValidationError

from election_guide.authorities.models import Authority, AuthorityRegistry
from election_guide.authorities.registry import read_authority_registry

PROJECT_ROOT = Path(__file__).parent.parent
REGISTRY_PATH = PROJECT_ROOT / "config" / "authorities" / "default.yaml"


def test_committed_authority_registry_registers_the_wa_2026_primary_authorities() -> None:
    registry = read_authority_registry(REGISTRY_PATH)

    ids = registry.authority_ids()
    assert ids == {"king-county-elections", "wa-secretary-of-state"}
    king_county = next(a for a in registry.authorities if a.id == "king-county-elections")
    assert king_county.name == "King County Elections"
    assert king_county.organization_url.startswith("https://")


def test_authority_registry_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="repeats an authority id"):
        AuthorityRegistry.model_validate(
            {
                "schema_version": "1.0",
                "authorities": [
                    {
                        "id": "king-county-elections",
                        "name": "King County Elections",
                        "organization_url": "https://kingcounty.gov/en/dept/elections",
                    },
                    {
                        "id": "king-county-elections",
                        "name": "King County Elections (duplicate)",
                        "organization_url": "https://kingcounty.gov/en/dept/elections",
                    },
                ],
            }
        )


def test_authority_rejects_an_invalid_id_pattern() -> None:
    with pytest.raises(ValidationError):
        Authority.model_validate(
            {
                "id": "King County Elections",
                "name": "King County Elections",
                "organization_url": "https://kingcounty.gov/en/dept/elections",
            }
        )


def test_authority_rejects_undeclared_fields() -> None:
    with pytest.raises(ValidationError):
        Authority.model_validate(
            {
                "id": "king-county-elections",
                "name": "King County Elections",
                "organization_url": "https://kingcounty.gov/en/dept/elections",
                "panel_role": "consensus",
            }
        )


def test_authority_registry_requires_at_least_one_authority() -> None:
    with pytest.raises(ValidationError):
        AuthorityRegistry.model_validate({"schema_version": "1.0", "authorities": []})
