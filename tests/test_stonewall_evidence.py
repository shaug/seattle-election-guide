"""Audit the manually transcribed Washington Stonewall endorsement gallery."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).parents[1]
EXTRACT_PATH = PROJECT_ROOT / "data/extracted/washington-stonewall-democrats-2026-primary.yaml"
LEDGER_PATH = PROJECT_ROOT / "data/releases/wa-2026-primary/source-decisions.yaml"
EVIDENCE_MANIFEST_DIR = PROJECT_ROOT / "data/manifests/evidence"

EXPECTED_SEATTLE_RACES = {
    "king-county-assessor",
    "king-county-council-2",
    "ld-11-state-representative-1",
    "ld-32-state-representative-2",
    "ld-32-state-senator",
    "ld-34-state-representative-1",
    "ld-34-state-representative-2",
    "ld-37-state-representative-1",
    "ld-37-state-representative-2",
    "ld-37-state-senator",
    "ld-43-state-representative-1",
    "ld-43-state-senator",
    "ld-46-state-representative-1",
    "ld-46-state-representative-2",
    "ld-46-state-senator",
    "seattle-city-council-5",
    "seattle-municipal-court-judge-5",
    "supreme-court-justice-1",
    "supreme-court-justice-3",
    "supreme-court-justice-5",
    "us-house-7",
    "us-house-9",
}

EXPECTED_GALLERY_EVIDENCE = (
    (
        1,
        "dbfc508a99d5",
        "1450343267135341",
        "58cf012090b41fa4229b808c7a1afb9af14527a389bea68694b5e81c6fef2d53",
    ),
    (
        2,
        "780874a27470",
        "1450343233802011",
        "a413816f7042f95b11786d7ac965bdec5a5fd6bf5faefaf2d934219d437ce9ef",
    ),
    (
        3,
        "3b7407801410",
        "1450343250468676",
        "1fb5e273813637b4cb43f63ccf598977b2d91a21539e778f2d3855a7813d40e6",
    ),
    (
        4,
        "80d8944642be",
        "1450745557095112",
        "ead081b39a53ebc8a2d165ed94d4ea39d0cc246700ba14f44da9d023f7012c50",
    ),
    (
        5,
        "9ad584ac7a91",
        "1451331600369841",
        "c52b3f18ef350f274b9026215a38445513521a19b2f70dd4d17671e0fd54e0a5",
    ),
    (
        6,
        "4ad76b40d509",
        "1451293500373651",
        "b5f37e28c03f3757564bdcfadebd6eba206fbf649f62c1fa038cab1c49b5f353",
    ),
    (
        7,
        "e571ee0cc660",
        "1450363150466686",
        "889959b8488a641ebacc5f15e8ca15c497d285f571742ab0e9e5e42d52189e61",
    ),
    (
        8,
        "d78a11fefcab",
        "1450363157133352",
        "4a87be4a9ffa3c11cbc0e0b42fb47111e81659dac104675512471a95bd60fa7c",
    ),
    (
        9,
        "35d4a81e006f",
        "1451296940373307",
        "e05dc6ecd701d62dfcaa443073dbd89185783036826502d2e76834b6440450be",
    ),
    (
        10,
        "9f058cc2b11e",
        "1450363237133344",
        "39bc03a96e227071aad014bd8521005066bd1f574f67a0962e3b11c163661f7e",
    ),
    (
        11,
        "6576d2c76e20",
        "1450363250466676",
        "12086357daa4d4ef86c575880714802c7acb88359785cdc9a98087269bb5509d",
    ),
    (
        12,
        "cf475b198f0a",
        "1451333713702963",
        "0948660acca4b7e08c651daf1360232c26f154a30d36623164effdb6803d2d15",
    ),
)

EXPECTED_ENDORSEMENTS_SHA256 = "9f2b4b77e39481214fe02767a02d4044c7e54dd1ad3d46f894ece7024c20e29a"
EXPECTED_SEATTLE_DECISIONS_SHA256 = (
    "442823109b9bdaf9acf6a81813ece1a26b55666d9ebd58b97ba96730c820b668"
)


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def test_complete_stonewall_gallery_transcription_is_auditable() -> None:
    extract = _load_yaml(EXTRACT_PATH)

    gallery_audit = extract["gallery_audit"]
    assert gallery_audit["attachment_overlay_text"] == "8 remaining items"
    assert gallery_audit["unique_photo_count"] == 12
    assert "includes the thumbnail underneath" in gallery_audit["count_interpretation"]
    assert "1451333713702963" in gallery_audit["navigation_cycle_check"]
    assert "1450343267135341" in gallery_audit["navigation_cycle_check"]

    evidence = extract["evidence"]
    assert len(evidence) == len(EXPECTED_GALLERY_EVIDENCE)
    capture_ids: list[str] = []
    for item, (image, capture_suffix, photo_id, expected_sha256) in zip(
        evidence, EXPECTED_GALLERY_EVIDENCE, strict=True
    ):
        capture_id = item["capture_id"]
        capture_ids.append(capture_id)
        assert item["image"] == image
        assert capture_id.endswith(capture_suffix)
        manifest = json.loads((EVIDENCE_MANIFEST_DIR / f"{capture_id}.json").read_text())
        assert manifest["id"] == capture_id
        assert manifest["source_id"] == "washington-stonewall-democrats"
        assert manifest["availability"] == "captured"
        assert manifest["capture_method"] == "browser"
        assert manifest["browser_required"] is True
        assert manifest["media_type"] == "image/jpeg"
        assert manifest["redistribution"] == "restricted"
        assert manifest["canonical_url"] == (
            f"https://www.facebook.com/photo/?fbid={photo_id}&set=pcb.1450344363801898"
        )
        assert manifest["requested_url"] == manifest["canonical_url"]
        assert manifest["content_sha256"] == expected_sha256
        assert manifest["storage_reference"] == f"sha256/{expected_sha256[:2]}/{expected_sha256}"

        local_snapshot = PROJECT_ROOT / "data/snapshots" / manifest["storage_reference"]
        if local_snapshot.exists():
            assert hashlib.sha256(local_snapshot.read_bytes()).hexdigest() == expected_sha256

    assert len(capture_ids) == len(set(capture_ids)) == 12

    endorsed_race_count = 0
    candidate_endorsement_count = 0
    for section in extract["endorsements"].values():
        endorsed_race_count += len(section)
        for endorsement in section:
            candidates = endorsement.get("candidates")
            candidate_endorsement_count += len(candidates) if candidates else 1

    assert endorsed_race_count == 94
    assert candidate_endorsement_count == 96
    endorsements_bytes = json.dumps(
        extract["endorsements"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(endorsements_bytes).hexdigest() == EXPECTED_ENDORSEMENTS_SHA256


def test_stonewall_seattle_ballot_mappings_are_complete() -> None:
    ledger = _load_yaml(LEDGER_PATH)
    stonewall = next(
        source
        for source in ledger["sources"]
        if source["source_id"] == "washington-stonewall-democrats"
    )

    assert {decision["race_id"] for decision in stonewall["decisions"]} == (EXPECTED_SEATTLE_RACES)
    decisions = stonewall["decisions"]
    assert len(decisions) == 22
    assert sum(len(decision["candidate_ids"]) for decision in decisions) == 24
    assert sum(len(decision["candidate_ids"]) > 1 for decision in decisions) == 2
    assert all(decision.get("evidence_locator") for decision in decisions)
    decisions_bytes = json.dumps(
        decisions, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(decisions_bytes).hexdigest() == EXPECTED_SEATTLE_DECISIONS_SHA256
