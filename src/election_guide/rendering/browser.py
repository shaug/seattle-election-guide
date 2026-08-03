"""Drive headless Chrome over the DevTools protocol.

Chrome process management, a minimal CDP client, and the emulated-viewport
capture the validation report references. The in-page probes live here rather
than in `rendering/validation.py` because they are only meaningful inside the
CDP session that runs them; what they assert about a document's own markup is
checked separately, without a browser, by that module.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PIL import Image, ImageChops
from websocket import (  # pyright: ignore[reportUnknownVariableType]
    WebSocket,
    WebSocketException,
    create_connection,  # pyright: ignore[reportUnknownVariableType]
)


def find_chrome() -> Path:
    """Resolve a supported local Chrome or Chromium executable."""
    environment_path = os.environ.get("CHROME_PATH")
    candidates = [
        Path(environment_path) if environment_path else None,
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/google-chrome-stable"),
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    for command in ("google-chrome", "chromium", "chromium-browser"):
        resolved = shutil.which(command)
        if resolved:
            return Path(resolved)
    raise ValueError("Chrome or Chromium is required; set CHROME_PATH to its executable")


# The screen controls are one select and four radios. Issue 97 merged the
# personalization controls into the page-anchored sources tree, so there is
# no longer a Customize button here.
EXPECTED_SCREEN_CONTROL_COUNT = 5


def render_screenshot(
    html_path: Path,
    output_path: Path,
    chrome_path: Path,
    *,
    width: int,
    height: int,
    expected_race_count: int,
    expected_source_count: int,
) -> Path:
    profile = Path(tempfile.mkdtemp(prefix="election-guide-chrome-"))
    try:
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as errors:
            process = subprocess.Popen(
                [
                    str(chrome_path),
                    "--headless=new",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-extensions",
                    "--hide-scrollbars",
                    "--no-first-run",
                    "--allow-file-access-from-files",
                    f"--user-data-dir={profile}",
                    "--remote-debugging-port=0",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=errors,
            )
            try:
                _capture_emulated_viewport(
                    process,
                    profile,
                    html_path.resolve().as_uri(),
                    output_path,
                    width=width,
                    height=height,
                    expected_race_count=expected_race_count,
                    expected_source_count=expected_source_count,
                )
            except (OSError, ValueError, TimeoutError, WebSocketException) as error:
                errors.seek(0)
                detail = errors.read().strip()
                suffix = f": {detail}" if detail else ""
                raise ValueError(f"Chromium screenshot failed: {error}{suffix}") from error
            finally:
                _terminate_process(process)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return output_path


def _capture_emulated_viewport(
    process: subprocess.Popen[bytes],
    profile: Path,
    url: str,
    output_path: Path,
    *,
    width: int,
    height: int,
    expected_race_count: int,
    expected_source_count: int,
) -> None:
    """Capture an exact CSS viewport through Chrome DevTools Protocol.

    Chrome enforces a 500-pixel minimum window width on macOS. Device emulation
    avoids silently cropping a wider layout when a narrower mobile screenshot is
    requested and uses the same path on Linux CI.
    """
    port, browser_path = _wait_for_devtools_endpoint(process, profile)
    websocket = create_connection(
        f"ws://127.0.0.1:{port}{browser_path}",
        timeout=30,
        suppress_origin=True,
        http_no_proxy=["127.0.0.1"],
    )
    try:
        cdp = _CdpSocket(websocket)
        target = cdp.command("Target.createTarget", {"url": "about:blank"})
        target_id = cast(str, target["targetId"])
        attached = cdp.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = cast(str, attached["sessionId"])
        cdp.command(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
                "screenWidth": width,
                "screenHeight": height,
            },
            session_id=session_id,
        )
        cdp.command("Page.enable", session_id=session_id)
        cdp.command("Page.navigate", {"url": url}, session_id=session_id)
        cdp.wait_event("Page.loadEventFired", session_id=session_id)
        # Issue 124 retired the guide-side Times comparison: nothing
        # comparison-shaped may render on a real page. The companion contract —
        # that a link shared before the removal still replays with its token
        # ignored — is a property of the codec, not of a viewport, so it is
        # owned by the lens-url Node tests and by the browser replay test in
        # tests/test_rendering.py rather than repeated per screenshot here.
        residue_probe = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(()=>{"
                    "const bindings=JSON.parse("
                    "document.querySelector('[data-client-payload]').textContent);"
                    "const comparison=bindings.sources.find("
                    "item=>item.panel_role==='comparison');"
                    "const countsAgree=()=>{"
                    "const dialogs=[...document.querySelectorAll('[data-race-detail-dialog]')];"
                    "const wasClosed=dialogs.filter(dialog=>!dialog.open);"
                    "wasClosed.forEach(dialog=>{dialog.open=true;});"
                    "const result=[...document.querySelectorAll("
                    "'.race-detail-source-list')].every(list=>{"
                    "const shown=[...list.children].filter(item=>"
                    "getComputedStyle(item).display!=='none').length;"
                    # Every source list is rendered immediately after the element that
                    # states its count (a <summary> or a heading <div>), so that single
                    # sibling is the only shape this template emits.
                    "const text=list.previousElementSibling?.innerText||'';"
                    "const claimed=Number((text.match(/(\\d+)\\s+source/)||[])[1]);"
                    "return !Number.isFinite(claimed)||claimed===shown;});"
                    "wasClosed.forEach(dialog=>{dialog.open=false;});"
                    "return result;};"
                    "const supportAligned=()=>[...document.querySelectorAll("
                    "'.screen-race-context')].filter(context=>context.offsetParent).every("
                    "context=>{const support=context.querySelector('.support-line');"
                    "const meter=context.closest('[data-publication-race-id]')"
                    "?.querySelector('.screen-meter');"
                    "if(!support||!meter)return true;"
                    "return Math.abs(support.getBoundingClientRect().right-"
                    "meter.getBoundingClientRect().right)<=1;});"
                    "const controlCount=document.querySelectorAll("
                    "'.screen-controls button,.screen-controls select,.screen-controls input')"
                    ".length;"
                    "return JSON.stringify({"
                    "comparisonPublished:Boolean(comparison),"
                    "noComparisonBars:document.querySelectorAll("
                    "'.comparison,.screen-comparisons,[data-display-role=\"comparison\"]')"
                    ".length===0,"
                    # The evidence panel still lists the Times as a source
                    # (a stated non-goal); what must be gone is every
                    # comparison row inside a race's own detail dialog.
                    "noComparisonRows:document.querySelectorAll("
                    '\'.race-detail-source-list [data-source-role="comparison"],'
                    ".race-detail-comparison-badge').length===0,"
                    "noTimesText:!document.querySelector('.screen-guide')"
                    ".innerHTML.includes('Times comparison'),"
                    "countsAgree:countsAgree(),supportAligned:supportAligned(),"
                    "controlCount});"
                    "})()"
                ),
                "returnByValue": True,
            },
            session_id=session_id,
        )
        residue_result = cast(dict[str, Any], residue_probe["result"])
        if "value" not in residue_result:
            raise ValueError(f"comparison removal validation failed: {residue_probe}")
        residue_metrics = cast(dict[str, object], json.loads(cast(str, residue_result["value"])))
        expected_residue = {
            "comparisonPublished": True,
            "noComparisonBars": True,
            "noComparisonRows": True,
            "noTimesText": True,
            "countsAgree": True,
            "supportAligned": True,
            "controlCount": EXPECTED_SCREEN_CONTROL_COUNT,
        }
        if residue_metrics != expected_residue:
            raise ValueError(f"comparison removal validation failed: {residue_metrics}")

        time.sleep(0.2)
        evaluated = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(async()=>JSON.stringify(await (async()=>{"
                    "const pause=()=>new Promise(resolve=>setTimeout(resolve,120));"
                    "const guide=document.querySelector('.screen-guide');"
                    "const filter=document.querySelector('#race-filter');"
                    "const status=document.querySelector('#filter-status');"
                    "const completeFilter=document.querySelector('#complete-filter');"
                    "const contestedFilter=document.querySelector('#contested-filter');"
                    "const viewInputs=[...document.querySelectorAll('input[name=ballot-view]')];"
                    "const binarySelectors=[...document.querySelectorAll("
                    "'.view-setting .segmented-control')];"
                    "const selectorWidths=binarySelectors.map(control=>"
                    "control.getBoundingClientRect().width);"
                    "const cards=[...document.querySelectorAll('[data-publication-race-id]')]"
                    ".filter(card=>getComputedStyle(card).display!=='none'&&"
                    "card.getBoundingClientRect().width>0&&card.getBoundingClientRect().height>0);"
                    "const cardParts=cards.flatMap(card=>[...card.querySelectorAll("
                    "'.screen-race-result,.screen-race-context,.screen-meter')]);"
                    "const meters=[...document.querySelectorAll('.screen-meter')]"
                    ".filter(meter=>getComputedStyle(meter).display!=='none');"
                    # Every meter is left-anchored in every view (issue 115,
                    # item D14a): the label rides the fill's left edge.
                    "const meterAligned=(meter)=>{"
                    "const label=meter.querySelector('strong');const style=getComputedStyle(meter);"
                    "return style.justifyContent==='flex-start'&&"
                    "Boolean(label&&getComputedStyle(label).textAlign==='left');};"
                    "const compactInput=viewInputs.find(input=>input.value==='compact');"
                    "const fullInput=viewInputs.find(input=>input.value==='full');"
                    "const scopedOption=[...filter.options].find(option=>option.value!=='all');"
                    "if(scopedOption){filter.value=scopedOption.value;"
                    "filter.dispatchEvent(new Event('change',{bubbles:true}));}"
                    "compactInput?.click();contestedFilter?.click();await pause();"
                    "const compactCards=cards.filter(card=>!card.hidden);"
                    "const expectedCompactCards=cards.filter(card=>"
                    "(!scopedOption||JSON.parse(card.dataset.filterTokens).includes(scopedOption.value))&&"
                    "card.dataset.contested==='true');"
                    "const compactGrid=[...document.querySelectorAll('.race-grid')].find(grid=>"
                    "!grid.closest('[hidden]'));"
                    "const compactColumns=compactGrid?getComputedStyle(compactGrid)"
                    ".gridTemplateColumns.split(/\\s+/).length:0;"
                    "const expectedCompactColumns=window.innerWidth<=720?2:"
                    "window.innerWidth<=1050?3:4;"
                    "const controlQuery=new URLSearchParams(window.location.search);"
                    "const controls={"
                    "compact:document.documentElement.dataset.ballotView==='compact',"
                    "scopePreserved:Boolean(scopedOption&&filter.value===scopedOption.value),"
                    "contested:Boolean(contestedFilter?.checked),"
                    "pairedSelectors:binarySelectors.length===2&&"
                    "Math.abs(selectorWidths[0]-selectorWidths[1])<=1&&"
                    "binarySelectors.every(control=>{"
                    "const inputs=[...control.querySelectorAll('input[type=radio]')];"
                    "return inputs.length===2&&inputs.filter(input=>input.checked).length===1;}),"
                    "countMatches:compactCards.length===expectedCompactCards.length,"
                    "urlView:controlQuery.get('view')==='compact',"
                    "urlRaces:controlQuery.get('races')==='contested',"
                    "urlFilter:controlQuery.get('filter')===scopedOption?.value,"
                    "denseColumns:compactColumns===expectedCompactColumns,"
                    "noOverflow:document.documentElement.scrollWidth<=window.innerWidth+1,"
                    "compactMetersLeftAligned:compactCards.every(card=>{"
                    "const meter=card.querySelector('.screen-meter');"
                    "return Boolean(meter&&meterAligned(meter));}),"
                    "};"
                    "fullInput?.click();completeFilter?.click();"
                    "filter.value='all';filter.dispatchEvent(new Event('change',{bubbles:true}));"
                    "await pause();controls.reset="
                    "document.documentElement.dataset.ballotView==='full'&&"
                    "filter.value==='all'&&!contestedFilter?.checked&&window.location.search==='';"
                    "controls.fullMetersLeftAligned=meters.every(meter=>"
                    "meterAligned(meter));"
                    "controls.statusAllGrouped=status?.children.length===3&&"
                    "status.lastElementChild?.textContent===' · All Seattle ballot races'&&"
                    "getComputedStyle(status.lastElementChild).whiteSpace==='nowrap';"
                    # Issue 108: the guide has no page-anchored <details>
                    # disclosures left (both the methodology and sources
                    # accordions are gone), so there is nothing left to toggle
                    # or measure here.
                    "const disclosures=[];"
                    "const dialogs=[...document.querySelectorAll('[data-race-detail-dialog]')];"
                    "const firstCard=cards[0];"
                    "const firstLink=firstCard?.querySelector('[data-race-detail-link]');"
                    "const coreRecommendationsLinked=cards.every(card=>{"
                    "const link=card.querySelector("
                    "':scope > .race-card-primary[data-race-detail-link]');"
                    "return Boolean(link&&['.race-office','.screen-race-result',"
                    "'.screen-race-context'].every(selector=>link.querySelector(selector))&&"
                    "!link.textContent?.includes('View endorsements'));});"
                    "const copyButton=firstCard?.querySelector('[data-copy-race-link]');"
                    "const firstDialog=firstCard?.querySelector('[data-race-detail-dialog]');"
                    "const closeButton=firstDialog?.querySelector('[data-close-race-detail]');"
                    "let copiedValue='';"
                    "Object.defineProperty(navigator,'clipboard',{configurable:true,value:{"
                    "writeText:async value=>{copiedValue=value;}}});"
                    "const firstHash=firstLink?.hash||'';"
                    "firstCard.hidden=true;"
                    "history.replaceState(null,'',firstHash);"
                    "window.dispatchEvent(new PopStateEvent('popstate',{state:null}));"
                    "await pause();"
                    "const directRect=firstDialog?.getBoundingClientRect();"
                    "const direct={open:Boolean(firstDialog?.open),"
                    "hash:window.location.hash===firstHash,"
                    "focused:document.activeElement===closeButton,"
                    "filterReset:filter?.value==='all'&&firstCard.hidden===false,"
                    "labelled:Boolean(firstDialog?.getAttribute('aria-labelledby')&&"
                    "firstDialog.getAttribute('aria-labelledby').split(/\\s+/).every("
                    "id=>document.getElementById(id))),"
                    "described:Boolean(firstDialog?.getAttribute('aria-describedby')&&"
                    "document.getElementById(firstDialog.getAttribute('aria-describedby'))),"
                    "sourceRows:new Set(Array.from(firstDialog?.querySelectorAll("
                    "'[data-race-detail-source-code]')||[],row=>row.dataset.raceDetailSourceCode)).size,"
                    "inViewport:Boolean(directRect&&directRect.left>=0&&directRect.top>=0&&"
                    "directRect.right<=window.innerWidth&&directRect.bottom<=window.innerHeight),"
                    "noOverflow:Boolean(firstDialog&&firstDialog.scrollWidth<=firstDialog.clientWidth+1)};"
                    "copyButton?.click();"
                    "await pause();"
                    "const copyStatus=firstDialog?.querySelector('[data-copy-race-status]');"
                    "const copyFeedback=copyStatus?.textContent||'';"
                    "const copyDescription=copyButton?.getAttribute('aria-describedby')||'';"
                    "const copiedLink=copiedValue?new URL(copiedValue):null;"
                    "const copy={copied:copiedValue.endsWith(firstHash),"
                    "pathPreserved:copiedLink?.pathname===window.location.pathname,"
                    "queryPreserved:copiedLink?.search===window.location.search,"
                    "announced:copyFeedback.startsWith('Link copied'),"
                    "inDialog:Boolean(copyStatus&&firstDialog?.contains(copyStatus)),"
                    "described:copyDescription===copyStatus?.id};"
                    "closeButton?.click();"
                    "await pause();"
                    "const directClosed={closed:firstDialog?.open===false,"
                    "hashCleared:window.location.hash==='',focused:document.activeElement===firstLink};"
                    "firstLink?.querySelector('[data-display-role=recommendation]')?.click();"
                    "await pause();"
                    "const ownedOpened=Boolean(firstDialog?.open&&"
                    "window.location.hash===firstHash&&"
                    "document.activeElement===closeButton);"
                    "return {innerWidth:window.innerWidth,innerHeight:window.innerHeight,"
                    "scrollWidth:document.documentElement.scrollWidth,"
                    "guideVisible:Boolean(guide&&getComputedStyle(guide).display!=='none'&&"
                    "guide.getBoundingClientRect().width>0&&guide.getBoundingClientRect().height>0),"
                    "filterVisible:Boolean(filter&&getComputedStyle(filter).display!=='none'&&"
                    "filter.getBoundingClientRect().width>0&&filter.getBoundingClientRect().height>0),"
                    "visibleRaceCount:cards.length,"
                    "cardOverflow:cardParts.filter(part=>part.scrollWidth>part.clientWidth+1||"
                    "(!part.matches('.screen-race-result,.screen-race-context')&&"
                    "part.scrollHeight>part.clientHeight+1)).map(part=>({"
                    "race:part.closest('[data-publication-race-id]')?.dataset.publicationRaceId,"
                    "className:part.className,width:[part.clientWidth,part.scrollWidth],"
                    "height:[part.clientHeight,part.scrollHeight]})),"
                    "metersRightAligned:meters.every(meter=>Math.abs(meter.getBoundingClientRect().right-"
                    "meter.parentElement.getBoundingClientRect().right)<1),"
                    "coreRecommendationsLinked,controls,"
                    "disclosures,dialogCount:dialogs.length,"
                    "copy,"
                    "direct,directClosed,ownedOpened};})()))()"
                ),
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=session_id,
        )
        result = cast(dict[str, Any], evaluated["result"])
        if "value" not in result:
            raise ValueError(f"responsive interaction validation failed: {evaluated}")
        metrics = cast(dict[str, object], json.loads(cast(str, result["value"])))
        cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "setTimeout(()=>document.querySelector("
                    "'[data-race-detail-dialog][open] [data-close-race-detail]')?.click(),0);"
                    "true"
                ),
                "returnByValue": True,
            },
            session_id=session_id,
        )
        time.sleep(0.25)
        traversed_back = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "JSON.stringify((()=>{"
                    "const dialog=document.querySelector('[data-race-detail-dialog]');"
                    "const card=dialog?.closest('[data-publication-race-id]');"
                    "const link=card?.querySelector('[data-race-detail-link]');"
                    "return {ownedClosed:Boolean(dialog?.open===false&&"
                    "window.location.hash===''&&document.activeElement===link)};})())"
                ),
                "returnByValue": True,
            },
            session_id=session_id,
        )
        back_result = cast(dict[str, Any], traversed_back["result"])
        if "value" not in back_result:
            raise ValueError(f"back navigation validation failed: {traversed_back}")
        metrics.update(cast(dict[str, object], json.loads(cast(str, back_result["value"]))))
        cdp.command(
            "Runtime.evaluate",
            {"expression": "setTimeout(()=>history.forward(),0);true", "returnByValue": True},
            session_id=session_id,
        )
        time.sleep(0.25)
        traversed_forward = cdp.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(async()=>{"
                    "const pause=()=>new Promise(resolve=>setTimeout(resolve,120));"
                    "const dialog=document.querySelector('[data-race-detail-dialog]');"
                    "const card=dialog?.closest('[data-publication-race-id]');"
                    "const link=card?.querySelector('[data-race-detail-link]');"
                    "const close=dialog?.querySelector('[data-close-race-detail]');"
                    "const firstHash=link?.hash||'';"
                    "const forwardOpened=Boolean(dialog?.open&&"
                    "window.location.hash===firstHash&&document.activeElement===close);"
                    "history.replaceState(null,'',firstHash);"
                    "dialog?.dispatchEvent(new Event('cancel',{cancelable:true}));"
                    "await pause();"
                    "return JSON.stringify({forwardOpened,escapeClosed:Boolean("
                    "dialog?.open===false&&window.location.hash===''&&"
                    "document.activeElement===link)});})()"
                ),
                "returnByValue": True,
                "awaitPromise": True,
            },
            session_id=session_id,
        )
        forward_result = cast(dict[str, Any], traversed_forward["result"])
        if "value" not in forward_result:
            raise ValueError(f"forward navigation validation failed: {traversed_forward}")
        metrics.update(cast(dict[str, object], json.loads(cast(str, forward_result["value"]))))
        expected_metrics: dict[str, object] = {
            "innerWidth": width,
            "innerHeight": height,
            "scrollWidth": width,
            "guideVisible": True,
            "filterVisible": True,
            "visibleRaceCount": expected_race_count,
            "cardOverflow": [],
            "metersRightAligned": True,
            "coreRecommendationsLinked": True,
            "controls": {
                "compact": True,
                "scopePreserved": True,
                "contested": True,
                "pairedSelectors": True,
                "countMatches": True,
                "urlView": True,
                "urlRaces": True,
                "urlFilter": True,
                "denseColumns": True,
                "noOverflow": True,
                "compactMetersLeftAligned": True,
                "reset": True,
                "statusAllGrouped": True,
                "fullMetersLeftAligned": True,
            },
            "disclosures": [],
            "dialogCount": expected_race_count,
            "copy": {
                "copied": True,
                "pathPreserved": True,
                "queryPreserved": True,
                "announced": True,
                "inDialog": True,
                "described": True,
            },
            "direct": {
                "open": True,
                "hash": True,
                "focused": True,
                "filterReset": True,
                "labelled": True,
                "described": True,
                "sourceRows": expected_source_count,
                "inViewport": True,
                "noOverflow": True,
            },
            "directClosed": {"closed": True, "hashCleared": True, "focused": True},
            "ownedOpened": True,
            "ownedClosed": True,
            "forwardOpened": True,
            "escapeClosed": True,
        }
        if metrics != expected_metrics:
            raise ValueError(f"responsive layout overflowed its viewport: {metrics}")
        captured = cdp.command(
            "Page.captureScreenshot",
            {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
            session_id=session_id,
        )
        encoded = cast(str, captured["data"])
        output_path.write_bytes(base64.b64decode(encoded, validate=True))
        if image_ink_fraction(output_path) <= 0.005:
            raise ValueError("responsive screenshot is blank")
    finally:
        websocket.close()


def _wait_for_devtools_endpoint(process: subprocess.Popen[bytes], profile: Path) -> tuple[int, str]:
    endpoint = profile / "DevToolsActivePort"
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ValueError("Chrome exited before exposing its DevTools endpoint")
        if endpoint.is_file():
            parts = endpoint.read_text(encoding="utf-8").splitlines()
            if len(parts) >= 2:
                return int(parts[0]), parts[1]
        time.sleep(0.05)
    raise TimeoutError("Chrome did not expose its DevTools endpoint")


class _CdpSocket:
    """Minimal request/response client for Chrome's DevTools WebSocket."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._pending: list[dict[str, Any]] = []
        self._next_id = 1

    def command(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        request: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            request["params"] = params
        if session_id is not None:
            request["sessionId"] = session_id
        self._websocket.send(json.dumps(request, separators=(",", ":")))
        response = self._next_matching(lambda message: message.get("id") == request_id)
        if "error" in response:
            raise ValueError(f"CDP {method} failed: {response['error']}")
        return cast(dict[str, Any], response.get("result", {}))

    def wait_event(self, method: str, *, session_id: str) -> None:
        self._next_matching(
            lambda message: (
                message.get("method") == method and message.get("sessionId") == session_id
            )
        )

    def _next_matching(self, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        for index, message in enumerate(self._pending):
            if predicate(message):
                return self._pending.pop(index)
        while True:
            message = self._read_message()
            if predicate(message):
                return message
            self._pending.append(message)

    def _read_message(self) -> dict[str, Any]:
        raw = self._websocket.recv()
        if not isinstance(raw, str):
            raise ValueError("Chrome returned a non-text DevTools message")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Chrome returned a non-object DevTools message")
        return cast(dict[str, Any], value)


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def image_ink_fraction(path: Path) -> float:
    with Image.open(path) as opened:
        image = opened.convert("RGB")
        background = Image.new("RGB", image.size, image.getpixel((0, 0)))
        histogram = ImageChops.difference(image, background).convert("L").histogram()
        return sum(histogram[8:]) / (image.width * image.height)
