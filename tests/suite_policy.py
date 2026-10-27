"""One semantic test-suite policy, shared by local selection and required CI."""

from collections.abc import Iterable, Mapping, Sequence
from typing import Literal, cast

Suite = Literal["unit", "contract", "integration", "e2e"]
SUITES: tuple[Suite, ...] = ("unit", "contract", "integration", "e2e")
Partition = Literal[
    "unit", "integration-comparisons", "integration-rendering", "integration-artifacts"
]
PARTITIONS: tuple[Partition, ...] = (
    "unit",
    "integration-comparisons",
    "integration-rendering",
    "integration-artifacts",
)
Policy = Mapping[str, Mapping[str, object]]
Node = tuple[str, str, str]


class UnitExternalIOError(BaseException):
    """An isolation breach must escape application-level exception recovery."""


def classify_test(path: str, function: str, policy: Policy) -> Suite:
    if path not in policy:
        raise ValueError(f"unclassified test module: {path}")
    module = policy[path]
    overrides = module.get("tests", {})
    if not isinstance(overrides, dict):
        raise ValueError(f"invalid test overrides: {path}")
    value = cast(Mapping[str, object], overrides).get(function, module.get("suite"))
    if value not in SUITES:
        raise ValueError(f"invalid test suite: {path}::{function}")
    return value


def partition_test(path: str, function: str, policy: Policy) -> Partition:
    if classify_test(path, function, policy) == "unit":
        return "unit"
    value = policy[path].get("partition")
    if value not in PARTITIONS[1:]:
        raise ValueError(f"missing required partition: {path}::{function}")
    return value


def group_nodes(
    nodes: Iterable[Node], policy: Policy, *, partitions: bool = False
) -> dict[str, list[str]]:
    names = PARTITIONS if partitions else SUITES
    groups: dict[str, list[str]] = {name: [] for name in names}
    seen: set[str] = set()
    for node_id, path, function in nodes:
        if node_id in seen:
            raise ValueError(f"duplicate test node: {node_id}")
        seen.add(node_id)
        name = (
            partition_test(path, function, policy)
            if partitions
            else classify_test(path, function, policy)
        )
        groups[name].append(node_id)
    return groups


def require_partition_coverage(
    declared: Sequence[str], groups: Mapping[str, Sequence[str]]
) -> None:
    if len(declared) != len(set(declared)) or set(declared) != set(groups):
        raise ValueError("required test partitions must each run exactly once")


def deny_external_unit_io(event: str, _arguments: tuple[object, ...]) -> None:
    if event in {
        "socket.__new__",
        "socket.connect",
        "socket.bind",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.gethostbyaddr",
        "socket.sendto",
        "subprocess.Popen",
        "os.system",
        "os.posix_spawn",
        "os.fork",
        "os.forkpty",
        "os.exec",
    }:
        raise UnitExternalIOError(f"unit tests cannot perform external IO: {event}")
