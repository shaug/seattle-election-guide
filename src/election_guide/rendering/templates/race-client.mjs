// A race page's wiring (issue #136).
//
// The page the guide's race-detail dialog became. It reads the same lens
// fragment the guide reads, through the same codec and the same address-bar
// owner, and rescores the one race it is about from the same published
// contract — so a reader who arrives from a personalized guide sees their own
// selection here, and can carry it back out again. The fragment never reaches a
// crawler, so the unfurl this page's `og:` tags describe is always the audited
// consensus (rendering/documents.py).
//
// Four regions are lit's, each one an element the server already renders whose
// children lit takes over the first time the reader's selection stops being the
// audited default: the headline's result (just the recommendation's name now —
// its own meter retired in favor of one in every candidate's section,
// docs/METER_V2.md, Chrome geometry; #325), caption, and foot — the guide
// card's own components, from `guide-card.mjs`, because a race page shows the
// same quantities the card showed — and the candidate sections, from
// `race-detail.mjs`, each carrying its own section meter built by this
// module's `candidateMeterViews` call below. Takeover is lazy and one-way, as
// § Rendering's idiom requires for a region whose content is a projection of
// state: an ordinary visit does no DOM work at all, and
// `race-markup-parity.test.mjs` is what makes the audited restore a render
// rather than a saved copy of the server's markup.
//
// Three further elements stay the server's for the life of the page and take
// only their text from lit: the strip's banner status, the link notice, and the
// headline's visually-hidden summary. The first two announce, so an element the
// client created would announce nothing; the third is referenced by
// `aria-describedby`, so its identity has to survive (docs/FRONTEND.md
// § Rendering).
//
// Wiring, not a computing module. Every string it renders comes from
// `guide-format.mjs`, which is pure and tested against the Python renderer it
// mirrors.

import { html, nothing, render } from 'lit-html';
import { candidateMeterViews, raceFootTemplate, raceHeadlineTemplate } from './guide-card.mjs';
import {
  allSourcesSummary,
  countingSummary,
  hasNoMajority,
  raceDetailAccessibleSummary,
  recommendationLabel,
} from './guide-format.mjs';
import { compareRaceResults } from './lens-divergence.mjs';
import { createLensRouter } from './lens-route.mjs';
import { scoreSelection } from './lens-score.mjs';
import {
  isDefaultSelection,
  resolveLensLink,
  resolveSelectedCodes,
  SELECTION_LINK_FAILURE_NOTICE,
  selectionFragment,
  tallyingSourceCodes,
} from './lens-selection.mjs';
import { decodeLensFragment, LEGACY_RACE_PREFIX, lensContext } from './lens-url.mjs';
import { meterEndorsementsFromCells } from './meter-layout.mjs';
import { candidateSectionsTemplate } from './race-detail.mjs';

/** The audited insufficiency warning, as race.html.j2 renders it. */
const AUDITED_INSUFFICIENT_NOTE = 'Too few endorsements to measure agreement.';
/** Its personalized wording: the same shortage, over the reader's own sources. */
const PERSONALIZED_INSUFFICIENT_NOTE =
  'Too few endorsements to measure agreement among your selected sources.';

/**
 * Wire one race page.
 *
 * @param {RacePayload} payload
 */
export function wireRacePage(payload) {
  const router = createLensRouter();
  const personalization = payload.personalization;
  const context = lensContext(payload, payload.data_version);
  const race = payload.race;
  const tallyingCodes = tallyingSourceCodes(payload.sources);
  const memberCodesByCategoryCode = new Map(
    payload.categories.map((category) => [category.code, category.member_source_codes]),
  );
  const panelSourceCodes = payload.sources.map((source) => source.code);
  const labels = new Map(
    race.candidates.map((candidate) => [candidate.candidate_id, candidate.label]),
  );
  // The meter's blocks need a source's display name, which a scored cell
  // carries only as its transport code (docs/FRONTEND.md, The data contract).
  const sourceNameByCode = new Map(payload.sources.map((source) => [source.code, source.name]));
  /** The audited candidate order, which a cleared lens restores exactly. */
  const auditedOrder = race.candidates.map((candidate) => candidate.candidate_id);
  const candidatesById = new Map(
    race.candidates.map((candidate) => [candidate.candidate_id, candidate]),
  );

  /** @param {string} selector */
  const element = (selector) => /** @type {HTMLElement|null} */ (document.querySelector(selector));

  const resultRegion = element('[data-lens-result]');
  const contextRegion = element('[data-lens-context]');
  const footRegion = element('[data-lens-foot]');
  const candidatesRegion = element('[data-race-candidates]');
  // The three elements lit renders into but never replaces; see the module note.
  const bannerStatus = element('[data-lens-banner-status]');
  const lensNotice = element('[data-lens-notice]');
  const summary = element('[data-race-detail-summary]');
  // Shown or hidden rather than rendered, for the same reason: it is the sole
  // leader's heading, and a lens decides whether the race has one.
  const headline = element('[data-race-headline]');
  /** The server's own text, dropped once so lit can own these two text nodes. */
  for (const region of [bannerStatus, lensNotice]) region?.replaceChildren();

  /**
   * The full selectable panel with no direct picks reproduces the published
   * audited consensus exactly (lens-score.mjs's own tested contract), so
   * scoring it once gives the page a structured baseline to diff against
   * instead of a second, independently maintained copy of the audited values.
   */
  const audited =
    personalization === null
      ? null
      : (scoreSelection(personalization, {
          categoryCodes: personalization.categories
            .filter((category) => category.selectable)
            .map((category) => category.code),
          sourceCodes: [],
        }).races.find((scored) => scored.raceId === race.race_id) ?? null);

  /** @type {string[]} */
  let selectedCodes = [...tallyingCodes];
  /** A persistent explanation of how this load resolved its link, when warranted. */
  /** @type {string|null} */
  let notice = null;
  /** Whether lit has taken the four regions over from the server. One-way. */
  let takenOver = false;

  /** A candidate with nothing to show under the current selection: the shared
   * empty-track state (docs/METER_V2.md, Edge states), scoped to this one
   * candidate rather than the whole race. Reachable only under a
   * personalized lens that deselects every one of this candidate's
   * endorsers — the audited default always has units for every candidate
   * `race.candidates` names.
   *
   * @param {string} label
   * @param {string} totalLabel
   * @returns {import('./guide-card.mjs').CandidateMeterView}
   */
  const naMeterView = (label, totalLabel) => ({
    na: true,
    blocks: [],
    contexts: [],
    accessibleLabel: `${label}: No endorsements recorded`,
    countLabel: '0',
    totalLabel,
    percentageLabel: '0%',
  });

  /**
   * One candidate's section, as `race-detail.mjs` renders it.
   *
   * @param {string} candidateId
   * @param {import('./lens-score.mjs').RaceScore} scored
   * @param {ReadonlySet<string>} counted
   * @param {{ views: Map<string, import('./guide-card.mjs').CandidateMeterView>, totalLabel: string }} meters
   * @returns {import('./race-detail.mjs').CandidateSectionView|null}
   */
  const candidateView = (candidateId, scored, counted, meters) => {
    const candidate = candidatesById.get(candidateId);
    if (candidate === undefined) return null;
    const isLeader = scored.winnerIds.includes(candidateId);
    // A sole leader — neither tied nor unscored — is the one candidate the
    // headline names, matching the audited template's own condition.
    const soleLeader =
      scored.grade !== 'Insufficient' && !scored.isTied && scored.winnerId === candidateId;
    const rows = candidate.endorsers.map((row) => ({
      code: row.code,
      name: row.name,
      category: row.category,
      categoryLabel: row.category_label,
      state: row.state,
      panelRole: row.panel_role,
      detailLabel: row.detail_label,
      evidenceUrl: row.evidence_url,
      notCounted: !counted.has(row.code),
    }));
    // A tied leader is every leader the headline does not name. The headline
    // names the sole leader and nobody else, so a tie leaves all of them here —
    // each once, and none of them in the headline's green, which claims a
    // favourite a tie does not have.
    const tied = isLeader && !soleLeader;
    return {
      candidateId,
      label: candidate.label,
      isLeader,
      inHeadline: soleLeader,
      kicker: tied ? 'Tied for lead' : null,
      meter: meters.views.get(candidateId) ?? naMeterView(candidate.label, meters.totalLabel),
      rows,
    };
  };

  /**
   * The order the sections are in, which follows whichever result is displayed
   * rather than the audited default baked into the server's order (#141 item 1).
   * `standings` is already sorted leader-first by the current support, so it
   * supplies that order directly; a candidate with no standing at all — one
   * whose only endorsers are deselected under the active lens — keeps its
   * audited relative position, appended after every scored candidate.
   *
   * @param {import('./lens-score.mjs').RaceScore} scored
   * @returns {string[]}
   */
  const candidateOrder = (scored) => {
    const scoredOrder = scored.standings.map((standing) => standing.candidateId);
    const seen = new Set(scoredOrder);
    return [...scoredOrder, ...auditedOrder.filter((candidateId) => !seen.has(candidateId))];
  };

  /**
   * Render every region from one scored result.
   *
   * `selectedTotal` is null for the audited view model, and that is the only
   * thing that distinguishes the audited restore from a personalized render:
   * it makes the caption read "Based on N endorsing sources" — the server's own
   * wording — and it selects the published candidate order and the published
   * summary below. Three parameters used to carry that one fact, which meant a
   * caller could ask for the audited view in the personalized order; the
   * markup-parity check caught exactly that once, so the distinction is drawn
   * here instead of at the call sites.
   *
   * @param {import('./lens-score.mjs').RaceScore} scored
   * @param {number|null} selectedTotal
   * @param {import('./guide-card.mjs').AllSourcesView|null} allSources
   * @param {readonly string[]} countedCodes
   */
  const renderRace = (scored, selectedTotal, allSources, countedCodes) => {
    const isAudited = selectedTotal === null;
    if (!takenOver) {
      // Takeover is one-way and explicit: the server's markup is dropped once,
      // and lit owns these four regions from now on. Without this, lit would
      // render its own copy after the server's rather than in place of it.
      for (const region of [resultRegion, contextRegion, footRegion, candidatesRegion]) {
        region?.replaceChildren();
      }
      takenOver = true;
    }
    if (resultRegion) {
      render(raceHeadlineTemplate(recommendationLabel(scored, labels)), resultRegion);
    }
    if (contextRegion) {
      // Not the card's `raceContextTemplate`: a card carries a caption because
      // it shows no rows, and this page lists the leader's endorsing sources
      // directly beneath this block, so a count of them would name the length
      // of a list already on screen. The pill is what survives.
      render(
        html`<p class="no-majority-pill" ?hidden=${!hasNoMajority(scored.winnerShare)}>No majority</p>`,
        contextRegion,
      );
    }
    if (footRegion) {
      render(
        raceFootTemplate({
          insufficientNote:
            scored.grade !== 'Insufficient'
              ? null
              : selectedTotal === null
                ? AUDITED_INSUFFICIENT_NOTE
                : PERSONALIZED_INSUFFICIENT_NOTE,
          allSources,
        }),
        footRegion,
      );
    }
    const counted = new Set(countedCodes);
    // The audited restore renders the order the server published, because the
    // audited *renderer* is what it has to reproduce and it breaks a tie
    // differently: `candidate_endorsement_groups` orders equal support by
    // display label, while `standings` orders it by ballot position.
    const order = isAudited ? auditedOrder : candidateOrder(scored);
    // Every candidate's own section meter reads the same shared, once-per-race
    // block layout and paint (docs/METER_V2.md, Chrome geometry; #325) — built
    // here, once, from whichever cells the active lens currently selects,
    // rather than once per section.
    const endorsements = meterEndorsementsFromCells(scored.meterCells, sourceNameByCode, labels);
    const meters = candidateMeterViews(
      endorsements,
      new Set(scored.winnerIds),
      !hasNoMajority(scored.winnerShare),
    );
    // Built by pushing rather than mapped and filtered, because `filter` does
    // not narrow away the null and the cast that would has to name this
    // module's sibling — which esbuild keeps in the bundle as a comment, where
    // `tests/test_frontend_bundle.py` reads it as a surviving import specifier.
    const sections = [];
    for (const candidateId of order) {
      const view = candidateView(candidateId, scored, counted, meters);
      if (view !== null) sections.push(view);
    }
    if (candidatesRegion) render(candidateSectionsTemplate(sections), candidatesRegion);
    // The headline is the sole leader's heading, so it is on screen exactly
    // when there is one. A lens can create that leader or dissolve it into a
    // tie, which is why the element is always in the document and only ever
    // shown or hidden — there would otherwise be nothing here to fill.
    if (headline) headline.hidden = !sections.some((section) => section.inHeadline);
    if (summary) {
      const leaderRows =
        sections.find((section) => section.candidateId === scored.winnerId)?.rows ?? [];
      summary.textContent = isAudited
        ? race.audited_accessible_summary
        : raceDetailAccessibleSummary(
            scored,
            labels,
            selectedTotal,
            leaderRows.filter((row) => !row.notCounted).length,
          );
    }
  };

  /**
   * Put the page back to the audited default, if lit ever took it over.
   *
   * A null selected total is what makes this the audited render, and
   * `renderRace` reads the published order and summary from it — which is why
   * the payload carries them at all.
   */
  const restoreAudited = () => {
    if (!takenOver || audited === null) return;
    renderRace(audited, null, null, tallyingCodes);
  };

  /**
   * Where the Sources link should carry the reader: the page they would edit
   * their selection on, holding the selection they are looking at and this race
   * as the place to come back to. Save returns them to the guide carrying that
   * race target, and the guide forwards it here (`guide-client.mjs`).
   *
   * A rejected encode — an oversized selection is the reachable case — says so
   * rather than silently publishing a link that drops the selection
   * (docs/FRONTEND.md § State and URLs).
   */
  const sourcesHref = () => {
    const result = selectionFragment({
      selectedCodes,
      tallyingCodes,
      raceTarget: `${LEGACY_RACE_PREFIX}${race.race_id}`,
      context,
    });
    if (result.status === 'rejected') notice = SELECTION_LINK_FAILURE_NOTICE;
    const fragment =
      result.status === 'ok' ? result.fragment : `#${LEGACY_RACE_PREFIX}${race.race_id}`;
    return `${payload.sources_page_path}${fragment}`;
  };

  /** Render the strip's text, and point every Sources link at the live selection. */
  const renderChrome = () => {
    const href = sourcesHref();
    if (bannerStatus) {
      const counted = tallyingCodes.filter((code) => selectedCodes.includes(code));
      render(
        html`${countingSummary(
          counted.length,
          tallyingCodes.length,
          !isDefaultSelection(counted, tallyingCodes),
        )}`,
        bannerStatus,
      );
    }
    if (lensNotice) {
      lensNotice.hidden = notice === null;
      render(html`${notice ?? nothing}`, lensNotice);
    }
    for (const link of /** @type {HTMLAnchorElement[]} */ ([
      ...document.querySelectorAll('[data-sources-link]'),
    ])) {
      link.href = href;
    }
  };

  /**
   * Apply one selection to the whole page.
   *
   * @param {readonly string[]} codes
   */
  const applyCodes = (codes) => {
    if (personalization === null || audited === null) return;
    const counted = tallyingCodes.filter((code) => codes.includes(code)).sort();
    const personalized = !isDefaultSelection(counted, tallyingCodes);
    document.documentElement.classList.toggle('lens-personalized', personalized);
    if (!personalized) {
      restoreAudited();
      return;
    }
    const results = scoreSelection(personalization, { categoryCodes: [], sourceCodes: counted });
    const scored = results.races.find((item) => item.raceId === race.race_id);
    if (!scored) return;
    const divergence = compareRaceResults(audited, scored);
    // The compact audited comparison renders only when this race actually
    // diverges, so an unchanged race stays free of redundant audited detail.
    const allSources = divergence.anyChanged
      ? { summary: allSourcesSummary(audited, labels), leaderChanged: divergence.leader }
      : null;
    renderRace(scored, results.sourceCodes.length, allSources, results.sourceCodes);
  };

  /**
   * Apply a decoded (or migrated) selection.
   *
   * @param {import('./lens-url.mjs').LensState|null} selection
   */
  const applySelection = (selection) => {
    selectedCodes = resolveSelectedCodes(selection, memberCodesByCategoryCode, panelSourceCodes);
    notice = null;
    applyCodes(selectedCodes);
    renderChrome();
  };

  const readFragment = () =>
    resolveLensLink(decodeLensFragment(router.fragment(), context), personalization);

  // Computed once, from the page's initial address, for the reason the guide
  // records: a migration or invalid-link explanation describes how this load
  // resolved a shared link, not an ongoing in-page navigation.
  const initial = readFragment();
  if (initial.state !== null) applySelection(initial.state);
  if (initial.notice) notice = initial.notice;
  if (initial.cleanAddress) router.clearFragment();
  renderChrome();

  router.onFragmentChange(() => {
    const outcome = readFragment();
    if (outcome.state) applySelection(outcome.state);
    else renderChrome();
  });
}
