"""Render the frozen source discovery report from the validated registry."""

from collections import Counter

from election_guide.sources.models import Source, SourceRegistry

CATEGORY_LABELS = {
    "progressive_general": "Progressive/general",
    "democratic_party": "Democratic Party",
    "transportation_urbanism": "Transportation/urbanism",
    "environmental": "Environmental",
    "labor": "Labor",
    "rights_representation": "Rights/representation",
    "comparison": "Comparison",
}


def render_discovery_report(registry: SourceRegistry) -> str:
    """Return a deterministic Markdown report for review and publication."""
    status_counts = Counter(source.discovery.status for source in registry.sources)
    role_counts = Counter(source.panel_role for source in registry.sources)
    lines = [
        "# 2026 Primary Source Discovery Report",
        "",
        f"Panel `{registry.id}` was frozen at `{registry.frozen_at.isoformat()}` before scoring. "
        f"The research cutoff is `{registry.research_cutoff.isoformat()}`; individual access "
        "times are recorded in the machine-readable registry.",
        "",
        (
            f"The preregistration contains **{len(registry.sources)} proposed sources**: "
            f"**{role_counts['consensus']} consensus**, "
            f"**{role_counts['comparison']} comparison**, "
            f"and **{role_counts['excluded']} excluded**. Discovery found "
            f"**{status_counts['published']} official 2026 publications**, "
            f"**{status_counts['not_found']} publication gaps**, "
            f"**{status_counts['access_restricted']} access-restricted sources**, and "
            f"**{status_counts['not_an_endorsement_publisher']} conditional organizations "
            "that do not publish endorsements**."
        ),
        "",
        "Search results were discovery leads only. Every link below is an official organization "
        "URL; no search snippet or third-party list is endorsement evidence. `not_found` means no "
        "official 2026 publication was located, not that the organization made an explicit "
        "no-endorsement decision.",
        "",
        "## Discovery inventory",
        "",
        "| Organization | Category | Panel | Discovery | Official record | "
        "Publication / update date | Media | Eligibility |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for source in registry.sources:
        discovery = source.discovery
        record_url = discovery.canonical_url or discovery.requested_url
        publication_date = _publication_date(source)
        lines.append(
            "| "
            + " | ".join(
                (
                    _escape(source.name),
                    CATEGORY_LABELS[source.category],
                    source.panel_role,
                    discovery.status,
                    f"[official page]({record_url})",
                    publication_date,
                    discovery.media_type or "—",
                    _eligibility(source),
                )
            )
            + " |"
        )

    lines.extend(["", "## Panel decisions", ""])
    for source in registry.sources:
        lines.append(f"- **{source.name} — {source.panel_role}.** {source.panel_reason}")

    gaps = [source for source in registry.sources if source.discovery.status != "published"]
    lines.extend(["", "## Gaps and conditional exclusions", ""])
    for source in gaps:
        lines.append(f"- **{source.name} — {source.discovery.status}.** {source.discovery.notes}")

    redirected = [source for source in registry.sources if source.discovery.redirect_chain]
    lines.extend(["", "## Redirects observed", ""])
    if redirected:
        for source in redirected:
            chain = " → ".join(
                f"[{index + 1}]({url})" for index, url in enumerate(source.discovery.redirect_chain)
            )
            lines.append(f"- **{source.name}:** {chain}")
    else:
        lines.append("No redirects were observed.")

    lines.extend(["", "## Coalition and ownership disclosures", ""])
    for group in registry.overlap_groups:
        members = ", ".join(
            next(source.name for source in registry.sources if source.id == member_id)
            for member_id in group.member_ids
        )
        lines.append(f"- **{group.label}:** {group.description} Members: {members}.")

    lines.extend(
        [
            "",
            "## Frozen eligibility rule",
            "",
            "The seven Seattle-overlapping legislative-district organizations count in the "
            "default consensus only for races specific to their own district. Their broader "
            "endorsements may be retained for audit or category analysis but cannot add party "
            "votes to statewide, countywide, congressional, citywide, municipal-court, ballot-"
            "measure, or precinct races. The Seattle Times remains comparison-only.",
            "",
            "The complete machine-readable record—including requested and canonical URLs, "
            "publication and update dates when available, access times, media types, redirect "
            "chains, evidence locators, and reasons—is "
            "[`config/sources/default.yaml`](../config/sources/default.yaml).",
            "",
        ]
    )
    return "\n".join(lines)


def _publication_date(source: Source) -> str:
    discovery = source.discovery
    if discovery.published_at is None:
        if discovery.updated_at is not None:
            return f"updated {discovery.updated_at.isoformat()}"
        return "—"
    value = discovery.published_at.isoformat()
    if discovery.updated_at is not None:
        value += f" (updated {discovery.updated_at.isoformat()})"
    return value


def _eligibility(source: Source) -> str:
    if source.eligibility.kind == "all_seattle_ballot_races":
        return "Seattle-ballot races"
    if source.eligibility.kind == "jurisdictions_only":
        return ", ".join(source.eligibility.jurisdiction_ids)
    return "None"


def _escape(value: str) -> str:
    return value.replace("|", "\\|")
