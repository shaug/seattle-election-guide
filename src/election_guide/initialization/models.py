"""Strict seed and canonical models for election initialization."""

from __future__ import annotations

import unicodedata
from datetime import date
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from election_guide.normalization.text import normalize_match_text
from election_guide.validation import validated_http_url

ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
VERSION_PATTERN = r"^[0-9]+(?:\.[0-9]+)*$"
JurisdictionKind = Literal[
    "country",
    "state",
    "county",
    "city",
    "congressional_district",
    "legislative_district",
    "judicial_district",
    "council_district",
    "county_council_district",
    "city_council_district",
    "precinct",
    "ballot_style",
]
RaceType = Literal["candidate", "measure", "party_office"]


class InitializationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ElectionIdentity(InitializationModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    election_type: Literal["primary", "general", "special"]
    election_scope: Literal["municipal", "county", "statewide", "mixed"]
    election_date: date
    state: str = Field(pattern=r"^[A-Z]{2}$")
    state_jurisdiction_id: str = Field(pattern=ID_PATTERN)
    official_url: str
    target_jurisdiction_ids: list[str] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _nonblank(value, "election name")

    @field_validator("official_url")
    @classmethod
    def validate_official_url(cls, value: str) -> str:
        return validated_http_url(value)

    @field_validator("target_jurisdiction_ids")
    @classmethod
    def validate_targets(cls, value: list[str]) -> list[str]:
        if value != sorted(set(value)):
            raise ValueError("target jurisdiction IDs must be unique and sorted")
        return value


class VersionedConfigurationReference(InitializationModel):
    id: str = Field(pattern=ID_PATTERN)
    version: str = Field(pattern=VERSION_PATTERN)
    path: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("configuration reference paths must use POSIX separators")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or str(path) != value:
            raise ValueError("configuration reference paths must be canonical and relative")
        if path.suffix not in {".json", ".yaml", ".yml"}:
            raise ValueError("configuration reference paths must name JSON or YAML")
        return value


class JurisdictionSeed(InitializationModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1)
    kind: JurisdictionKind
    state_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    parent_id: str | None = Field(default=None, pattern=ID_PATTERN)
    aliases: list[str] = Field(default_factory=list)
    seattle_relationship: Literal["contains_city", "citywide", "intersects_city", "within_city"]
    seattle_explanation: str = Field(min_length=1)

    @field_validator("name", "seattle_explanation")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return _nonblank(value, "jurisdiction text")

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        return _normalized_aliases(value, "jurisdiction")

    @model_validator(mode="after")
    def validate_identity(self) -> JurisdictionSeed:
        if self.parent_id == self.id:
            raise ValueError("jurisdiction cannot parent itself")
        if self.kind == "state" and self.state_code is None:
            raise ValueError("state jurisdictions require state_code")
        if self.kind != "state" and self.state_code is not None:
            raise ValueError("only state jurisdictions may declare state_code")
        return self


class RaceSeed(InitializationModel):
    id: str = Field(pattern=ID_PATTERN)
    jurisdiction_id: str = Field(pattern=ID_PATTERN)
    race_type: RaceType
    district: str = Field(min_length=1)
    office: str = Field(min_length=1)
    position: str | None = None
    display_name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    publication_eligible: bool = Field(strict=True)

    @field_validator("district", "office", "display_name")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _nonblank(value, "race identity text")

    @field_validator("position")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return None if value is None else _nonblank(value, "race position")

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        return _normalized_aliases(value, "race")

    @model_validator(mode="after")
    def validate_aliases(self) -> RaceSeed:
        return self


class ElectionInitializationSeed(InitializationModel):
    schema_version: Literal["1.0"] = "1.0"
    election: ElectionIdentity
    source_panel: VersionedConfigurationReference
    scoring_policy: VersionedConfigurationReference
    jurisdictions: list[JurisdictionSeed] = Field(min_length=1)
    races: list[RaceSeed]

    @model_validator(mode="after")
    def validate_topology(self) -> ElectionInitializationSeed:
        _validate_topology(self.election, self.jurisdictions, self.races)
        return self


class ElectionJurisdiction(JurisdictionSeed):
    election_id: str = Field(pattern=ID_PATTERN)


class ElectionRaceDeclaration(RaceSeed):
    election_id: str = Field(pattern=ID_PATTERN)


class ElectionConfiguration(InitializationModel):
    schema_version: Literal["1.0"] = "1.0"
    election: ElectionIdentity
    source_panel: VersionedConfigurationReference
    scoring_policy: VersionedConfigurationReference
    jurisdictions: list[ElectionJurisdiction] = Field(min_length=1)
    races: list[ElectionRaceDeclaration]

    @model_validator(mode="after")
    def validate_configuration(self) -> ElectionConfiguration:
        if [item.id for item in self.jurisdictions] != sorted(
            {item.id for item in self.jurisdictions}
        ):
            raise ValueError("election jurisdictions must be unique and sorted")
        if [item.id for item in self.races] != sorted({item.id for item in self.races}):
            raise ValueError("election races must be unique and sorted")
        if any(item.election_id != self.election.id for item in self.jurisdictions):
            raise ValueError("every jurisdiction must be scoped to this election")
        if any(item.election_id != self.election.id for item in self.races):
            raise ValueError("every race must be scoped to this election")
        _validate_topology(self.election, self.jurisdictions, self.races)
        return self


def _validate_topology(
    election: ElectionIdentity,
    jurisdictions: list[JurisdictionSeed] | list[ElectionJurisdiction],
    races: list[RaceSeed] | list[ElectionRaceDeclaration],
) -> None:
    jurisdiction_ids = [item.id for item in jurisdictions]
    if len(jurisdiction_ids) != len(set(jurisdiction_ids)):
        raise ValueError("duplicate jurisdiction ID")
    known_jurisdictions = set(jurisdiction_ids)
    parents = {item.id: item.parent_id for item in jurisdictions}
    jurisdiction_by_id = {item.id: item for item in jurisdictions}
    state_jurisdiction = jurisdiction_by_id.get(election.state_jurisdiction_id)
    if state_jurisdiction is None:
        raise ValueError(
            f"election has unknown state jurisdiction {election.state_jurisdiction_id!r}"
        )
    if state_jurisdiction.kind != "state" or state_jurisdiction.state_code != election.state:
        raise ValueError("election state must match its explicit state jurisdiction")
    for jurisdiction_id, parent_id in parents.items():
        if parent_id is not None and parent_id not in known_jurisdictions:
            raise ValueError(f"jurisdiction {jurisdiction_id!r} has unknown parent {parent_id!r}")
    for jurisdiction_id in jurisdiction_ids:
        visited: set[str] = set()
        current: str | None = jurisdiction_id
        while current is not None:
            if current in visited:
                raise ValueError(f"jurisdiction hierarchy contains a cycle at {current!r}")
            visited.add(current)
            current = parents[current]
    _validate_parent_kinds(jurisdiction_by_id)
    citywide_id = _validate_seattle_applicability(jurisdiction_by_id, parents)

    target_ids = set(election.target_jurisdiction_ids)
    unknown_targets = target_ids - known_jurisdictions
    if unknown_targets:
        raise ValueError(f"election has unknown target jurisdictions: {sorted(unknown_targets)}")
    target_kinds = {jurisdiction_by_id[item].kind for item in target_ids}
    if not target_kinds.issubset({"city", "county", "state"}):
        raise ValueError("election targets must be city, county, or state jurisdictions")
    seattle_hierarchy = set(_jurisdiction_ancestry(citywide_id, parents))
    seattle_state_ancestors = [
        item
        for item in _jurisdiction_ancestry(citywide_id, parents)
        if jurisdiction_by_id[item].kind == "state"
    ]
    if seattle_state_ancestors != [election.state_jurisdiction_id]:
        raise ValueError(
            "state_jurisdiction_id must be Seattle's unique state jurisdiction ancestor"
        )
    if not target_ids.issubset(seattle_hierarchy):
        raise ValueError("election targets must belong to the Seattle-containing hierarchy")
    expected_kind = {
        "municipal": "city",
        "county": "county",
        "statewide": "state",
    }.get(election.election_scope)
    if expected_kind is not None and (len(target_ids) != 1 or target_kinds != {expected_kind}):
        raise ValueError(
            f"{election.election_scope} scope requires exactly one {expected_kind} target"
        )
    if election.election_scope == "mixed" and (len(target_ids) < 2 or len(target_kinds) < 2):
        raise ValueError("mixed scope requires targets at two or more jurisdiction levels")
    if any(
        jurisdiction_by_id[item].kind == "city"
        and jurisdiction_by_id[item].seattle_relationship != "citywide"
        for item in target_ids
    ):
        raise ValueError("a city election target must be the citywide Seattle jurisdiction")

    race_ids = [item.id for item in races]
    if len(race_ids) != len(set(race_ids)):
        raise ValueError("duplicate race ID")
    logical_races: set[tuple[str, str, str, str, str]] = set()
    represented_targets: set[str] = set()
    allowed_target_kinds = {
        "city": {
            "city",
            "city_council_district",
            "council_district",
            "precinct",
            "ballot_style",
        },
        "county": {
            "county",
            "county_council_district",
            "council_district",
            "judicial_district",
            "precinct",
            "ballot_style",
        },
        "state": {
            "state",
            "congressional_district",
            "legislative_district",
            "judicial_district",
        },
    }
    for race in races:
        if race.jurisdiction_id not in known_jurisdictions:
            raise ValueError(f"race {race.id!r} has unknown jurisdiction {race.jurisdiction_id!r}")
        identity = (
            race.jurisdiction_id,
            race.race_type,
            normalize_match_text(race.district),
            normalize_match_text(race.office),
            normalize_match_text(race.position or ""),
        )
        if identity in logical_races:
            raise ValueError(f"race {race.id!r} duplicates a declared logical race")
        logical_races.add(identity)

        ancestry = _jurisdiction_ancestry(race.jurisdiction_id, parents)
        matching_targets = [item for item in ancestry if item in target_ids]
        if not matching_targets:
            raise ValueError(f"race {race.id!r} is outside the election target jurisdictions")
        represented_target = matching_targets[0]
        represented_targets.add(represented_target)
        target_kind = jurisdiction_by_id[represented_target].kind
        allowed = allowed_target_kinds[target_kind]
        race_kind = jurisdiction_by_id[race.jurisdiction_id].kind
        if race_kind not in allowed:
            raise ValueError(
                f"a {target_kind} target cannot be represented by a race in {race_kind!r}"
            )
        if (
            target_kind == "state"
            and race_kind == "judicial_district"
            and parents[race.jurisdiction_id] != represented_target
        ):
            raise ValueError(
                "a state target cannot be represented by a county-parented judicial district"
            )
        if race_kind == "council_district" and parents[race.jurisdiction_id] != represented_target:
            raise ValueError(
                f"a {target_kind} target cannot be represented by a differently parented "
                "generic council district"
            )
    if races and election.election_scope == "mixed" and represented_targets != target_ids:
        missing = sorted(target_ids - represented_targets)
        raise ValueError(f"mixed scope has no declared race for targets: {missing}")


def _validate_parent_kinds(
    jurisdiction_by_id: dict[str, JurisdictionSeed | ElectionJurisdiction],
) -> None:
    permitted_parents: dict[str, set[str | None]] = {
        "country": {None},
        "state": {None, "country"},
        "county": {"state"},
        "city": {"county"},
        "congressional_district": {"state"},
        "legislative_district": {"state"},
        "judicial_district": {"state", "county"},
        "council_district": {"county", "city"},
        "county_council_district": {"county"},
        "city_council_district": {"city"},
        "precinct": {
            "county",
            "city",
            "legislative_district",
            "council_district",
            "county_council_district",
            "city_council_district",
        },
        "ballot_style": {
            "state",
            "county",
            "city",
            "congressional_district",
            "legislative_district",
            "judicial_district",
            "precinct",
        },
    }
    for jurisdiction in jurisdiction_by_id.values():
        parent_kind = (
            None
            if jurisdiction.parent_id is None
            else jurisdiction_by_id[jurisdiction.parent_id].kind
        )
        if parent_kind not in permitted_parents[jurisdiction.kind]:
            raise ValueError(
                f"jurisdiction {jurisdiction.id!r} of kind {jurisdiction.kind!r} "
                f"cannot have parent kind {parent_kind!r}"
            )


def _validate_seattle_applicability(
    jurisdiction_by_id: dict[str, JurisdictionSeed | ElectionJurisdiction],
    parents: dict[str, str | None],
) -> str:
    citywide = [
        jurisdiction
        for jurisdiction in jurisdiction_by_id.values()
        if jurisdiction.seattle_relationship == "citywide"
    ]
    if len(citywide) != 1 or citywide[0].kind != "city":
        raise ValueError("jurisdiction topology must declare exactly one citywide Seattle city")

    city_id = citywide[0].id
    city_ancestry = set(_jurisdiction_ancestry(city_id, parents))
    for jurisdiction in jurisdiction_by_id.values():
        ancestry = set(_jurisdiction_ancestry(jurisdiction.id, parents))
        if jurisdiction.id == city_id:
            expected = "citywide"
        elif jurisdiction.id in city_ancestry:
            expected = "contains_city"
        elif city_id in ancestry:
            expected = "within_city"
        else:
            expected = "intersects_city"
        if jurisdiction.seattle_relationship != expected:
            raise ValueError(
                f"jurisdiction {jurisdiction.id!r} must use Seattle relationship {expected!r}"
            )
    return city_id


def _jurisdiction_ancestry(jurisdiction_id: str, parents: dict[str, str | None]) -> list[str]:
    ancestry: list[str] = []
    current: str | None = jurisdiction_id
    while current is not None:
        ancestry.append(current)
        current = parents[current]
    return ancestry


def _nonblank(value: str, label: str) -> str:
    normalized = unicodedata.normalize("NFC", value.strip())
    if not normalized:
        raise ValueError(f"{label} must not be blank")
    return normalized


def _normalized_aliases(values: list[str], label: str) -> list[str]:
    normalized = [_nonblank(value, f"{label} alias") for value in values]
    if normalized != sorted(set(normalized)):
        raise ValueError(f"{label} aliases must be unique and sorted")
    return normalized
