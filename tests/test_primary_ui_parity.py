"""Current UI over literal archived Primary11 facts and admitted capabilities (#723)."""

from __future__ import annotations

import gzip
import hashlib
import re
from pathlib import Path

import pytest

from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import (
    render_comparison_document,
    render_html_document,
    render_sources_document,
)
from election_guide.rendering.payload import sources_payload

FIXTURE = Path(__file__).parent / "fixtures/ballot/primary11-view-model.json.gz"


@pytest.fixture
def primary11() -> PublicationViewModel:
    raw = gzip.decompress(FIXTURE.read_bytes())
    assert hashlib.sha256(raw).hexdigest() == (
        "78b7afc76c77ebe58d9f5195a9ee26fbeceefd7a46538953664e9760d3f9fa22"
    )
    return PublicationViewModel.model_validate_json(raw)


@pytest.mark.parametrize("page", ["guide", "comparisons"])
def test_primary_uses_current_native_controls_without_inventing_precincts(
    primary11: PublicationViewModel, page: str
) -> None:
    before = primary11.model_dump_json()
    html = (
        render_html_document(
            primary11, read_rendering_configuration(Path("config/rendering/guide.yaml"))
        )
        if page == "guide"
        else render_comparison_document(primary11, public_site_url="https://seattleelections.guide")
    )
    assert primary11.model_dump_json() == before
    assert primary11.precinct_ballot is None
    assert re.findall(r'<select[^>]+data-filter-native="([^"]+)"', html) == [
        "view",
        "races",
        "ballot",
    ]
    assert "All ballot races" in html.split("<script", 1)[0]
    assert "<section data-compact-filters" in html
    assert '<button class="precinct-open' not in html.split("<script", 1)[0]
    if page == "guide":
        assert "data-compact-sources" in html.split("<script", 1)[0]
        assert "Sources: <span data-sources-summary>All 40</span>" in html
        assert len(re.findall(r"<article[^>]+data-publication-race-id=", html)) == 32


def test_primary_sources_carries_explicit_current_race_query_capability(
    primary11: PublicationViewModel,
) -> None:
    payload = sources_payload(
        primary11,
        guide_path="/e/wa-2026-primary/",
        comparisons_path="/e/wa-2026-primary/comparisons/",
    ).model_dump()
    assert payload.get("race_mode_query_enabled") is True
    assert payload.get("comparisons_path") == "/e/wa-2026-primary/comparisons/"


@pytest.mark.parametrize("page", ["sources", "comparisons"])
def test_primary_uses_current_shared_intro(primary11: PublicationViewModel, page: str) -> None:
    html = (
        render_sources_document(primary11, public_site_url="https://seattleelections.guide")
        if page == "sources"
        else render_comparison_document(primary11, public_site_url="https://seattleelections.guide")
    )
    intro = (
        "The endorsements you trust, aggregated."
        if page == "sources"
        else "The endorsements you choose, juxtaposed."
    )
    assert intro in html


@pytest.fixture
def supplemented_site(tmp_path: Path) -> tuple[Path, Path]:
    """Compose the original authenticated Primary11 with a small current fixture."""
    import json
    import shutil

    from election_guide.hosting.models import PublishedElection
    from election_guide.hosting.pages import stage_pages_site
    from election_guide.hosting.releases import extract_release_bundle
    from election_guide.serialization import canonical_json_bytes
    from tests.test_historical_presentation import (  # pyright: ignore[reportPrivateUsage]
        _archive,  # pyright: ignore[reportPrivateUsage]
        _reseal_view,  # pyright: ignore[reportPrivateUsage]
    )

    root = Path(__file__).resolve().parents[1]
    source = json.loads(
        (root / "config/elections/wa-2026-primary-precinct-supplement.json").read_bytes()
    )
    relative = Path("config/elections/wa-2026-primary-precinct-supplement.json")
    (tmp_path / relative).parent.mkdir(parents=True)
    shutil.copyfile(root / relative, tmp_path / relative)
    for key in [
        "source_csv",
        "source_metadata",
        "source_csv_capture",
        "source_metadata_capture",
        "source_acquisition",
        "city_membership",
    ]:
        path = Path(source[key]["path"])
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / path, tmp_path / path)
    current, declaration, current_view = _archive(
        tmp_path / "current", election_id="wa-2026-general"
    )
    current_view["comparisons"]["policy"]["enabled"] = True
    _reseal_view(current, current_view)
    historical = PublishedElection(
        election_id="wa-2026-primary",
        bundle_id="wa-2026-primary-2026-primary.11",
        release_version="2026-primary.11",
        source_panel_id="wa-2026-primary-default-sources-v4",
        source_panel_hash="389a978b149da9afdb919fdb9dfd1d4d3fbecc290d3b1cd41da3e3fd363de0b5",
        source_registry_hash="76f9897a764e66698f45c544b1ade09dbc77cc71c79d0302bf59def05f3c26a8",
        git_commit="ccce7f3f0285e39bb541d7e2984e36b8e92e1595",
        release_manifest_sha256="d7590c753deed52ea9e8439c7cacf8c02318bcf31e28bf0c005227a0ee3d4894",
        bundle_sha256="e61152cad9f195a68c420cf98c35f55d7479c4fd15ba3aee4ac48da7d775c81a",
    )
    original = tmp_path / "original-primary"
    extract_release_bundle(FIXTURE.parent / "primary11.original.zip", original, historical)
    site_manifest = tmp_path / "config/hosting/site.yaml"
    site_manifest.parent.mkdir(parents=True)
    site_manifest.write_bytes(
        canonical_json_bytes(
            {
                "schema_version": "1.2",
                "canonical_origin": "https://seattleelections.guide",
                "current_election_id": "wa-2026-general",
                "elections": [declaration.model_dump(), historical.model_dump()],
                "historical_capabilities": {
                    "wa-2026-primary": {
                        "path": str(relative),
                        "sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest(),
                    }
                },
            }
        )
    )
    output = tmp_path / "site"
    before = {
        p.relative_to(original): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in original.rglob("*")
        if p.is_file()
    }
    stage_pages_site(
        site_manifest, {declaration.bundle_id: current, historical.bundle_id: original}, output
    )
    assert before == {
        p.relative_to(original): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in original.rglob("*")
        if p.is_file()
    }
    return output, site_manifest


def test_supplemented_primary_head_distinguishes_data_presentation_and_capability(
    supplemented_site: tuple[Path, Path],
) -> None:
    import json

    output, _ = supplemented_site
    deployed = json.loads((output / "deployment-manifest.json").read_bytes())
    assert deployed["schema_version"] == "3.1"
    primary = deployed["elections"][1]
    supplement = primary["precinct_supplement"]
    assert primary["git_commit"] == "ccce7f3f0285e39bb541d7e2984e36b8e92e1595"
    assert primary["presentation"]["source_git_commit"] == supplement["source_git_commit"]
    assert supplement["archive_view_model_sha256"] == (
        "78b7afc76c77ebe58d9f5195a9ee26fbeceefd7a46538953664e9760d3f9fa22"
    )
    for page in ["index.html", "comparisons/index.html", "sources/index.html"]:
        html = (output / "e/wa-2026-primary" / page).read_text().split("<script", 1)[0]
        assert (
            f'<meta name="seg-precinct-supplement" content="{supplement["artifact_sha256"]}">'
            in html
        )
        if page != "sources/index.html":
            assert 'class="precinct-info"' not in html
    assert "no-transform" in (output / "_headers").read_text()
    assert "`${cache}, no-transform`" in (output / "_worker.js").read_text()


@pytest.mark.parametrize("fault", ["metadata", "payload-membership", "missing-payload"])
def test_independent_verification_rejects_rehashed_supplement_page_claims(
    supplemented_site: tuple[Path, Path], fault: str
) -> None:
    import json

    from election_guide.hosting.pages import verify_staged_pages_site
    from tests.test_historical_presentation import _reseal_site  # pyright: ignore[reportPrivateUsage]

    output, manifest = supplemented_site
    page = output / "e/wa-2026-primary/index.html"
    html = page.read_text()
    if fault == "metadata":
        html = re.sub(
            r'(<meta name="seg-precinct-supplement" content=")[^"]+',
            r"\g<1>" + "0" * 64,
            html,
        )
    else:
        pattern = r'(<script type="application/json" data-client-payload>)(.*?)(</script>)'
        match = re.search(pattern, html, re.S)
        assert match is not None
        if fault == "missing-payload":
            html = html[: match.start()] + html[match.end() :]
        else:
            value = json.loads(match[2])
            value["precinct_ballot"]["precincts"][0]["contest_ids"].pop()
            body = json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e")
            html = html[: match.start(2)] + body + html[match.end(2) :]
    page.write_text(html)
    _reseal_site(output)
    with pytest.raises(ValueError, match=r"supplement|precinct"):
        verify_staged_pages_site(output, manifest)


def test_source12_requires_current_presentation_and_supplement_production_checks(
    supplemented_site: tuple[Path, Path],
) -> None:
    import json

    from election_guide.hosting.models import DeploymentManifest
    from election_guide.hosting.pages import read_site_manifest
    from election_guide.hosting.production_check import (
        evaluate_deployment_contract,
        plan_presentation_assets,
    )

    output, manifest = supplemented_site
    deployed = DeploymentManifest.model_validate_json(
        (output / "deployment-manifest.json").read_bytes()
    )
    expected = read_site_manifest(manifest)
    result = evaluate_deployment_contract(
        expected, deployed, expected_git_commit=deployed.elections[0].git_commit
    )
    assert result.ok, result.errors
    planned = plan_presentation_assets(deployed)
    assert "e/wa-2026-primary/precinct-supplement.json" in planned
    assert "e/wa-2026-primary/index.html" in planned
    assert "e/wa-2026-general/index.html" in planned
    assert deployed.elections[1].precinct_supplement is not None
    assert (
        json.loads((output / "e/wa-2026-primary/precinct-supplement.json").read_bytes())[
            "mapping_hash"
        ]
        == deployed.elections[1].precinct_supplement.mapping_hash
    )


@pytest.mark.parametrize("page", ["guide", "comparisons"])
def test_current_contested_treatment_keeps_measures_without_a_precinct_catalog(
    primary11: PublicationViewModel, page: str
) -> None:
    import json

    view = primary11.model_copy(deep=True)
    measure = next(r for s in view.sections for r in s.races if r.race_type == "measure")
    measure.is_contested = False
    assert view.precinct_ballot is None
    html = (
        render_html_document(
            view, read_rendering_configuration(Path("config/rendering/guide.yaml"))
        )
        if page == "guide"
        else render_comparison_document(view, public_site_url="https://seattleelections.guide")
    )
    if page == "guide":
        card = re.search(rf'<article[^>]+data-publication-race-id="{measure.id}"[^>]*>', html)
        assert card is not None and 'data-contested="true"' in card[0]
    else:
        match = re.search(
            r'<script type="application/json" data-client-payload>(.*?)</script>', html, re.S
        )
        assert match is not None
        assert measure.id in json.loads(match[1])["contested_race_ids"]


@pytest.mark.parametrize("fault", [None, "missing-audit", "page-membership"])
def test_source12_http_strict_and_retained_evidence_cover_the_supplement(
    supplemented_site: tuple[Path, Path], fault: str | None
) -> None:
    import json
    from contextlib import contextmanager, suppress
    from http.server import BaseHTTPRequestHandler

    from election_guide.hosting.pages import read_site_manifest
    from election_guide.hosting.production_check import render_summary_lines
    from election_guide.hosting.production_probe import run_production_check
    from election_guide.hosting.production_wait import complete_strict_report
    from tests.test_historical_presentation import _reseal_site  # pyright: ignore[reportPrivateUsage]
    from tests.test_production_probe import _start  # pyright: ignore[reportPrivateUsage]

    output, manifest = supplemented_site
    if fault == "page-membership":
        page = output / "e/wa-2026-primary/index.html"
        html = page.read_text()
        match = re.search(
            r'(<script type="application/json" data-client-payload>)(.*?)(</script>)', html, re.S
        )
        assert match is not None
        value = json.loads(match[2])
        value["precinct_ballot"]["precincts"][0]["contest_ids"].pop()
        page.write_text(
            html[: match.start(2)]
            + json.dumps(value).replace("<", "\\u003c")
            + html[match.end(2) :]
        )
        _reseal_site(output)
    deployed = json.loads((output / "deployment-manifest.json").read_bytes())
    expected = read_site_manifest(manifest)
    commit = deployed["elections"][0]["git_commit"]
    audit_path = "/e/wa-2026-primary/precinct-supplement.json"
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            requests.append(self.path)
            if self.path == "/" or self.path.endswith("/voter-guide.pdf"):
                self.send_response(307 if self.path == "/" else 301)
                election = (
                    "wa-2026-primary" if "wa-2026-primary" in self.path else "wa-2026-general"
                )
                self.send_header("Location", f"https://seattleelections.guide/e/{election}/")
                self.end_headers()
                return
            path = output / self.path.lstrip("/")
            if self.path.endswith("/"):
                path /= "index.html"
            missing = fault == "missing-audit" and self.path == audit_path
            self.send_response(200 if path.is_file() and not missing else 404)
            self.send_header("Cache-Control", "public, max-age=0, must-revalidate, no-transform")
            self.end_headers()
            if path.is_file() and not missing:
                with suppress(BrokenPipeError, ConnectionResetError):
                    self.wfile.write(path.read_bytes())

    with contextmanager(_start)(Handler) as origin:
        report = run_production_check(
            origin, expected_git_commit=commit, timeout=5, site_manifest=expected
        )
    assert audit_path in requests
    assert report.deployment_contract is not None and report.deployment_contract.ok
    if fault is not None:
        assert not report.ok
        assert any(not check.ok for check in report.presentation_assets)
        return
    assert report.ok, "\n".join(render_summary_lines(report))
    # Unit-test retained-report inventory with the canonical origin; actual HTTP
    # observations above remain loopback evidence, not production acceptance.
    canonical = report.model_copy(update={"base_url": expected.canonical_origin})
    assert complete_strict_report(canonical, expected, commit, False)
    checks = canonical.presentation_assets
    for changed in [
        checks[:-1],
        (*checks, checks[0]),
        tuple(c for c in checks if c.path != audit_path.lstrip("/")),
    ]:
        incomplete = canonical.model_copy(update={"presentation_assets": changed})
        assert not complete_strict_report(incomplete, expected, commit, False)


def test_source12_rejects_wrong_deployment_schema_and_missing_supplement(
    supplemented_site: tuple[Path, Path],
) -> None:
    import copy
    import json

    from election_guide.hosting.models import DeploymentManifest

    output, _ = supplemented_site
    original = json.loads((output / "deployment-manifest.json").read_bytes())
    for fault in ["old-schema", "future-schema", "missing-supplement", "cross-election"]:
        value = copy.deepcopy(original)
        if fault == "old-schema":
            value["schema_version"] = "3.0"
        elif fault == "future-schema":
            value["schema_version"] = "4.0"
        elif fault == "missing-supplement":
            value["elections"][1].pop("precinct_supplement")
        else:
            value["elections"][1]["precinct_supplement"]["election_id"] = "wa-2026-general"
        with pytest.raises(ValueError):
            DeploymentManifest.model_validate(value)


def test_page_without_supplement_provenance_rejects_an_unbound_payload_claim() -> None:
    from election_guide.hosting.supplement_pages import verify_page_supplement

    html = (
        '<head></head><script type="application/json" data-client-payload>'
        '{"precinct_ballot":{"supplement":{"election_id":"wa-2026-primary"}}}'
        "</script>"
    )
    with pytest.raises(ValueError, match="supplement"):
        verify_page_supplement(html, None, None)


@pytest.mark.parametrize("page", ["index.html", "comparisons/index.html"])
@pytest.mark.parametrize("width", [320, 360, 390])
def test_actual_primary_full_name_and_shared_controls_fit_narrow_viewports(
    supplemented_site: tuple[Path, Path], page: str, width: int
) -> None:
    """Local engineering geometry; Root owns final candidate native acceptance."""
    import base64
    import json
    import os
    from typing import Any

    from election_guide.rendering.browser import _CdpSocket  # pyright: ignore[reportPrivateUsage]
    from tests.test_rendering import _evaluate_in_chrome  # pyright: ignore[reportPrivateUsage]

    output, _ = supplemented_site
    path = output / "e/wa-2026-primary" / page
    evidence = Path(os.environ.get("SEG_723_EVIDENCE_DIR", str(path.parent))) / f"narrow-{width}"
    evidence.mkdir(parents=True, exist_ok=True)
    observations: dict[str, Any] = {"html_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def interact(cdp: _CdpSocket, session: str) -> None:
        def ev(script: str) -> Any:
            result = cdp.command(
                "Runtime.evaluate",
                {"expression": script, "returnByValue": True, "awaitPromise": True},
                session_id=session,
            )
            assert "exceptionDetails" not in result, result
            return result["result"].get("value")

        ev(
            "document.fonts.ready.then(()=>new Promise(r=>"
            "requestAnimationFrame(()=>requestAnimationFrame(r))))"
        )
        observations["closed"] = ev("""(()=>{
          const bar=document.querySelector('[data-compact-filters]');
          const opener=bar.querySelector('[data-precinct-open]');
          const rect=bar.getBoundingClientRect();
          const slots=[...bar.querySelectorAll('.compact-filter-controls > *')];
          return {identity:opener.getAttribute('aria-label'),title:opener.title,
            full:opener.querySelector('[data-precinct-name]').textContent,
            short:opener.querySelector('[data-precinct-short]').textContent,
            target:slots.every(s=>{const r=s.getBoundingClientRect();
              return r.width>=44&&r.height>=44&&r.left>=rect.left-1&&r.right<=rect.right+1;}),
            pageFits:document.documentElement.scrollWidth===innerWidth,
            nativeCount:bar.querySelectorAll('select').length,
            labelTexts:[...bar.querySelectorAll('select')].map(s=>
              document.querySelector(`label[for="${s.id}"]`).textContent),
            source:document.querySelector('[data-compact-sources]')!==null,
            countFits:(()=>{const s=bar.querySelector('.filter-control-status');
              return s.scrollWidth<=s.clientWidth+1;})(),
            noAddressMap:document.querySelector('.precinct-info')===null,
            supported:CSS.supports('appearance','base-select')&&
              CSS.supports('selector(::picker(select))')};})()""")
        shot = cdp.command("Page.captureScreenshot", {"format": "png"}, session_id=session)
        (evidence / "closed.png").write_bytes(base64.b64decode(shot["data"]))
        point = ev("""(()=>{
          window.primaryBallotSelect=document.querySelector('[data-filter-native=ballot]');
          const r=primaryBallotSelect.getBoundingClientRect();
          return {x:r.x+r.width/2,y:r.y+r.height/2};})()""")
        for kind in ["mousePressed", "mouseReleased"]:
            cdp.command(
                "Input.dispatchMouseEvent",
                {"type": kind, **point, "button": "left", "clickCount": 1},
                session_id=session,
            )
        observations["picker"] = ev(r"""(()=>{const s=primaryBallotSelect;
          return {open:s.matches(':open'),options:[...s.options].map(o=>({text:o.textContent.trim(),
            height:o.getBoundingClientRect().height,left:o.getBoundingClientRect().left,
            right:o.getBoundingClientRect().right,
            width:o.clientWidth,scrollWidth:o.scrollWidth,font:getComputedStyle(o).fontSize,
            words:(()=>{const words=[],walker=document.createTreeWalker(o,NodeFilter.SHOW_TEXT);
              let node;while((node=walker.nextNode()))
              for(const match of node.textContent.matchAll(/\S+/g)){
                const range=document.createRange();range.setStart(node,match.index);
                range.setEnd(node,match.index+match[0].length);
                const rects=[...range.getClientRects()].filter(r=>r.width>0&&r.height>0);
                words.push({text:match[0],lines:new Set(rects.map(r=>r.top)).size});}
              return words;})()}))};})()""")
        shot = cdp.command("Page.captureScreenshot", {"format": "png"}, session_id=session)
        (evidence / "ballot-picker.png").write_bytes(base64.b64decode(shot["data"]))
        (evidence / "observations.json").write_text(json.dumps(observations, indent=2) + "\n")

    result = _evaluate_in_chrome(
        path,
        "JSON.stringify({done:true})",
        viewport=(width, 844),
        initial_url=path.resolve().as_uri() + "?precinct=SEA+46-1279",
        interact=interact,
    )
    assert result["done"]
    closed = observations["closed"]
    assert closed["identity"] == closed["title"] == "Precinct: SEA 46-1279"
    assert closed["full"] == "SEA 46-1279" and closed["short"] == "46-1279"
    assert (
        closed["target"] and closed["pageFits"] and closed["countFits"] and closed["noAddressMap"]
    )
    assert closed["nativeCount"] == 3 and closed["labelTexts"] == ["View", "Races", "Ballot"]
    assert closed["source"] == (page == "index.html")
    if closed["supported"]:
        picker = observations["picker"]
        assert picker["open"] and len(picker["options"]) > 3
        for option in picker["options"]:
            assert option["height"] >= 44 and option["font"] == "14px"
            assert 0 <= option["left"] < option["right"] <= width
            assert option["scrollWidth"] <= option["width"] + 1
            assert option["words"] and all(w["lines"] == 1 for w in option["words"])


def test_source12_worker_keeps_exact_body_status_security_and_cache_directives(
    supplemented_site: tuple[Path, Path],
) -> None:
    import json
    import subprocess

    output, _ = supplemented_site
    script = r"""
const fs=require('node:fs');
(async()=>{
  const code=fs.readFileSync(process.argv[1],'utf8');
  const moduleUrl=`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`;
  const worker=(await import(moduleUrl)).default;
  const output=[];
  for(const cache of [null,'public, max-age=0, must-revalidate','private, NO-TRANSFORM']){
    const headers={'Content-Type':'text/html','X-Frame-Options':'DENY','ETag':'"original"'};
    if(cache!==null)headers['Cache-Control']=cache;
    const env={ASSETS:{fetch:()=>new Response('literal contact@example.org bytes',{
      status:203,statusText:'Original status',headers})}};
    for(const url of ['https://seattleelections.guide/e/wa-2026-primary/',
      'https://preview.pages.dev/e/wa-2026-primary/','https://seattleelections.guide/missing/']){
      const r=await worker.fetch(new Request(url),env);
      output.push({cache,url,status:r.status,statusText:r.statusText,
        headers:Object.fromEntries(r.headers),body:await r.text()});
    }
  }
  process.stdout.write(JSON.stringify(output));
})();
"""
    result = subprocess.run(
        ["node", "-e", script, str(output / "_worker.js")],
        check=True,
        capture_output=True,
        text=True,
    )
    for observed in json.loads(result.stdout):
        cache = observed["headers"]["cache-control"]
        assert cache.lower().count("no-transform") == 1
        original = observed["cache"]
        if observed["url"].endswith("/missing/"):
            assert observed["status"] == 404
            assert observed["headers"]["x-robots-tag"] == "noindex"
            continue
        expected = (
            original
            if original and "no-transform" in original.lower()
            else (f"{original}, no-transform" if original else "no-transform")
        )
        assert cache == expected
        assert observed["body"] == "literal contact@example.org bytes"
        assert observed["status"] == 203 and observed["statusText"] == "Original status"
        assert observed["headers"]["etag"] == '"original"'
        assert observed["headers"]["x-frame-options"] == "DENY"
        assert (observed["headers"].get("x-robots-tag") == "noindex") == (
            "preview.pages.dev" in observed["url"]
        )


def test_direct_primary_semantic_validation_requires_no_county_address_promise(
    primary11: PublicationViewModel, tmp_path: Path
) -> None:
    from election_guide.rendering.documents import render_race_document
    from election_guide.rendering.validation import validate_rendered_guide
    from tests.test_historical_precinct_supplement import (
        ROOT,
        _admit,  # pyright: ignore[reportPrivateUsage]
    )

    view = primary11.model_copy(update={"precinct_ballot": _admit(ROOT).contract("a" * 40)})
    config = read_rendering_configuration(Path("config/rendering/guide.yaml"))
    path = tmp_path / "guide.html"
    path.write_text(render_html_document(view, config))
    races = {
        r.id: render_race_document(
            view, r.id, public_site_url=config.public_site_url, project_url=config.project_url
        )
        for section in view.guide_sections
        for r in section.races
    }
    report = validate_rendered_guide(view, config, path, [], races)
    check = next(c for c in report.checks if c.id == "html-source-evidence")
    assert check.passed, check.message


def test_actual_primary_direct_only_contract_passes_the_release_screenshot_audit(
    primary11: PublicationViewModel, tmp_path: Path
) -> None:
    from election_guide.rendering.browser import find_chrome, render_screenshot
    from tests.test_historical_precinct_supplement import ROOT, _admit  # pyright: ignore[reportPrivateUsage]

    view = primary11.model_copy(update={"precinct_ballot": _admit(ROOT).contract("a" * 40)})
    config = read_rendering_configuration(Path("config/rendering/guide.yaml"))
    path = tmp_path / "direct-primary.html"
    path.write_text(render_html_document(view, config))
    render_screenshot(
        path,
        tmp_path / "primary.png",
        find_chrome(),
        width=320,
        height=1200,
        expected_race_count=32,
    )
