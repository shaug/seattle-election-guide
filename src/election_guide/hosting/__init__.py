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

__all__ = [
    "DeployedElection",
    "DeploymentManifest",
    "PublishedElection",
    "SiteManifest",
    "StagedPagesSite",
    "read_site_manifest",
    "stage_pages_site",
    "verify_staged_pages_site",
]
