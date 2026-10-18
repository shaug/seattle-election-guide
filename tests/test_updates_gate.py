"""Published page changes need a fresh entry in the same served election log."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.hosting.updates import (
    build_updates_snapshot,
    check_updates,
    compare_updates_snapshots,
)
from election_guide.serialization import canonical_json_bytes

PRIMARY = "wa-2026-primary"
GENERAL = "wa-2026-general"
OLD_ENTRY = ("October 16, 2026", "First publication.", "The guide opened.")
NEW_ENTRY = ("October 18, 2026", "Added an endorsement.", "One more source endorsed A.")


def _page(content: str = "A: 2 endorsements, 100%", *, revision: str = "a") -> str:
    return (
        "<html><head><style>.meter { color: navy; }</style></head><body>"
        f"<main><p>{content}</p></main>"
        '<footer><span class="audit-data">Data updated 2026-10-16 '
        '(<a href="release-manifest.json">aaaaaaaaaaaa</a>) · Panel test (bbbb)</span>'
        f'<span class="audit-site">Site updated 2026-10-16 ({revision})</span></footer>'
        '<script type="application/json" data-client-payload>'
        '{"data_version":"aaaaaaaaaaaa","races":[{"leader":"A"}]}</script>'
        '<script type="module">inspectEndorsements();</script></body></html>'
    )


def _updates(*entries: tuple[str, str, str]) -> str:
    return (
        '<main id="corrections-main">'
        + "".join(
            '<article class="corrections-entry">'
            f'<p class="corrections-date">{day}</p>'
            f'<p class="corrections-body"><strong>{headline}</strong> {body}</p></article>'
            for day, headline, body in entries
        )
        + "</main>"
    )


def _seal(site: Path) -> None:
    manifest = {
        "schema_version": "2.0",
        "canonical_origin": "https://seattleelections.guide",
        "current_election_id": GENERAL,
        "elections": [
            {
                "election_id": election,
                "bundle_id": election + "-release",
                "release_version": "test.1",
                "git_commit": "a" * 40,
                "source_panel_id": election + "-panel",
                "source_panel_hash": "b" * 64,
                "release_manifest_sha256": "c" * 64,
            }
            for election in (GENERAL, PRIMARY)
        ],
        "assets": {
            p.relative_to(site).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(site.rglob("*"))
            if p.is_file() and p.name != "deployment-manifest.json"
        },
    }
    (site / "deployment-manifest.json").write_bytes(canonical_json_bytes(manifest))


def _write(site: Path, relative: str, content: str) -> None:
    path = site / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture
def sites(tmp_path: Path) -> tuple[Path, Path]:
    baseline = tmp_path / "published"
    for election in (GENERAL, PRIMARY):
        _write(baseline, f"e/{election}/index.html", _page())
        _write(baseline, f"e/{election}/races/race-1/index.html", _page())
        _write(baseline, f"e/{election}/updates/index.html", _updates(OLD_ENTRY))
    _seal(baseline)
    candidate = tmp_path / "candidate"
    shutil.copytree(baseline, candidate)
    return baseline, candidate


@pytest.mark.parametrize("election", [GENERAL, PRIMARY])
@pytest.mark.parametrize("route", ["index.html", "races/race-1/index.html"])
def test_changed_count_with_unchanged_leader_requires_entry(
    sites: tuple[Path, Path], election: str, route: str
) -> None:
    baseline, candidate = sites
    path = f"e/{election}/{route}"
    _write(candidate, path, _page("A: 3 endorsements, 100%"))
    _seal(candidate)

    report = check_updates(baseline, candidate)

    assert report["result"] == "fail"
    assert report["elections"][election]["changed_pages"] == ["/" + path]
    assert report["elections"][election]["new_entries"] == []


def test_entry_must_be_in_the_affected_elections_served_log(sites: tuple[Path, Path]) -> None:
    baseline, candidate = sites
    _write(candidate, f"e/{PRIMARY}/races/race-1/index.html", _page("A: 3 endorsements"))
    _write(candidate, f"e/{GENERAL}/updates/index.html", _updates(NEW_ENTRY, OLD_ENTRY))
    # A changed repository YAML is not the frozen primary's served Updates page.
    (candidate.parent / "wa-2026-primary.yaml").write_text("entries: [new entry]")
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "fail"


def test_new_served_entry_allows_the_change(sites: tuple[Path, Path]) -> None:
    baseline, candidate = sites
    _write(candidate, f"e/{GENERAL}/index.html", _page("A: 3 endorsements"))
    _write(candidate, f"e/{GENERAL}/updates/index.html", _updates(NEW_ENTRY, OLD_ENTRY))
    _seal(candidate)

    report = check_updates(baseline, candidate)

    assert report["result"] == "pass"
    assert report["elections"][GENERAL]["new_entries"] == [
        {"date": NEW_ENTRY[0], "headline": NEW_ENTRY[1]}
    ]


@pytest.mark.parametrize(
    "entry",
    [
        (OLD_ENTRY[0], OLD_ENTRY[1], "Edited body."),
        (NEW_ENTRY[0], NEW_ENTRY[1], "Replaced the old entry."),
    ],
)
def test_editing_an_old_entry_does_not_satisfy_the_gate(
    sites: tuple[Path, Path], entry: tuple[str, str, str]
) -> None:
    baseline, candidate = sites
    _write(candidate, f"e/{GENERAL}/index.html", _page("B now leads"))
    _write(candidate, f"e/{GENERAL}/updates/index.html", _updates(entry))
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "fail"


@pytest.mark.parametrize(
    "old,new",
    [
        ("inspectEndorsements();", "hideEndorsements();"),
        ("color: navy", "display: none"),
        ('"leader":"A"', '"leader":"B"'),
        ("100%", "90%"),
        ("<html>", "<!doctype html><html>"),
    ],
)
def test_rendering_and_client_changes_require_entries(
    sites: tuple[Path, Path], old: str, new: str
) -> None:
    baseline, candidate = sites
    _write(candidate, f"e/{PRIMARY}/races/race-1/index.html", _page().replace(old, new))
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "fail"


def test_build_provenance_and_noop_refresh_need_no_entry(sites: tuple[Path, Path]) -> None:
    baseline, candidate = sites
    refreshed = _page(revision="different commit").replace("2026-10-16", "2026-10-18")
    refreshed = refreshed.replace("aaaaaaaaaaaa", "dddddddddddd")
    _write(candidate, f"e/{GENERAL}/index.html", refreshed)
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "pass"


def test_referenced_client_asset_changes_require_an_entry(sites: tuple[Path, Path]) -> None:
    baseline, candidate = sites
    for site in sites:
        _write(site, "assets/race.js", "inspectEndorsements();")
        _write(site, f"e/{GENERAL}/index.html", _page() + '<script src="/assets/race.js"></script>')
        _seal(site)
    _write(candidate, "assets/race.js", "hideEndorsements();")
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "fail"


@pytest.mark.parametrize("added", [True, False])
def test_added_and_removed_position_pages_require_entries(
    sites: tuple[Path, Path], added: bool
) -> None:
    baseline, candidate = sites
    if added:
        _write(candidate, f"e/{GENERAL}/races/race-2/index.html", _page())
    else:
        (candidate / f"e/{GENERAL}/races/race-1/index.html").unlink()
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "fail"


def test_history_only_date_correction_needs_no_extra_entry(sites: tuple[Path, Path]) -> None:
    baseline, candidate = sites
    _write(
        candidate,
        f"e/{GENERAL}/updates/index.html",
        _updates(("October 15, 2026", OLD_ENTRY[1], OLD_ENTRY[2])),
    )
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "pass"


@pytest.mark.parametrize("which", [0, 1])
def test_unverified_page_bytes_fail_closed(sites: tuple[Path, Path], which: int) -> None:
    _write(sites[which], f"e/{GENERAL}/index.html", _page("unverified change"))

    with pytest.raises(ValueError, match="hash"):
        check_updates(*sites)


def test_missing_baseline_fails_closed(sites: tuple[Path, Path]) -> None:
    (sites[0] / "deployment-manifest.json").unlink()

    with pytest.raises(ValueError, match="baseline"):
        check_updates(*sites)


def test_report_is_json_serializable(sites: tuple[Path, Path]) -> None:
    assert json.loads(json.dumps(check_updates(*sites)))["result"] == "pass"


def test_site_directory_may_be_reached_through_a_symlink(sites: tuple[Path, Path]) -> None:
    alias = sites[0].parent / "published-alias"
    alias.symlink_to(sites[0], target_is_directory=True)

    assert check_updates(alias, sites[1])["result"] == "pass"


def test_retained_snapshot_still_detects_changes_after_artifact_expiry(
    sites: tuple[Path, Path],
) -> None:
    baseline, candidate = sites
    snapshot = build_updates_snapshot(baseline)
    shutil.rmtree(baseline)
    _write(candidate, f"e/{GENERAL}/index.html", _page("B: 3 endorsements"))
    _seal(candidate)

    assert (
        compare_updates_snapshots(snapshot, build_updates_snapshot(candidate))["result"] == "fail"
    )


def test_cli_blocks_a_change_and_preserves_the_page_report(sites: tuple[Path, Path]) -> None:
    baseline, candidate = sites
    _write(candidate, f"e/{GENERAL}/index.html", _page("A: 3 endorsements"))
    _seal(candidate)
    report_path = candidate.parent / "updates-check.json"

    result = CliRunner().invoke(
        app,
        [
            "hosting",
            "check-updates",
            str(candidate),
            "--baseline-site-dir",
            str(baseline),
            "--output-path",
            str(report_path),
        ],
    )

    assert result.exit_code == 1, result.output
    report = json.loads(report_path.read_text())
    assert report["result"] == "fail"
    assert report["elections"][GENERAL]["changed_pages"] == [f"/e/{GENERAL}/index.html"]
    assert f"/e/{GENERAL}/index.html" in result.output


def test_cli_writes_failure_evidence_when_baseline_is_missing(sites: tuple[Path, Path]) -> None:
    baseline, candidate = sites
    (baseline / "deployment-manifest.json").unlink()
    report_path = candidate.parent / "updates-check.json"

    result = CliRunner().invoke(
        app,
        [
            "hosting",
            "check-updates",
            str(candidate),
            "--baseline-site-dir",
            str(baseline),
            "--output-path",
            str(report_path),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(report_path.read_text())["error"]
