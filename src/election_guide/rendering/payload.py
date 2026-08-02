"""The embedded JSON payload each page publishes for its client modules.

docs/FRONTEND.md (The data contract) makes this payload the complete client
contract: everything client code needs — identifiers, display labels, ordering,
summaries — is published here, so no module reads state back out of rendered
markup. Two consequences shape this module.

*One identifier space.* A panel source is addressed by its transport `code`
everywhere the client can see it: in this payload, in the markup's data
attributes, and in the client modules. The publication view model's internal
`id` is deliberately absent, because a payload that carried both would put the
client back in the business of translating between two of our own identifier
spaces.

*One generator.* These models are the sole source of the TypeScript
declarations the client is checked against: `client_payload_json_schema()`
emits their JSON Schema and `generate_client_payload_types()` renders it to
`templates/types/client-payload.d.ts`, which is committed and diff-checked by
`tests/test_client_payload_types.py`. A Python model change that breaks a
client consumer therefore fails `make check` rather than the published page.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, RootModel
from pydantic.json_schema import GenerateJsonSchema

from election_guide.publication.comparisons import ComparisonsContract
from election_guide.publication.models import PublicationViewModel
from election_guide.publication.personalization import PersonalizationContract
from election_guide.rendering.bundler import (
    EXACT_VERSION,
    PACKAGE_JSON,
    REPO_ROOT,
    TEMPLATE_DIR,
)
from election_guide.scoring.models import Grade

CLIENT_PAYLOAD_SCHEMA_VERSION = "1.0"
"""Bumped whenever a published payload stops being readable by the shipped
client. The client validates it at parse time and, on a version it does not
understand, leaves the server-rendered baseline alone behind a visible notice
(docs/FRONTEND.md, The data contract)."""

TYPES_DIR = TEMPLATE_DIR / "types"
CLIENT_PAYLOAD_TYPES = TYPES_DIR / "client-payload.d.ts"
JSON2TS = REPO_ROOT / "node_modules" / ".bin" / "json2ts"
GENERATOR_MANIFEST = REPO_ROOT / "node_modules" / "json-schema-to-typescript" / "package.json"

# `export` makes the file a module, and a module's names stop being ambient.
_AMBIENT = re.compile(r"^export ", re.MULTILINE)


class ClientPayloadModel(BaseModel):
    """Reject undeclared fields so a drifting payload fails publication."""

    model_config = ConfigDict(extra="forbid")


class LensPolicy(ClientPayloadModel):
    """The slice of the release policy the fragment codec needs."""

    maximum_url_characters: int


class LensScoring(ClientPayloadModel):
    """The scoring identity a shared link is validated against."""

    configuration_id: str


class LensCategory(ClientPayloadModel):
    """A selectable grouping, addressed by code."""

    code: str
    label: str
    selectable: bool
    panel_role: Literal["tallying", "comparison"]
    member_source_codes: list[str]


class LensSource(ClientPayloadModel):
    """One panel source, addressed by code.

    A comparison source is published even though nothing selects it any more
    (issue 124): the codec identifies a pre-removal link's comparison token by
    the published role, and must see that role to ignore the token rather than
    reject the whole link.
    """

    code: str
    name: str
    panel_role: Literal["consensus", "comparison"]
    selectable: bool


class RaceCandidateDisplay(ClientPayloadModel):
    """One candidate's published identity and display label."""

    candidate_id: str
    label: str


class FilterScope(ClientPayloadModel):
    """One option of the guide's Ballot filter, addressed by its token."""

    value: str
    label: str


class RaceDisplay(ClientPayloadModel):
    """The audited presentation of one race that client code must be able to
    reproduce or restore.

    Every field here was previously read back out of the server-rendered
    dialog. The document's rule is the opposite (The data contract: the DOM is
    write-only projection), and its Cross-language mirrors section prefers
    carrying a computed value over maintaining a second implementation of the
    logic that computes it — so the audited candidate labels, the audited
    candidate order, and the audited accessible summary are published here.
    """

    race_id: str
    race_label: str
    """The race's display name. The dialog's share button used to read it back
    out of the card's own `[data-display-role="race-label"]` text (issue
    #239)."""
    candidates: list[RaceCandidateDisplay]
    """The audited default's own candidate order, with each candidate's display
    label. A lens that stops diverging restores exactly this order rather than
    leaving whatever a prior lens last arranged."""
    audited_accessible_summary: str
    """The dialog's visually-hidden `aria-describedby` text as the server
    rendered it, so clearing a lens restores it verbatim."""


class LensPayload(ClientPayloadModel):
    """What every lens-aware page publishes: the panel identity the fragment
    codec validates a link against, plus the categories and sources it names."""

    schema_version: Literal["1.0"]
    data_version: str
    panel_id: str
    panel_hash: str
    policy: LensPolicy
    scoring: LensScoring
    categories: list[LensCategory]
    sources: list[LensSource]


class GuidePayload(LensPayload):
    """The endorsements guide's payload."""

    races: list[RaceDisplay]
    filter_scopes: list[FilterScope]
    """Every Ballot-filter token the page offers, with the label the select
    renders for it, in rendered order. The filter status line used to read the
    selected option's text back out of the select (issue #239), and the set of
    admissible tokens off `select.options`."""
    sources_page_path: str
    """Where the page's `[data-sources-link]` anchors point, so the module that
    appends the live lens fragment does not have to be told by the template."""
    personalization: PersonalizationContract | None
    """Null while the release policy disables the lens: without it nothing on
    the page can rescore, so publishing it would ship a contract no code reads.
    """


class SourcesPayload(LensPayload):
    """The standalone sources editor's payload.

    A selection editor only: it never scores anything, so it publishes no
    personalization contract and no race display data.
    """

    guide_path: str
    """Where Save, Cancel, and Reset return the reader."""


class ComparisonsPayload(ClientPayloadModel):
    """The Comparisons page's payload."""

    schema_version: Literal["1.0"]
    data_version: str
    default_columns: list[str]
    personalization: PersonalizationContract
    comparisons: ComparisonsContract
    source_labels: dict[str, str]
    contested_race_ids: list[str]


class ComputedGrade(RootModel[Grade]):
    """A grade the client's own scoring engine can resolve to.

    No payload field carries this: the client computes it. It is declared here
    anyway because the grade strings have a Python origin
    (`scoring/models.py`), and docs/FRONTEND.md's Shared names section allows
    exactly one generator for such a value. Declaring it from the Python
    definition keeps the client's `ComputedGrade` and the audited engine's
    `Grade` from drifting apart.
    """


class ClientPayloadTypes(ClientPayloadModel):
    """The complete client type surface, in one root.

    Nothing serializes this model; each page publishes one of its members. It
    exists so the schema-to-types generator emits every declaration from one
    document, in one pass, into one committed file.
    """

    guide_page: GuidePayload
    sources_page: SourcesPayload
    comparisons_page: ComparisonsPayload
    computed_grade: ComputedGrade


class ClientPayloadTypesError(RuntimeError):
    """The schema-to-types generator is unavailable, mispinned, or failed."""


def _lens_categories(view_model: PublicationViewModel) -> list[LensCategory]:
    return [
        LensCategory(
            code=category.code,
            label=category.label,
            selectable=category.selectable,
            panel_role=category.panel_role,
            member_source_codes=category.member_source_codes,
        )
        for category in view_model.personalization.categories
    ]


def _lens_sources(
    view_model: PublicationViewModel,
    *,
    contributing_only: bool,
) -> list[LensSource]:
    """The panel sources a page publishes.

    `contributing_only` drops the coverage-gap sources: they have zero
    endorsements and were never selectable on the sources page's own tree
    (issue 107's "contributing" filter), so they must not count toward the
    guide's "Counting N of M" total either. A comparison source is exempt for
    the reason `LensSource` records.
    """
    name_by_id = {source.id: source.name for source in view_model.sources}
    status_by_id = {source.id: source.contribution_status for source in view_model.sources}
    return [
        LensSource(
            code=source.code,
            name=name_by_id[source.id],
            panel_role=source.panel_role,
            selectable=source.selectable,
        )
        for source in view_model.personalization.sources
        if not contributing_only
        or source.panel_role == "comparison"
        or status_by_id[source.id] == "contributing"
    ]


def _lens_fields(view_model: PublicationViewModel, *, contributing_only: bool) -> dict[str, Any]:
    return {
        "schema_version": CLIENT_PAYLOAD_SCHEMA_VERSION,
        "data_version": view_model.metadata.data_version,
        "panel_id": view_model.metadata.source_panel_id,
        "panel_hash": view_model.metadata.source_panel_hash,
        "policy": LensPolicy(
            maximum_url_characters=view_model.personalization.policy.maximum_url_characters
        ),
        "scoring": LensScoring(
            configuration_id=view_model.personalization.scoring.configuration_id
        ),
        "categories": _lens_categories(view_model),
        "sources": _lens_sources(view_model, contributing_only=contributing_only),
    }


def guide_payload(
    view_model: PublicationViewModel,
    *,
    races: list[RaceDisplay],
    filter_scopes: list[FilterScope],
    sources_page_path: str,
) -> GuidePayload:
    """Build the guide's payload.

    `races` and `filter_scopes` come from the renderer rather than from here,
    because they must be the very text and order the server rendered — the
    renderer owns the audited presentation, and the payload publishes it rather
    than recomputing it.
    """
    return GuidePayload(
        **_lens_fields(view_model, contributing_only=True),
        races=races,
        filter_scopes=filter_scopes,
        sources_page_path=sources_page_path,
        personalization=(
            view_model.personalization if view_model.personalization.policy.enabled else None
        ),
    )


def sources_payload(view_model: PublicationViewModel, *, guide_path: str) -> SourcesPayload:
    """Build the sources editor's payload.

    Categories and sources are published in full regardless of the lens policy,
    and regardless of contribution status: this page renders the whole tree.
    """
    return SourcesPayload(
        **_lens_fields(view_model, contributing_only=False), guide_path=guide_path
    )


def comparisons_payload(
    view_model: PublicationViewModel,
    *,
    default_columns: list[str],
) -> ComparisonsPayload:
    """Build the Comparisons page's payload."""
    name_by_id = {source.id: source.name for source in view_model.sources}
    race_by_id = {race.id: race for section in view_model.sections for race in section.races}
    return ComparisonsPayload(
        schema_version=CLIENT_PAYLOAD_SCHEMA_VERSION,
        data_version=view_model.metadata.data_version,
        default_columns=default_columns,
        personalization=view_model.personalization,
        comparisons=view_model.comparisons,
        source_labels={
            source.code: name_by_id[source.id] for source in view_model.personalization.sources
        },
        contested_race_ids=[
            display.race_id
            for display in view_model.comparisons.display_index
            if race_by_id[display.race_id].is_contested
        ],
    )


AMBIENT_BANNER = """\
// GENERATED BY `make types` FROM THE PYDANTIC MODELS IN
// `src/election_guide/rendering/payload.py`. DO NOT EDIT BY HAND.
//
// The embedded JSON payload's shape, as the client consumes it
// (docs/FRONTEND.md, The data contract). `tsc --noEmit --checkJs` holds every
// client module to these declarations and
// `tests/test_client_payload_types.py` fails when this file and the models
// disagree, so a Python model change that breaks a client consumer fails
// `make check` rather than the published page.
//
// Emitted by json-schema-to-typescript {pinned}, with `export` stripped so the
// names stay ambient.

"""


class _UntitledFields(GenerateJsonSchema):
    """Emit no per-field `title`.

    Pydantic titles every field by default, and the generator turns a titled
    property into its own named type — so a payload of forty fields would emit
    forty aliases like `Code1` and `PanelRole2` around the handful of
    declarations client code actually names. Suppressed at the one knob
    Pydantic provides rather than by stripping the key afterwards, which would
    also delete a title a model legitimately set, including a field named
    `title`. Model titles are untouched, and they are what names each
    declaration after the Python class it came from.
    """

    def field_title_should_be_set(self, schema: Any) -> bool:
        return False


def client_payload_json_schema() -> dict[str, Any]:
    """The JSON Schema of the complete client type surface."""
    return ClientPayloadTypes.model_json_schema(
        mode="serialization", schema_generator=_UntitledFields
    )


def _verified_generator_version() -> str:
    """The exact version `package.json` pins, proven installed before it runs.

    Checked the way the bundler checks esbuild, and for the same reason: the
    committed output is only reproducible per exact version, so a machine
    running a different one would otherwise report itself as a stale-
    declarations failure rather than as the toolchain mismatch it is.
    """
    manifest = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    pinned = manifest.get("devDependencies", {}).get("json-schema-to-typescript")
    if not isinstance(pinned, str) or not EXACT_VERSION.fullmatch(pinned):
        raise ClientPayloadTypesError(
            f"{PACKAGE_JSON} must pin json-schema-to-typescript to an exact version; "
            f"found {pinned!r}. Dev-time dependencies are exact-pinned "
            "(docs/FRONTEND.md, Dependencies)."
        )
    if not GENERATOR_MANIFEST.exists():
        raise ClientPayloadTypesError(
            f"the schema-to-types generator is not installed at {GENERATOR_MANIFEST.parent}: "
            "run `npm ci` (CONTRIBUTING.md; docs/FRONTEND.md, Dependencies)."
        )
    found = json.loads(GENERATOR_MANIFEST.read_text(encoding="utf-8")).get("version")
    if found != pinned:
        raise ClientPayloadTypesError(
            f"json-schema-to-typescript {found} is installed, but package.json pins {pinned}. "
            "The committed declarations are only reproducible for the pinned version: run "
            "`npm ci` (docs/FRONTEND.md, Dependencies)."
        )
    return pinned


def render_client_payload_types() -> str:
    """Render the committed TypeScript declarations from the models above.

    The declarations are emitted ambient — no `export`, so every name is
    global — because they are read from JSDoc annotations spread across the
    whole module graph, and an `import(...)` at each of those dozens of use
    sites buys nothing for a payload that is one page-wide contract.
    """
    pinned = _verified_generator_version()
    result = subprocess.run(
        [
            str(JSON2TS),
            "--bannerComment",
            "",
            "--additionalProperties",
            "false",
        ],
        input=json.dumps(client_payload_json_schema()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise ClientPayloadTypesError(
            f"json-schema-to-typescript {pinned} failed:\n{result.stderr.strip()}"
        )
    return AMBIENT_BANNER.format(pinned=pinned) + _AMBIENT.sub("", result.stdout)


def generate_client_payload_types() -> None:
    """Write the committed declarations. `make types` is the only caller."""
    TYPES_DIR.mkdir(parents=True, exist_ok=True)
    CLIENT_PAYLOAD_TYPES.write_text(render_client_payload_types(), encoding="utf-8")
