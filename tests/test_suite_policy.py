"""Test suite boundaries fail closed and preserve every collected obligation (#651)."""

import json
import socket
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from tests import conftest
from tests.suite_policy import (
    PARTITIONS,
    UnitExternalIOError,
    classify_test,
    deny_external_unit_io,
    group_nodes,
    partition_test,
    require_partition_coverage,
)

POLICY = {
    "tests/test_logic.py": {"suite": "unit", "tests": {"test_catalog": "contract"}},
    "tests/test_build.py": {
        "suite": "integration",
        "partition": "integration-rendering",
        "tests": {"test_browser": "e2e"},
    },
}


def test_suite_assignment_uses_explicit_semantic_exceptions() -> None:
    assert classify_test("tests/test_logic.py", "test_add", POLICY) == "unit"
    assert classify_test("tests/test_logic.py", "test_catalog", POLICY) == "contract"
    assert classify_test("tests/test_build.py", "test_archive", POLICY) == "integration"
    assert classify_test("tests/test_build.py", "test_browser", POLICY) == "e2e"


def test_unknown_module_cannot_silently_escape_required_suites() -> None:
    with pytest.raises(ValueError, match="unclassified test module"):
        classify_test("tests/test_new.py", "test_new", POLICY)


def test_each_parameter_case_retains_one_original_node_identity() -> None:
    nodes = [
        ("tests/test_logic.py::test_add[one]", "tests/test_logic.py", "test_add"),
        ("tests/test_logic.py::test_add[two]", "tests/test_logic.py", "test_add"),
        ("tests/test_logic.py::test_catalog", "tests/test_logic.py", "test_catalog"),
        ("tests/test_build.py::test_browser", "tests/test_build.py", "test_browser"),
    ]
    assert group_nodes(nodes, POLICY) == {
        "unit": ["tests/test_logic.py::test_add[one]", "tests/test_logic.py::test_add[two]"],
        "contract": ["tests/test_logic.py::test_catalog"],
        "integration": [],
        "e2e": ["tests/test_build.py::test_browser"],
    }
    with pytest.raises(ValueError, match="duplicate test node"):
        group_nodes([*nodes, nodes[0]], POLICY)


@pytest.mark.parametrize(
    "event",
    [
        "socket.connect",
        "socket.bind",
        "socket.getaddrinfo",
        "subprocess.Popen",
        "os.system",
        "os.posix_spawn",
        "os.fork",
    ],
)
def test_unit_external_boundary_is_rejected_before_execution(event: str) -> None:
    with pytest.raises(UnitExternalIOError, match="unit tests cannot perform external IO"):
        deny_external_unit_io(event, ())


def test_unit_guard_allows_local_fixture_reads_and_computation() -> None:
    deny_external_unit_io("open", ("fixture.json", "r", 0))
    deny_external_unit_io("compile", (b"1 + 1", "fixture.py"))


def test_unit_partition_contains_only_true_units_and_every_other_case_is_required() -> None:
    assert partition_test("tests/test_logic.py", "test_add", POLICY) == "unit"
    with pytest.raises(ValueError, match="missing required partition"):
        partition_test("tests/test_logic.py", "test_catalog", POLICY)
    assert partition_test("tests/test_build.py", "test_browser", POLICY) == "integration-rendering"


def test_partition_selection_cannot_hide_an_unassigned_case() -> None:
    nodes = [
        ("logic", "tests/test_logic.py", "test_add"),
        ("browser", "tests/test_build.py", "test_browser"),
    ]
    partitions = group_nodes(nodes, POLICY, partitions=True)
    assert partitions == {
        "unit": ["logic"],
        "integration-comparisons": [],
        "integration-rendering": ["browser"],
        "integration-artifacts": [],
    }


def test_real_unit_network_and_child_process_attempts_stop_before_side_effects(
    tmp_path: Path,
) -> None:
    with (
        pytest.raises(UnitExternalIOError, match="unit tests cannot perform external IO"),
        socket.socket(),
    ):
        pass
    sentinel = tmp_path / "child-ran"
    with pytest.raises(UnitExternalIOError, match="unit tests cannot perform external IO"):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran')",
                str(sentinel),
            ],
            check=True,
        )
    assert not sentinel.exists()


@pytest.mark.parametrize(
    "partitions",
    [
        [],
        ["unit"],
        ["unit", "integration-comparisons", "integration-rendering"],
        ["unit", "integration-comparisons", "integration-rendering", "integration-rendering"],
    ],
)
def test_a_missing_or_duplicate_required_partition_is_rejected(partitions: list[str]) -> None:
    groups = group_nodes([], POLICY, partitions=True)
    with pytest.raises(ValueError, match="required test partitions"):
        require_partition_coverage(partitions, groups)


def test_unit_io_rejection_cannot_be_swallowed_by_application_error_handling() -> None:
    with (
        pytest.raises(UnitExternalIOError, match="unit tests cannot perform external IO"),
        suppress(Exception),
    ):
        deny_external_unit_io("socket.connect", ())


@pytest.mark.parametrize("missing", PARTITIONS)
def test_collection_rejects_an_omitted_ci_partition_before_any_case_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """Omitting the partition containing the coverage test cannot hide that contract."""
    policy_path = tmp_path / "suites.json"
    policy_path.write_text(json.dumps({"tests/test_logic.py": {"suite": "unit"}}))
    monkeypatch.setattr(conftest, "POLICY_PATH", policy_path)
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        json.dumps(
            {
                "jobs": {
                    "tests": {
                        "strategy": {
                            "matrix": {"partition": [p for p in PARTITIONS if p != missing]}
                        }
                    }
                }
            }
        )
    )
    config = Mock(spec=pytest.Config)
    config.rootpath = tmp_path
    config.stash = pytest.Stash()
    config.getoption.return_value = "all"
    item = Mock(spec=pytest.Function)
    item.path = tmp_path / "tests/test_logic.py"
    item.nodeid = "tests/test_logic.py::test_logic"
    item.originalname = "test_logic"
    with pytest.raises(pytest.UsageError, match="required test partitions"):
        conftest.pytest_collection_modifyitems(
            cast(pytest.Config, config), [cast(pytest.Item, item)]
        )
