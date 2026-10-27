"""Validate the public archive without requiring a decryption secret in PR CI."""

import base64
from pathlib import Path

from election_guide.collection.discovery import (
    DiscoveryAudit,
    read_sgn_discovery_obligation,
    read_ufcw_discovery_obligation,
)
from election_guide.collection.refresh import read_extraction_snapshot, read_refresh_event
from election_guide.collection.tru_discovery import (
    read_tru_discovery_obligation,
    validate_tru_audit,
)
from election_guide.collection.vault import SealedCapture
from election_guide.collection.verification import (
    Activation,
    BaselineApproval,
    RunAudit,
    VerificationPolicy,
    read_checks,
    read_panel,
)
from election_guide.evidence.models import CapturedManifest, ObservedManifest, evidence_fingerprint
from election_guide.evidence.storage import read_capture_manifest
from election_guide.serialization import read_json


def validate_state(policy: VerificationPolicy, root: Path) -> int:
    if root.is_symlink() or any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("verification archive must not contain symbolic links")
    if any(path.is_file() and path.suffix != ".json" for path in root.rglob("*")):
        raise ValueError(
            "verification archive accepts JSON records only; raw artifacts are forbidden"
        )
    count = 0
    known_elections = {election.election_id for election in policy.elections}
    if root.exists() and any(
        path.name not in known_elections | {"runs"} or not path.is_dir() for path in root.iterdir()
    ):
        raise ValueError("verification archive contains an undeclared election")
    for election in policy.elections:
        directory = root / election.election_id
        expected = {
            "vault",
            "manifests",
            "extractions",
            "refreshes",
            "checks",
            "approvals",
            "source-reviews",
            "discovery",
            "discovery-obligations",
            "activation.json",
        }
        if directory.exists() and any(path.name not in expected for path in directory.iterdir()):
            raise ValueError("verification archive contains an unexpected record location")
        if (directory / "activation.json").exists():
            Activation.model_validate(read_json(directory / "activation.json"))
        registry, _ = read_panel(election)
        sources = {source.id for source in registry.sources}
        from election_guide.collection.verification_access import (
            read_qualifications,
            validate_access_disposition,
        )

        qualifications = read_qualifications(directory)
        if any(item.source_id not in sources for item in qualifications.values()):
            raise ValueError("complete-review qualification belongs to an unknown source")
        count += len(qualifications)
        envelopes: dict[str, SealedCapture] = {}
        for path in directory.glob("vault/sha256/*/*.json"):
            envelope = SealedCapture.model_validate(read_json(path))
            if (
                path.stem != envelope.content_sha256
                or path.parent.name != envelope.content_sha256[:2]
            ):
                raise ValueError("sealed capture path contradicts its content address")
            encrypted = base64.b64decode(envelope.encrypted, validate=True)
            if len(encrypted) != envelope.byte_length + 28:
                raise ValueError("sealed capture size contradicts its envelope")
            envelopes[envelope.content_sha256] = envelope
            count += 1
        manifests: dict[str, CapturedManifest | ObservedManifest] = {}
        for path in directory.glob("manifests/*.json"):
            manifest = read_capture_manifest(path)
            if (
                not isinstance(manifest, (CapturedManifest, ObservedManifest))
                or manifest.redistribution != "restricted"
            ):
                raise ValueError(
                    "verification evidence requires restricted capture or observation metadata"
                )
            if manifest.source_id not in sources:
                raise ValueError("verification observation belongs to an unknown source")
            if isinstance(manifest, CapturedManifest) and manifest.content_sha256 not in envelopes:
                raise ValueError(
                    "verification capture lacks its source or committed encrypted bytes"
                )
            if isinstance(manifest, CapturedManifest) and (
                envelopes[manifest.content_sha256].byte_length != manifest.byte_length
            ):
                raise ValueError("verification capture and envelope lengths differ")
            manifests[manifest.id] = manifest
            count += 1
        snapshots = {
            snapshot.id: snapshot
            for path in directory.glob("extractions/*.json")
            if (snapshot := read_extraction_snapshot(path))
        }
        for snapshot in snapshots.values():
            manifest = manifests.get(snapshot.capture_id)
            if (
                not manifest
                or manifest.source_id != snapshot.source_id
                or manifest.content_sha256 != snapshot.content_sha256
            ):
                raise ValueError("comparison baseline lacks matching durable evidence")
            count += 1
        events = {
            event.id: event
            for path in directory.glob("refreshes/*.json")
            if (event := read_refresh_event(path))
        }
        for event in events.values():
            if event.source_id not in sources:
                raise ValueError("refresh belongs to an unknown source")
            if event.capture_id and event.capture_id not in manifests:
                raise ValueError("refresh lacks its durable capture")
            observation = manifests.get(event.capture_id) if event.capture_id else None
            if observation and observation.source_id != event.source_id:
                raise ValueError("refresh observation belongs to another source")
            if (
                isinstance(observation, ObservedManifest)
                and observation.retrieved_at != event.checked_at
            ):
                raise ValueError("refresh observation time contradicts its check")
            for identifier in (event.snapshot_id, event.previous_snapshot_id):
                if identifier and (
                    identifier not in snapshots
                    or snapshots[identifier].source_id != event.source_id
                ):
                    raise ValueError("refresh lacks its source comparison baseline")
            if event.status != "failed":
                snapshot = snapshots.get(event.snapshot_id) if event.snapshot_id else None
                if (
                    not observation
                    or not snapshot
                    or (observation.content_sha256 != snapshot.content_sha256)
                ):
                    raise ValueError("successful refresh lacks matching observation and facts")
            count += 1
        checks = read_checks(directory)
        for check in checks:
            if check.source_id not in sources:
                raise ValueError("scheduled observation belongs to an unknown source")
            if check.event_id:
                event = events.get(check.event_id)
                if not event or (event.source_id, event.checked_at, event.status) != (
                    check.source_id,
                    check.checked_at,
                    check.status,
                ):
                    raise ValueError("scheduled observation contradicts its refresh event")
                if check.access_disposition:
                    validate_access_disposition(directory, check, event)
            count += 1
        for path in directory.glob("approvals/*.json"):
            approval = BaselineApproval.model_validate(read_json(path))
            snapshot = snapshots.get(approval.snapshot_id)
            if (
                not snapshot
                or path.stem != snapshot.id
                or approval.reviewed_at < snapshot.extracted_at
            ):
                raise ValueError("baseline approval does not identify a current captured snapshot")
            if not any(
                check.mode == "live"
                and check.event_id
                and events[check.event_id].snapshot_id == snapshot.id
                for check in checks
            ):
                raise ValueError("fixture baseline cannot receive live approval")
            count += 1
        for path in directory.glob("discovery-obligations/*.json"):
            source_id = read_json(path).get("source_id")
            if source_id == "transit-riders-union":
                obligation = read_tru_discovery_obligation(path)
            elif source_id == "ufcw-3000":
                obligation = read_ufcw_discovery_obligation(path)
            elif source_id == "seattle-gay-news":
                obligation = read_sgn_discovery_obligation(path)
            else:
                raise ValueError("discovery obligation belongs to an unsupported source")
            if obligation.source_id not in sources or obligation.capture_id not in manifests:
                raise ValueError("discovery obligation lacks durable source evidence")
            count += 1
        for path in directory.glob("discovery/*.json"):
            record = read_json(path)
            audit = DiscoveryAudit.model_validate(record)
            if (
                path.stem != evidence_fingerprint(record)
                or record["source_id"] not in sources
                or any(identifier not in manifests for identifier in record["captures"])
            ):
                raise ValueError("discovery record lacks its immutable original inputs")
            if audit.source_id == "transit-riders-union":
                validate_tru_audit(audit, manifests)
            else:
                inputs = [manifests[identifier] for identifier in audit.captures]
                if len(set(audit.captures)) != len(audit.captures) or any(
                    item.source_id != audit.source_id
                    or item.retrieved_at != audit.checked_at
                    or item.capture_method != "static_html"
                    for item in inputs
                ):
                    raise ValueError("discovery input contradicts its source, time or method")
                if not set(audit.articles) <= {item.requested_url for item in inputs}:
                    raise ValueError("discovery lacks its required article observations")
                if not any(
                    item.source_id == audit.source_id
                    and item.retrieved_at <= audit.checked_at
                    and item.capture_method == "manual_upload"
                    and item.http_status is None
                    and item.content_sha256 == audit.comparison_sha256
                    for item in manifests.values()
                ):
                    raise ValueError("discovery lacks its derived comparison provenance")
            count += 1
    for path in root.glob("runs/*.json"):
        RunAudit.model_validate(read_json(path))
        if path.stem != evidence_fingerprint(read_json(path)):
            raise ValueError("run audit identity contradicts its content")
        count += 1
    return count
