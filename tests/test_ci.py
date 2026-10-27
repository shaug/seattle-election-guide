"""CI partitioning and required-status contracts (issue 428)."""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.serialization import read_json
from tests.suite_policy import Node, Policy, group_nodes, require_partition_coverage

PROJECT_ROOT = Path(__file__).parents[1]
INTEGRATION_PARTITIONS = (
    "integration-comparisons",
    "integration-rendering",
    "integration-artifacts",
)
PARALLEL_JOBS = ("python", "client", "contracts", "tests", "publication")
SHARED_CONTRACT_COMMAND = "make check-election-contracts"


def test_updates_gate_is_required_in_publication_and_serialized_deployment() -> None:
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    jobs = workflow["jobs"]
    for job_id in ("publication", "deploy"):
        steps = jobs[job_id]["steps"]
        gate = next(step for step in steps if step.get("run") == "make check-updates")
        assert "if" not in gate
        assert gate["env"]["GH_TOKEN"] == "${{ github.token }}"
        after_gate = steps[steps.index(gate) + 1 :]
        assert any(
            step.get("if") == "always()" and "upload-artifact@" in step.get("uses", "")
            for step in after_gate
        )
    deploy_steps = jobs["deploy"]["steps"]
    deploy = next(step for step in deploy_steps if step.get("name") == "Deploy production site")
    assert deploy_steps.index(
        next(s for s in deploy_steps if s.get("run") == "make check-updates")
    ) < deploy_steps.index(deploy)
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    assert jobs["deploy"]["permissions"]["actions"] == "read"
    assert workflow["permissions"]["actions"] == "read"
    assert workflow["permissions"]["deployments"] == "read"
    assert "publication" in jobs["check"]["needs"]
    command = _make_dry_run("check-updates")
    assert command.returncode == 0
    assert "hosting check-updates dist/cloudflare-site" in command.stdout


def _assert_contracts_lane_uses_shared_target(workflow_text: str) -> None:
    """Reject a contracts lane that reconstructs the election list itself."""
    workflow = yaml.load(workflow_text, Loader=yaml.BaseLoader)
    contract_steps = workflow["jobs"]["contracts"]["steps"]
    assert SHARED_CONTRACT_COMMAND in [step.get("run") for step in contract_steps]


def _make_dry_run(target: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "--no-print-directory", "-n", target],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _pytest_arguments(make_target: str) -> list[str]:
    """Ask Make for the pytest invocation an operator or CI would receive."""
    result = subprocess.run(
        ["make", "--no-print-directory", "-n", make_target],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    command = next(line for line in result.stdout.splitlines() if line.startswith("uv run pytest"))
    return shlex.split(command)[3:]


def test_local_test_suites_cover_each_integration_module_once(
    collected_nodes: tuple[Node, ...],
) -> None:
    """A file omitted from both unit and integration targets would silently escape CI."""
    policy: Policy = read_json(PROJECT_ROOT / "tests/suites.json")
    groups = group_nodes(collected_nodes, policy, partitions=True)
    assert set(groups) == {"unit", *INTEGRATION_PARTITIONS}
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader
    )
    require_partition_coverage(workflow["jobs"]["tests"]["strategy"]["matrix"]["partition"], groups)
    partitioned = [node for nodes in groups.values() for node in nodes]
    assert sorted(partitioned) == sorted(node[0] for node in collected_nodes)
    assert len(partitioned) == len(set(partitioned))
    assert all((PROJECT_ROOT / path).is_file() for _, path, _ in collected_nodes)
    for partition in ("unit", *INTEGRATION_PARTITIONS):
        assert _pytest_arguments(f"test-{partition}") == ["--test-partition", partition]
    assert _pytest_arguments("test") == []
    assert _pytest_arguments("test-integration") == ["--test-suite", "integration"]


def test_ci_runs_independent_lanes_in_parallel_behind_one_required_check() -> None:
    """Dropping a lane from the aggregator would let branch protection miss its failure."""
    workflow = yaml.load(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    jobs = workflow["jobs"]

    for job_id in PARALLEL_JOBS:
        assert "needs" not in jobs[job_id], job_id

    tests = jobs["tests"]
    assert tests["strategy"]["fail-fast"] == "false"
    assert tests["strategy"]["matrix"]["partition"] == [
        "unit",
        *INTEGRATION_PARTITIONS,
    ]
    test_step = next(step for step in tests["steps"] if step.get("name") == "Run partition")
    assert test_step["run"] == "make test-${{ matrix.partition }}"

    check = jobs["check"]
    assert check["name"] == "check"
    assert check["if"] == "${{ always() }}"
    assert check["needs"] == list(PARALLEL_JOBS)

    gate_step = next(
        step for step in check["steps"] if step.get("name") == "Require every CI lane to pass"
    )
    result_environment = {job_id: f"${{{{ needs.{job_id}.result }}}}" for job_id in PARALLEL_JOBS}
    assert gate_step["env"] == {
        f"{job_id.upper()}_RESULT": expression for job_id, expression in result_environment.items()
    }

    success_environment = {environment_name: "success" for environment_name in gate_step["env"]}
    assert (
        subprocess.run(
            ["bash", "-euo", "pipefail", "-c", gate_step["run"]],
            env=success_environment,
            check=False,
        ).returncode
        == 0
    )
    for environment_name in success_environment:
        for unsuccessful_result in ("failure", "cancelled", "skipped", ""):
            environment = success_environment | {
                environment_name: unsuccessful_result,
            }
            assert (
                subprocess.run(
                    ["bash", "-euo", "pipefail", "-c", gate_step["run"]],
                    env=environment,
                    check=False,
                ).returncode
                != 0
            )

    assert set(jobs["deploy"]["needs"]) == {"check", "publication-evidence", "publish"}


def test_ci_contracts_lane_uses_the_shared_election_contract_target() -> None:
    """CI must discover the election set from the same target contributors run."""
    _assert_contracts_lane_uses_shared_target(
        (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )


def test_workflow_discovery_rejects_a_contracts_lane_that_bypasses_the_shared_target() -> None:
    """A future inline election list must fail the workflow-discovery contract."""
    workflow_text = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    bypassing_fixture = workflow_text.replace(
        f"run: {SHARED_CONTRACT_COMMAND}",
        "run: uv run election-guide inventory validate "
        "data/normalized/wa-2026-primary-inventory.json",
    )

    with pytest.raises(AssertionError):
        _assert_contracts_lane_uses_shared_target(bypassing_fixture)


def test_shared_election_contract_target_owns_both_committed_elections() -> None:
    """Adding an election in only local or CI checks would leave the other path blind."""
    result = _make_dry_run("check-election-contracts")

    assert result.returncode == 0, result.stderr
    for expected in (
        "inventory validate data/normalized/wa-2026-primary-inventory.json",
        "inventory validate data/normalized/wa-2026-general-inventory.json",
        "sources validate config/sources/default.yaml",
        "sources validate config/sources/wa-2026-general.yaml "
        "--inventory-path data/normalized/wa-2026-general-inventory.json",
        "release verify data/releases/wa-2026-primary/source-decisions.yaml",
        "release verify data/releases/wa-2026-general/source-decisions.yaml",
    ):
        assert expected in result.stdout

    assert SHARED_CONTRACT_COMMAND in _make_dry_run("check").stdout


def test_default_release_targets_build_the_general_without_primary_inputs() -> None:
    """The supported defaults must cut over atomically to the general release."""
    verify = _make_dry_run("release-verify")
    general_verify = _make_dry_run("release-verify-general")
    reproduce = _make_dry_run("check-release-reproducible")
    general_reproduce = _make_dry_run("check-release-reproducible-general")

    assert verify.returncode == 0, verify.stderr
    assert general_verify.returncode == 0, general_verify.stderr
    assert reproduce.returncode == 0, reproduce.stderr
    assert general_reproduce.returncode == 0, general_reproduce.stderr
    for expected in (
        "data/releases/wa-2026-general/source-decisions.yaml",
        "--inventory-path data/normalized/wa-2026-general-inventory.json",
        "--registry-path config/sources/wa-2026-general.yaml",
        "--dataset-path data/normalized/wa-2026-general-canonical-dataset.json",
        "--snapshot-root data/releases/wa-2026-general/snapshots",
        "--manifest-dir data/releases/wa-2026-general/manifests",
    ):
        assert expected in verify.stdout
        assert expected in general_verify.stdout

    command = "release automation build --source-sha"
    assert command in reproduce.stdout
    assert command in general_reproduce.stdout
    assert '"$(git rev-parse HEAD)" --output-dir dist' in reproduce.stdout
    result = CliRunner().invoke(app, ["release", "automation", "resolve"])
    assert result.exit_code == 0, result.output
    resolved = json.loads(result.stdout)
    assert resolved["current"]["election_id"] == "wa-2026-general"
    assert resolved["inputs"]["ledger"].endswith(
        "data/releases/wa-2026-general/source-decisions.yaml"
    )
    assert resolved["inputs"]["dataset"].endswith(
        "data/normalized/wa-2026-general-canonical-dataset.json"
    )
    assert (
        resolved["archive_name"]
        == f"seattle-election-guide-{resolved['current']['release_version']}.zip"
    )
    stage = _make_dry_run("hosting-stage")
    assert "release automation stage --bundle-dir dist/reproducibility-a/bundle" in stage.stdout
    assert '--source-sha "$(git rev-parse HEAD)"' in stage.stdout
    assert "wa-2026-primary" not in verify.stdout
    assert "wa-2026-primary" not in reproduce.stdout


def test_primary_release_verification_remains_an_explicit_repository_contract() -> None:
    """Cutting over the defaults must not silently drop the historical input gate."""
    verify = _make_dry_run("release-verify-primary")
    contracts = _make_dry_run("check-election-contracts")

    assert verify.returncode == 0, verify.stderr
    assert "data/releases/wa-2026-primary/source-decisions.yaml" in verify.stdout
    assert "wa-2026-general" not in verify.stdout
    assert "release verify data/releases/wa-2026-primary/source-decisions.yaml" in contracts.stdout
    assert "release verify data/releases/wa-2026-general/source-decisions.yaml" in contracts.stdout


def test_local_production_upload_route_is_retired() -> None:
    deploy = _make_dry_run("hosting-deploy")
    assert deploy.returncode == 0, deploy.stderr
    assert "verify-release.yml" in deploy.stdout
    assert "exit 1" in deploy.stdout
    assert "pages:deploy" not in deploy.stdout
