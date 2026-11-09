"""Bind current page capability claims to their separately admitted audit asset."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any, cast

from election_guide.hosting.supplements import HistoricalPrecinctSupplement
from election_guide.publication.precinct_ballot import (
    HistoricalPrecinctProvenance,
    PrecinctBallotContract,
)
from election_guide.serialization import parse_json_bytes


class _CapabilityPage(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_head = False
        self.collect_payload = False
        self.current_payload: list[str] = []
        self.payloads: list[str] = []
        self.metadata: dict[str, list[str | None]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "head":
            self.in_head = True
        name = attributes.get("name")
        if self.in_head and tag == "meta" and name is not None:
            self.metadata.setdefault(name, []).append(attributes.get("content"))
        if tag == "script" and "data-client-payload" in attributes:
            self.collect_payload = True
            self.current_payload = []

    def handle_data(self, data: str) -> None:
        if self.collect_payload:
            self.current_payload.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self.in_head = False
        if tag == "script" and self.collect_payload:
            self.payloads.append("".join(self.current_payload))
            self.collect_payload = False


def verify_page_supplement(
    document: str,
    provenance: HistoricalPrecinctProvenance | None,
    supplement: HistoricalPrecinctSupplement | None,
    *,
    require_contract: bool = False,
) -> None:
    parser = _CapabilityPage()
    parser.feed(document)
    parser.close()
    expected = {
        "seg-precinct-supplement": provenance.artifact_sha256 if provenance else None,
        "seg-precinct-source": provenance.source_git_commit if provenance else None,
    }
    for name, value in expected.items():
        if parser.metadata.get(name, []) != ([value] if value is not None else []):
            raise ValueError(f"page precinct supplement metadata differs: {name}")
    if provenance is None:
        for raw in parser.payloads:
            payload: Any = parse_json_bytes(raw.encode())
            if isinstance(payload, dict) and "precinct_ballot" in payload:
                contract_value = cast(dict[str, Any], payload)["precinct_ballot"]
                if (
                    isinstance(contract_value, dict)
                    and "supplement" in contract_value
                    and contract_value["supplement"] is not None
                ):
                    raise ValueError("page claims an unbound precinct supplement")
        return
    if supplement is None:
        raise ValueError("page precinct supplement has no admitted audit asset")
    if require_contract and len(parser.payloads) != 1:
        raise ValueError("page precinct supplement requires exactly one client payload")
    found_contract = False
    for raw in parser.payloads:
        payload: Any = parse_json_bytes(raw.encode())
        if not isinstance(payload, dict) or "precinct_ballot" not in payload:
            continue
        found_contract = True
        contract = PrecinctBallotContract.model_validate(payload["precinct_ballot"])
        if (
            contract.election_id != supplement.election_id
            or contract.supplement != provenance
            or contract.mapping_hash != supplement.mapping_hash
            or contract.precincts != supplement.precincts
            or contract.address_lookup is not None
        ):
            raise ValueError("page precinct membership differs from admitted historical supplement")
    if require_contract and not found_contract:
        raise ValueError("page precinct supplement has no membership contract")
