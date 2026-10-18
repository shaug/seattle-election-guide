"""Behavior tests for the shared `gh` CLI plumbing (issue #387).

Direct coverage for `parse_issue_list`, independent of its callers
(`calendar.github_tracker.issue_records`,
`sources.link_rot_alert.LinkRotAlertTracker.find_open_alert`), each of which
keeps its own per-call-site tests for the field extraction layered on top.
"""

from __future__ import annotations

import json

import pytest

from election_guide import github_cli
from election_guide.github_cli import parse_issue_list


def test_a_valid_payload_is_returned_as_raw_records() -> None:
    payload = json.dumps([{"number": 5, "body": "details"}, {"number": 6, "title": "other"}])

    assert parse_issue_list(payload) == [
        {"number": 5, "body": "details"},
        {"number": 6, "title": "other"},
    ]


def test_an_empty_listing_is_an_empty_list() -> None:
    assert parse_issue_list("[]") == []


def test_a_non_array_payload_is_rejected() -> None:
    with pytest.raises(ValueError, match="not an array"):
        parse_issue_list(json.dumps({"number": 5}))


def test_an_array_containing_a_non_object_entry_is_rejected() -> None:
    with pytest.raises(ValueError, match="not an object"):
        parse_issue_list(json.dumps([{"number": 5}, "not an issue"]))


PAGINATED_CASES: list[tuple[list[list[dict[str, int]]], list[dict[str, int]]]] = [
    ([[]], []),
    ([[], []], []),
    ([[{"id": 1}], [], [{"id": 2}, {"id": 3}]], [{"id": 1}, {"id": 2}, {"id": 3}]),
]


@pytest.mark.parametrize("key", [None, "items"])
@pytest.mark.parametrize(("pages", "expected"), PAGINATED_CASES)
def test_paginated_objects_accept_complete_pages(
    key: str | None, pages: list[list[dict[str, int]]], expected: list[dict[str, int]]
) -> None:
    payload = json.dumps(pages if key is None else [{key: page} for page in pages])
    assert github_cli.parse_paginated_objects(payload, key=key, context="test listing") == expected


@pytest.mark.parametrize("key", [None, "items"])
@pytest.mark.parametrize("payload", ["[]", "{}", "null", '"not pages"'])
def test_paginated_objects_require_nonempty_outer_array(key: str | None, payload: str) -> None:
    with pytest.raises(ValueError, match="test listing"):
        github_cli.parse_paginated_objects(payload, key=key, context="test listing")


@pytest.mark.parametrize("key", [None, "items"])
@pytest.mark.parametrize("bad_page", [None, {}, "not a page", [{"id": 2}, None]])
def test_paginated_objects_reject_malformed_later_pages(key: str | None, bad_page: object) -> None:
    pages = [[{"id": 1}], bad_page]
    payload = json.dumps(pages if key is None else [{key: page} for page in pages])
    with pytest.raises(ValueError, match="test listing"):
        github_cli.parse_paginated_objects(payload, key=key, context="test listing")


@pytest.mark.parametrize("bad_page", [{"other": []}, {}, [], None])
def test_paginated_objects_require_the_key_on_every_page(bad_page: object) -> None:
    payload = json.dumps([{"items": [{"id": 1}]}, bad_page])
    with pytest.raises(ValueError, match="test listing"):
        github_cli.parse_paginated_objects(payload, key="items", context="test listing")
