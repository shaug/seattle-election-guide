"""Reviewed jurisdiction applicability; deliberately no section or ordering policy."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from election_guide.inventory.geography import reviewed_geography
from election_guide.inventory.models import Inventory


class BallotModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BallotDistrict(BallotModel):
    id: str
    label: str


class BallotGroup(BallotModel):
    id: str
    label: str
    mode: Literal["district", "membership"]
    options: list[BallotDistrict]


class BallotRaceRule(BallotModel):
    jurisdiction_id: str
    shared: bool
    outside_target: bool
    group_id: str | None


class BallotMembershipContract(BallotModel):
    confirmation_label: str
    election_id: str
    geography_hash: str | None
    inventory_notice: str | None
    groups: list[BallotGroup]
    races: dict[str, BallotRaceRule]

    @model_validator(mode="after")
    def validate_references(self) -> "BallotMembershipContract":
        groups = {group.id: group for group in self.groups}
        if len(groups) != len(self.groups):
            raise ValueError("ballot groups must have unique identifiers")
        for group in self.groups:
            ids = [option.id for option in group.options]
            if not ids or len(set(ids)) != len(ids):
                raise ValueError("ballot groups require unique district options")
            if group.mode == "membership" and len(ids) != 1:
                raise ValueError("independent membership questions name one jurisdiction")
        for rule in self.races.values():
            if rule.shared and rule.outside_target:
                raise ValueError("a contest cannot be shared and outside the target electorate")
            if rule.shared or rule.outside_target:
                if rule.group_id is not None:
                    raise ValueError("shared/outside contests cannot require a district choice")
            else:
                group = groups.get(rule.group_id or "")
                if group is None or rule.jurisdiction_id not in {
                    option.id for option in group.options
                }:
                    raise ValueError("ballot rule must name a jurisdiction in its group")
        return self


def build_ballot_membership(inventory: Inventory) -> BallotMembershipContract:
    """Only reviewed city-containing jurisdictions are automatically shared.

    Intersecting judicial and otherwise unclassified jurisdictions are independent
    membership questions: identical kinds do not establish mutually exclusive areas.
    """
    labels = {
        "legislative_district": "Legislative district",
        "congressional_district": "Congressional district",
        "county_council_district": "County council district",
        "city_council_district": "City council district",
    }
    geography = reviewed_geography(inventory.election.id)
    jurisdictions = {item.id: item for item in inventory.jurisdictions}
    groups: dict[str, BallotGroup] = {}
    if geography is not None:
        prefixes = {
            "congressional_district": "congressional-district",
            "legislative_district": "legislative-district",
            "county_council_district": "county-council-district",
            "city_council_district": "seattle-city-council-district",
        }
        for kind, codes in geography.districts.items():
            groups[kind] = BallotGroup(
                id=kind,
                label=labels[kind],
                mode="district",
                options=[
                    BallotDistrict(id=f"{prefixes[kind]}-{code}", label=f"{labels[kind]} {code}")
                    for code in codes
                ],
            )
    rules: dict[str, BallotRaceRule] = {}
    for race in sorted(inventory.races, key=lambda item: item.id):
        if not race.publication_eligible:
            continue
        jurisdiction = jurisdictions[race.jurisdiction_id]
        shared = jurisdiction.seattle_applicability.relationship in {"contains_city", "citywide"}
        outside = (
            geography is not None and jurisdiction.id in geography.outside_target_jurisdiction_ids
        )
        group_id = None
        if not shared and not outside:
            group_id = jurisdiction.kind if jurisdiction.kind in labels else jurisdiction.id
            if group_id not in groups:
                groups[group_id] = BallotGroup(
                    id=group_id,
                    label=labels.get(jurisdiction.kind, jurisdiction.name),
                    mode="district" if jurisdiction.kind in labels else "membership",
                    options=[],
                )
            if not any(option.id == jurisdiction.id for option in groups[group_id].options):
                if geography is not None and jurisdiction.kind in labels:
                    raise ValueError(
                        "contest district is absent from reviewed geography and exclusion review"
                    )
                groups[group_id].options.append(
                    BallotDistrict(id=jurisdiction.id, label=jurisdiction.name)
                )
        rules[race.id] = BallotRaceRule(
            jurisdiction_id=jurisdiction.id,
            shared=shared,
            outside_target=outside,
            group_id=group_id,
        )
    for group in groups.values():
        group.options.sort(key=lambda option: option.id)
    return BallotMembershipContract(
        confirmation_label="District needs confirmation",
        election_id=inventory.election.id,
        geography_hash=geography.configuration_hash if geography else None,
        inventory_notice=geography.inventory_notice
        if geography and any(rule.outside_target for rule in rules.values())
        else None,
        groups=[groups[key] for key in sorted(groups)],
        races=rules,
    )
