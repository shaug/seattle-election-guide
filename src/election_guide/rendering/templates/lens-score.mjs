// Deterministic personalized-lens scoring for a chosen subset of the panel.
//
// This engine reproduces the audited scoring identity from the published
// payload. It never recalculates the pipeline-owned audited values, never
// touches the DOM or the network, and never uses floating point: every share
// is an exact rational, so a threshold comparison can never drift.
//
// Category membership is resolved here rather than in the URL, so a shared
// category link follows current published membership.

const SCORED_STATES = new Set(['endorsement', 'multi_endorsement']);
const NO_ENDORSEMENT_STATE = 'no_endorsement';
const CATEGORY_PREFIX = 'G';

/** An exact rational. BigInt throughout so no share is ever approximated. */
export class Rational {
  constructor(numerator, denominator = 1n) {
    if (denominator === 0n) throw new RangeError('a rational needs a nonzero denominator');
    const sign = denominator < 0n ? -1n : 1n;
    const top = sign * numerator;
    const bottom = sign * denominator;
    const divisor = gcd(top < 0n ? -top : top, bottom);
    this.numerator = top / divisor;
    this.denominator = bottom / divisor;
  }

  static zero() {
    return new Rational(0n);
  }

  /** Parse the published `numerator/denominator` (or integer) form. */
  static parse(value) {
    const text = String(value).trim();
    const [top, bottom = '1'] = text.split('/');
    if (!/^-?\d+$/.test(top) || !/^\d+$/.test(bottom)) {
      throw new SyntaxError(`not an exact rational: ${text}`);
    }
    return new Rational(BigInt(top), BigInt(bottom));
  }

  add(other) {
    return new Rational(
      this.numerator * other.denominator + other.numerator * this.denominator,
      this.denominator * other.denominator,
    );
  }

  divide(other) {
    if (other.numerator === 0n) throw new RangeError('cannot divide a rational by zero');
    return new Rational(this.numerator * other.denominator, this.denominator * other.numerator);
  }

  /** -1, 0, or 1. Cross-multiplied, so no rounding enters the comparison. */
  compare(other) {
    const left = this.numerator * other.denominator;
    const right = other.numerator * this.denominator;
    if (left < right) return -1;
    return left > right ? 1 : 0;
  }

  isZero() {
    return this.numerator === 0n;
  }

  toString() {
    return this.denominator === 1n
      ? `${this.numerator}`
      : `${this.numerator}/${this.denominator}`;
  }
}

function gcd(left, right) {
  let a = left;
  let b = right;
  while (b !== 0n) {
    const next = a % b;
    a = b;
    b = next;
  }
  return a === 0n ? 1n : a;
}

function isCategoryCode(code) {
  return code.startsWith(CATEGORY_PREFIX);
}

/**
 * The single owner of who may enter a personalized score.
 *
 * Read from the published payload rather than from a caller's argument, so
 * every entry point is closed over the panel roles the publication declares.
 * A comparison source is displayed but never scored, and a source the panel
 * does not publish as selectable can never be selected back in.
 */
function panelAdmission(personalization) {
  const forbidden = new Set(personalization.policy.comparison_source_codes);
  return {
    sources: new Map(
      personalization.sources
        .filter((item) => item.selectable && !forbidden.has(item.code))
        .map((item) => [item.code, item]),
    ),
    categories: new Map(
      personalization.categories
        .filter((item) => item.selectable)
        .map((item) => [item.code, item]),
    ),
  };
}

/**
 * Resolve the effective source codes for a selection.
 *
 * Direct selections and selected-category memberships combine as a set union,
 * so a source reached through several categories, or through both a category
 * and a direct pick, contributes exactly once. Anything the panel does not
 * publish as selectable is refused even when the caller asks for it, which is
 * what keeps the comparison source out of every personalized score.
 */
export function resolveSelection(selection, personalization) {
  const { sources: admissible, categories: selectableCategories } = panelAdmission(personalization);

  const effective = new Set();
  const ignored = [];
  const admit = (code) => {
    if (!admissible.has(code)) {
      ignored.push(code);
      return;
    }
    effective.add(code);
  };

  for (const code of selection.categoryCodes ?? []) {
    const category = selectableCategories.get(code);
    if (category === undefined) {
      ignored.push(code);
      continue;
    }
    for (const member of category.member_source_codes) admit(member);
  }
  for (const code of selection.sourceCodes ?? []) {
    if (isCategoryCode(code)) {
      ignored.push(code);
      continue;
    }
    admit(code);
  }
  return { sourceCodes: [...effective].sort(), ignoredCodes: [...new Set(ignored)].sort() };
}

/** Resolve a grade in the audited policy order: tie, then insufficient, then share. */
function gradeFor(scoring, explicitCount, winnerShare, isTied) {
  if (isTied) return 'TIED';
  if (explicitCount < scoring.minimum_explicit_sources || winnerShare === null) {
    return 'Insufficient';
  }
  for (const rule of scoring.grades) {
    const required = rule.minimum_explicit_sources ?? scoring.minimum_explicit_sources;
    if (explicitCount >= required && winnerShare.compare(Rational.parse(rule.minimum_share)) >= 0) {
      return rule.grade;
    }
  }
  throw new RangeError('the published scoring configuration has no applicable grade');
}

/**
 * Score one published race for the effective source codes.
 *
 * A source that is not eligible for this race has no published cell, so it
 * cannot contribute: that is what keeps a legislative-district source out of
 * another district's races even when the caller selects it.
 */
export function scoreRace(race, effectiveCodes, personalization) {
  // Admission is re-derived from the payload here rather than trusted from the
  // argument: the published cells include the comparison source, so a caller
  // that assembles codes without resolveSelection must not be able to score it.
  const admissible = panelAdmission(personalization).sources;
  const selected = new Set([...effectiveCodes].filter((code) => admissible.has(code)));
  const cells = race.cells.filter((cell) => selected.has(cell.source_code));

  const explicit = cells.filter((cell) => SCORED_STATES.has(cell.state));
  const noEndorsement = cells.filter((cell) => cell.state === NO_ENDORSEMENT_STATE);
  const covered = new Set([...explicit, ...noEndorsement].map((cell) => cell.source_code));
  const eligible = race.eligible_source_codes.filter((code) => selected.has(code));

  const support = new Map();
  for (const cell of explicit) {
    for (const [candidateId, points] of Object.entries(cell.allocation)) {
      const current = support.get(candidateId) ?? Rational.zero();
      support.set(candidateId, current.add(Rational.parse(points)));
    }
  }

  let total = Rational.zero();
  for (const points of support.values()) total = total.add(points);

  let maximum = null;
  for (const points of support.values()) {
    if (maximum === null || points.compare(maximum) > 0) maximum = points;
  }
  const winnerIds = maximum === null
    ? []
    : [...support.entries()]
        .filter(([, points]) => points.compare(maximum) === 0)
        .map(([candidateId]) => candidateId)
        .sort();
  const isTied = winnerIds.length > 1;
  const winnerShare = maximum === null || total.isZero() ? null : maximum.divide(total);

  const standings = [...support.entries()]
    .sort(([leftId, leftPoints], [rightId, rightPoints]) => {
      const bySupport = rightPoints.compare(leftPoints);
      return bySupport !== 0 ? bySupport : leftId.localeCompare(rightId);
    })
    .map(([candidateId, points]) => ({
      candidateId,
      supportPoints: points.toString(),
      share: total.isZero() ? null : points.divide(total).toString(),
    }));

  return {
    raceId: race.race_id,
    grade: gradeFor(personalization.scoring, explicit.length, winnerShare, isTied),
    winnerId: winnerIds.length === 1 ? winnerIds[0] : null,
    winnerIds,
    isTied,
    winnerShare: winnerShare === null ? null : winnerShare.toString(),
    explicitCount: explicit.length,
    eligibleCount: eligible.length,
    coveredCount: covered.size,
    missingCodes: eligible.filter((code) => !covered.has(code)),
    noEndorsementCodes: noEndorsement.map((cell) => cell.source_code).sort(),
    confidenceWarningCodes: cells
      .filter((cell) => cell.confidence_warning)
      .map((cell) => cell.source_code)
      .sort(),
    standings,
  };
}

/**
 * Score every published race for one normalized selection.
 *
 * Returns structured results only. Presentation, URLs, and migration are owned
 * elsewhere; this function mutates nothing.
 */
export function scoreSelection(personalization, selection) {
  const resolved = resolveSelection(selection, personalization);
  return {
    sourceCodes: resolved.sourceCodes,
    ignoredCodes: resolved.ignoredCodes,
    races: personalization.races.map((race) =>
      scoreRace(race, resolved.sourceCodes, personalization),
    ),
  };
}
