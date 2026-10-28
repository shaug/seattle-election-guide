"""Select semantic suites without changing the default complete pytest gate."""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from election_guide.serialization import read_json, read_yaml
from tests.suite_policy import (
    PARTITIONS,
    SUITES,
    Node,
    Policy,
    classify_test,
    deny_external_unit_io,
    group_nodes,
    partition_test,
    require_partition_coverage,
)

POLICY_PATH = Path(__file__).with_name("suites.json")
COLLECTED_NODES = pytest.StashKey[tuple[Node, ...]]()
UNIT_GUARD_ACTIVE = pytest.StashKey[bool]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--test-suite", choices=("all", *SUITES), default="all")
    parser.addoption("--test-partition", choices=("all", *PARTITIONS), default="all")


def pytest_configure(config: pytest.Config) -> None:
    for suite in SUITES:
        config.addinivalue_line("markers", f"{suite}: semantic {suite} test obligation")
    config.stash[UNIT_GUARD_ACTIVE] = (
        config.getoption("--test-suite") == "unit" or config.getoption("--test-partition") == "unit"
    )

    def audit(event: str, arguments: tuple[object, ...]) -> None:
        if config.stash[UNIT_GUARD_ACTIVE]:
            deny_external_unit_io(event, arguments)

    # The unit-only process is guarded before collection; the full gate guards
    # each unit's complete setup/call/teardown without blocking integration IO.
    sys.addaudithook(audit)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item) -> Iterator[None]:
    previous = item.config.stash[UNIT_GUARD_ACTIVE]
    item.config.stash[UNIT_GUARD_ACTIVE] = previous or item.get_closest_marker("unit") is not None
    try:
        yield
    finally:
        item.config.stash[UNIT_GUARD_ACTIVE] = previous


def pytest_unconfigure(config: pytest.Config) -> None:
    config.stash[UNIT_GUARD_ACTIVE] = False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    policy = cast(Policy, read_json(POLICY_PATH))
    nodes = [
        (
            item.nodeid,
            item.path.relative_to(config.rootpath).as_posix(),
            str(getattr(item, "originalname", item.name)).split("[", 1)[0],
        )
        for item in items
    ]
    try:
        group_nodes(nodes, policy)
        partitions = group_nodes(nodes, policy, partitions=True)
        workflow = read_yaml(config.rootpath / ".github/workflows/ci.yml")
        require_partition_coverage(
            workflow["jobs"]["tests"]["strategy"]["matrix"]["partition"], partitions
        )
        assigned = {
            node_id: classify_test(path, function, policy) for node_id, path, function in nodes
        }
    except ValueError as error:
        raise pytest.UsageError(str(error)) from error
    selected = str(config.getoption("--test-suite"))
    partition = str(config.getoption("--test-partition"))
    if selected != "all" and partition != "all":
        raise pytest.UsageError("select a semantic suite or an execution partition, not both")
    config.stash[COLLECTED_NODES] = tuple(nodes)
    included: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item, (_, path, function) in zip(items, nodes, strict=True):
        suite = assigned[item.nodeid]
        item.add_marker(suite)
        selected_partition = partition_test(path, function, policy)
        keep = (selected == "all" or suite == selected) and (
            partition == "all" or selected_partition == partition
        )
        (included if keep else deselected).append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = included


@pytest.fixture
def collected_nodes(request: pytest.FixtureRequest) -> tuple[Node, ...]:
    return request.config.stash[COLLECTED_NODES]
