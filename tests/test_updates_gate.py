"""Published page changes need a fresh entry in the same served election log."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Literal

import pytest
from typer.testing import CliRunner

from election_guide.cli import app
from election_guide.hosting.updates import (
    UPDATES_SNAPSHOT,
    build_updates_snapshot,
    check_updates,
    compare_updates_snapshots,
    verify_updates_snapshot,
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


def _seal(site: Path, *, source_commit: str = "a" * 40) -> None:
    manifest = {
        "schema_version": "2.0",
        "canonical_origin": "https://seattleelections.guide",
        "current_election_id": GENERAL,
        "elections": [
            {
                "election_id": election,
                "bundle_id": election + "-release",
                "release_version": "test.1",
                "git_commit": source_commit,
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
        ('"leader":"A"', '"leader":"B"'),
        ("100%", "90%"),
    ],
)
def test_served_election_facts_and_client_facts_require_entries(
    sites: tuple[Path, Path], old: str, new: str
) -> None:
    baseline, candidate = sites
    _write(candidate, f"e/{PRIMARY}/races/race-1/index.html", _page().replace(old, new))
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "fail"


@pytest.mark.parametrize(
    "old,new",
    [
        ("inspectEndorsements();", "hideEndorsements();"),
        ("color: navy", "display: none"),
        ("<html>", "<!doctype html><html>"),
        ("<p>A:", "<div>A:"),
    ],
)
def test_software_markup_styles_and_code_do_not_require_election_entries(
    sites: tuple[Path, Path], old: str, new: str
) -> None:
    baseline, candidate = sites
    _write(candidate, f"e/{GENERAL}/index.html", _page().replace(old, new))
    _seal(candidate)
    assert check_updates(baseline, candidate)["result"] == "pass"


def test_build_provenance_and_noop_refresh_need_no_entry(sites: tuple[Path, Path]) -> None:
    baseline, candidate = sites
    refreshed = _page(revision="different commit").replace("2026-10-16", "2026-10-18")
    refreshed = refreshed.replace("aaaaaaaaaaaa", "dddddddddddd")
    _write(candidate, f"e/{GENERAL}/index.html", refreshed)
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "pass"


@pytest.mark.parametrize(
    "before,after",
    [
        ("<strong>A</strong> B", "<strong>A</strong>B"),
        ("A <strong>B</strong>", "A<strong>B</strong>"),
        ("<span>A</span> <span>B</span>", "<span>A</span><span>B</span>"),
        ("A&nbsp;B", "A B"),
        ("<pre>A B</pre>", "<pre>A  B</pre>"),
    ],
)
def test_visible_word_spacing_changes_require_an_entry(
    sites: tuple[Path, Path], before: str, after: str
) -> None:
    baseline, candidate = sites
    path = f"e/{GENERAL}/index.html"
    _write(baseline, path, _page(before))
    _write(candidate, path, _page(after))
    for site in sites:
        _seal(site)

    assert check_updates(baseline, candidate)["result"] == "fail"


def test_indentation_between_block_elements_needs_no_entry(sites: tuple[Path, Path]) -> None:
    baseline, candidate = sites
    indented = _page().replace("<main>", "<main>\n  ").replace("</p>", "</p>\n")
    _write(candidate, f"e/{GENERAL}/index.html", indented)
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "pass"


@pytest.mark.parametrize("remove_comment", [False, True])
@pytest.mark.parametrize(
    "plain,commented",
    [
        ("A B", "A<!-- maintenance --> B"),
        ("A B", "A <!-- maintenance --> B"),
        ("A&nbsp;B", "A<!-- maintenance -->&nbsp;B"),
        ("<pre>A  B</pre>", "<pre>A<!-- maintenance -->  B</pre>"),
    ],
)
def test_comments_inside_text_need_no_entry(
    sites: tuple[Path, Path], plain: str, commented: str, remove_comment: bool
) -> None:
    before, after = (commented, plain) if remove_comment else (plain, commented)
    for site, content in zip(sites, (before, after), strict=True):
        _write(site, f"e/{GENERAL}/index.html", _page(content))
        _seal(site)

    assert check_updates(*sites)["result"] == "pass"


@pytest.mark.parametrize("remove_comment", [False, True])
def test_shared_shell_comments_need_no_entry(
    sites: tuple[Path, Path], remove_comment: bool
) -> None:
    plain = _page().replace("<body>", '<body><a href="#main">Skip to recommendations</a>')
    commented = plain.replace("Skip to", "Skip<!-- maintenance --> to")
    before, after = (commented, plain) if remove_comment else (plain, commented)
    for site, content in zip(sites, (before, after), strict=True):
        for election in (GENERAL, PRIMARY):
            for route in ("index.html", "races/race-1/index.html"):
                _write(site, f"e/{election}/{route}", content)
        _seal(site)

    assert check_updates(*sites)["result"] == "pass"


def test_textarea_comment_syntax_remains_visible_content(sites: tuple[Path, Path]) -> None:
    before, after = "<textarea></textarea>", "<textarea><!-- visible text --></textarea>"
    for site, content in zip(sites, (before, after), strict=True):
        _write(site, f"e/{GENERAL}/index.html", _page(content))
        _seal(site)

    assert check_updates(*sites)["result"] == "fail"


def test_referenced_software_asset_change_needs_no_election_entry(sites: tuple[Path, Path]) -> None:
    baseline, candidate = sites
    for site in sites:
        _write(site, "assets/race.js", "inspectEndorsements();")
        _write(site, f"e/{GENERAL}/index.html", _page() + '<script src="/assets/race.js"></script>')
        _seal(site)
    _write(candidate, "assets/race.js", "hideEndorsements();")
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "pass"


@pytest.mark.parametrize("relation", ["stylesheet", "StyleSheet", "alternate stylesheet"])
def test_linked_stylesheet_change_needs_no_election_entry(
    sites: tuple[Path, Path], relation: str
) -> None:
    baseline, candidate = sites
    for site in sites:
        _write(site, "assets/race.css", ".meter { color: navy; }")
        _write(
            site,
            f"e/{GENERAL}/index.html",
            _page() + f'<link rel="{relation}" href="/assets/race.css" title="Other">',
        )
        _seal(site)
    _write(candidate, "assets/race.css", ".meter { color: red; }")
    _seal(candidate)

    assert check_updates(baseline, candidate)["result"] == "pass"


def test_material_information_correction_still_requires_a_served_entry(
    sites: tuple[Path, Path],
) -> None:
    baseline, candidate = sites
    for site, content in zip(
        sites,
        [
            '<p>Certified August 19: A 51%</p><a href="https://county.test/old">Evidence</a>',
            '<p>Certified August 18: A 49%</p><a href="https://county.test/new">Evidence</a>',
        ],
        strict=True,
    ):
        _write(site, f"e/{GENERAL}/index.html", _page(content))
        _seal(site)
    assert check_updates(baseline, candidate)["result"] == "fail"
    _write(candidate, f"e/{GENERAL}/updates/index.html", _updates(NEW_ENTRY, OLD_ENTRY))
    _seal(candidate)
    assert check_updates(baseline, candidate)["result"] == "pass"


def test_incompatible_snapshot_policies_cannot_be_compared(sites: tuple[Path, Path]) -> None:
    old = build_updates_snapshot(sites[0]).model_copy(update={"schema_version": "1.0"})
    with pytest.raises(ValueError, match="policy"):
        compare_updates_snapshots(old, build_updates_snapshot(sites[1]))


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


@pytest.mark.parametrize("content_changed", [False, True])
def test_removing_a_history_only_entry_is_reported_and_cannot_excuse_content_changes(
    sites: tuple[Path, Path], content_changed: bool
) -> None:
    baseline, candidate = sites
    _write(baseline, f"e/{GENERAL}/updates/index.html", _updates(OLD_ENTRY, NEW_ENTRY))
    _seal(baseline)
    if content_changed:
        _write(candidate, f"e/{GENERAL}/index.html", _page("A changed voting decision."))
    _seal(candidate)

    report = check_updates(baseline, candidate)

    assert report["result"] == ("fail" if content_changed else "pass")
    assert report["elections"][GENERAL]["previous_entry_identities_retained"] is False
    assert report["elections"][GENERAL]["new_entries"] == []


@pytest.mark.parametrize("route", ["index.html", "races/race-1/index.html"])
def test_same_content_addressed_result_original_survives_a_software_commit(
    sites: tuple[Path, Path], route: str
) -> None:
    baseline, candidate = sites
    digest = "f" * 64
    for site, revision in [(baseline, "a" * 40), (candidate, "b" * 40)]:
        url = f"https://github.com/shaug/seattle-election-guide/blob/{revision}/data/evidence/official/sha256/ff/{digest}"
        content = f'<div class="race-results">Unofficial A 10<a href="{url}">evidence</a></div>'
        _write(site, f"e/{GENERAL}/{route}", _page(content))
        _seal(site, source_commit=revision)
    assert check_updates(baseline, candidate)["result"] == "pass"


def _result_clock_placement(kind: str, *, compact_badge: bool) -> str:
    status = "Certified" if kind == "certified" else "Unofficial"
    clock = "Aug 19, 2026" if kind == "certified" else "Nov 7, 4:35:00 a.m. PST"
    previous_clock = ("Export generated " if kind == "export" else "") + clock
    badge = status if compact_badge else f"{status} · {previous_clock}"
    clock_line = (
        f"Certified on {clock}"
        if kind == "certified"
        else f"{'Export generated' if kind == 'export' else 'Count updated'} {clock} · "
    )
    recency = (
        '<span data-preliminary-recency="race-1">Last checked Nov 7, 5:22:18 a.m. PST</span>'
        if kind != "certified"
        else ""
    )
    bottom = clock_line if compact_badge else ""
    if not compact_badge and kind == "export":
        bottom = "Count timestamp not provided · "
    return (
        '<div class="race-results"><div class="race-results-head">Result '
        f'<span class="race-results-status">{badge}</span></div>'
        '<div class="race-results-tally">Candidate A 10 · Candidate B 5</div>'
        '<p class="race-results-provenance">15 votes · Official authority'
        f"<br>{bottom}{recency}</p></div>"
    )


@pytest.mark.parametrize("kind", ["count", "export", "certified"])
@pytest.mark.parametrize("route", ["index.html", "races/race-1/index.html"])
def test_result_clock_placement_is_presentation_when_all_facts_are_preserved(
    sites: tuple[Path, Path], kind: str, route: str
) -> None:
    baseline, candidate = sites
    for site, compact in [(baseline, False), (candidate, True)]:
        _write(
            site,
            f"e/{GENERAL}/{route}",
            _page(_result_clock_placement(kind, compact_badge=compact)),
        )
        _seal(site)
    report = check_updates(baseline, candidate)
    assert report["result"] == "pass"
    assert report["elections"][GENERAL]["new_entries"] == []


@pytest.mark.parametrize(
    "kind,old,new",
    [
        ("certified", "Aug 19", "Aug 20"),
        ("count", "Unofficial", "Certified"),
        ("count", "Candidate A 10", "Candidate A 11"),
        ("count", "Official authority", "Another authority"),
        ("count", "Count updated", "Unreviewed clock"),
        ("count", "Count updated", "Count finished"),
        ("count", "4:35:00", "4:35:99"),
        ("count", "Count updated", "Extra explanation · Count updated"),
        ("count", "race-results-provenance", "source-provenance"),
        ("count", "race-results-status", "source-status"),
    ],
)
def test_compact_result_badges_still_compare_every_fact_and_unrecognized_text(
    sites: tuple[Path, Path], kind: str, old: str, new: str
) -> None:
    baseline, candidate = sites
    content = _result_clock_placement(kind, compact_badge=True)
    for site, text in [(baseline, content), (candidate, content.replace(old, new))]:
        _write(site, f"e/{GENERAL}/index.html", _page(text))
        _seal(site)
    assert check_updates(baseline, candidate)["result"] == "fail"


@pytest.mark.parametrize("compact_badge", [False, True])
def test_missing_count_notice_is_not_ignored_beside_an_available_count_clock(
    sites: tuple[Path, Path], compact_badge: bool
) -> None:
    baseline, candidate = sites
    content = _result_clock_placement("count", compact_badge=compact_badge)
    changed = content.replace("<br>", "<br><span>Count timestamp not provided · </span>")
    for site, text in [(baseline, content), (candidate, changed)]:
        _write(site, f"e/{GENERAL}/index.html", _page(text))
        _seal(site)
    assert check_updates(baseline, candidate)["result"] == "fail"


def test_later_count_clock_prevents_omitting_a_legacy_missing_count_notice(
    sites: tuple[Path, Path],
) -> None:
    baseline, candidate = sites
    content = _result_clock_placement("export", compact_badge=False)
    content = content.replace(
        "<span data-preliminary-recency=",
        "<span>Count updated Nov 7, 4:35:00 a.m. PST · </span><span data-preliminary-recency=",
    )
    for site, text in [
        (baseline, content.replace("Count timestamp not provided · ", "")),
        (candidate, content),
    ]:
        _write(site, f"e/{GENERAL}/index.html", _page(text))
        _seal(site)
    assert check_updates(baseline, candidate)["result"] == "fail"


@pytest.mark.parametrize(
    "change", ["hash", "wrong-pin", "wrong-prefix", "other-repository", "outside-result", "count"]
)
def test_result_original_identity_rule_does_not_hide_changed_evidence_or_facts(
    sites: tuple[Path, Path], change: str
) -> None:
    baseline, candidate = sites
    for site, revision in [(baseline, "a" * 40), (candidate, "b" * 40)]:
        digest = "e" * 64 if site == candidate and change == "hash" else "f" * 64
        prefix = "00" if site == candidate and change == "wrong-prefix" else digest[:2]
        pin = "c" * 40 if site == candidate and change == "wrong-pin" else revision
        repository = (
            "someone/else"
            if site == candidate and change == "other-repository"
            else "shaug/seattle-election-guide"
        )
        value = "11" if site == candidate and change == "count" else "10"
        url = f"https://github.com/{repository}/blob/{pin}/data/evidence/official/sha256/{prefix}/{digest}"
        classes = "source-evidence" if change == "outside-result" else "race-results"
        _write(
            site,
            f"e/{GENERAL}/index.html",
            _page(f'<div class="{classes}">Unofficial A {value}<a href="{url}">evidence</a></div>'),
        )
        _seal(site, source_commit=revision)
    assert check_updates(baseline, candidate)["result"] == "fail"


@pytest.mark.parametrize("route", ["index.html", "races/race-1/index.html"])
@pytest.mark.parametrize(
    "label", ["Last checked", "Stale · last checked", "Refresh unavailable · last checked"]
)
def test_unchanged_preliminary_results_can_refresh_their_verification_clock(
    sites: tuple[Path, Path], route: str, label: str
) -> None:
    baseline, candidate = sites
    for site, clock in [(baseline, "5:22:18"), (candidate, "7:21:45")]:
        content = (
            '<div class="race-results">Unofficial A 10 · Count as of Nov 7, 4:35 a.m. PST '
            '<span data-preliminary-recency="race-1">'
            f"{label} Nov 7, {clock} a.m. PST</span></div>"
        )
        _write(site, f"e/{GENERAL}/{route}", _page(content))
        _seal(site)

    report = check_updates(baseline, candidate)

    assert report["result"] == "pass"
    assert report["elections"][GENERAL]["changed_pages"] == []
    assert report["elections"][GENERAL]["new_entries"] == []


@pytest.mark.parametrize(
    "change",
    [
        "count",
        "count-clock",
        "export-clock",
        "authority",
        "status",
        "extra-text",
        "outside",
        "unmarked",
        "malformed",
    ],
)
def test_verification_clock_rule_preserves_other_result_information(
    sites: tuple[Path, Path], change: str
) -> None:
    baseline, candidate = sites
    for site, clock in [(baseline, "5:22:18"), (candidate, "7:21:45")]:
        changed = site == candidate
        count = "11" if changed and change == "count" else "10"
        count_clock = "4:36" if changed and change == "count-clock" else "4:35"
        export_clock = "4:37" if changed and change == "export-clock" else "4:35"
        authority = "Different authority" if changed and change == "authority" else "County"
        label = (
            "Refresh unavailable · last checked"
            if changed and change == "status"
            else "Last checked"
        )
        extra = " A 11" if changed and change == "extra-text" else ""
        classes = "source-evidence" if change == "outside" else "race-results"
        marker = "" if change == "unmarked" else ' data-preliminary-recency="race-1"'
        stamp = f"Nov 7, {clock} a.m. PST" if change != "malformed" else f"not-a-clock-{clock}"
        content = (
            f'<div class="{classes}">Unofficial A {count} · {authority} '
            f"Count as of Nov 7, {count_clock} a.m. PST · "
            f"Export generated Nov 7, {export_clock} a.m. PST "
            f"<span{marker}>{label} {stamp}{extra}</span></div>"
        )
        _write(site, f"e/{GENERAL}/index.html", _page(content))
        _seal(site)

    assert check_updates(baseline, candidate)["result"] == "fail"


def test_legacy_snapshot_verification_still_compares_its_original_check_clock(
    sites: tuple[Path, Path],
) -> None:
    baseline, _ = sites
    path = f"e/{GENERAL}/index.html"
    content = (
        '<div class="race-results">Unofficial A 10 '
        '<span data-preliminary-recency="race-1">Last checked Nov 7, 5:22:18 a.m. PST</span></div>'
    )
    _write(baseline, path, _page(content))
    _seal(baseline)
    snapshot = build_updates_snapshot(baseline, schema_version="3.0")
    (baseline / UPDATES_SNAPSHOT).write_bytes(
        canonical_json_bytes(snapshot.model_dump(mode="json"))
    )
    _write(baseline, path, _page(content.replace("5:22:18", "7:21:45")))
    _seal(baseline)

    with pytest.raises(ValueError, match="snapshot differs"):
        verify_updates_snapshot(baseline)


@pytest.mark.parametrize("policy", ["3.0", "4.0"])
def test_original_result_clock_is_verified_before_migrating_its_placement_policy(
    sites: tuple[Path, Path], policy: Literal["3.0", "4.0"]
) -> None:
    baseline, _ = sites
    path = f"e/{GENERAL}/index.html"
    content = _result_clock_placement("export", compact_badge=False)
    _write(baseline, path, _page(content))
    _seal(baseline)
    snapshot = build_updates_snapshot(baseline, schema_version=policy)
    (baseline / UPDATES_SNAPSHOT).write_bytes(
        canonical_json_bytes(snapshot.model_dump(mode="json"))
    )
    _write(baseline, path, _page(content.replace("4:35:00", "4:36:00")))
    _seal(baseline)
    with pytest.raises(ValueError, match="snapshot differs"):
        verify_updates_snapshot(baseline)


@pytest.mark.parametrize("kind", ["count", "export"])
@pytest.mark.parametrize("change", ["clock", "original", "failed-refresh", "clock-absent"])
def test_metadata_only_preliminary_changes_do_not_force_filler_updates(
    sites: tuple[Path, Path], kind: str, change: str
) -> None:
    baseline, candidate = sites
    original = "https://github.com/shaug/seattle-election-guide/blob/" + "a" * 40
    original += "/data/evidence/official/sha256/ff/" + "f" * 64
    before = _result_clock_placement(kind, compact_badge=True).replace(
        "Official authority", f'Official authority <a href="{original}">evidence</a>'
    )
    after = before
    if change == "clock":
        after = after.replace("4:35:00", "4:36:00")
    elif change == "original":
        after = after.replace("/ff/" + "f" * 64, "/ee/" + "e" * 64)
    elif change == "failed-refresh":
        after = after.replace("Last checked", "Refresh unavailable · last checked")
    else:
        label = "Count updated" if kind == "count" else "Export generated"
        after = after.replace(label + " Nov 7, 4:35:00 a.m. PST · ", "")
    for site, content in [(baseline, before), (candidate, after)]:
        _write(site, f"e/{GENERAL}/index.html", _page(content))
        _seal(site)
    assert check_updates(baseline, candidate)["result"] == "pass"
    # Historical snapshots keep the policy under which they were accepted.
    old = build_updates_snapshot(baseline, schema_version="5.0")
    new = build_updates_snapshot(candidate, schema_version="5.0")
    assert old.elections[GENERAL].information_pages != new.elections[GENERAL].information_pages


def test_metadata_change_cannot_hide_simultaneous_preliminary_vote_change(
    sites: tuple[Path, Path],
) -> None:
    baseline, candidate = sites
    content = _result_clock_placement("export", compact_badge=True)
    for site, text in [
        (baseline, content),
        (
            candidate,
            content.replace("4:35:00", "4:36:00").replace("Candidate A 10", "Candidate A 11"),
        ),
    ]:
        _write(site, f"e/{GENERAL}/index.html", _page(text))
        _seal(site)
    assert check_updates(baseline, candidate)["result"] == "fail"


@pytest.mark.parametrize(
    "replacement",
    [
        "Candidate A 11",
        "Last checked Nov 7, 5:22:99 a.m. PST",
        "Extra election information · Last checked Nov 7, 5:22:18 a.m. PST",
    ],
)
def test_recency_normalization_keeps_unrecognized_text_in_real_unofficial_results(
    sites: tuple[Path, Path], replacement: str
) -> None:
    baseline, candidate = sites
    content = _result_clock_placement("export", compact_badge=True)
    for site, text in [
        (baseline, content),
        (candidate, content.replace("Last checked Nov 7, 5:22:18 a.m. PST", replacement)),
    ]:
        _write(site, f"e/{GENERAL}/index.html", _page(text))
        _seal(site)
    assert check_updates(baseline, candidate)["result"] == "fail"
