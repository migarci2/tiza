/**
 * nema: learner state inference (the vault brain).
 *
 * Pure functions, no imports, no I/O, no clock reads at all: `now` is always
 * passed in, and `deriveState`, `summarize` and `computeNeeds` throw when it is
 * missing or unparsable rather than reading the system clock behind your back.
 * Everything here is deterministic: the same receipts and the same `now` always
 * produce the same state, the same needs and the same need ids. The vault never
 * stores learner state, it derives it from the evidence ledger on every read, so
 * this file is the only place where "what does this learner know" is decided.
 *
 * ---------------------------------------------------------------------------
 * Scoring
 * ---------------------------------------------------------------------------
 *
 * Input: evidence receipts, each wrapped as
 *   { receiptId, payload (EvidenceReceipt, contract 5.4), status, receivedAt }
 * with status `verified` (signature checked), `agent` (recorded by the agent
 * against a rubric, kept but visibly weaker) or `pending` (unknown issuer).
 * Only `verified` and `agent` are counted. Everything else, `pending` included,
 * is ignored entirely: an unknown or unchecked issuer never moves learner state,
 * it only sits in the ledger.
 *
 * Every claim in a receipt is
 *   { concept, ability, evidenceType, result, difficulty }
 * and the receipt carries `conditions.grader`, which decides how much the claim
 * is worth.
 *
 * 1. Ladder. A claim contributes to its own ability and to every lower ability
 *    on the ladder recognize < retrieve < explain < apply < transfer. Passing an
 *    application task is also evidence that you can explain and recall the idea.
 *    `discriminate` is a side ability: it is off the ladder, so a discriminate
 *    claim contributes only to `discriminate`, and nothing contributes to it.
 *
 * 2. Value of one contribution:
 *      value = weight(grader) * resultValue * recency
 *      weight:   deterministic 1, provider-rubric 0.8, agent-assessed 0.6,
 *                self-report 0.3, exposure 0.1 (unknown grader is treated as
 *                exposure, the most conservative reading), then capped by the
 *                optional `weightCap(receipt)`: the grader says how the work
 *                was judged, the cap says how much the judge can be believed.
 *                The vault caps self certified receipts at the self-report
 *                weight, so a page that grades itself deterministically is
 *                still only worth a learner saying "I can do this".
 *      result:   passed 1, partial 0.5, failed -0.5
 *      recency:  exp(-daysSince / 60), so evidence halves in about 42 days and
 *                never quite reaches zero. Future dates are clamped to today.
 *
 * 3. score = sum of contributions. Bands:
 *      >= 1.6 durable, >= 0.9 usable, >= 0.4 fragile, > 0 uncertain, else unknown.
 *    One cap: if the best grader behind an ability is exposure grade (weight
 *    0.1 or less), the band is clamped to `uncertain`. Reading ten pages is not
 *    the same as doing the thing once, and no amount of exposure should ever
 *    certify readiness to a provider.
 *
 * 4. Memory. `passes` counts passed claims at that ability or higher, ignoring
 *    exposure grade claims: reading a page is not a successful recall, so it
 *    neither schedules nor postpones a review.
 *      stabilityDays = min(60, 3 * 2 ** (passes - 1))
 *      nextReview    = lastSuccess + stabilityDays
 *      reviewDue     = nextReview < now
 *    A failed claim dated after the last success resets stabilityDays to 3: the
 *    schedule restarts, it does not keep coasting on old wins. With no assessed
 *    pass at all, lastSuccess, stabilityDays and nextReview are null.
 *
 * 5. Confidence. `high` when score >= 1.2 and the best grader weight >= 0.8,
 *    `medium` when score >= 0.6, otherwise `low`. Confidence is about how much
 *    the evidence can be trusted, the band is about how strong it is.
 *
 * 6. Bookkeeping the planner needs. Each ability also records `passes` (assessed
 *    passes, exposure excluded), `lastFailure`, and the three numbers the
 *    encompassing graph propagates: `gradedPasses`, `gradedScore` and
 *    `lastGradedPass`. A pass is graded when somebody other than the learner
 *    checked it, that is when the grader weight is at least 0.6.
 *
 * ---------------------------------------------------------------------------
 * The encompassing graph
 * ---------------------------------------------------------------------------
 *
 * Contract section 30, from `docs/LEARNING_FAST_NOTES.md`. Flashcards treat
 * knowledge as independent units. Cooking, cryptography and computer
 * architecture are hierarchical: practising a pan sauce also practises
 * emulsions, deglazing and heat control. Math Academy calls the partial version
 * of this Fractional Implicit Repetition, and `applyImplicitRepetition` is our
 * small version of it.
 *
 *   implicit = weight x result x recency x f,  f = concept.encompasses[prereq] ?? 0.5
 *
 * Summed over a concept's graded passes at one ability, that is `f` times the
 * concept's `gradedScore` at that ability. It travels one level, to the direct
 * prerequisites. It travels a second level, at `f squared`, only through a
 * relation the registry marks explicitly with `encompasses`.
 *
 * Two rules keep it honest, and both are load bearing:
 *
 *   - Implicit repetition is repetition. It only reaches an ability the learner
 *     has already produced evidence for. It never invents a first claim about
 *     something nobody ever asked.
 *   - Only graded passes propagate. A learner ticking their own box is not
 *     practice for anything underneath it.
 *
 * The implicit evidence also moves the schedule. Each implicit pass is worth
 * half a pass (a quarter at the second level), and `lastSuccess` moves to the
 * date of the implicit practice, so new learning is the spaced repetition of
 * what sits below it. Implicit passes that predate the concept's own last
 * success are ignored by the schedule: the interval that success set already
 * reflects them.
 *
 * The ledger and the bands report what the learner produced. The encompassing
 * graph is applied when the vault decides what to do next, which is why
 * `computeNeeds` runs it and `deriveState` does not.
 *
 * ---------------------------------------------------------------------------
 * Needs
 * ---------------------------------------------------------------------------
 *
 * A LearningNeed (contract 5.5) is what the vault asks for next. Kinds, with
 * their trigger and base urgency:
 *
 *   retrieve            a review is due for some ability at retrieve or above,
 *                       or for a side ability such as discriminate
 *                       urgency 0.6 + 0.4 * overdueDays / 7, capped at 1
 *   apply               explain is usable or better, apply is fragile or worse   0.7
 *   discriminate        concept has a confusable neighbour, apply or explain is
 *                       usable or better, no discrimination evidence yet        0.65
 *   acquire             an active goal names the concept, or a goal concept
 *                       lists it as a prerequisite, and every ability is unknown 0.5
 *   repair_misconception the vault has one or more recorded misconceptions for
 *                       the concept, all carried in the one need              0.8
 *   reassess            evidence exists but the best grader weight is below 0.6  0.45
 *   transfer            apply is durable and transfer is unknown                 0.35
 *
 *   goalRelevance = 1.5 in an active goal, 1.2 prerequisite of a goal concept,
 *                   else 1
 *   priority      = urgency * goalRelevance / max(2, minutes)
 *
 * Four rules from contract section 30 sit on top of that table:
 *
 *   Edge of mastery. An `acquire` need is only worth doing when every
 *   prerequisite is already usable. When one is not, the work is the weakest
 *   prerequisite, and that is the need the vault issues, with reason
 *   `prerequisite_first` naming the goal it unblocks. The goal concept itself
 *   keeps a quarter urgency need so it never disappears from the panel, marked
 *   `prerequisites_are_not_ready`.
 *
 *   Interference. A `discriminate` need whose confusable neighbour is itself
 *   usable or better is urgent at 0.8 rather than 0.65: the confusion is live,
 *   not hypothetical. Reason `confusable_neighbour_is_strong`.
 *
 *   Illusion of understanding. A concept whose evidence is only exposure or
 *   self report produces a retrieve need with reason `exposure_only`, because
 *   rereading measures recognition and only retrieval measures memory.
 *
 *   Audits, not grades. A failed claim with nothing after it is a node that
 *   needs an intervention, not minus one point. It produces a
 *   `repair_misconception` need when the vault has a misconception on record
 *   for that concept, and a `reassess` need otherwise.
 *
 * Needs are sorted by priority descending. With `budgetMinutes` the list
 * becomes a session, which is a different thing from a list:
 *
 *   Minimum effective dose. Retrieve needs are capped at four minutes, so a
 *   budget holds several retrievals rather than one long exercise. The fill is
 *   greedy by priority and keeps scanning after a need does not fit, so a short
 *   need still rides along behind a long one that was skipped.
 *
 *   Interference. Two confusable concepts never share a session unless one of
 *   them is a `discriminate` need, which is the whole point of that kind. The
 *   need that stays is marked `interference_avoided`.
 *
 *   Interleaving. No two needs on the same concept sit next to each other and
 *   kinds alternate where the session allows it, because choosing the method is
 *   part of the skill. A need pulled ahead of a higher priority one to make that
 *   work is marked `interleaved`.
 *
 * Each need carries the rubric a coach grades it against. The concept registry
 * only defines rubrics for explain, apply and discriminate, so a need whose kind
 * and ability have no entry falls back along the ladder and then to the first
 * rubric the concept has. A need never ships an empty rubric while the concept
 * has one, because `record_agent_assessment` passes a need when every criterion
 * is met, and no criteria at all would be a free pass.
 *
 * Need ids are deterministic: "need_" + a 32 bit FNV-1a hash of concept + kind,
 * in base 36. Calling computeNeeds twice returns the same ids, which is what
 * lets `record_agent_assessment` reject a needId it never issued. One concept
 * therefore yields at most one need of each kind.
 */

export const ABILITY_LADDER = ['recognize', 'retrieve', 'explain', 'apply', 'transfer'];
export const SIDE_ABILITIES = ['discriminate'];
export const ABILITIES = [...ABILITY_LADDER, ...SIDE_ABILITIES];

export const BANDS = ['unknown', 'uncertain', 'fragile', 'usable', 'durable'];

export const WEIGHTS = {
  deterministic: 1,
  'provider-rubric': 0.8,
  'agent-assessed': 0.6,
  'self-report': 0.3,
  exposure: 0.1
};

export const RESULT_VALUES = { passed: 1, partial: 0.5, failed: -0.5 };

export const NEED_KINDS = [
  'acquire',
  'retrieve',
  'apply',
  'transfer',
  'discriminate',
  'repair_misconception',
  'reassess'
];

const DAY_MS = 86400000;
const HALF_LIFE_DAYS = 60;
const BASE_STABILITY_DAYS = 3;
const MAX_STABILITY_DAYS = 60;
const DEFAULT_MINUTES = 4;

/** The fraction of a pass a concept lends to a direct prerequisite by default. */
export const IMPLICIT_FRACTION = 0.5;

/** A pass is graded when somebody other than the learner checked it. */
export const GRADED_WEIGHT = WEIGHTS['agent-assessed'];

/** What one implicit repetition is worth to the review schedule. */
const IMPLICIT_PASS = 0.5;

/** Minimum effective dose: a retrieval is short, so a session can hold several. */
const MAX_RETRIEVE_MINUTES = 4;

/** How far the edge of mastery walk follows prerequisites before it gives up. */
const MAX_PREREQUISITE_WALK = 8;

const BAND_THRESHOLDS = [
  [1.6, 'durable'],
  [0.9, 'usable'],
  [0.4, 'fragile']
];

const NEED_ABILITY = {
  acquire: 'explain',
  retrieve: 'retrieve',
  apply: 'apply',
  transfer: 'transfer',
  discriminate: 'discriminate',
  repair_misconception: 'explain',
  reassess: 'explain'
};

const NEED_URGENCY = {
  acquire: 0.5,
  retrieve: 0.6,
  apply: 0.7,
  transfer: 0.35,
  discriminate: 0.65,
  repair_misconception: 0.8,
  reassess: 0.45
};

/** Copy a person reads, for the reasons that need more than two words. */
const NEED_NOTES = {
  exposure_only: 'You have read about this. You have not retrieved it yet.'
};

const EXERCISE_HINTS = {
  acquire: 'short explanation of the idea, then one worked example',
  retrieve: 'closed book recall, one prompt, no options and no hints',
  apply: 'one small task that forces the idea into use',
  transfer: 'the same idea in a context the learner has not seen before',
  discriminate: 'compare-and-contrast with one concrete failure case',
  repair_misconception: 'confront the misconception with a counterexample, then ask for the corrected rule',
  reassess: 'one deterministic check that confirms or drops the earlier evidence'
};

/**
 * Where a need looks for its rubric when the concept registry has no entry for
 * the need's own kind or ability. Tried in order after `kind` and `ability`.
 */
const RUBRIC_FALLBACK = {
  acquire: ['explain', 'apply', 'discriminate'],
  retrieve: ['explain', 'apply', 'discriminate'],
  apply: ['apply', 'explain', 'discriminate'],
  transfer: ['apply', 'explain', 'discriminate'],
  discriminate: ['discriminate', 'explain', 'apply'],
  repair_misconception: ['explain', 'apply', 'discriminate'],
  reassess: ['explain', 'apply', 'discriminate']
};

/* ------------------------------------------------------------------ utils */

function toMs(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

function resolveNow(options) {
  const ms = toMs(options && options.now);
  if (ms === null) {
    throw new TypeError('nema/inference: options.now is required and must be an ISO date string or epoch milliseconds');
  }
  return ms;
}

function isoFrom(ms) {
  return new Date(ms).toISOString();
}

function round(value, places = 4) {
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
}

/** 32 bit FNV-1a, base 36. Small, stable, no crypto. */
function shortHash(input) {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(36).padStart(7, '0');
}

export function bandRank(band) {
  const index = BANDS.indexOf(band);
  return index === -1 ? 0 : index;
}

export function bestBand(conceptState) {
  if (!conceptState || typeof conceptState !== 'object') return 'unknown';
  let best = 'unknown';
  for (const entry of Object.values(conceptState)) {
    if (!entry || typeof entry.band !== 'string') continue;
    if (bandRank(entry.band) > bandRank(best)) best = entry.band;
  }
  return best;
}

function bandForScore(score) {
  for (const [threshold, band] of BAND_THRESHOLDS) {
    if (score >= threshold) return band;
  }
  return score > 0 ? 'uncertain' : 'unknown';
}

/**
 * The band for a score, with the one cap: evidence that never rose above
 * exposure grade is clamped to `uncertain`, however much of it there is.
 */
function bandFor(score, weight) {
  const band = bandForScore(score);
  if (weight <= WEIGHTS.exposure && bandRank(band) > bandRank('uncertain')) return 'uncertain';
  return band;
}

function confidenceFor(score, weight) {
  if (score >= 1.2 && weight >= 0.8) return 'high';
  if (score >= 0.6) return 'medium';
  return 'low';
}

/**
 * The review schedule for one ability: how long the memory should hold and when
 * it needs touching again. `passes` may be fractional, because an implicit
 * repetition is worth half a pass.
 */
function scheduleFor(passes, lastSuccessMs, lastFailureMs, nowMs) {
  if (lastSuccessMs === null || passes <= 0) {
    return { stabilityDays: null, nextReview: null, reviewDue: false };
  }
  let stabilityDays = Math.min(MAX_STABILITY_DAYS, BASE_STABILITY_DAYS * 2 ** (passes - 1));
  if (lastFailureMs !== null && lastFailureMs > lastSuccessMs) stabilityDays = BASE_STABILITY_DAYS;
  stabilityDays = round(stabilityDays, 2);
  const nextReviewMs = lastSuccessMs + stabilityDays * DAY_MS;
  return { stabilityDays, nextReview: isoFrom(nextReviewMs), reviewDue: nextReviewMs < nowMs };
}

function graderWeight(grader) {
  const weight = WEIGHTS[grader];
  return typeof weight === 'number' ? weight : WEIGHTS.exposure;
}

/**
 * The ceiling one receipt's evidence may reach, from the caller's optional
 * `weightCap(receipt)`. No function, a non number or NaN means no ceiling.
 * A negative ceiling is read as zero, so a cap can silence a receipt but never
 * turn a pass into a penalty.
 */
function capFor(weightCap, receipt) {
  if (typeof weightCap !== 'function') return Infinity;
  const value = weightCap(receipt);
  if (typeof value !== 'number' || Number.isNaN(value)) return Infinity;
  return Math.max(0, value);
}

/** Abilities a claim contributes to: itself plus every lower ladder rung. */
function targetAbilities(ability) {
  const index = ABILITY_LADDER.indexOf(ability);
  if (index >= 0) return ABILITY_LADDER.slice(0, index + 1);
  return SIDE_ABILITIES.includes(ability) ? [ability] : [];
}

function abilityOrder(ability) {
  const index = ABILITIES.indexOf(ability);
  return index === -1 ? ABILITIES.length : index;
}

/* ------------------------------------------------------------ deriveState */

/**
 * Derive learner state from the evidence ledger.
 *
 * @param {Array<{receiptId?: string, payload: object, status?: string, receivedAt?: string}>} receipts
 * @param {{ now?: string|number, weightCap?: (receipt: object) => number }} [options]
 *   `weightCap` is asked, per receipt, for the most that receipt's evidence may
 *   ever be worth. The vault passes the trust tier rule of contract section 21,
 *   which caps a self certified receipt at the self-report weight.
 * @returns {Object} state: { [concept]: { [ability]: { band, score, confidence,
 *   graderWeight, lastSuccess, stabilityDays, nextReview, reviewDue,
 *   evidenceRefs } } }. Concepts and abilities are sorted, so the object is
 *   stable enough to compare or render directly.
 */
export function deriveState(receipts, options = {}) {
  const nowMs = resolveNow(options);
  const weightCap = options.weightCap;
  const buckets = new Map();

  for (const receipt of Array.isArray(receipts) ? receipts : []) {
    if (!receipt || typeof receipt !== 'object') continue;
    // Whitelist, not blacklist: only a checked signature or an agent recorded
    // assessment moves state. Anything else (pending, rejected, a typo, a
    // missing field) sits in the ledger and is ignored here.
    if (receipt.status !== 'verified' && receipt.status !== 'agent') continue;

    const payload = receipt.payload;
    if (!payload || !Array.isArray(payload.claims)) continue;

    const grader = payload.conditions ? payload.conditions.grader : undefined;
    const weight = Math.min(graderWeight(grader), capFor(weightCap, receipt));
    const issuedMs = toMs(payload.issuedAt) ?? toMs(receipt.receivedAt) ?? nowMs;
    const daysSince = Math.max(0, (nowMs - issuedMs) / DAY_MS);
    const recency = Math.exp(-daysSince / HALF_LIFE_DAYS);
    const receiptId = receipt.receiptId || payload.receiptId || null;

    for (const claim of payload.claims) {
      if (!claim || typeof claim.concept !== 'string') continue;
      const resultValue = RESULT_VALUES[claim.result];
      if (typeof resultValue !== 'number') continue;
      const targets = targetAbilities(claim.ability);
      if (targets.length === 0) continue;

      if (!buckets.has(claim.concept)) buckets.set(claim.concept, new Map());
      const conceptBucket = buckets.get(claim.concept);

      for (const ability of targets) {
        if (!conceptBucket.has(ability)) conceptBucket.set(ability, []);
        conceptBucket.get(ability).push({
          value: weight * resultValue * recency,
          weight,
          result: claim.result,
          issuedMs,
          receiptId
        });
      }
    }
  }

  const state = {};
  for (const concept of [...buckets.keys()].sort()) {
    const conceptBucket = buckets.get(concept);
    const abilities = [...conceptBucket.keys()].sort((a, b) => abilityOrder(a) - abilityOrder(b));
    const conceptState = {};
    for (const ability of abilities) {
      conceptState[ability] = summarizeAbility(conceptBucket.get(ability), nowMs);
    }
    state[concept] = conceptState;
  }
  return state;
}

function summarizeAbility(contributions, nowMs) {
  const ordered = [...contributions].sort((a, b) => a.issuedMs - b.issuedMs);

  let score = 0;
  let bestWeight = 0;
  let passes = 0;
  let gradedPasses = 0;
  let gradedScore = 0;
  let lastSuccessMs = null;
  let lastGradedMs = null;
  let lastFailureMs = null;
  const evidenceRefs = [];

  for (const item of ordered) {
    score += item.value;
    if (item.weight > bestWeight) bestWeight = item.weight;
    // Exposure grade evidence never schedules a review: reading a page is not
    // a successful recall, so it must not push the next review away.
    if (item.result === 'passed' && item.weight > WEIGHTS.exposure) {
      passes += 1;
      lastSuccessMs = item.issuedMs;
    }
    // Only a pass somebody else checked lends anything to a prerequisite.
    if (item.result === 'passed' && item.weight >= GRADED_WEIGHT) {
      gradedPasses += 1;
      gradedScore += item.value;
      lastGradedMs = item.issuedMs;
    }
    if (item.result === 'failed') lastFailureMs = item.issuedMs;
    if (item.receiptId && !evidenceRefs.includes(item.receiptId)) evidenceRefs.push(item.receiptId);
  }

  score = round(score);

  const band = bandFor(score, bestWeight);
  const confidence = confidenceFor(score, bestWeight);

  const { stabilityDays, nextReview, reviewDue } = scheduleFor(passes, lastSuccessMs, lastFailureMs, nowMs);

  return {
    band,
    score,
    confidence,
    graderWeight: bestWeight,
    passes,
    gradedPasses,
    gradedScore: round(gradedScore),
    lastSuccess: lastSuccessMs === null ? null : isoFrom(lastSuccessMs),
    lastGradedPass: lastGradedMs === null ? null : isoFrom(lastGradedMs),
    lastFailure: lastFailureMs === null ? null : isoFrom(lastFailureMs),
    stabilityDays,
    nextReview,
    reviewDue,
    evidenceRefs
  };
}

/* --------------------------------------------------------- band reporting */

/** What a provider is allowed to see for a band. */
export function toAssertionStatus(band) {
  if (band === 'durable' || band === 'usable') return 'verified';
  if (band === 'fragile' || band === 'uncertain') return 'uncertain';
  return 'missing';
}

/**
 * Confidence from a band and a score, for callers that do not have the grader
 * mix at hand. deriveState stores a slightly stricter value that also looks at
 * the best grader weight.
 */
export function bandToConfidence(band, score) {
  const value = typeof score === 'number' && Number.isFinite(score) ? score : 0;
  if (band === 'unknown') return 'low';
  if (band === 'durable' || band === 'usable') {
    if (value >= 1.2) return 'high';
    if (value >= 0.6) return 'medium';
    return 'low';
  }
  return value >= 0.6 ? 'medium' : 'low';
}

/** Human readable band changes between two states, for the tool result. */
export function diffStates(before, after) {
  const left = before && typeof before === 'object' ? before : {};
  const right = after && typeof after === 'object' ? after : {};
  const concepts = [...new Set([...Object.keys(left), ...Object.keys(right)])].sort();

  const changes = [];
  for (const concept of concepts) {
    const abilities = [
      ...new Set([...Object.keys(left[concept] || {}), ...Object.keys(right[concept] || {})])
    ].sort((a, b) => abilityOrder(a) - abilityOrder(b));

    for (const ability of abilities) {
      const from = bandAt(left, concept, ability);
      const to = bandAt(right, concept, ability);
      if (from !== to) changes.push({ concept, ability, from, to });
    }
  }
  return changes;
}

function bandAt(state, concept, ability) {
  const entry = state && state[concept] && state[concept][ability];
  return entry && typeof entry.band === 'string' ? entry.band : 'unknown';
}

/* ---------------------------------------------------------------- summary */

/**
 * Counts for the vault summary strip. Band counts are per concept, using the
 * concept's best ability. `reviewsDue` counts concepts with at least one
 * ability whose review date has passed.
 */
export function summarize(state, options = {}) {
  const nowMs = resolveNow(options);
  const source = state && typeof state === 'object' ? state : {};

  const counts = { concepts: 0, durable: 0, usable: 0, fragile: 0, uncertain: 0, unknown: 0, reviewsDue: 0 };

  for (const conceptState of Object.values(source)) {
    if (!conceptState || typeof conceptState !== 'object') continue;
    counts.concepts += 1;
    const band = bestBand(conceptState);
    counts[band] += 1;
    for (const entry of Object.values(conceptState)) {
      if (isReviewDue(entry, nowMs)) {
        counts.reviewsDue += 1;
        break;
      }
    }
  }
  return counts;
}

function isReviewDue(entry, nowMs) {
  if (!entry) return false;
  const nextReviewMs = toMs(entry.nextReview);
  if (nextReviewMs !== null) return nextReviewMs < nowMs;
  return entry.reviewDue === true;
}

/* ------------------------------------------- the encompassing graph */

/**
 * The prerequisites one concept implicitly practises, and by how much.
 *
 * Every direct prerequisite is in, at `concept.encompasses[prereq]` or 0.5.
 * A second level is in only where the registry marked the first hop with
 * `encompasses`, and it is worth the square of that fraction. A direct
 * prerequisite always keeps its own fraction, so a concept reached both ways
 * is counted once, at the level that is closer.
 *
 * @param {object} def a concept from the registry
 * @param {Map<string, object>} registry
 * @returns {Map<string, {fraction: number, level: number}>}
 */
export function encompassedPrereqs(def, registry) {
  const out = new Map();
  if (!def) return out;
  const declared = def.encompasses && typeof def.encompasses === 'object' ? def.encompasses : {};
  const prereqs = Array.isArray(def.prereqs) ? def.prereqs : [];

  for (const prereq of prereqs) {
    if (typeof prereq !== 'string' || prereq === def.id) continue;
    const stated = declared[prereq];
    const fraction = typeof stated === 'number' && stated > 0 ? Math.min(1, stated) : IMPLICIT_FRACTION;
    const current = out.get(prereq);
    if (!current || current.fraction < fraction) out.set(prereq, { fraction, level: 1 });
  }

  for (const prereq of prereqs) {
    const stated = declared[prereq];
    if (typeof stated !== 'number' || !(stated > 0)) continue;
    const fraction = Math.min(1, stated) ** 2;
    const parent = registry.get(prereq);
    for (const grandparent of (parent && Array.isArray(parent.prereqs) ? parent.prereqs : [])) {
      if (typeof grandparent !== 'string' || grandparent === def.id) continue;
      const current = out.get(grandparent);
      if (current && current.level === 1) continue;
      if (!current || current.fraction < fraction) out.set(grandparent, { fraction, level: 2 });
    }
  }
  return out;
}

/**
 * Fractional implicit repetition over the encompassing graph, contract 30.
 *
 * Returns a state where every prerequisite has been credited for the graded
 * passes of the concepts above it: a fraction of their score, half a pass each
 * for the schedule, and their date as a new `lastSuccess` when it is later than
 * the one the prerequisite earned itself. The input is never mutated, and a
 * call with no registry returns the state it was given.
 *
 * Nothing here invents a claim. Implicit repetition only reaches an ability the
 * learner already has evidence for, so the set of concepts and abilities in the
 * result is exactly the set that went in.
 *
 * @param {object} state derived state
 * @param {{ concepts?: Array, now?: string|number }} [options]
 * @returns {object} state with the implicit evidence folded in
 */
export function applyImplicitRepetition(state, options = {}) {
  const nowMs = resolveNow(options);
  const source = state && typeof state === 'object' ? state : {};
  const concepts = Array.isArray(options.concepts) ? options.concepts : [];
  if (concepts.length === 0) return source;

  const registry = new Map();
  for (const concept of concepts) {
    if (concept && typeof concept.id === 'string') registry.set(concept.id, concept);
  }

  // conceptId -> ability -> { score, weight, passes, atMs, from: Set }
  const credit = new Map();
  const creditFor = (conceptId, ability) => {
    if (!credit.has(conceptId)) credit.set(conceptId, new Map());
    const abilities = credit.get(conceptId);
    if (!abilities.has(ability)) {
      abilities.set(ability, { score: 0, weight: 0, passes: 0, atMs: null, from: new Set() });
    }
    return abilities.get(ability);
  };

  for (const [conceptId, conceptState] of Object.entries(source)) {
    const def = registry.get(conceptId);
    if (!def || !conceptState || typeof conceptState !== 'object') continue;
    const edges = encompassedPrereqs(def, registry);
    if (edges.size === 0) continue;

    for (const [ability, entry] of Object.entries(conceptState)) {
      if (!entry || !(entry.gradedPasses > 0)) continue;
      const gradedAtMs = toMs(entry.lastGradedPass);

      for (const [prereqId, edge] of edges) {
        const prereqState = source[prereqId];
        // Implicit repetition is repetition: it strengthens what the learner has
        // already been asked for, it never opens a new ability.
        if (!prereqState || !prereqState[ability]) continue;

        const bucket = creditFor(prereqId, ability);
        bucket.score += edge.fraction * entry.gradedScore;
        bucket.weight = Math.max(bucket.weight, edge.fraction * entry.graderWeight);
        bucket.from.add(conceptId);

        // The schedule only moves for practice newer than the prerequisite's own
        // last success. Anything older is already inside the interval that
        // success set.
        const ownSuccessMs = toMs(prereqState[ability].lastSuccess);
        if (gradedAtMs === null) continue;
        if (ownSuccessMs !== null && gradedAtMs <= ownSuccessMs) continue;
        bucket.passes += entry.gradedPasses * IMPLICIT_PASS ** edge.level;
        if (bucket.atMs === null || gradedAtMs > bucket.atMs) bucket.atMs = gradedAtMs;
      }
    }
  }

  if (credit.size === 0) return source;

  const result = {};
  for (const conceptId of Object.keys(source)) {
    const conceptState = source[conceptId];
    const abilities = credit.get(conceptId);
    if (!abilities) {
      result[conceptId] = conceptState;
      continue;
    }
    const next = {};
    for (const [ability, entry] of Object.entries(conceptState)) {
      const bucket = abilities.get(ability);
      next[ability] = bucket ? creditedEntry(entry, bucket, nowMs) : entry;
    }
    result[conceptId] = next;
  }
  return result;
}

/** One ability's entry with its implicit credit folded in. */
function creditedEntry(entry, bucket, nowMs) {
  const score = round(entry.score + bucket.score);
  const graderWeight = Math.max(entry.graderWeight, round(bucket.weight));
  const passes = round(entry.passes + bucket.passes, 3);

  const ownSuccessMs = toMs(entry.lastSuccess);
  const lastSuccessMs = bucket.atMs !== null && (ownSuccessMs === null || bucket.atMs > ownSuccessMs)
    ? bucket.atMs
    : ownSuccessMs;

  const schedule = scheduleFor(passes, lastSuccessMs, toMs(entry.lastFailure), nowMs);

  return {
    ...entry,
    band: bandFor(score, graderWeight),
    score,
    confidence: confidenceFor(score, graderWeight),
    graderWeight,
    passes,
    lastSuccess: lastSuccessMs === null ? null : isoFrom(lastSuccessMs),
    stabilityDays: schedule.stabilityDays,
    nextReview: schedule.nextReview,
    reviewDue: schedule.reviewDue,
    implicit: {
      score: round(bucket.score),
      passes: round(bucket.passes, 3),
      from: [...bucket.from].sort()
    }
  };
}

/* ------------------------------------------------------------ needs */

/**
 * Turn learner state into an ordered list of LearningNeed objects.
 *
 * @param {object} state derived state
 * @param {{ concepts?: Array, goals?: Array, misconceptions?: Array,
 *           now?: string|number, budgetMinutes?: number }} [options]
 * @returns {Array} needs, highest priority first
 */
export function computeNeeds(state, options = {}) {
  const nowMs = resolveNow(options);
  const ledgerState = state && typeof state === 'object' ? state : {};
  const concepts = Array.isArray(options.concepts) ? options.concepts : [];
  const goals = Array.isArray(options.goals) ? options.goals : [];
  const misconceptions = Array.isArray(options.misconceptions) ? options.misconceptions : [];

  const registry = new Map();
  for (const concept of concepts) {
    if (concept && typeof concept.id === 'string') registry.set(concept.id, concept);
  }

  // What the learner practised implicitly counts before anything is planned.
  const source = applyImplicitRepetition(ledgerState, { concepts, now: nowMs });

  const goalConcepts = new Set();
  const goalPrereqs = new Set();
  for (const goal of goals) {
    for (const id of (goal && Array.isArray(goal.concepts) ? goal.concepts : [])) {
      goalConcepts.add(id);
      const def = registry.get(id);
      for (const prereq of (def && Array.isArray(def.prereqs) ? def.prereqs : [])) {
        goalPrereqs.add(prereq);
      }
    }
  }

  const misconceptionsByConcept = new Map();
  for (const item of misconceptions) {
    if (!item || typeof item.concept !== 'string') continue;
    if (!misconceptionsByConcept.has(item.concept)) misconceptionsByConcept.set(item.concept, []);
    misconceptionsByConcept.get(item.concept).push({
      id: item.id || null,
      text: item.text || ''
    });
  }

  const ids = [...new Set([...registry.keys(), ...Object.keys(source)])].sort();
  const needs = [];
  const redirected = new Map();

  for (const conceptId of ids) {
    const def = registry.get(conceptId) || null;
    const conceptState = source[conceptId] || {};
    const hasEvidence = Object.keys(conceptState).length > 0;
    const band = (ability) => bandAt(source, conceptId, ability);
    const context = { conceptId, def, goalConcepts, goalPrereqs };

    // retrieve: a review is due, or the only evidence is somebody reading.
    // Both are one need per concept, so they share a reason list.
    const overdue = worstOverdue(conceptState, nowMs);
    const exposureOnly = hasEvidence && bestGraderWeight(conceptState) <= WEIGHTS['self-report'];
    if (overdue !== null || exposureOnly) {
      const reason = [];
      let urgency = NEED_URGENCY.retrieve;
      let ability = NEED_ABILITY.retrieve;
      if (overdue !== null) {
        const days = Math.max(0, Math.round(overdue.days * 10) / 10);
        reason.push('spaced_review_is_due', `overdue_by_${days}_days`);
        urgency = Math.min(1, 0.6 + (0.4 * overdue.days) / 7);
        ability = overdue.ability;
      }
      // The illusion of understanding: rereading measures recognition, and only
      // retrieval measures memory.
      if (exposureOnly) reason.push('exposure_only');
      needs.push(buildNeed(context, 'retrieve', { ability, urgency, reason }));
    }

    // apply: can explain it, cannot yet use it.
    if (bandRank(band('explain')) >= bandRank('usable') && bandRank(band('apply')) <= bandRank('fragile')) {
      needs.push(buildNeed(context, 'apply', {
        reason: ['explanation_is_solid', 'application_is_weak']
      }));
    }

    // discriminate: strong enough to be confused with a neighbour. When that
    // neighbour is strong too the confusion is live rather than hypothetical,
    // and telling them apart is as urgent as repairing a misconception.
    const confusable = firstConfusable(def);
    const strongEnough = bandRank(band('apply')) >= bandRank('usable')
      || bandRank(band('explain')) >= bandRank('usable');
    if (confusable && strongEnough && !conceptState.discriminate) {
      const neighbourIsStrong = bandRank(bestBand(source[confusable])) >= bandRank('usable');
      needs.push(buildNeed(context, 'discriminate', {
        reason: neighbourIsStrong
          ? ['application_is_strong', 'no_discrimination_evidence', 'confusable_neighbour_is_strong']
          : ['application_is_strong', 'no_discrimination_evidence'],
        urgency: neighbourIsStrong ? 0.8 : NEED_URGENCY.discriminate,
        confusableWith: confusable
      }));
    }

    // acquire: a goal depends on it and there is nothing at all. Only at the
    // edge of mastery, which means every prerequisite is already usable.
    const inGoalScope = goalConcepts.has(conceptId) || goalPrereqs.has(conceptId);
    const allUnknown = bandRank(bestBand(conceptState)) === 0;
    if (inGoalScope && allUnknown) {
      const blocking = weakestPrerequisite(conceptId, registry, source);
      if (blocking === null) {
        needs.push(buildNeed(context, 'acquire', {
          reason: ['goal_depends_on_this_concept', 'no_evidence_yet']
        }));
      } else {
        // The work is the prerequisite. The goal keeps a quarter urgency need so
        // it stays visible, and never outranks the thing that unblocks it.
        if (!redirected.has(blocking)) redirected.set(blocking, new Set());
        redirected.get(blocking).add(conceptId);
        needs.push(buildNeed(context, 'acquire', {
          urgency: NEED_URGENCY.acquire / 2,
          reason: [
            'goal_depends_on_this_concept',
            'prerequisites_are_not_ready',
            `start_with_${plainId(blocking)}`
          ]
        }));
      }
    }

    // repair_misconception: the learner said something wrong and we kept it.
    // Every misconception recorded for the concept goes into one repair need,
    // so none is silently dropped by the needId hash. A failed claim with
    // nothing after it lands here too: an error is a node that needs an
    // intervention, not one point off.
    const unrepaired = unrepairedFailure(conceptState);
    const recorded = misconceptionsByConcept.get(conceptId);
    if (recorded && recorded.length > 0) {
      needs.push(buildNeed(context, 'repair_misconception', {
        ability: unrepaired ? unrepaired.ability : undefined,
        reason: [
          'recorded_misconception',
          ...recorded.map((item) => item.id || 'unnamed_misconception'),
          ...(unrepaired ? ['failed_claim_on_record'] : [])
        ],
        misconceptions: recorded
      }));
    }

    // reassess: the only evidence is weakly graded, or something failed and
    // nothing has confirmed or dropped it since.
    if (hasEvidence) {
      const weakGrader = bestGraderWeight(conceptState) < GRADED_WEIGHT;
      const needsRepair = unrepaired && !(recorded && recorded.length > 0);
      if (weakGrader || needsRepair) {
        const reason = [];
        if (weakGrader) reason.push('evidence_is_weakly_graded', 'no_strong_grader_on_record');
        if (needsRepair) reason.push('failed_claim_on_record', 'nothing_has_confirmed_it_since');
        needs.push(buildNeed(context, 'reassess', {
          reason,
          ability: needsRepair ? unrepaired.ability : highestAbilityWithEvidence(conceptState)
        }));
      }
    }

    // transfer: durable in one context, untested in another.
    if (band('apply') === 'durable' && band('transfer') === 'unknown') {
      needs.push(buildNeed(context, 'transfer', {
        reason: ['application_is_durable', 'no_transfer_evidence']
      }));
    }
  }

  // A goal concept that is blocked names the prerequisite that unblocks it, and
  // that prerequisite says which goal it is for. When the learner has never
  // touched it there is nothing to mark yet, so the need is made here.
  for (const [target, blocked] of redirected) {
    let need = needs
      .filter((entry) => entry.concept === target)
      .sort((a, b) => b.priority - a.priority)[0];
    if (!need) {
      need = buildNeed(
        { conceptId: target, def: registry.get(target) || null, goalConcepts, goalPrereqs },
        'acquire',
        { reason: ['goal_depends_on_this_concept', 'no_evidence_yet'] }
      );
      needs.push(need);
    }
    if (!need.reason.includes('prerequisite_first')) need.reason.unshift('prerequisite_first');
    // The reason names the goal, not every step between here and it.
    const named = [...blocked].filter((id) => goalConcepts.has(id));
    for (const id of (named.length > 0 ? named : [...blocked]).sort()) {
      const token = `before_${plainId(id)}`;
      if (!need.reason.includes(token)) need.reason.push(token);
    }
  }

  needs.sort((a, b) => (
    b.priority - a.priority
    || b.urgency - a.urgency
    || a.concept.localeCompare(b.concept)
    || NEED_KINDS.indexOf(a.kind) - NEED_KINDS.indexOf(b.kind)
  ));

  const budget = Number(options.budgetMinutes);
  if (Number.isFinite(budget) && budget > 0) return planSession(needs, budget, registry);
  return needs;
}

/**
 * Fill a session of `budgetMinutes` and put it in an order worth working
 * through, contract 30.
 *
 * The fill is greedy by priority and keeps scanning after a need does not fit,
 * so a short need still rides along behind a long one that was skipped. Two
 * confusable concepts never share a session unless one of them is the
 * `discriminate` need that exists to tell them apart. The order then avoids
 * putting two needs on the same concept next to each other and alternates kinds
 * where it can, because choosing the method is part of the skill.
 */
function planSession(needs, budgetMinutes, registry) {
  const neighbours = confusableIndex(registry);
  const picked = [];
  let remaining = budgetMinutes;

  for (const need of needs) {
    if (need.minutes > remaining) continue;
    const clash = picked.find((chosen) => (
      chosen.kind !== 'discriminate'
      && need.kind !== 'discriminate'
      && (neighbours.get(chosen.concept) || EMPTY_SET).has(need.concept)
    ));
    if (clash) {
      if (!clash.reason.includes('interference_avoided')) clash.reason.push('interference_avoided');
      continue;
    }
    picked.push({ ...need, reason: [...need.reason] });
    remaining -= need.minutes;
  }

  const session = [];
  const waiting = [...picked];
  while (waiting.length > 0) {
    let index = 0;
    if (session.length > 0) {
      const previous = session[session.length - 1];
      const differs = (need) => need.concept !== previous.concept;
      let found = waiting.findIndex((need) => differs(need) && need.kind !== previous.kind);
      if (found === -1) found = waiting.findIndex(differs);
      if (found !== -1) index = found;
    }
    const [next] = waiting.splice(index, 1);
    if (index > 0) next.reason.push('interleaved');
    session.push(next);
  }
  return session;
}

const EMPTY_SET = new Set();

/** Confusable pairs, both ways round, so the session rule is symmetric. */
function confusableIndex(registry) {
  const index = new Map();
  const link = (a, b) => {
    if (!index.has(a)) index.set(a, new Set());
    index.get(a).add(b);
  };
  for (const [id, def] of registry) {
    for (const other of (def && Array.isArray(def.confusableWith) ? def.confusableWith : [])) {
      if (typeof other !== 'string' || other === id) continue;
      link(id, other);
      link(other, id);
    }
  }
  return index;
}

/**
 * The prerequisite to work on before this concept, or null when the concept is
 * already at the edge of mastery.
 *
 * Walks down the weakest branch: the prerequisite with the lowest band, ties
 * broken by the one closest to being ready and then by id, until it reaches a
 * concept whose own prerequisites are all usable. That is the deepest thing
 * standing in the way, and the only one worth asking for.
 */
function weakestPrerequisite(conceptId, registry, state, depth = MAX_PREREQUISITE_WALK, seen = new Set()) {
  const def = registry.get(conceptId);
  const prereqs = def && Array.isArray(def.prereqs) ? def.prereqs : [];
  const blocking = prereqs
    .filter((id) => typeof id === 'string' && !seen.has(id))
    .filter((id) => bandRank(bestBand(state[id])) < bandRank('usable'));
  if (blocking.length === 0) return null;

  blocking.sort((a, b) => (
    bandRank(bestBand(state[a])) - bandRank(bestBand(state[b]))
    || readiness(b, registry, state) - readiness(a, registry, state)
    || a.localeCompare(b)
  ));

  const weakest = blocking[0];
  if (depth <= 0) return weakest;
  const next = new Set(seen).add(conceptId).add(weakest);
  const deeper = weakestPrerequisite(weakest, registry, state, depth - 1, next);
  return deeper === null ? weakest : deeper;
}

/** How many of a concept's own prerequisites are already usable. */
function readiness(conceptId, registry, state) {
  const def = registry.get(conceptId);
  const prereqs = def && Array.isArray(def.prereqs) ? def.prereqs : [];
  if (prereqs.length === 0) return Infinity;
  return prereqs.filter((id) => bandRank(bestBand(state[id])) >= bandRank('usable')).length - prereqs.length;
}

/**
 * The highest ability carrying a failure that nothing has answered since. An
 * error is a node needing an intervention, so the vault asks for one.
 */
function unrepairedFailure(conceptState) {
  let found = null;
  for (const [ability, entry] of Object.entries(conceptState)) {
    if (!entry || !entry.lastFailure) continue;
    const failedMs = toMs(entry.lastFailure);
    const successMs = toMs(entry.lastSuccess);
    if (failedMs === null) continue;
    if (successMs !== null && successMs >= failedMs) continue;
    if (found === null || abilityOrder(ability) > abilityOrder(found.ability)) {
      found = { ability, at: entry.lastFailure };
    }
  }
  return found;
}

/** A concept id as a reason string a person can read. */
function plainId(conceptId) {
  return String(conceptId).replace(/^nema:/, '').replace(/-/g, '_');
}

/**
 * The worst overdue review on a concept, or null when nothing is due.
 *
 * Scans every ladder ability at `retrieve` or above plus the side abilities, so
 * a discrimination review that the summary strip counts is also a need the
 * panel can show. Ladder reviews are practised as recall at the `retrieve`
 * rung; a side ability is practised as itself.
 *
 * @returns {{ ability: string, days: number }|null}
 */
function worstOverdue(conceptState, nowMs) {
  let ladderDays = null;
  let sideAbility = null;
  let sideDays = null;

  for (const [ability, entry] of Object.entries(conceptState)) {
    const onLadder = ABILITY_LADDER.indexOf(ability) >= ABILITY_LADDER.indexOf('retrieve');
    const onSide = SIDE_ABILITIES.includes(ability);
    if (!onLadder && !onSide) continue;
    if (!isReviewDue(entry, nowMs)) continue;

    const nextReviewMs = toMs(entry.nextReview);
    const days = nextReviewMs === null ? 0 : (nowMs - nextReviewMs) / DAY_MS;
    if (onLadder) {
      if (ladderDays === null || days > ladderDays) ladderDays = days;
    } else if (sideDays === null || days > sideDays) {
      sideDays = days;
      sideAbility = ability;
    }
  }

  if (ladderDays === null && sideDays === null) return null;
  const days = Math.max(ladderDays === null ? -Infinity : ladderDays, sideDays === null ? -Infinity : sideDays);
  return { ability: ladderDays === null ? sideAbility : 'retrieve', days };
}

function firstConfusable(def) {
  if (!def || !Array.isArray(def.confusableWith) || def.confusableWith.length === 0) return null;
  const first = def.confusableWith[0];
  return typeof first === 'string' && first.length > 0 ? first : null;
}

/** The strongest grader that ever produced evidence for this concept. */
function bestGraderWeight(conceptState) {
  let best = 0;
  for (const entry of Object.values(conceptState)) {
    const weight = entry && typeof entry.graderWeight === 'number' ? entry.graderWeight : 0;
    if (weight > best) best = weight;
  }
  return best;
}

function highestAbilityWithEvidence(conceptState) {
  let best = null;
  for (const ability of Object.keys(conceptState)) {
    if (best === null || abilityOrder(ability) > abilityOrder(best)) best = ability;
  }
  return best || 'explain';
}

function buildNeed(context, kind, extra = {}) {
  const { conceptId, def, goalConcepts, goalPrereqs } = context;
  const ability = extra.ability || NEED_ABILITY[kind];

  const goalRelevance = goalConcepts.has(conceptId) ? 1.5 : (goalPrereqs.has(conceptId) ? 1.2 : 1);
  const urgency = round(Math.min(1, extra.urgency ?? NEED_URGENCY[kind]), 3);
  const minutes = minutesFor(def, ability, kind);
  const priority = round((urgency * goalRelevance) / Math.max(2, minutes), 5);

  const reason = [...(extra.reason || [])];
  if (goalRelevance === 1.5) reason.push('active_goal_depends_on_this_concept');
  else if (goalRelevance === 1.2) reason.push('prerequisite_of_an_active_goal');

  return {
    needId: `need_${shortHash(`${conceptId}|${kind}`)}`,
    concept: conceptId,
    conceptTitle: (def && def.title) || conceptId,
    ability,
    kind,
    reason,
    note: noteFor(reason),
    urgency,
    minutes,
    confusableWith: extra.confusableWith || null,
    exerciseHint: EXERCISE_HINTS[kind],
    rubric: rubricFor(def, kind, ability),
    constraints: {
      maxHints: kind === 'retrieve' ? 0 : 1,
      doNotRevealAnswerBeforeSubmission: true
    },
    misconceptions: extra.misconceptions || [],
    goalRelevance,
    priority
  };
}

/**
 * How long the need takes. The registry decides, with one ceiling: a retrieval
 * is at most four minutes, so a budget holds several retrievals rather than one
 * long exercise. Minimum effective dose, contract 30.
 */
function minutesFor(def, ability, kind) {
  const stated = def && def.minutes ? def.minutes[ability] : undefined;
  const minutes = typeof stated === 'number' && stated > 0 ? stated : DEFAULT_MINUTES;
  return kind === 'retrieve' ? Math.min(minutes, MAX_RETRIEVE_MINUTES) : minutes;
}

/** The one sentence a reason gets when a token is not enough. */
function noteFor(reason) {
  for (const token of reason) {
    if (NEED_NOTES[token]) return NEED_NOTES[token];
  }
  return null;
}

/**
 * The rubric a coach grades this need against.
 *
 * The concept registry only carries rubrics for `explain`, `apply` and
 * `discriminate`, so an exact lookup would ship an empty rubric for every
 * retrieve, transfer, acquire and reassess need. An empty rubric is worse than
 * useless: `record_agent_assessment` passes a need when every criterion is met,
 * so no criteria at all is a vacuous pass, exactly the fabricated evidence the
 * protocol exists to prevent. So we fall back along the ladder and, failing
 * that, take the first rubric the concept has, in a fixed order. The result is
 * empty only when the concept carries no rubric at all.
 */
function rubricFor(def, kind, ability) {
  const rubric = def && def.rubric ? def.rubric : null;
  if (!rubric) return [];
  const order = [kind, ability, ...(RUBRIC_FALLBACK[kind] || RUBRIC_FALLBACK.reassess), ...Object.keys(rubric).sort()];
  for (const key of order) {
    const chosen = rubric[key];
    if (Array.isArray(chosen) && chosen.length > 0) return [...chosen];
  }
  return [];
}
