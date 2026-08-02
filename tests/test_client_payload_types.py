"""The payload's types are generated from the Pydantic models, not transcribed.

docs/FRONTEND.md (The data contract): the publication view model emits JSON
Schema, the build generates TypeScript declarations from it, and client modules
are checked against them, so a Python model change that breaks a client
consumer fails `make check`.

That guarantee needs two halves. `tsc --noEmit --checkJs` (`make check-js`)
holds the modules to the committed declarations without running any Python.
This module supplies the other half: the committed declarations are what the
current models generate. Regenerate with `make types`.
"""

from __future__ import annotations

import re

import pytest

from election_guide.rendering.bundler import TEMPLATE_DIR
from election_guide.rendering.payload import (
    CLIENT_PAYLOAD_SCHEMA_VERSION,
    CLIENT_PAYLOAD_TYPES,
    client_payload_json_schema,
    render_client_payload_types,
)

CLIENT_PAYLOAD_MODULE = TEMPLATE_DIR / "client-payload.mjs"


def test_the_committed_declarations_are_what_the_models_generate() -> None:
    committed = CLIENT_PAYLOAD_TYPES.read_text(encoding="utf-8")

    assert committed == render_client_payload_types(), (
        f"{CLIENT_PAYLOAD_TYPES.name} is stale: the client payload models changed without "
        "regenerating the declarations the client is type-checked against. Run `make types` "
        "and commit the result (docs/FRONTEND.md, The data contract)."
    )


def test_every_modeled_field_reaches_the_declarations() -> None:
    """The staleness check above is only worth having if the models actually
    drive the text. Asserted mechanically: every field the models declare is a
    field the declarations declare, so a generator that stopped reading them,
    or a field it silently dropped, fails here rather than at a call site."""
    schema = client_payload_json_schema()
    declarations = CLIENT_PAYLOAD_TYPES.read_text(encoding="utf-8")

    modeled_fields = {
        field
        for definition in schema["$defs"].values()
        for field in definition.get("properties", {})
    } | set(schema.get("properties", {}))
    assert modeled_fields

    missing = sorted(field for field in modeled_fields if f"{field}:" not in declarations)
    assert missing == []


def test_every_declaration_the_client_names_is_generated() -> None:
    """The declarations client modules annotate against, all from one source.

    Named explicitly because a rename in Python is otherwise a silent break:
    `tsc` would report the missing name, but only after someone regenerated.
    """
    declarations = CLIENT_PAYLOAD_TYPES.read_text(encoding="utf-8")

    for name in (
        "GuidePayload",
        "SourcesPayload",
        "ComparisonsPayload",
        "PersonalizationContract",
        "PersonalizationCategory",
        "PersonalizationCell",
        "PersonalizationRace",
        "PersonalizationScoring",
        "PersonalizationSource",
        "PersonalizationRetiredCode",
        "ComparisonsContract",
        "ComparisonDisplayRace",
        "RaceDisplay",
        "ComputedGrade",
    ):
        assert f"interface {name} " in declarations or f"type {name} =" in declarations


def test_the_grade_strings_have_exactly_one_generator() -> None:
    """docs/FRONTEND.md, Shared names: a value with a Python origin is declared
    once. The client's grade vocabulary is `scoring/models.py`'s `Grade`, routed
    through the generator, so nothing hand-restates it."""
    from election_guide.scoring.models import Grade

    declarations = CLIENT_PAYLOAD_TYPES.read_text(encoding="utf-8")
    grades = Grade.__args__  # pyright: ignore[reportAttributeAccessIssue]

    expected = " | ".join(f'"{grade}"' for grade in grades)
    assert f"type ComputedGrade = {expected};" in declarations


def test_the_declarations_stay_ambient() -> None:
    """Client modules annotate these names bare, from a dozen files. An `export`
    would make the file a module and every one of those annotations an error."""
    declarations = CLIENT_PAYLOAD_TYPES.read_text(encoding="utf-8")

    assert "export " not in declarations
    assert "import " not in declarations


def test_the_schema_forbids_undeclared_payload_fields() -> None:
    """`extra="forbid"` is what makes the generated declarations exhaustive: a
    payload field nobody modeled would otherwise be typed as permitted."""
    schema = client_payload_json_schema()

    for name, definition in schema["$defs"].items():
        if definition.get("type") != "object":
            continue
        assert definition.get("additionalProperties") is False, name


@pytest.mark.parametrize("model", ["GuidePayload", "SourcesPayload", "ComparisonsPayload"])
def test_every_page_payload_declares_its_schema_version(model: str) -> None:
    """Validated at parse time by the client, so it can never be optional."""
    definition = client_payload_json_schema()["$defs"][model]

    assert "schema_version" in definition["required"]
    assert definition["properties"]["schema_version"]["const"] == CLIENT_PAYLOAD_SCHEMA_VERSION


def test_the_client_understands_the_version_the_payload_carries() -> None:
    """The one value the generator cannot carry, checked instead of commented.

    `client-payload.mjs` compares the version it reads against a literal of its
    own, because the check has to run before anything in the payload is
    trusted. A comment is not a contract (docs/FRONTEND.md, Cross-language
    mirrors), and the failure this guards is total: a build whose parser
    refuses its own payload leaves every page on the audited baseline.
    """
    module = CLIENT_PAYLOAD_MODULE.read_text(encoding="utf-8")

    declared = re.search(r"CLIENT_PAYLOAD_SCHEMA_VERSION = '([^']+)';", module)
    assert declared is not None, f"{CLIENT_PAYLOAD_MODULE.name} no longer declares the version"
    assert declared.group(1) == CLIENT_PAYLOAD_SCHEMA_VERSION
