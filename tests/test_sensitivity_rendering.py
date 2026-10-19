from __future__ import annotations

from pathlib import Path

import pytest

from election_guide.publication import build_publication_bundle
from election_guide.rendering import read_rendering_configuration, render_html_document
from election_guide.rendering.browser import _CdpSocket  # pyright: ignore[reportPrivateUsage]
from election_guide.rendering.documents import render_race_document
from election_guide.scoring import score_dataset
from election_guide.scoring.sensitivity import build_sensitivity_report
from tests.sensitivity_fixtures import synthetic_dataset
from tests.test_publication import _snapshot_store  # pyright: ignore[reportPrivateUsage]
from tests.test_rendering import _evaluate_in_chrome  # pyright: ignore[reportPrivateUsage]
from tests.test_scoring import NOW, _configuration  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(
    ("categories", "summary", "material"),
    [
        ([(15, 5)] * 4, "Same leading choice in all tested exclusions.", False),
        ([(11, 9)] * 4, "Close lead; same choice in all tested exclusions.", False),
        ([(2, 1)], "Tied without Synthetic source 0.", True),
    ],
)
def test_existing_pages_show_material_warning_and_complete_all_sources_details(
    tmp_path: Path, categories: list[tuple[int, int]], summary: str, material: bool
) -> None:
    dataset = synthetic_dataset(tmp_path, categories)
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    bundle = build_publication_bundle(
        dataset, consensus, git_commit="fixture", snapshot_root=_snapshot_store(tmp_path, dataset)
    )
    configuration = read_rendering_configuration(
        Path(__file__).parents[1] / "config/rendering/guide.yaml"
    )
    guide = render_html_document(bundle.view_model, configuration)
    race = bundle.view_model.sections[0].races[0]
    page = render_race_document(
        bundle.view_model, race.id, public_site_url="https://seattleelections.guide"
    )
    assert 'id="source-checks"' in page
    assert "Source checks · All sources" in page
    assert summary in page
    assert page.count("data-sensitivity-scenario=") == len(
        build_sensitivity_report(dataset, consensus, git_commit="fixture").races[0].scenarios
    )
    assert ('class="sensitivity-warning"' in guide.split("<script", 1)[0]) == material
    assert "sensitivity_scenarios.csv" in page


def test_warning_resets_and_details_open_from_keyboard_at_mobile_width(tmp_path: Path) -> None:
    dataset = synthetic_dataset(tmp_path, [(2, 1)])
    consensus = score_dataset(dataset, _configuration(), computed_at=NOW)
    bundle = build_publication_bundle(
        dataset, consensus, git_commit="fixture", snapshot_root=_snapshot_store(tmp_path, dataset)
    )
    configuration = read_rendering_configuration(
        Path(__file__).parents[1] / "config/rendering/guide.yaml"
    )
    guide = tmp_path / "guide.html"
    guide.write_text(render_html_document(bundle.view_model, configuration))
    result = _evaluate_in_chrome(
        guide,
        """
      (() => {
        const payload = JSON.parse(document.querySelector('[data-client-payload]').textContent);
        const warning = () => document.querySelector('.sensitivity-warning')
          ?.textContent.trim() ?? null;
        const initial = warning();
        const select = codes => {
          location.hash = `lens=2&mode=s&panel=${payload.panel_id}`
            + `&ph=${payload.panel_hash.slice(0,12)}&data=${payload.data_version}`
            + `&scoring=${payload.scoring.configuration_id}&sel=${codes.join('')}`;
          window.dispatchEvent(new HashChangeEvent('hashchange'));
        };
        select(['s000']);
        const customized = warning();
        select(['s000','s001','s002']);
        return JSON.stringify({initial, customized, reset: warning(),
          overflow: document.documentElement.scrollWidth > innerWidth});
      })()
    """,
        viewport=(360, 780),
    )
    assert result == {
        "initial": "Tied without Synthetic source 0.",
        "customized": None,
        "reset": "Tied without Synthetic source 0.",
        "overflow": False,
    }
    race = bundle.view_model.sections[0].races[0]
    page = tmp_path / "race.html"
    page.write_text(
        render_race_document(
            bundle.view_model, race.id, public_site_url="https://seattleelections.guide"
        )
    )

    def keyboard_open(cdp: _CdpSocket, session: str) -> None:
        cdp.command(
            "Runtime.evaluate",
            {"expression": "document.querySelector('#source-checks summary').focus()"},
            session_id=session,
        )
        cdp.command(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
                "text": "\r",
            },
            session_id=session,
        )
        cdp.command(
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
            session_id=session,
        )

    details = _evaluate_in_chrome(
        page,
        """
      JSON.stringify({
        open: document.querySelector('#source-checks details').open,
        focused: document.activeElement === document.querySelector('#source-checks summary'),
        rows: document.querySelectorAll('[data-sensitivity-scenario]').length,
        overflow: document.documentElement.scrollWidth > innerWidth,
      })
    """,
        viewport=(360, 780),
        interact=keyboard_open,
    )
    assert details == {"open": True, "focused": True, "rows": 3, "overflow": False}
