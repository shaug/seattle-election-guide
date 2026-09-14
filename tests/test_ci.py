"""CI partitioning and required-status contracts (issue 428)."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parents[1]
INTEGRATION_PARTITIONS = (
    "integration-comparisons",
    "integration-rendering",
    "integration-artifacts",
)
PARALLEL_JOBS = ("python", "client", "contracts", "tests", "publication")


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


def test_local_test_suites_cover_each_integration_module_once() -> None:
    """A file omitted from both unit and integration targets would silently escape CI."""
    aggregate = _pytest_arguments("test-integration")
    partitioned = [
        path
        for partition in INTEGRATION_PARTITIONS
        for path in _pytest_arguments(f"test-{partition}")
    ]

    assert partitioned == aggregate
    assert len(partitioned) == len(set(partitioned))
    assert all((PROJECT_ROOT / path).is_file() for path in aggregate)
    assert _pytest_arguments("test-unit") == [f"--ignore={path}" for path in aggregate]


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
        for unsuccessful_result in ("failure", "cancelled"):
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

    assert jobs["deploy"]["needs"] == "check"
