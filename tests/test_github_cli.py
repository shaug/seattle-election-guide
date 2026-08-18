"""Behavior tests for the shared `gh` CLI plumbing (issue #387).

Direct coverage for `parse_issue_list`, independent of its three callers
(`calendar.github_tracker.issue_records`,
`hosting.production_alert.ProductionAlertTracker.find_open_alert`,
`sources.link_rot_alert.LinkRotAlertTracker.find_open_alert`), each of which
keeps its own per-call-site tests for the field extraction layered on top.
"""

from __future__ import annotations

import json

import pytest

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
