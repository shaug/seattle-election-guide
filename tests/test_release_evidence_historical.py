"""Execute original source/workflow code through an explicitly offline fixture API.

This is a compatibility proof, never a historical CI publication or new production
acceptance. The saved authenticated General128 operations keep their identities.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.test_release_evidence_v2 import CHECKPOINTS, FIXTURE, checkpoint, compressed_comments

ROOT = Path(__file__).parents[1]

# No forwarding to a real gh executable exists. Anything outside these fixture
# reads and append-only comment POSTs is an error, including Actions artifacts.
GH_FIXTURE = r"""
import json, os, pathlib, sys
from urllib.parse import parse_qs, urlsplit
args = sys.argv[1:]
assert args[0] == 'api', args
endpoint = urlsplit('https://api.github.com/' + args[1])
path = endpoint.path
root = pathlib.Path(os.environ['FIXTURE_STORE'])
with (root / 'calls.jsonl').open('a') as sink:
    sink.write(json.dumps(args) + '\n')
store = json.loads((root / 'store.json').read_bytes())
prefix = '/repos/shaug/seattle-election-guide/'
assert path.startswith(prefix), path
path = path.removeprefix(prefix)
if path == 'issues/696/comments':
    if '--method' in args:
        assert args[args.index('--method') + 1] == 'POST'
        payload = json.loads(pathlib.Path(args[args.index('--input') + 1]).read_bytes())
        row = dict(store['comments'][0], id=store['next_id'], body=payload['body'],
                   fixture_transport=True)
        store['next_id'] += 1
        store['comments'].append(row)
        (root / 'store.json').write_text(json.dumps(store))
        print(json.dumps(row))
    else:
        assert '--paginate' in args and '--slurp' in args
        print(json.dumps([store['comments']]))
elif path == 'deployments':
    assert '--method' not in args and '--paginate' in args and '--slurp' in args
    rows = store['deployments']
    query = parse_qs(endpoint.query)
    if 'sha' in query:
        rows = [row for row in rows if row['sha'] == query['sha'][0]]
    print(json.dumps([rows]))
elif path == 'deployments/' + str(store['deployments'][0]['id']) + '/statuses':
    assert '--method' not in args and '--paginate' in args and '--slurp' in args
    print(json.dumps([store['statuses']]))
else:
    raise AssertionError('forbidden fixture endpoint: ' + path)
"""

# Observe loaded project files without changing the historical package. The
# parent compares every file to the original immutable Git blob, even on error.
IMPORT_OBSERVER = r"""
import atexit, hashlib, json, os, pathlib, sys
@atexit.register
def record_imports():
    rows = {}
    for name, module in tuple(sys.modules.items()):
        if name == 'election_guide' or name.startswith('election_guide.'):
            value = getattr(module, '__file__', None)
            if value:
                path = pathlib.Path(value).resolve()
                rows[name] = {'path': str(path),
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    pathlib.Path(os.environ['PROOF_IMPORTS']).write_text(json.dumps(rows))
"""

READ_CONSUMERS = r"""
import hashlib, json, pathlib
from election_guide.release.evidence import load_verified_receipts, read_evidence_reports
from election_guide.release.workflow import require_no_unverified_uploads
require_no_unverified_uploads('shaug/seattle-election-guide')
records = load_verified_receipts(repository='shaug/seattle-election-guide', issue_number=696,
    release_version='2026-general.128', source_sha='4f9d09ac39ba09166123500bf3107c1b665ea6dc')
rows = [{'receipt': r.model_dump(mode='json'), 'reports': {
    name: hashlib.sha256(data).hexdigest()
    for name, data in read_evidence_reports(r, issue_number=696).items()}} for r in records]
pathlib.Path('dist/consumers.json').write_text(json.dumps(rows))
"""


def _git(*args: str, cwd: Path = ROOT) -> bytes:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True).stdout


def _attest(imports: Path, checkout: Path, source: str) -> dict[str, Any]:
    rows: dict[str, Any] = json.loads(imports.read_bytes())
    assert "election_guide.release.evidence" in rows
    assert "election_guide.release.evidence_v2" not in rows
    for row in rows.values():
        relative = Path(row["path"]).relative_to(checkout)
        expected = _git("show", f"{source}:{relative.as_posix()}")
        assert row["sha256"] == hashlib.sha256(expected).hexdigest(), relative
    return rows


@pytest.mark.parametrize("damage", ["current-origin", "wrong-blob"])
def test_historical_proof_rejects_current_import_origins(tmp_path: Path, damage: str) -> None:
    source = checkpoint("publication")[0].producer.source_sha
    checkout = tmp_path / "original-source"
    relative = Path("src/election_guide/release/evidence.py")
    imports = tmp_path / "imports.json"
    imports.write_text(
        json.dumps(
            {
                "election_guide.release.evidence": {
                    "path": str((ROOT if damage == "current-origin" else checkout) / relative),
                    "sha256": "0" * 64,
                }
            }
        )
    )
    with pytest.raises((ValueError, AssertionError)):
        _attest(imports, checkout, source)


def test_original_workflow_and_consumers_after_lossless_preparation(tmp_path: Path) -> None:
    source = checkpoint("publication")[0].producer.source_sha
    old = tmp_path / "original-source"
    _git("clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(old))
    _git("checkout", "--quiet", "--detach", source, cwd=old)
    assert _git("rev-parse", "HEAD", cwd=old).decode().strip() == source
    transport = tmp_path / "fixture-bin"
    transport.mkdir()
    gh = transport / "gh"
    gh.write_text(f"#!{sys.executable}\n" + GH_FIXTURE)
    gh.chmod(0o755)
    (transport / "sitecustomize.py").write_text(IMPORT_OBSERVER)
    store = {
        "fixture_transport": True,
        "comments": compressed_comments(),
        "deployments": [json.loads((FIXTURE / "deployment.original.json").read_bytes())],
        "statuses": json.loads((FIXTURE / "statuses.original.json").read_bytes())[0],
        "next_id": 2000000,
    }
    store_path = tmp_path / "store.json"
    store_path.write_text(json.dumps(store))
    head = _git("rev-parse", "HEAD").decode().strip()
    env = os.environ | {
        "PATH": f"{transport}:{os.environ['PATH']}",
        "FIXTURE_STORE": str(tmp_path),
        "GH_TOKEN": "",
        "GITHUB_TOKEN": "",
        "UV_NO_SYNC": "true",
        "UV_FROZEN": "true",
        "UV_OFFLINE": "true",
        "UV_PROJECT_ENVIRONMENT": sys.prefix,
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "shaug/seattle-election-guide",
        "GITHUB_SHA": head,
        "GITHUB_RUN_ID": "9002000",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_STEP_SUMMARY": str(tmp_path / "fixture-summary.md"),
        "GITHUB_OUTPUT": str(tmp_path / "fixture-outputs"),
        "ISSUE": "696",
        "VERSION": "2026-general.128",
        "SOURCE_SHA": source,
        "RUN_ID": "43755212223",
        "RUN_ATTEMPT": "1",
    }
    # These environment variables only select the existing locked interpreter.
    # Project imports are separately attested against original Git objects.
    old_env = env | {"PYTHONPATH": os.pathsep.join([str(old / "src"), str(transport)])}
    workflow_bytes = (old / ".github/workflows/verify-release.yml").read_bytes()
    document = yaml.safe_load(workflow_bytes)
    recover = next(
        step["run"]
        for step in document["jobs"]["verify"]["steps"]
        if step.get("name") == "Recover immutable upload evidence"
    )
    assert recover.startswith("uv run election-guide release automation recover-upload ")
    latest = (
        "uv run election-guide release automation latest-production "
        '--repository "$GITHUB_REPOSITORY" --output dist/latest.json'
    )
    commands: list[dict[str, Any]] = []

    def run(name: str, command: str, expected: int) -> None:
        imports = tmp_path / f"{name}-imports.json"
        actual = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", command],
            cwd=old,
            env=old_env | {"PROOF_IMPORTS": str(imports)},
            capture_output=True,
            text=True,
            check=False,
        )
        assert actual.returncode == expected, actual.stdout + actual.stderr
        origins = _attest(imports, old, source)
        commands.append(
            {
                "name": name,
                "command": command,
                "exit_code": actual.returncode,
                "stdout": actual.stdout,
                "stderr": actual.stderr,
                "imports": origins,
            }
        )

    # An old reader must not mistake ignored compressed evidence for acceptance.
    run("pure-v2-recover", recover, 1)
    run("pure-v2-latest", latest, 1)
    prepared = subprocess.run(
        [
            "uv",
            "run",
            "election-guide",
            "release",
            "automation",
            "prepare-historical-evidence",
            "--repository",
            env["GITHUB_REPOSITORY"],
            "--issue",
            "696",
            "--output-dir",
            str(tmp_path / "prepared"),
        ],
        cwd=ROOT,
        env=env | {"PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    prepared_report = json.loads((tmp_path / "prepared/compatibility-report.json").read_bytes())
    assert prepared_report["complete"] is True
    assert len(prepared_report["observed_new_comment_ids"]) == 15
    after = json.loads(store_path.read_bytes())
    assert after["comments"][:3] == store["comments"]
    run("prepared-recover", recover, 0)
    run("prepared-latest", latest, 0)
    import shlex

    run("prepared-consumers", f"{shlex.quote(sys.executable)} -c {shlex.quote(READ_CONSUMERS)}", 0)
    expected_upload = checkpoint("upload")[0].upload
    assert expected_upload is not None
    assert json.loads((old / "dist/upload.json").read_bytes()) == expected_upload.model_dump(
        mode="json"
    )
    assert json.loads((old / "dist/latest.json").read_bytes()) == (
        checkpoint("verified")[0].model_dump(mode="json")
    )
    expected = [
        {
            "receipt": receipt.model_dump(mode="json"),
            "reports": {name: hashlib.sha256(data).hexdigest() for name, data in reports.items()},
        }
        for receipt, reports in (checkpoint(name) for name in CHECKPOINTS)
    ]
    assert json.loads((old / "dist/consumers.json").read_bytes()) == expected
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert not any("/actions/" in call[1] for call in calls)
    assert all("/comments" in call[1] for call in calls if "--method" in call)
    proof = {
        "kind": "unmodified-historical-reader-offline-compatibility-proof",
        "fixture_transport": True,
        "new_production_acceptance": False,
        "historical_source": source,
        "reader_checkout_head": head,
        "reader_tracked_clean": not _git("status", "--porcelain", "--untracked-files=no").strip(),
        "workflow_blob_sha256": {
            name: hashlib.sha256((old / ".github/workflows" / name).read_bytes()).hexdigest()
            for name in ["ci.yml", "verify-release.yml"]
        },
        "preparation": prepared_report,
        "commands": commands,
        "old_receipts_and_report_hashes": expected,
        "fixture_calls": calls,
    }
    if destination := os.environ.get("HISTORICAL_PROOF_OUTPUT"):
        output = Path(destination)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(proof, sort_keys=True, indent=2) + "\n")
