# Project: Seattle Election Endorsement Consensus Guide

You are a senior software architect, data engineer, investigative researcher, and information designer.

Build a complete, executable, auditable application that gathers election endorsements from Seattle- and Washington-focused organizations, normalizes them into a canonical dataset, computes transparent consensus metrics, and generates a polished, shareable voter-guide PDF.

The immediate target is the **August 4, 2026 Washington primary election**, with emphasis on races that may appear on ballots within the City of Seattle. The architecture must support future primary, general, special, municipal, county, and statewide elections without requiring substantial rewrites.

This is not a one-off scraping script. It must be a maintainable election-data publishing system with:

- reproducible data collection;
- explicit provenance;
- deterministic normalization;
- auditable calculations;
- human-review workflows;
- automated validation;
- high-quality PDF generation;
- machine-readable outputs;
- documentation sufficient for another engineer to maintain the project.

Do not fabricate endorsements, candidates, races, source URLs, publication dates, or interpretations. When data cannot be verified, preserve the gap explicitly.

---

# 1. Product objective

Produce a voter-guide package that answers:

1. Which candidates or ballot positions were endorsed by each source?
2. Where is there broad consensus among progressive or left-of-center sources?
3. Where do sources meaningfully disagree?
4. What alternative candidates received notable support?
5. Did the Seattle Times editorial board agree or diverge?
6. Which races have insufficient source coverage to support a consensus recommendation?
7. What evidence and source material supports every displayed result?

The primary human-facing artifact is a polished, two-page PDF:

## Page 1: Endorsement consensus cheat sheet

A highly scannable guide showing:

- race;
- consensus candidate or ballot position;
- consensus grade;
- consensus percentage or visual bar;
- number of sources supporting the recommendation;
- notable alternatives;
- explicit no-endorsement signals;
- Seattle Times comparison;
- flags for divided or weak-consensus races.

## Page 2: Methodology and sources

A concise but complete explanation of:

- source categories;
- source inclusion rules;
- normalization;
- dual endorsements;
- no endorsements;
- missing coverage;
- consensus calculation;
- grade thresholds;
- possible coalition overlap;
- Seattle Times treatment;
- limitations;
- publication timestamp;
- data version;
- verification instructions.

The PDF must look like a professional election briefing rather than a spreadsheet export.

---

# 2. Guiding principles

## 2.1 Accuracy before coverage

Never invent or infer an endorsement merely to increase source count.

A source may be marked:

- `endorsed`;
- `dual_endorsement`;
- `multiple_endorsement`;
- `no_endorsement`;
- `declined_to_endorse`;
- `not_covered`;
- `not_published`;
- `unverified`;
- `source_unavailable`;
- `ambiguous`.

Do not collapse these states.

## 2.2 Provenance for every fact

Every normalized endorsement must link back to evidence containing:

- source organization;
- source URL;
- page title;
- publication or update date, when available;
- access timestamp;
- raw captured text or structured extraction;
- selector, heading, table row, screenshot reference, PDF page, or quoted fragment;
- extraction method;
- confidence;
- manual-review status.

A reader or maintainer must be able to reconstruct how each record was produced.

## 2.3 Reproducibility

Running the pipeline against the same captured source material must produce the same normalized data and consensus outputs.

Live-site collection may change over time, so preserve immutable source snapshots or permitted extracts with timestamps and content hashes.

## 2.4 Human review is a feature

Some endorsement pages will be:

- JavaScript-rendered;
- poorly structured;
- image-based;
- PDF-based;
- incomplete;
- updated over time;
- ambiguous about races;
- inconsistent in candidate spelling.

Build an explicit review queue rather than hiding ambiguity.

## 2.5 Transparent heuristics

Consensus is a heuristic synthesis, not a statistical probability.

Do not describe a 90% endorsement share as a 90% chance of electoral victory or candidate quality.

## 2.6 Separation of concerns

Keep these layers independent:

1. election and jurisdiction data;
2. source discovery;
3. raw source capture;
4. extraction;
5. normalization;
6. human overrides;
7. consensus calculation;
8. publication rendering.

A rendering change must not require recollecting or renormalizing data.

---

# 3. Initial source universe

The system must support all of the following source categories and organizations. Verify whether each has published endorsements for the target election.

## 3.1 Progressive editorial and general voter guides

- The Stranger
- The Urbanist
- Progressive Voters Guide
- Fuse Washington
- Working Families Party of Washington

## 3.2 Democratic Party organizations

- Washington State Democrats, where relevant
- King County Democrats
- 32nd Legislative District Democrats
- 34th Legislative District Democrats
- 36th Legislative District Democrats
- 37th Legislative District Democrats
- 43rd Legislative District Democrats
- 46th Legislative District Democrats
- other Democratic legislative-district organizations covering any portion of Seattle
- relevant Democratic constituency caucuses

Do not use one district’s endorsement as evidence for another district’s local legislative race. District organizations may still be relevant to:

- statewide races;
- judicial contests;
- countywide positions;
- Seattle-wide measures;
- federal races overlapping multiple districts.

## 3.3 Transportation, urbanism, and mobility

- Transit Riders Union
- Washington Bikes
- Cascade Bicycle Club, if it independently endorses
- Seattle Subway
- Transportation Choices Coalition, if it endorses
- Disability Mobility Initiative or equivalent organizations, if they publish endorsements

Do not assume Cascade Bicycle Club and Washington Bikes are interchangeable. Record actual organizational ownership and publication responsibility.

## 3.4 Environmental and climate organizations

- Washington Conservation Action
- Sierra Club Washington State Chapter
- Climate Solutions, if it endorses
- environmental justice organizations with published endorsements
- relevant local conservation-voter organizations

## 3.5 Labor organizations

- MLK Labor
- Washington State Labor Council, AFL-CIO
- SEIU locals that publish election endorsements
- UFCW 3000
- AFT Washington
- Washington Education Association, where relevant
- Teamsters or building-trades councils, where relevant
- other major unions with Seattle or King County endorsement programs

Preserve the distinction between:

- labor-council endorsements;
- individual-union endorsements;
- coalition endorsements that already incorporate labor partners.

## 3.6 Rights, representation, and issue organizations

- Planned Parenthood Alliance Advocates
- OneAmerica Votes
- Alliance for Gun Responsibility
- Washington Housing Alliance Action Fund
- LGBTQ+ and Stonewall Democratic organizations
- National Women’s Political Caucus of Washington
- reproductive-rights organizations
- racial-justice organizations
- immigrant-rights organizations
- tenant or housing organizations
- public-safety reform organizations
- accessibility and disability-rights organizations

Include only organizations that actually publish candidate or measure endorsements for this election.

## 3.7 Comparison source

- Seattle Times editorial board

The Seattle Times must be displayed separately from the progressive consensus by default.

It must not affect the primary progressive consensus score unless an alternate scoring configuration explicitly enables that behavior.

---

# 4. Source discovery requirements

Implement a repeatable discovery process.

For each organization:

1. locate the official organization website;
2. find the exact election endorsement page;
3. confirm the election year and election type;
4. distinguish current endorsements from archived or stale pages;
5. capture publication and update dates;
6. record redirects and canonical URLs;
7. record whether the page is:
   - HTML;
   - dynamically rendered HTML;
   - PDF;
   - image;
   - social post;
   - embedded voter guide;
   - external platform;
8. confirm that the content is an official organizational endorsement rather than a news report about the endorsement.

Search-engine snippets are not sufficient evidence.

Social media may be used as primary evidence only when:

- the organization clearly publishes the endorsement through its official account;
- no more authoritative page exists;
- the captured post is preserved with sufficient context.

Create a discovery report listing:

- sources successfully found;
- sources with no 2026 endorsement page;
- sources pending publication;
- inaccessible sources;
- ambiguous sources;
- duplicate or coalition-owned guides;
- sources intentionally excluded and why.

---

# 5. Technical architecture

Use a modern, maintainable stack suitable for a command-line data pipeline and publication build.

Preferred baseline:

- Python 3.12 or newer;
- `uv` for dependency and environment management;
- Pydantic for schemas and validation;
- Typer for CLI commands;
- HTTPX for HTTP fetching;
- Beautiful Soup or selectolax for HTML parsing;
- Playwright for JavaScript-rendered pages;
- PyMuPDF or pypdf for PDF extraction;
- Pillow for image inspection;
- optional OCR only as a last resort;
- DuckDB or SQLite for normalized storage;
- Pandas or Polars for analysis;
- Jinja2 for templates;
- HTML/CSS rendered to PDF through Playwright, WeasyPrint, or another deterministic print-quality engine;
- pytest for testing;
- Ruff for linting and formatting;
- mypy or Pyright for type checking.

Alternative technologies are acceptable when justified in `ARCHITECTURE.md`.

Do not build the final PDF with a rigid spreadsheet-table abstraction unless visual review proves it produces publication-quality output.

---

# 6. Repository structure

Create a coherent structure similar to:

```text
.
├── README.md
├── ARCHITECTURE.md
├── METHODOLOGY.md
├── SOURCE_POLICY.md
├── REVIEW_GUIDE.md
├── CONTRIBUTING.md
├── pyproject.toml
├── uv.lock
├── Makefile
├── .env.example
├── .gitignore
├── config/
│   ├── elections/
│   │   └── wa-2026-primary.yaml
│   ├── sources/
│   │   ├── progressive.yaml
│   │   ├── party.yaml
│   │   ├── transportation.yaml
│   │   ├── environment.yaml
│   │   ├── labor.yaml
│   │   ├── rights.yaml
│   │   └── comparison.yaml
│   ├── scoring/
│   │   └── default.yaml
│   └── rendering/
│       └── pdf.yaml
├── data/
│   ├── raw/
│   ├── snapshots/
│   ├── extracted/
│   ├── normalized/
│   ├── overrides/
│   ├── review/
│   └── published/
├── src/
│   └── election_guide/
│       ├── cli.py
│       ├── models/
│       ├── discovery/
│       ├── collection/
│       ├── extraction/
│       ├── normalization/
│       ├── matching/
│       ├── scoring/
│       ├── validation/
│       ├── rendering/
│       ├── provenance/
│       └── utilities/
├── templates/
│   ├── guide.html.j2
│   ├── methodology.html.j2
│   └── styles/
│       ├── base.css
│       ├── print.css
│       └── theme.css
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   ├── snapshots/
│   └── visual/
├── scripts/
└── build/
```

Adjust where warranted, but preserve clear separation between source material, normalized data, and generated artifacts.

---

# 7. Canonical data model

Define typed schemas for at least the following entities.

## 7.1 Election

Fields should include:

```yaml
id:
name:
election_type:
election_date:
state:
jurisdictions:
official_election_url:
ballot_data_source:
created_at:
updated_at:
```

## 7.2 Jurisdiction

Support:

- country;
- state;
- congressional district;
- county;
- city;
- legislative district;
- judicial district;
- council district;
- precinct or ballot style when needed.

Fields:

```yaml
id:
name:
type:
parent_id:
geometry_reference:
official_identifier:
```

## 7.3 Race

Fields:

```yaml
id:
election_id:
office_name:
office_level:
district:
position_number:
jurisdiction_id:
race_type:
is_partisan:
party:
ballot_title:
short_display_name:
sort_order:
official_source_url:
```

## 7.4 Candidate or ballot option

Fields:

```yaml
id:
race_id:
canonical_name:
display_name:
first_name:
middle_name:
last_name:
suffix:
party:
incumbency:
campaign_url:
official_ballot_name:
aliases:
```

Ballot measures must support options such as:

- Yes;
- No;
- Approve;
- Reject;
- Maintained;
- Repealed.

## 7.5 Endorsement source

Fields:

```yaml
id:
organization_name:
short_name:
category:
subcategory:
official_url:
endorsement_url:
ideological_context:
geographic_scope:
included_in_default_consensus:
comparison_only:
coalition_parent:
possible_overlap_groups:
active:
notes:
```

## 7.6 Raw source capture

Fields:

```yaml
id:
source_id:
url:
canonical_url:
retrieved_at:
http_status:
content_type:
content_hash:
storage_path:
title:
publication_date:
updated_date:
capture_method:
browser_required:
license_or_usage_note:
```

## 7.7 Extracted endorsement claim

Fields:

```yaml
id:
capture_id:
source_id:
raw_race_text:
raw_candidate_text:
raw_status_text:
raw_notes:
evidence_excerpt:
evidence_locator:
extractor:
extractor_version:
extraction_confidence:
requires_review:
```

## 7.8 Normalized endorsement

Fields:

```yaml
id:
election_id:
race_id:
source_id:
status:
candidate_ids:
allocation:
published_at:
source_capture_id:
extracted_claim_id:
normalization_confidence:
manually_verified:
reviewer:
reviewed_at:
notes:
```

## 7.9 Override

Overrides must be data, not hidden code branches.

Fields:

```yaml
id:
target_record_id:
field:
old_value:
new_value:
reason:
evidence:
author:
created_at:
```

## 7.10 Consensus result

Fields:

```yaml
race_id:
configuration_id:
eligible_source_count:
explicit_endorsement_count:
no_endorsement_count:
missing_source_count:
candidate_support:
winner_candidate_id:
winner_support_points:
winner_share:
grade:
is_tied:
notable_alternatives:
comparison_results:
warnings:
computed_at:
input_hash:
```

---

# 8. Election and ballot scope

Do not derive the race universe solely from endorsement pages.

Establish an authoritative election-race inventory using an official Washington or King County election source.

The system must determine which races can appear on ballots in Seattle, including:

- U.S. House districts overlapping Seattle;
- Washington legislative districts overlapping Seattle;
- statewide judicial positions;
- King County offices and council districts;
- Seattle city offices;
- Seattle municipal court;
- ballot measures;
- other relevant district races.

Maintain a jurisdiction-to-race mapping.

A source’s silence must be recorded as `not_covered`, not interpreted as opposition.

The PDF may omit races with no useful source coverage, but omitted races must remain visible in machine-readable audit reports.

---

# 9. Collection pipeline

Implement source adapters with a common interface.

Example:

```python
class SourceAdapter(Protocol):
    source_id: str

    async def discover(self, election: Election) -> DiscoveryResult:
        ...

    async def collect(self, target: SourceTarget) -> RawCapture:
        ...

    def extract(self, capture: RawCapture) -> list[ExtractedClaim]:
        ...
```

Support:

## 9.1 Static HTML

- fetch;
- preserve raw HTML;
- extract main content;
- retain headings, lists, tables, and links.

## 9.2 Dynamic HTML

Use Playwright when static fetching does not contain the endorsement data.

Preserve:

- final DOM;
- screenshot;
- page title;
- loaded URL;
- relevant network or embedded JSON data when useful.

## 9.3 PDFs

Preserve the original PDF and extract:

- page text;
- page references;
- tables;
- links;
- screenshots of relevant pages when necessary.

## 9.4 Images

Use direct visual inspection or OCR only when the source itself publishes image-based endorsements.

Record OCR confidence and require manual review.

## 9.5 Manual-entry adapter

Create a structured, validated mechanism for entering endorsements from:

- user-provided screenshots;
- blocked pages;
- inaccessible paywalled content;
- email communications;
- scanned materials.

Manual data must retain provenance and must not be silently mixed with directly parsed data.

For the Seattle Times, support both:

- parsing the official article when accessible;
- manually transcribing a user-provided screenshot with explicit review metadata.

---

# 10. Extraction and normalization

## 10.1 Candidate matching

Build robust candidate-name matching that handles:

- middle initials;
- punctuation;
- apostrophes;
- accents;
- nicknames;
- suffixes;
- parenthetical preferred names;
- inconsistent capitalization;
- slight spelling differences.

Use:

1. exact alias matches;
2. normalized string matches;
3. constrained fuzzy matching within the same race;
4. manual review for ambiguity.

Never fuzzy-match across unrelated races.

## 10.2 Race matching

Use jurisdiction, office, district, position number, and candidate set.

Maintain aliases such as:

- `WA Supreme Court Position 3`;
- `Washington State Supreme Court, Pos. 3`;
- `Justice of the Supreme Court Position No. 3`.

## 10.3 Endorsement semantics

Correctly distinguish:

- singular endorsement;
- dual endorsement;
- ranked endorsement;
- acceptable-candidate list;
- sole recommendation;
- no endorsement;
- no consensus;
- threshold not met;
- explicit rejection;
- recommendation to vote yes or no;
- recommendation to skip a race.

Do not treat a candidate merely discussed in an article as endorsed.

## 10.4 Source-specific parsers

Prefer explicit source adapters over a single brittle universal scraper.

Each adapter must include tests based on captured fixtures.

---

# 11. Consensus methodology

Implement scoring through configuration.

Provide at least two modes.

## 11.1 Default mode: unweighted progressive consensus

Each included source receives one vote per race.

### Singular endorsement

The endorsed candidate receives `1.0`.

### Dual endorsement

Each candidate receives `0.5`.

### Three-way endorsement

Each receives `1/3`.

### No endorsement

- does not enter the candidate-share denominator;
- increments `no_endorsement_count`;
- appears as a caution signal.

### Missing coverage

- does not enter the denominator;
- is not treated as opposition;
- increments `missing_source_count`.

### Consensus percentage

```text
winning candidate support points
-------------------------------- × 100
total explicit endorsement points
```

Because each explicitly endorsing source contributes one total point, this is equivalent to the winning share of explicit endorsement decisions.

## 11.2 Source-class mode

Provide an optional analysis that reports consensus across source categories:

- editorial;
- party;
- coalition;
- transportation;
- environment;
- labor;
- rights;
- comparison.

Do not silently substitute category weighting for source-level consensus.

Possible output:

```json
{
  "overall_source_share": 0.78,
  "categories_supporting": 5,
  "categories_represented": 7,
  "category_breakdown": {}
}
```

## 11.3 Coalition-overlap analysis

Some voter guides aggregate endorsements from partner organizations.

Record possible dependency or overlap groups.

Examples:

- Progressive Voters Guide and Fuse;
- coalition guides incorporating Washington Conservation Action, Planned Parenthood, labor, or other partners.

Do not attempt to turn this into falsely precise statistical correction.

Instead:

- preserve raw source-level totals;
- optionally report a deduplicated coalition view;
- display a methodology warning;
- include overlap metadata in JSON.

## 11.4 Seattle Times

Default:

- excluded from progressive consensus;
- displayed separately;
- marked as `agrees`, `differs`, `no_endorsement`, or `not_covered`.

A Seattle Times agreement may be described as a broad-consensus signal, not as an additional progressive vote.

## 11.5 Grade thresholds

Implement configurable defaults:

| Grade | Rule |
|---|---|
| A+ | 90–100% and at least four explicit progressive sources |
| A | 75–89% |
| B | 60–74% |
| C | 45–59% |
| D | below 45% |
| Insufficient | fewer than two explicit progressive endorsements |

Add tie handling.

A tied result must not be presented as a singular consensus recommendation.

For ties:

- label `TIED`;
- show all tied candidates;
- show source breakdown;
- assign no ordinary grade unless configuration defines one.

## 11.6 Confidence and coverage

In addition to consensus grade, calculate:

- source coverage count;
- category coverage count;
- no-endorsement count;
- extraction-confidence warnings;
- pending-review count.

A result with high agreement from only two sources must not look equivalent to agreement from twelve sources.

---

# 12. Human-review workflow

Create commands such as:

```bash
election-guide review list
election-guide review show <record-id>
election-guide review approve <record-id>
election-guide review override <record-id>
election-guide review reject <record-id>
```

Produce a review file containing:

- raw source text;
- normalized race;
- normalized candidate;
- confidence;
- competing matches;
- direct evidence link;
- screenshot or PDF locator.

Do not allow publishing when unresolved high-severity review items affect a displayed race, unless an explicit `--allow-unresolved` flag is supplied.

Such builds must contain a visible warning.

---

# 13. Validation requirements

Add validators for:

- endorsement candidate belongs to race;
- race belongs to target election;
- source URL exists;
- evidence capture exists;
- no duplicate source/race decision;
- endorsement allocations sum to 1.0;
- dual endorsements contain multiple candidates;
- no-endorsement records contain no candidate IDs;
- comparison-only sources are excluded from default consensus;
- candidate aliases do not collide within a race;
- publication dates are plausible;
- source snapshot hashes match stored content;
- PDF rows match canonical consensus JSON.

Generate a validation report on every build.

The standard publication build must fail on serious validation errors.

---

# 14. CLI design

Provide a discoverable CLI, such as:

```bash
election-guide init wa-2026-primary
election-guide discover --election wa-2026-primary
election-guide collect --election wa-2026-primary
election-guide extract --election wa-2026-primary
election-guide normalize --election wa-2026-primary
election-guide review list
election-guide score --config default
election-guide validate
election-guide render pdf
election-guide render html
election-guide export json
election-guide export csv
election-guide export xlsx
election-guide build
```

`build` should orchestrate:

1. normalization;
2. scoring;
3. validation;
4. data exports;
5. HTML generation;
6. PDF generation;
7. visual checks;
8. manifest generation.

Do not recollect live websites during a normal publication build unless explicitly requested.

Support:

```bash
election-guide collect --refresh
election-guide build --from-snapshots
```

---

# 15. Output artifacts

The build must produce:

```text
build/
├── Seattle_2026_Primary_Consensus_Guide.pdf
├── Seattle_2026_Primary_Consensus_Guide.html
├── consensus.json
├── race_summary.csv
├── endorsement_records.csv
├── source_metadata.csv
├── unresolved_review_items.csv
├── validation_report.json
├── provenance_manifest.json
├── build_manifest.json
└── Seattle_2026_Primary_Endorsement_Bundle.zip
```

Optionally include:

- XLSX workbook;
- source-comparison matrix;
- screenshots of rendered PDF pages;
- source-coverage report;
- coalition-overlap report.

The ZIP should contain all published artifacts except raw copyrighted page captures when redistribution would be inappropriate.

---

# 16. PDF design requirements

The PDF is a core product, not an afterthought.

Use a proper HTML/CSS print workflow or equivalent vector-capable layout engine.

## 16.1 Format

- US Letter portrait;
- exactly two pages for the standard Seattle guide;
- printable on ordinary home and office printers;
- readable digitally at normal zoom;
- no clipping;
- no content outside safe print margins;
- selectable text;
- accessible document metadata;
- embedded links where supported.

If the number of covered races makes two pages impossible without illegible typography, create:

1. a two-page concise edition;
2. a longer detailed edition.

Do not reduce body text below a reasonable print size merely to satisfy a page-count target.

## 16.2 Page 1: Cheat sheet

Use a full-width editorial layout rather than a conventional spreadsheet.

Organize races by sections such as:

- Federal;
- State Legislature;
- King County;
- Judicial;
- Seattle.

Each race block should include:

- race label;
- recommended candidate or ballot choice;
- consensus percentage, labeled as agreement among explicitly endorsing sources;
- visual consensus bar;
- explicit-source count such as `Based on 8 explicitly endorsing sources`;
- Seattle Times badge and candidate;
- candidate-first affirmative endorsement details with direct evidence links;
- an insufficient-evidence warning only when too few sources explicitly endorse.

Recommended visual pattern:

```text
LD 43 — STATE SENATE

HANNAH SABIO-HOWELL              75% consensus among endorsers
██████████████████░░░░░░

Based on 3 explicitly endorsing sources

Seattle Times  DIFFERENT: Jamie Pedersen
View endorsements: Hannah — The Urbanist, Sierra Club, ...
```

Use compact cards or clearly separated rows.

Optimize for a voter scanning the page while filling out a ballot.

Use both columns for the full available cheat-sheet height. Favor a clean sans-serif hierarchy,
generous but space-aware row padding, differentiated adjacent rows, and fixed-width consensus
tracks that are easy to compare vertically. Keep each race to three visual lines: office; choice
with a right-filled percentage meter; and the Times comparison with the explicitly endorsing source
count aligned beneath the fields they explain. Do not compress the race list into the upper portion
of the page while leaving a large unused region above the footer.

Give fixed-width percentage meters a fine outline, a soft empty track, a restrained teal fill, and a
vertically centered tabular percentage label. The meter should reinforce the number without becoming
the dominant visual element in the row.

## 16.3 Seattle Times comparison chips

Use background color and text together. Never rely on color alone.

Display one concise Seattle Times comparison chip beneath the consensus choice. Use an outlined,
lightly tinted pill with vertically centered contents and typographic hierarchy:

- green or teal `Times agrees · <choice>` chip — agrees with the consensus choice;
- amber or brown `Times differs · <choice>` chip — endorses a different choice;
- neutral `Times · not covered` chip — no Seattle Times endorsement for the race or measure.

Make the status phrase bold, the choice lighter, and the centered-dot separator visually quiet.

Keep the chip directly beneath the consensus choice. Do not add separate `Seattle Times`, `AGREES`,
`DIFFERENT PICK`, or `NO PICK` labels.

## 16.4 Consensus presentation

Do not display letter grades in voter-facing HTML or PDF. A lower consensus share means endorsing
sources are divided; it is not a judgment that a candidate is average or poor. Pair every share
with the number of explicitly endorsing sources and label insufficient evidence directly.

## 16.5 Typography

Use a professional, restrained typographic system.

Requirements:

- strong distinction among title, section, race, recommendation, and metadata;
- sans-serif type throughout the concise print edition;
- no dense wall of uniformly sized text;
- no illegibly small URLs;
- tabular numerals where useful;
- consistent line heights;
- no orphaned section labels;
- no awkward text wrapping in candidate names.

Prefer Trebuchet MS with a portable open-source fallback over Arial so the guide feels contemporary
without bundling or redistributing a licensed font file.

Use only redistributable system or open-source fonts.

Do not include font files in the published bundle unless licensing and redistribution are explicitly addressed.

## 16.6 Color

Use a Seattle-appropriate but restrained palette:

- deep navy;
- civic blue;
- teal;
- amber;
- warm gray;
- off-white;
- accessible red for warnings.

The design must also remain understandable in grayscale.

## 16.7 Page 2: Methodology

Page 2 should use the full page and feel like a designed infographic.

Include:

### How consensus works

A visual process:

```text
Collect official endorsements
        ↓
Preserve source evidence
        ↓
Normalize races and candidates
        ↓
Split multi-candidate endorsements
        ↓
Compute progressive consensus
        ↓
Compare separately with Seattle Times
```

### How to read consensus

Explain that the percentage is the leading choice's share of exact endorsement points among
explicitly endorsing sources, and that it measures agreement rather than candidate quality.

### Source categories

Group sources by:

- progressive editorial;
- coalition;
- Democratic Party;
- transportation and urbanism;
- environment;
- labor;
- rights and representation;
- centrist comparison.

### Interpretation

Explain:

- strong agreement;
- meaningful split;
- low coverage;
- explicit no endorsement;
- Seattle Times convergence;
- Seattle Times divergence.

### Limitations

State that:

- this is an aggregation of endorsements;
- it is not independent candidate vetting;
- sources may overlap;
- organizations update endorsements;
- exact ballots vary by address.

### Metadata

Include:

- election date;
- generated timestamp;
- data version;
- code version or Git commit;
- source count;
- race count;
- unresolved review count;
- project URL when available.

## 16.8 Visual verification

Automate PDF rendering to PNG.

At minimum verify:

- exactly expected page count;
- no blank pages;
- no overflow;
- no content clipped by page bounds;
- adequate contrast;
- no text rendered outside cards;
- all section headers present;
- all expected races present;
- PDF text matches canonical JSON.

Include rendered page images in test artifacts, though not necessarily in the public ZIP.

---

# 17. HTML output

Generate a responsive HTML version from the same view model.

It should:

- work on mobile and desktop;
- preserve the same methodology;
- allow filtering by legislative district or jurisdiction;
- allow expanding a race to view source-by-source endorsements;
- provide links to original source evidence;
- visually distinguish Seattle Times;
- include a print stylesheet matching the PDF.

Do not create separate hand-maintained logic for HTML and PDF.

Both should use the same normalized data and consensus results.

---

# 18. Source matrix and detailed views

Create a complete source-by-race matrix.

Example:

| Race | Urbanist | Stranger | WFP | 36th | 43rd | 46th | KC Dems | TRU | WCA | Labor | Times |
|---|---|---|---|---|---|---|---|---|---|---|---|

Cell states must distinguish:

- endorsement;
- dual endorsement;
- no endorsement;
- not covered;
- unavailable;
- unverified.

This matrix may be exported to CSV, XLSX, and HTML rather than appearing in the concise PDF.

---

# 19. Testing strategy

Implement comprehensive tests.

## 19.1 Unit tests

Test:

- candidate-name normalization;
- race aliases;
- multi-endorsement allocation;
- no-endorsement handling;
- missing-coverage handling;
- grade assignment;
- tie handling;
- Seattle Times comparison;
- source-category analysis;
- coalition overlap metadata;
- provenance creation.

## 19.2 Fixture-based extraction tests

Capture representative source pages and test each adapter against stable local fixtures.

Do not make ordinary test runs depend on live websites.

Include fixtures for:

- HTML lists;
- HTML tables;
- article prose;
- JavaScript-rendered pages;
- PDFs;
- screenshots or manually transcribed records;
- dual endorsements;
- explicit no endorsements;
- pages containing multiple elections.

## 19.3 Integration tests

Test the full path:

```text
fixture capture
→ extracted claims
→ normalized endorsements
→ consensus result
→ HTML
→ PDF
```

## 19.4 Snapshot tests

Snapshot:

- normalized records;
- race summaries;
- rendered HTML fragments;
- PDF text extraction;
- page screenshots where stable.

## 19.5 Visual regression tests

Use rendered PDF page images with a reasonable comparison tolerance.

Detect:

- major layout shifts;
- missing content;
- overflow;
- contrast regressions;
- unexpected extra pages.

---

# 20. Documentation requirements

## README.md

Explain:

- what the project does;
- how to install it;
- how to run the full pipeline;
- how to refresh sources;
- how to review ambiguous records;
- how to generate the PDF;
- where outputs appear;
- known limitations.

## ARCHITECTURE.md

Explain:

- system boundaries;
- data flow;
- adapter architecture;
- snapshot strategy;
- normalization;
- scoring;
- rendering;
- testing.

## METHODOLOGY.md

Document all analytical choices, including:

- source inclusion;
- unweighted scoring;
- dual endorsements;
- no endorsements;
- missing coverage;
- grade thresholds;
- coalition overlap;
- Seattle Times treatment;
- ties;
- low coverage.

## SOURCE_POLICY.md

Document:

- acceptable evidence;
- official versus secondary sources;
- snapshot handling;
- social-media use;
- paywalled content;
- copyrighted material;
- blocked pages;
- manual transcription.

## REVIEW_GUIDE.md

Explain how a human reviewer should:

- verify a race match;
- verify a candidate match;
- assess ambiguous endorsement wording;
- approve or override a record;
- document evidence;
- handle source updates.

## CONTRIBUTING.md

Document how to:

- add a source adapter;
- add a future election;
- add a new jurisdiction;
- modify scoring configuration;
- update the visual design safely.

---

# 21. Auditing and build manifests

Every build must create a manifest including:

```json
{
  "election_id": "wa-2026-primary",
  "generated_at": "...",
  "git_commit": "...",
  "configuration_hash": "...",
  "input_snapshot_hashes": {},
  "normalized_data_hash": "...",
  "consensus_output_hash": "...",
  "source_count": 0,
  "race_count": 0,
  "published_race_count": 0,
  "unresolved_review_count": 0,
  "warnings": []
}
```

The PDF should display a short build version or data timestamp.

---

# 22. Update and refresh strategy

Support incremental refreshes.

The system must identify:

- changed source pages;
- newly published endorsements;
- removed endorsements;
- candidate changes;
- updated source text;
- newly added races;
- previously unresolved records that can now be normalized.

Generate a diff report:

```text
Source: The Urbanist
Changed since: 2026-07-18

Added:
- Race X → Candidate Y

Changed:
- Race A: No endorsement → Candidate B

Removed:
- Race C endorsement
```

Do not overwrite historical snapshots.

---

# 23. Ethical and editorial safeguards

The application is designed to aggregate political endorsements, not impersonate neutral election administration.

The guide must clearly identify itself as:

- an endorsement consensus guide;
- based on selected organizations;
- not an official voter pamphlet;
- not an independent evaluation of all candidates.

Do not obscure source ideology or editorial orientation.

Do not manipulate the consensus by silently:

- omitting disagreeing sources;
- double-counting coalition partners;
- changing weights after seeing results;
- treating missing coverage as opposition;
- presenting ties as singular recommendations.

All configuration choices must be visible in output metadata.

---

# 24. Initial implementation phases

Work in disciplined phases.

## Phase 1: Repository and architecture

Create:

- project structure;
- schemas;
- CLI skeleton;
- configuration system;
- documentation outline;
- test infrastructure.

Deliver an implementation plan before writing all adapters.

## Phase 2: Election inventory

Create the authoritative 2026 primary race and candidate dataset for Seattle-area ballots.

Validate jurisdictions and aliases.

## Phase 3: Source registry and discovery

Populate all candidate sources and produce a discovery report.

Do not yet claim comprehensive endorsement coverage.

## Phase 4: Collection and snapshots

Implement collection adapters and preserve source captures.

## Phase 5: Extraction and normalization

Implement source-specific extractors and the manual-review queue.

## Phase 6: Scoring

Implement unweighted progressive consensus, comparison logic, ties, grades, and coverage metrics.

## Phase 7: Data exports

Generate JSON, CSV, XLSX, and source matrix.

## Phase 8: HTML and PDF design

Build the publication-quality two-page guide and responsive HTML edition.

## Phase 9: Validation and visual QA

Render, inspect, test, and correct the output.

## Phase 10: Final bundle

Produce the ZIP, manifests, documentation, and a final status report.

---

# 25. Definition of done

The project is complete when:

1. A fresh developer can install and run it from the README.
2. The target election has an authoritative race inventory.
3. Every included source has explicit discovery status.
4. Every published endorsement has traceable evidence.
5. Normalization is deterministic and reviewable.
6. No unresolved high-severity ambiguity affects the published guide.
7. Consensus calculations pass tests.
8. Seattle Times is separately represented.
9. The two-page PDF is polished, readable, and visually verified.
10. The HTML and PDF use the same underlying view model.
11. JSON and CSV outputs reproduce all displayed results.
12. The build emits validation and provenance manifests.
13. The project supports future elections through configuration and adapters.
14. No endorsement has been fabricated or inferred from insufficient evidence.

---

# 26. Required initial response

Before implementing, inspect the repository and any provided seed artifacts.

Then respond with:

1. a concise assessment of the existing state;
2. a proposed architecture;
3. an implementation sequence;
4. major risks and unknowns;
5. the files you will create or change;
6. any source-access limitations;
7. the exact acceptance tests you intend to use.

Do not begin with vague assurances.

Do not spend the response describing aspirational possibilities without executable next steps.

After the plan, begin implementation unless a blocking ambiguity makes that impossible.

---

# 27. Seed artifacts

The project may receive some or all of the following:

- an earlier two-page PDF;
- canonical or partial `consensus.json`;
- `race_summary.csv`;
- `endorsement_records.csv`;
- `sources.csv`;
- an XLSX workbook;
- screenshots of inaccessible endorsement articles;
- manual corrections.

Treat them as seed data, not unquestioned truth.

Import them through a documented migration process.

Validate:

- candidate names;
- source URLs;
- race mappings;
- scoring;
- page content;
- timestamps;
- manual transcriptions.

Preserve the original seed files under an immutable import directory.

---

# 28. Final operating instruction

Build the system.

Do not merely propose what it could become.

Write the executable code, tests, documentation, source adapters, validation tools, analysis pipeline, HTML templates, CSS, and PDF renderer.

Run the pipeline.

Inspect the rendered output.

Correct defects.

Deliver the complete repository and generated artifacts with an honest report of:

- what was verified;
- what remains incomplete;
- which sources could not be accessed;
- which records require manual review;
- how to reproduce the build.
