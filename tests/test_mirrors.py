"""The cross-language mirror inventory, and the fixtures that hold it up.

docs/FRONTEND.md § Cross-language mirrors. Three things have to stay true and
none of them can be left to a reader noticing:

- the inventory names every mirror the tree actually contains, which
  `tests/cross_language_mirrors.py` derives rather than trusts;
- every mirror the inventory promises a fixture for has one, and every case in
  the fixture belongs to a mirror the inventory names; and
- the committed fixture is what a fresh run of the generator produces, so a
  server-side change that moves an expectation cannot leave a green fixture
  asserting the old answer.

The last is the one a parity fixture most easily loses. A committed golden file
is only evidence while it is current, and nothing about a stale one looks wrong.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from election_guide.rendering import context
from tests.cross_language_mirrors import derived_evidence
from tests.mirror_parity import FIXTURE_PATH, FIXTURE_SCHEMA_VERSION, generate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIRRORS_PATH = PROJECT_ROOT / "tests" / "mirrors.json"
LENS_FIXTURE_PATH = PROJECT_ROOT / "tests" / "js" / "fixtures" / "lens-parity.json"
DOCUMENT = "docs/FRONTEND.md"
REGENERATE = "uv run python -m tests.mirror_parity"

PROOFS = {
    "parity-fixture",
    "lens-parity-fixture",
    "markup-parity",
    "shared-literal",
    "payload-carried",
}
# Proofs that rest on the derivation seeing the text on both sides, and so are
# meaningless without evidence to lose. `markup-parity` is included because its
# region diff and the derivation cover each other: the diff catches a rendering
# that stops matching, the evidence catches wording that leaves one side.
_TEXT_BACKED_PROOFS = {"markup-parity", "shared-literal"}


@pytest.fixture(scope="module")
def inventory() -> dict[str, Any]:
    return json.loads(MIRRORS_PATH.read_text(encoding="utf-8"))["mirrors"]


@pytest.fixture(scope="module")
def committed_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_every_entry_declares_a_known_proof(inventory: dict[str, Any]) -> None:
    for name, entry in inventory.items():
        assert entry["proof"] in PROOFS, f"{name} claims the unknown proof {entry['proof']!r}"
        assert entry["note"].strip(), f"{name} has no note saying what the mirror is"
        assert entry["client"].strip() and entry["server"].strip(), f"{name} names only one side"


def test_a_text_backed_proof_rests_on_derived_text(inventory: dict[str, Any]) -> None:
    """A string-only mirror is proven by the derivation seeing it on both sides.

    So that proof is meaningless without text evidence: with none declared,
    nothing about the entry would change when one side's wording moved.
    """
    for name, entry in inventory.items():
        if entry["proof"] not in _TEXT_BACKED_PROOFS:
            continue
        assert any(item.startswith("text:") for item in entry["evidence"]), (
            f"{name} is proven by its shared text but declares none, so no change to either "
            f"side could fail this check ({DOCUMENT} § Cross-language mirrors)."
        )


def test_the_inventory_accounts_for_every_derived_mirror(inventory: dict[str, Any]) -> None:
    """Both directions, so neither a new mirror nor a stale claim survives.

    An undeclared candidate is a mirror nobody chose a proof for. A declared
    candidate the tree no longer shows is the drift detector firing: the words
    moved on one side, or the mirror is gone and its entry should be too.
    """
    derived = set(derived_evidence())
    declared = {item for entry in inventory.values() for item in entry["evidence"]}

    undeclared = sorted(derived - declared)
    assert not undeclared, (
        f"the tree shows cross-language mirrors that tests/mirrors.json does not name: "
        f"{undeclared}. Add an entry saying how each is proven, or delete the duplicate "
        f"({DOCUMENT} § Cross-language mirrors: prefer deleting a mirror to fixing one)."
    )

    stale = sorted(declared - derived)
    assert not stale, (
        f"tests/mirrors.json declares evidence the tree no longer shows: {stale}. Either one "
        f"side's wording changed and the other did not — which is the drift this evidence "
        f"exists to catch — or the mirror is gone and its entry should go with it."
    )


def test_every_fixtured_mirror_has_cases(
    inventory: dict[str, Any], committed_fixture: dict[str, Any]
) -> None:
    covered = {case["mirror"] for case in committed_fixture["cases"]}
    promised = {name for name, entry in inventory.items() if entry["proof"] == "parity-fixture"}

    missing = sorted(promised - covered)
    assert not missing, (
        f"{missing} are marked parity-fixture but the committed fixture has no case for them. "
        f"Regenerate with `{REGENERATE}`, or change the proof to what actually holds them."
    )

    unclaimed = sorted(covered - promised)
    assert not unclaimed, (
        f"the fixture carries cases for {unclaimed}, which tests/mirrors.json does not mark "
        f"parity-fixture. The inventory is what says a mirror is covered, so it has to say so."
    )


def test_the_lens_fixture_backs_the_entry_that_cites_it(inventory: dict[str, Any]) -> None:
    if not any(entry["proof"] == "lens-parity-fixture" for entry in inventory.values()):
        return
    lens = json.loads(LENS_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert lens["cases"], "lens-parity.json has no cases, so it proves nothing"


def test_every_case_carries_the_provenance_of_its_expectation(
    committed_fixture: dict[str, Any],
) -> None:
    """A case whose expectation has no stated source cannot be audited later."""
    assert committed_fixture["schema_version"] == FIXTURE_SCHEMA_VERSION
    for case in committed_fixture["cases"]:
        assert case["source"].strip(), f"{case['mirror']} has a case with no source"
        assert case["note"].strip(), f"{case['mirror']} has a case with no note"


def test_the_meter_layout_ignores_the_order_its_cells_arrive_in(
    committed_fixture: dict[str, Any],
) -> None:
    """The server's half of the claim the client's own suite makes on its side.

    Meter v2's block list is generated here from `race.source_cells` in
    active-source order, while the client hands the same race's cells to its
    mirror keyed by sorted transport code. Every expectation in the fixture is
    therefore only reproducible if the layout's canonical order is what decides
    the result — so feeding the same cells backwards has to change nothing.
    """
    cases = [case for case in committed_fixture["cases"] if case["mirror"] == "meter-layout-blocks"]
    assert cases, "the fixture carries no meter-layout cases, so this proves nothing"
    for case in cases:
        endorsements = [
            context.MeterEndorsement(
                source_label=item["source_label"],
                candidate_ids=tuple(item["candidate_ids"]),
                candidate_labels=tuple(item["candidate_labels"]),
            )
            for item in case["input"]["endorsements"]
        ]
        assert context.meter_layout_blocks(list(reversed(endorsements))) == (
            context.meter_layout_blocks(endorsements)
        ), (
            f"{case['source']} laid out differently when its cells were reversed, so something "
            f"in the layout reads the input order rather than the canonical one."
        )


def test_the_committed_fixture_matches_a_fresh_generation(
    committed_fixture: dict[str, Any],
) -> None:
    """The staleness check.

    Every expectation in the fixture is the server's answer at the moment it was
    generated. Change a label, a rounding rule, or a caption and the committed
    file keeps asserting the old one against a client that may have followed the
    change — green, and wrong in both directions at once. Regenerating here is
    the only way to notice.
    """
    assert committed_fixture == generate(), (
        f"tests/js/fixtures/mirror-parity.json no longer matches what the server produces. "
        f"Regenerate it with `{REGENERATE}` and read the diff: a changed expectation is a "
        f"changed contract, and the client half has to move with it."
    )
