"""Build one complete, validated rendering generation.

The composition root for the rendering package: render the document, capture
the responsive screenshots, validate both, and publish the result atomically.
The destination must be absent or empty and the generation is staged beside it,
so a failed build never leaves a partial guide behind (docs/RENDERING.md).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from election_guide.publication.models import PublicationViewModel
from election_guide.rendering.browser import find_chrome, render_screenshot
from election_guide.rendering.config import read_rendering_configuration
from election_guide.rendering.documents import render_html_document, render_race_document
from election_guide.rendering.models import RenderingValidationReport
from election_guide.rendering.validation import validate_rendered_guide
from election_guide.serialization import canonical_json_bytes, read_json


@dataclass(frozen=True)
class RenderedGuide:
    html_path: Path
    validation_path: Path
    screenshots: list[Path]
    validation_report: RenderingValidationReport


def build_rendered_guide(
    view_model_path: Path,
    configuration_path: Path,
    output_dir: Path,
    *,
    chrome_path: Path | None = None,
) -> RenderedGuide:
    """Build and validate a complete HTML rendering generation."""
    view_model = PublicationViewModel.model_validate(read_json(view_model_path))
    configuration = read_rendering_configuration(configuration_path)
    resolved_chrome = chrome_path or find_chrome()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink():
        raise ValueError("render output path cannot be a symbolic link")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("render output directory must be absent or empty")
    stage: Path | None = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.render-", dir=output_dir.parent)
    )
    try:
        assert stage is not None
        html_path = stage / configuration.html_filename
        screenshot_dir = stage / "screenshots"
        screenshot_dir.mkdir()
        html_path.write_text(
            render_html_document(view_model, configuration),
            encoding="utf-8",
            newline="\n",
        )
        expected_race_count = sum(len(section.races) for section in view_model.sections)
        screenshots = [
            render_screenshot(
                html_path,
                screenshot_dir / "desktop.png",
                resolved_chrome,
                width=configuration.desktop_width,
                height=configuration.screenshot_height,
                expected_race_count=expected_race_count,
            ),
            render_screenshot(
                html_path,
                screenshot_dir / "mobile.png",
                resolved_chrome,
                width=configuration.mobile_width,
                height=configuration.screenshot_height,
                expected_race_count=expected_race_count,
            ),
        ]
        # The race pages are audited here but not written into the generation.
        # The release bundle is the guide plus its evidence, and `hosting` stages
        # the race pages from this same view model with this same function, so
        # what is validated is exactly what will be published — while the bundle
        # keeps the shape every already-published release has (issue #136).
        race_documents = {
            race.id: render_race_document(
                view_model,
                race.id,
                public_site_url=configuration.public_site_url,
                project_url=configuration.project_url,
            )
            for section in view_model.sections
            for race in section.races
        }
        validation_report = validate_rendered_guide(
            view_model,
            configuration,
            html_path,
            screenshots,
            race_documents,
        )
        validation_path = stage / "rendering_validation_report.json"
        validation_path.write_bytes(canonical_json_bytes(validation_report.model_dump(mode="json")))
        if not validation_report.passed:
            failed = "; ".join(
                f"{check.id}: {check.message}"
                for check in validation_report.checks
                if not check.passed
            )
            raise ValueError(f"rendered guide validation failed: {failed}")
        _set_public_modes(stage)
        if output_dir.exists():
            output_dir.rmdir()
        os.replace(stage, output_dir)
        stage = None
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
    final_screenshots = [output_dir / "screenshots" / path.name for path in screenshots]
    return RenderedGuide(
        html_path=output_dir / configuration.html_filename,
        validation_path=output_dir / "rendering_validation_report.json",
        screenshots=final_screenshots,
        validation_report=validation_report,
    )


def _set_public_modes(root: Path) -> None:
    root.chmod(0o755)
    for path in root.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
