"""Prepare validated election archives for static hosting."""

from election_guide.hosting.models import (
    DeployedElection,
    DeploymentManifest,
    PublishedElection,
    SiteManifest,
)
from election_guide.hosting.pages import (
    StagedPagesSite,
    read_site_manifest,
    stage_pages_site,
    verify_staged_pages_site,
)
from election_guide.hosting.releases import (
    download_release_archive,
    materialize_released_bundle,
    published_release_tags,
    verify_declared_releases_published,
)

__all__ = [
    "DeployedElection",
    "DeploymentManifest",
    "PublishedElection",
    "SiteManifest",
    "StagedPagesSite",
    "download_release_archive",
    "materialize_released_bundle",
    "published_release_tags",
    "read_site_manifest",
    "stage_pages_site",
    "verify_declared_releases_published",
    "verify_staged_pages_site",
]
