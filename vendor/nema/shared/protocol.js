// nema protocol 0.1: object builders, compact tokens, verification rules.
//
// Runs unchanged in browsers, Cloudflare Workers and Node 20+. It imports only
// /shared/crypto.js and holds no JSON imports, so the vault, the providers and
// the seed script all agree on byte-for-byte identical payloads.
//
// Token format:
//
//   nema1.<b64url(payloadJson)>.<b64url(signature)>
//
// The signature covers the UTF-8 bytes of the exact payload JSON string.
// Verification decodes that string and verifies it as transmitted. It never
// re-serializes the parsed object, so key order and whitespace of a foreign
// producer can never break a valid token.

import {
  b64url,
  sha256,
  sha256Bytes,
  sign,
  verify,
  randomId,
  nowIso
} from './crypto.js';

export const PROTOCOL = 'nema/0.1';
export const TOKEN_PREFIX = 'nema1';

export const ASSERTION_TYPE = 'readiness-assertion';
export const RECEIPT_TYPE = 'evidence-receipt';

/** Default lifetime of a readiness assertion, in minutes. */
export const DEFAULT_TTL_MINUTES = 30;

/**
 * The complete set of keys a ReadinessAssertion may carry. A provider that
 * sees anything else must treat the token as malformed. This list is the
 * machine readable form of the privacy promise: no history, no dates of
 * study, no other concepts.
 */
export const ALLOWED_ASSERTION_KEYS = Object.freeze([
  'type',
  'protocol',
  'audience',
  'purpose',
  'requestHash',
  'learnerKeyId',
  'assertions',
  'issuedAt',
  'expiresAt',
  'vaultKey'
]);

export const REQUIRED_ASSERTION_KEYS = Object.freeze([
  'type',
  'protocol',
  'audience',
  'purpose',
  'requestHash',
  'learnerKeyId',
  'assertions',
  'issuedAt',
  'expiresAt',
  'vaultKey'
]);

export const ALLOWED_RECEIPT_KEYS = Object.freeze([
  'type',
  'protocol',
  'receiptId',
  'issuer',
  'keyId',
  'issuerKey',
  'subject',
  'activity',
  'claims',
  'conditions',
  'issuedAt'
]);

export const REQUIRED_RECEIPT_KEYS = Object.freeze([
  'type',
  'protocol',
  'receiptId',
  'issuer',
  'keyId',
  'subject',
  'activity',
  'claims',
  'issuedAt'
]);

const SHAPES = {
  [ASSERTION_TYPE]: {
    allowed: ALLOWED_ASSERTION_KEYS,
    required: REQUIRED_ASSERTION_KEYS
  },
  [RECEIPT_TYPE]: {
    allowed: ALLOWED_RECEIPT_KEYS,
    required: REQUIRED_RECEIPT_KEYS
  }
};

/**
 * Human readable names for the demo issuers, keyed by the id used in
 * shared/issuers.json.
 */
export const ISSUER_NAMES = Object.freeze({
  harness: 'Saucier School',
  security: 'Line Cook Lab',
  seed: 'nema demo seed'
});

/** Origin used by the offline seed issuer, which has no website. */
export const SEED_ORIGIN = 'urn:nema:seed';

/**
 * How much a vault may believe a receipt, weakest last.
 *
 *   registered  the keyId is in the vault's issuer registry
 *   origin      the embedded issuerKey signed it and the issuer publishes that
 *               same key at /.well-known/nema-issuer.json
 *   self        the embedded issuerKey signed it, and nothing else
 *   pending     no key matches, so the receipt sits in the ledger and moves
 *               nothing
 *
 * `verifyReceipt` decides `registered`, `self` and `pending` on its own. It
 * never returns `origin`, because that tier needs a network fetch and this
 * module does no I/O: the caller fetches the well known document and upgrades
 * `self` to `origin` with `matchesPublishedKey`.
 */
export const TRUST_TIERS = Object.freeze(['registered', 'origin', 'self', 'pending']);

/** Key ids of self certifying issuers start with this. Contract section 21. */
export const SELF_KEY_PREFIX = 'self:';

/** Where an issuer publishes its key to earn the `origin` tier. */
export const ISSUER_WELL_KNOWN_PATH = '/.well-known/nema-issuer.json';

// ---------------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------------

function isPlainObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** An EC P-256 public JWK, the only key shape the protocol carries. */
function isPublicJwk(value) {
  return isPlainObject(value)
    && value.kty === 'EC'
    && typeof value.crv === 'string'
    && typeof value.x === 'string'
    && typeof value.y === 'string';
}

function requireString(value, what) {
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`${what} must be a non-empty string`);
  }
  return value;
}

function requireOptionalString(value, what) {
  if (value === undefined) return undefined;
  return requireString(value, what);
}

function requireNumber(value, what) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${what} must be a finite number`);
  }
  return value;
}

function requireTimestamp(value, what) {
  requireString(value, what);
  if (Number.isNaN(new Date(value).getTime())) {
    throw new Error(`${what} must be an ISO 8601 timestamp, got ${value}`);
  }
  return value;
}

function toDate(value) {
  if (value === undefined || value === null) return new Date();
  if (value instanceof Date) return value;
  if (typeof value === 'number') return new Date(value);
  if (typeof value === 'string') {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) throw new Error(`invalid date: ${value}`);
    return parsed;
  }
  throw new TypeError('expected a Date, an ISO string or milliseconds');
}

/**
 * ISO 8601 in UTC with whole seconds. Keeps tokens short and stable.
 * @param {Date|string|number} [value]
 * @returns {string}
 */
export function isoSeconds(value) {
  return toDate(value).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/**
 * True when a string looks like a nema compact token. Used by the coach to
 * detect tokens inside tool results without parsing them.
 * @param {unknown} value
 * @returns {boolean}
 */
export function isToken(value) {
  return typeof value === 'string' && value.startsWith(`${TOKEN_PREFIX}.`);
}

// ---------------------------------------------------------------------------
// shape validation
// ---------------------------------------------------------------------------

/**
 * Validate a decoded payload against the allowed and required key sets for its
 * type. Throws on an unknown key, a missing required key, a wrong type or a
 * wrong protocol version. The verify functions below turn any throw into the
 * reason 'malformed'.
 *
 * @param {object} payload
 * @param {'readiness-assertion'|'evidence-receipt'} type
 * @returns {object} the same payload, for chaining
 */
export function assertShape(payload, type) {
  const shape = SHAPES[type];
  if (!shape) throw new Error(`unknown payload type: ${type}`);
  if (!isPlainObject(payload)) throw new Error('payload must be an object');
  if (payload.type !== type) {
    throw new Error(`expected type ${type}, got ${String(payload.type)}`);
  }
  if (payload.protocol !== PROTOCOL) {
    throw new Error(`expected protocol ${PROTOCOL}, got ${String(payload.protocol)}`);
  }
  for (const key of Object.keys(payload)) {
    if (!shape.allowed.includes(key)) {
      throw new Error(`unexpected key in ${type}: ${key}`);
    }
  }
  for (const key of shape.required) {
    if (payload[key] === undefined || payload[key] === null) {
      throw new Error(`missing key in ${type}: ${key}`);
    }
  }
  if (type === ASSERTION_TYPE) {
    requireString(payload.audience, 'audience');
    requireString(payload.purpose, 'purpose');
    requireString(payload.requestHash, 'requestHash');
    requireString(payload.learnerKeyId, 'learnerKeyId');
    requireTimestamp(payload.issuedAt, 'issuedAt');
    requireTimestamp(payload.expiresAt, 'expiresAt');
    if (!Array.isArray(payload.assertions)) {
      throw new Error('assertions must be an array');
    }
    payload.assertions.forEach((entry, index) => {
      if (!isPlainObject(entry)) {
        throw new Error(`assertions[${index}] must be an object`);
      }
      requireString(entry.concept, `assertions[${index}].concept`);
      requireString(entry.ability, `assertions[${index}].ability`);
      requireString(entry.status, `assertions[${index}].status`);
      requireString(entry.confidence, `assertions[${index}].confidence`);
      /* Concept alignment, contract 23: the registry concept the band was read
       * from, and the reason nothing could be read. Both optional. */
      requireOptionalString(entry.alignedTo, `assertions[${index}].alignedTo`);
      requireOptionalString(entry.reason, `assertions[${index}].reason`);
    });
    if (!isPlainObject(payload.vaultKey) || typeof payload.vaultKey.x !== 'string') {
      throw new Error('vaultKey must be an EC public JWK');
    }
  } else {
    requireString(payload.receiptId, 'receiptId');
    requireString(payload.issuer, 'issuer');
    requireString(payload.keyId, 'keyId');
    requireString(payload.subject, 'subject');
    requireTimestamp(payload.issuedAt, 'issuedAt');
    if (!Array.isArray(payload.claims) || payload.claims.length === 0) {
      throw new Error('claims must be a non-empty array');
    }
    payload.claims.forEach((claim, index) => {
      if (!isPlainObject(claim)) {
        throw new Error(`claims[${index}] must be an object`);
      }
      requireString(claim.concept, `claims[${index}].concept`);
      requireString(claim.ability, `claims[${index}].ability`);
      requireString(claim.evidenceType, `claims[${index}].evidenceType`);
      requireString(claim.result, `claims[${index}].result`);
      requireOptionalString(claim.difficulty, `claims[${index}].difficulty`);
    });
    if (!isPlainObject(payload.activity)) {
      throw new Error('activity must be an object');
    }
    requireString(payload.activity.id, 'activity.id');
    requireOptionalString(payload.activity.version, 'activity.version');
    requireOptionalString(payload.activity.title, 'activity.title');
    requireOptionalString(payload.activity.contentHash, 'activity.contentHash');
    if (payload.conditions !== undefined && !isPlainObject(payload.conditions)) {
      throw new Error('conditions must be an object');
    }
    /* A self certifying receipt carries the public key that signed it. It is
     * optional: a receipt from a registered issuer names a key the vault
     * already holds and carries none. */
    if (payload.issuerKey !== undefined && !isPublicJwk(payload.issuerKey)) {
      throw new Error('issuerKey must be an EC public JWK with kty, crv, x and y');
    }
  }
  return payload;
}

// ---------------------------------------------------------------------------
// tokens
// ---------------------------------------------------------------------------

/**
 * @param {object} payloadObj
 * @param {string} signatureB64url
 * @returns {string}
 */
export function encodeToken(payloadObj, signatureB64url) {
  if (!isPlainObject(payloadObj)) throw new TypeError('payload must be an object');
  requireString(signatureB64url, 'signature');
  return `${TOKEN_PREFIX}.${b64url.encode(JSON.stringify(payloadObj))}.${signatureB64url}`;
}

/**
 * @param {string} token
 * @returns {{ payload: object, payloadString: string, signature: string }}
 * @throws when the token is not a well formed nema1 token
 */
export function decodeToken(token) {
  if (typeof token !== 'string') throw new Error('token must be a string');
  const parts = token.trim().split('.');
  if (parts.length !== 3) throw new Error('token must have three parts');
  const [prefix, payloadPart, signature] = parts;
  if (prefix !== TOKEN_PREFIX) throw new Error(`unknown token prefix: ${prefix}`);
  if (!payloadPart || !signature) throw new Error('token has an empty part');
  const payloadString = b64url.decodeToString(payloadPart);
  const payload = JSON.parse(payloadString);
  if (!isPlainObject(payload)) throw new Error('payload must be an object');
  return { payload, payloadString, signature };
}

/**
 * Serialize, sign and encode in one step. The bytes that are signed are the
 * bytes that travel.
 * @param {object} payloadObj
 * @param {object} privateJwk
 * @returns {Promise<string>}
 */
export async function signToken(payloadObj, privateJwk) {
  if (!isPlainObject(payloadObj)) throw new TypeError('payload must be an object');
  const payloadString = JSON.stringify(payloadObj);
  const signature = await sign(privateJwk, payloadString);
  return `${TOKEN_PREFIX}.${b64url.encode(payloadString)}.${signature}`;
}

/**
 * Signature only. Callers add the semantic checks.
 * @param {string} token
 * @param {object} publicJwk
 * @returns {Promise<{ ok: boolean, payload?: object, reason?: string }>}
 */
export async function verifyToken(token, publicJwk) {
  let decoded;
  try {
    decoded = decodeToken(token);
  } catch {
    return { ok: false, reason: 'malformed' };
  }
  const ok = await verify(publicJwk, decoded.payloadString, decoded.signature);
  if (!ok) return { ok: false, payload: decoded.payload, reason: 'bad-signature' };
  return { ok: true, payload: decoded.payload };
}

// ---------------------------------------------------------------------------
// ReadinessRequest
// ---------------------------------------------------------------------------

/**
 * @param {{ audience: string, purpose: string, requirements: Array<{concept: string, ability: string}> }} input
 * @returns {object} an unsigned ReadinessRequest
 */
export function buildReadinessRequest({ audience, purpose, requirements }) {
  requireString(audience, 'audience');
  requireString(purpose, 'purpose');
  if (!Array.isArray(requirements)) throw new Error('requirements must be an array');
  return {
    protocol: PROTOCOL,
    audience,
    purpose,
    requirements: requirements.map((entry) => ({
      concept: requireString(entry && entry.concept, 'requirement.concept'),
      ability: requireString(entry && entry.ability, 'requirement.ability')
    }))
  };
}

/**
 * @param {object} request
 * @returns {Promise<string>} "sha256:" prefixed hex digest of the canonical JSON
 */
export async function requestHash(request) {
  if (!isPlainObject(request)) throw new TypeError('request must be an object');
  return sha256(JSON.stringify(request));
}

// ---------------------------------------------------------------------------
// learner key ids
// ---------------------------------------------------------------------------

/**
 * Per-audience pseudonym for the learner. Two providers see two different ids
 * for the same vault, so they cannot correlate learners by comparing subjects.
 *
 * id = "lk_" + b64url(sha256(vaultKey.x + "|" + audience)).slice(0, 16)
 *
 * @param {object} vaultPublicJwk
 * @param {string} audience
 * @returns {Promise<string>}
 */
export async function learnerKeyId(vaultPublicJwk, audience) {
  if (!isPlainObject(vaultPublicJwk) || typeof vaultPublicJwk.x !== 'string') {
    throw new Error('vaultPublicJwk must be an EC public JWK');
  }
  requireString(audience, 'audience');
  const digest = await sha256Bytes(`${vaultPublicJwk.x}|${audience}`);
  return `lk_${b64url.encode(digest).slice(0, 16)}`;
}

// ---------------------------------------------------------------------------
// ReadinessAssertion
// ---------------------------------------------------------------------------

function publicJwkFields(jwk, what = 'vault key') {
  if (!isPlainObject(jwk) || jwk.kty !== 'EC' || typeof jwk.x !== 'string' || typeof jwk.y !== 'string') {
    throw new Error(`${what} must be an EC public JWK with x and y`);
  }
  return { kty: 'EC', crv: jwk.crv || 'P-256', x: jwk.x, y: jwk.y };
}

/** Key for the (concept, ability) pairs a request asked about. */
function pairKey(concept, ability) {
  return `${concept} ${ability}`;
}

/**
 * The set of (concept, ability) pairs a ReadinessRequest asked about. The
 * assertion builder refuses to sign anything outside it, so a vault bug that
 * passes the whole learner state through cannot turn into a disclosure.
 */
function requestedPairs(request) {
  if (!Array.isArray(request.requirements)) {
    throw new Error('request.requirements must be an array');
  }
  const pairs = new Set();
  for (const entry of request.requirements) {
    if (!isPlainObject(entry)) throw new Error('request.requirements entries must be objects');
    pairs.add(
      pairKey(
        requireString(entry.concept, 'requirement.concept'),
        requireString(entry.ability, 'requirement.ability')
      )
    );
  }
  return pairs;
}

/**
 * Build the payload of a ReadinessAssertion. It carries status bands only:
 * never a score, never a date of study, never a concept the provider did not
 * ask about.
 *
 * @param {object} input
 * @param {object} input.request the ReadinessRequest being answered
 * @param {Array<{concept: string, ability: string, status: string, confidence: string}>} input.statuses
 * @param {object} input.vaultPublicJwk
 * @param {Date|string|number} [input.now]
 * @param {number} [input.ttlMinutes]
 * @returns {Promise<object>}
 */
export async function buildAssertionPayload({
  request,
  statuses,
  vaultPublicJwk,
  now,
  ttlMinutes = DEFAULT_TTL_MINUTES
}) {
  if (!isPlainObject(request)) throw new TypeError('request must be an object');
  if (!Array.isArray(statuses)) throw new TypeError('statuses must be an array');
  if (!Number.isFinite(ttlMinutes) || ttlMinutes <= 0) {
    throw new Error('ttlMinutes must be a positive number');
  }
  const audience = requireString(request.audience, 'request.audience');
  const purpose = requireString(request.purpose, 'request.purpose');
  const allowedPairs = requestedPairs(request);
  const issuedAtDate = toDate(now);
  const expiresAtDate = new Date(issuedAtDate.getTime() + ttlMinutes * 60 * 1000);
  const vaultKey = publicJwkFields(vaultPublicJwk);

  const payload = {
    type: ASSERTION_TYPE,
    protocol: PROTOCOL,
    audience,
    purpose,
    requestHash: await requestHash(request),
    learnerKeyId: await learnerKeyId(vaultKey, audience),
    assertions: statuses.map((entry) => {
      const concept = requireString(entry && entry.concept, 'assertion.concept');
      const ability = requireString(entry && entry.ability, 'assertion.ability');
      if (!allowedPairs.has(pairKey(concept, ability))) {
        throw new Error(
          `assertion would disclose ${concept}.${ability}, which the request did not ask about`
        );
      }
      const line = {
        concept,
        ability,
        status: requireString(entry && entry.status, 'assertion.status'),
        confidence: requireString(entry && entry.confidence, 'assertion.confidence')
      };
      /* A site that speaks its own names is answered in its own names, and
       * told which registry concept the vault read the band from. `reason`
       * names the one case where nothing could be read: a local id this vault
       * has no confirmed alignment for. Contract section 23. */
      if (entry.alignedTo !== undefined) {
        line.alignedTo = requireString(entry.alignedTo, 'assertion.alignedTo');
      }
      if (entry.reason !== undefined) {
        line.reason = requireString(entry.reason, 'assertion.reason');
      }
      return line;
    }),
    issuedAt: isoSeconds(issuedAtDate),
    expiresAt: isoSeconds(expiresAtDate),
    vaultKey
  };
  return assertShape(payload, ASSERTION_TYPE);
}

/**
 * Provider side verification of an assertion presented by the agent.
 *
 * Checks, in order: token shape, payload shape, signature against the embedded
 * vault key, audience equal to our own origin, expiry in the future.
 *
 * `audience` is mandatory: it is the whole point of the check, and a verifier
 * that cannot name its own origin must not accept a token addressed to someone
 * else. Passing anything but a non-empty string throws, so a Worker where
 * `location` is undefined fails loudly instead of accepting every assertion.
 * Use `inspectAssertion` to read a token that is not addressed to you.
 *
 * @param {string} token
 * @param {{ audience: string, now?: Date|string|number, skipAudience?: boolean }} options
 * @returns {Promise<{ ok: boolean, payload?: object, reason?: string }>}
 *   reasons: 'malformed', 'bad-signature', 'wrong-audience', 'expired'
 * @throws {TypeError} when no audience is given and the check is not waived
 */
export async function verifyAssertion(token, { audience, now, skipAudience = false } = {}) {
  const checkAudience = skipAudience !== true;
  if (checkAudience && (typeof audience !== 'string' || audience.length === 0)) {
    throw new TypeError(
      'verifyAssertion requires the verifier own origin as a non-empty audience string. ' +
        'Use inspectAssertion(token, { now }) to read an assertion without binding it.'
    );
  }
  let decoded;
  try {
    decoded = decodeToken(token);
    assertShape(decoded.payload, ASSERTION_TYPE);
  } catch {
    return { ok: false, reason: 'malformed' };
  }
  const payload = decoded.payload;

  const signatureOk = await verify(payload.vaultKey, decoded.payloadString, decoded.signature);
  if (!signatureOk) return { ok: false, payload, reason: 'bad-signature' };

  if (checkAudience && payload.audience !== audience) {
    return { ok: false, payload, reason: 'wrong-audience' };
  }

  const at = toDate(now).getTime();
  const expiresAt = new Date(payload.expiresAt).getTime();
  if (!Number.isFinite(expiresAt) || expiresAt <= at) {
    return { ok: false, payload, reason: 'expired' };
  }

  return { ok: true, payload };
}

/**
 * Read an assertion without binding it to an audience: signature, shape and
 * expiry only. This is for a holder inspecting its own token, for example the
 * vault re-reading a disclosure it just issued, or a UI decoding a token to
 * show what it contains. A provider deciding whether to act on an assertion
 * must call `verifyAssertion` with its own origin instead.
 *
 * @param {string} token
 * @param {{ now?: Date|string|number }} [options]
 * @returns {Promise<{ ok: boolean, payload?: object, reason?: string }>}
 */
export async function inspectAssertion(token, { now } = {}) {
  return verifyAssertion(token, { skipAudience: true, now });
}

// ---------------------------------------------------------------------------
// EvidenceReceipt
// ---------------------------------------------------------------------------

function activityFields(activity) {
  if (!isPlainObject(activity)) throw new Error('activity must be an object');
  const out = {
    id: requireString(activity.id, 'activity.id'),
    version: requireString(activity.version, 'activity.version'),
    title: requireString(activity.title, 'activity.title')
  };
  if (activity.contentHash !== undefined) {
    out.contentHash = requireString(activity.contentHash, 'activity.contentHash');
  }
  return out;
}

function claimFields(claim) {
  if (!isPlainObject(claim)) throw new Error('claim must be an object');
  const out = {
    concept: requireString(claim.concept, 'claim.concept'),
    ability: requireString(claim.ability, 'claim.ability'),
    evidenceType: requireString(claim.evidenceType, 'claim.evidenceType'),
    result: requireString(claim.result, 'claim.result')
  };
  if (claim.difficulty !== undefined) {
    out.difficulty = requireString(claim.difficulty, 'claim.difficulty');
  }
  return out;
}

function conditionFields(conditions) {
  if (conditions === undefined || conditions === null) return undefined;
  if (!isPlainObject(conditions)) throw new Error('conditions must be an object');
  const out = {};
  if (conditions.attempts !== undefined) {
    out.attempts = requireNumber(conditions.attempts, 'conditions.attempts');
  }
  if (conditions.hintsUsed !== undefined) {
    out.hintsUsed = requireNumber(conditions.hintsUsed, 'conditions.hintsUsed');
  }
  if (conditions.durationSeconds !== undefined) {
    out.durationSeconds = requireNumber(conditions.durationSeconds, 'conditions.durationSeconds');
  }
  if (conditions.grader !== undefined) {
    out.grader = requireString(conditions.grader, 'conditions.grader');
  }
  if (conditions.graderVersion !== undefined) {
    const version = conditions.graderVersion;
    if (typeof version === 'number' && Number.isFinite(version)) {
      out.graderVersion = String(version);
    } else {
      out.graderVersion = requireString(version, 'conditions.graderVersion');
    }
  }
  return out;
}

/**
 * Build the payload of an EvidenceReceipt. A provider signs one of these after
 * its own grader ran. It never contains the learner's answer.
 *
 * @param {object} input
 * @param {string} input.issuer origin of the issuing provider
 * @param {string} input.keyId key id from shared/issuers.json, or
 *   "self:<origin>" for a page that signs with a key it generated itself
 * @param {object} [input.issuerKey] the public JWK that signs this receipt.
 *   A self certifying issuer carries it so a vault that has never heard of the
 *   site can still check the signature and file the receipt as `self`.
 * @param {string} input.subject the audience-scoped learnerKeyId
 * @param {object} input.activity { id, version, title, contentHash? }
 * @param {Array<object>} input.claims
 * @param {object} [input.conditions]
 * @param {Date|string|number} [input.now]
 * @param {string} [input.receiptId] pass one to make the receipt reproducible
 * @returns {object}
 */
export function buildReceiptPayload({
  issuer,
  keyId,
  issuerKey,
  subject,
  activity,
  claims,
  conditions,
  now,
  receiptId
}) {
  requireString(issuer, 'issuer');
  requireString(keyId, 'keyId');
  requireString(subject, 'subject');
  if (!Array.isArray(claims) || claims.length === 0) {
    throw new Error('claims must be a non-empty array');
  }
  const payload = {
    type: RECEIPT_TYPE,
    protocol: PROTOCOL,
    receiptId: receiptId ? requireString(receiptId, 'receiptId') : randomId('rcpt'),
    issuer,
    keyId
  };
  if (issuerKey !== undefined) payload.issuerKey = publicJwkFields(issuerKey, 'issuerKey');
  payload.subject = subject;
  payload.activity = activityFields(activity);
  payload.claims = claims.map(claimFields);
  const normalizedConditions = conditionFields(conditions);
  if (normalizedConditions) payload.conditions = normalizedConditions;
  payload.issuedAt = isoSeconds(now);
  return assertShape(payload, RECEIPT_TYPE);
}

/**
 * True when a receipt carries its own signing key: a keyId of the form
 * "self:<origin>" and the matching public JWK in `issuerKey`. Anyone can mint
 * one, which is exactly why the vault caps what it is worth.
 *
 * @param {object} payload a decoded receipt payload
 * @returns {boolean}
 */
export function isSelfCertified(payload) {
  return isPlainObject(payload)
    && typeof payload.keyId === 'string'
    && payload.keyId.startsWith(SELF_KEY_PREFIX)
    && isPublicJwk(payload.issuerKey);
}

/**
 * Does the issuer publish the very key that signed this receipt?
 *
 * Pure, so it runs in the vault, in a test or in a Worker: the caller fetches
 * `https://<payload.issuer>/.well-known/nema-issuer.json` and passes the parsed
 * document here. A match lifts a `self` receipt to `origin`, because the site
 * that owns the domain has vouched for the key. Anything else, a miss, a
 * timeout, a wrong key or a fetch that never arrived, leaves it at `self`.
 *
 * @param {object} payload a decoded receipt payload carrying `issuerKey`
 * @param {object} published the parsed well known document `{ keyId, jwk }`
 * @returns {boolean}
 */
export function matchesPublishedKey(payload, published) {
  if (!isPlainObject(payload) || !isPlainObject(published)) return false;
  const signing = payload.issuerKey;
  const declared = published.jwk;
  if (!isPublicJwk(signing) || !isPublicJwk(declared)) return false;
  if (typeof payload.keyId !== 'string' || payload.keyId !== published.keyId) return false;
  return signing.kty === declared.kty
    && signing.crv === declared.crv
    && signing.x === declared.x
    && signing.y === declared.y;
}

/**
 * Vault side verification of a receipt.
 *
 * Checks, in order: token shape, payload shape, a key to check the signature
 * with, the signature itself, and the receiptId against the receipts already
 * stored. Two kinds of key are accepted:
 *
 *   registered  `issuerMap[payload.keyId]` whose origin matches the issuer
 *   self        `payload.issuerKey`, when the keyId starts with "self:"
 *
 * A registered key always wins, so a site cannot claim a registered keyId and
 * hand over its own key with it. `trust` names the tier the receipt earned:
 * 'registered', 'self', or 'pending' when nothing could check it. The `origin`
 * tier is the caller's to award, after fetching the issuer's well known
 * document and passing it to `matchesPublishedKey`.
 *
 * @param {string} token
 * @param {Record<string, {origin: string, jwk: object, name?: string, id?: string}>} issuerMap
 * @param {{ seenReceiptIds?: Set<string>|Array<string> }} [options]
 * @returns {Promise<{ ok: boolean, payload?: object, issuer?: object, trust: string, reason?: string }>}
 *   reasons: 'malformed', 'unknown-issuer', 'bad-signature', 'duplicate'
 */
export async function verifyReceipt(token, issuerMap, { seenReceiptIds } = {}) {
  let decoded;
  try {
    decoded = decodeToken(token);
    assertShape(decoded.payload, RECEIPT_TYPE);
  } catch {
    return { ok: false, trust: 'pending', reason: 'malformed' };
  }
  const payload = decoded.payload;

  const registered = isPlainObject(issuerMap) ? issuerMap[payload.keyId] : undefined;
  const known = registered && registered.jwk && registered.origin === payload.issuer
    ? registered
    : null;

  if (!known && !isSelfCertified(payload)) {
    return { ok: false, payload, trust: 'pending', reason: 'unknown-issuer' };
  }

  const issuer = known || {
    origin: payload.issuer,
    jwk: payload.issuerKey,
    name: payload.issuer,
    selfCertified: true
  };
  const trust = known ? 'registered' : 'self';

  const signatureOk = await verify(issuer.jwk, decoded.payloadString, decoded.signature);
  /* A signature that does not check out earns nothing, whichever key it named. */
  if (!signatureOk) return { ok: false, payload, issuer, trust: 'pending', reason: 'bad-signature' };

  if (seenReceiptIds) {
    const seen =
      typeof seenReceiptIds.has === 'function'
        ? seenReceiptIds.has(payload.receiptId)
        : Array.from(seenReceiptIds).includes(payload.receiptId);
    if (seen) return { ok: false, payload, issuer, trust, reason: 'duplicate' };
  }

  return { ok: true, payload, issuer, trust };
}

// ---------------------------------------------------------------------------
// concept alignment (contract section 23)
// ---------------------------------------------------------------------------
//
// The registry in shared/concepts.json stays the anchor, but a site is not
// obliged to speak it. A manifest may declare its own concepts, and any id
// without the `nema:` prefix is local to the origin that published it. The
// vault translates those names at its edges, never inside the inference: an
// assertion answers with the id the site asked for, a receipt keeps the claim
// the issuer signed, and the mapping lives in the learner's own vault where
// the learner can confirm or reject it.
//
// Everything below is pure, so the same rules run in the vault, in the
// extension panel, in a test and in a Worker.

/** The three relations an alignment may claim. Contract section 23. */
export const ALIGNMENT_RELATIONS = Object.freeze(['equivalent', 'broader', 'narrower']);

/** Lifecycle of one alignment. Only the learner moves it off `proposed`. */
export const ALIGNMENT_STATUSES = Object.freeze(['proposed', 'confirmed', 'rejected']);

/** Who put the alignment in front of the learner. */
export const ALIGNMENT_PROPOSERS = Object.freeze(['agent', 'provider', 'learner']);

/** Concept ids in the shared registry carry this prefix. Everything else is local. */
export const REGISTRY_PREFIX = 'nema:';

/**
 * @param {unknown} id
 * @returns {boolean} true for a `nema:` id from the shared registry
 */
export function isRegistryConcept(id) {
  return typeof id === 'string' && id.startsWith(REGISTRY_PREFIX);
}

/**
 * @param {unknown} id
 * @returns {boolean} true for an id local to a provider's own manifest
 */
export function isLocalConcept(id) {
  return typeof id === 'string' && id.length > 0 && !id.startsWith(REGISTRY_PREFIX);
}

/**
 * Build one alignment record for vault storage.
 *
 * @param {object} input
 * @param {string} input.origin the site that uses `providerConcept`
 * @param {string} input.providerConcept the site's own id, without a prefix
 * @param {string} input.concept the registry id it is aligned to
 * @param {string} [input.relation] one of ALIGNMENT_RELATIONS
 * @param {string} [input.status] one of ALIGNMENT_STATUSES
 * @param {string} [input.proposedBy] one of ALIGNMENT_PROPOSERS
 * @param {string} [input.rationale] why the proposer believes it
 * @param {Date|string|number} [input.now]
 * @param {string} [input.alignmentId] pass one to make the record reproducible
 * @returns {object}
 */
export function buildAlignment({
  origin,
  providerConcept,
  concept,
  relation = 'equivalent',
  status = 'proposed',
  proposedBy = 'agent',
  rationale = '',
  now,
  alignmentId
}) {
  requireString(origin, 'origin');
  requireString(providerConcept, 'providerConcept');
  requireString(concept, 'concept');
  if (!ALIGNMENT_RELATIONS.includes(relation)) {
    throw new Error(`relation must be one of ${ALIGNMENT_RELATIONS.join(', ')}`);
  }
  if (!ALIGNMENT_STATUSES.includes(status)) {
    throw new Error(`status must be one of ${ALIGNMENT_STATUSES.join(', ')}`);
  }
  if (!ALIGNMENT_PROPOSERS.includes(proposedBy)) {
    throw new Error(`proposedBy must be one of ${ALIGNMENT_PROPOSERS.join(', ')}`);
  }
  if (!isRegistryConcept(concept)) {
    throw new Error(`an alignment must point at a registry concept, got ${concept}`);
  }
  if (!isLocalConcept(providerConcept)) {
    throw new Error(`providerConcept must be the site's own id, without the ${REGISTRY_PREFIX} prefix`);
  }
  const proposedAt = isoSeconds(now);
  return {
    alignmentId: alignmentId ? requireString(alignmentId, 'alignmentId') : randomId('aln'),
    origin,
    providerConcept,
    concept,
    relation,
    status,
    proposedBy,
    rationale: typeof rationale === 'string' ? rationale : '',
    proposedAt,
    decidedAt: status === 'proposed' ? null : proposedAt
  };
}

/**
 * The confirmed alignments of one origin, keyed by the site's own concept id.
 * Only confirmed entries translate anything: a proposal the learner has not
 * answered moves no band and answers no requirement.
 *
 * @param {Array<object>} alignments every alignment the vault holds
 * @param {string} origin the site whose names are being read
 * @returns {Map<string, object>}
 */
export function alignmentIndex(alignments, origin) {
  const index = new Map();
  for (const entry of Array.isArray(alignments) ? alignments : []) {
    if (!isPlainObject(entry) || entry.status !== 'confirmed') continue;
    if (entry.origin !== origin) continue;
    if (index.has(entry.providerConcept)) continue;
    index.set(entry.providerConcept, entry);
  }
  return index;
}

/**
 * How far a band on the registry concept may answer a question asked in the
 * site's own words.
 *
 * `equivalent` passes through. `narrower` means the site's concept is a part of
 * the registry concept, so knowing the whole broadly does not prove the part:
 * the answer is `uncertain` at best. `broader` is the mirror of that, and it is
 * capped on the evidence side instead (see `translateClaim`).
 *
 * @param {string} status 'verified' | 'uncertain' | 'missing'
 * @param {string} [relation]
 * @returns {string}
 */
export function capStatus(status, relation) {
  if (relation === 'narrower' && status === 'verified') return 'uncertain';
  return status;
}

/**
 * Translate one requirement id before the bands are read.
 *
 * @param {{concept: string, ability: string}} requirement as the site asked it
 * @param {Map<string, object>} index confirmed alignments for that audience
 * @returns {{ concept: string, ability: string, lookup: string|null,
 *             alignedTo?: string, relation?: string, unaligned?: boolean }}
 *   `lookup` is the id whose band answers the question, or null when the site
 *   used a local name this vault has no confirmed alignment for.
 */
export function alignRequirement(requirement, index) {
  const concept = requirement.concept;
  const ability = requirement.ability;
  if (!isLocalConcept(concept)) return { concept, ability, lookup: concept };
  const alignment = index instanceof Map ? index.get(concept) : null;
  if (!alignment) return { concept, ability, lookup: null, unaligned: true };
  return {
    concept,
    ability,
    lookup: alignment.concept,
    alignedTo: alignment.concept,
    relation: alignment.relation
  };
}

/**
 * The alignment note the vault stores beside one signed claim. The receipt
 * itself is never rewritten: the note says what the claim was read as.
 *
 * @param {object} claim a claim from a signed receipt
 * @param {Map<string, object>} index confirmed alignments for the issuer
 * @returns {{ concept: string, ability: string, alignedTo?: string,
 *             relation?: string, pendingAlignment?: boolean }}
 */
export function alignClaim(claim, index) {
  const note = { concept: claim.concept, ability: claim.ability };
  if (!isLocalConcept(claim.concept)) return note;
  const alignment = index instanceof Map ? index.get(claim.concept) : null;
  if (!alignment) {
    note.pendingAlignment = true;
    return note;
  }
  note.alignedTo = alignment.concept;
  note.relation = alignment.relation;
  return note;
}

/**
 * The claim a derivation should count, or null when it is still waiting for an
 * alignment the learner has not confirmed.
 *
 * A `broader` alignment says the site's concept covers more ground than the
 * registry concept, so a pass on the whole is only partial evidence for the
 * part: the claim maps with `result` capped at `partial`. This is a semantic
 * cap on what the name can mean, not a trust one. The grader weight and the
 * trust tier are untouched by alignment, exactly as the contract says: who
 * signed the receipt decides the weight, who translated the name never does.
 *
 * @param {object} claim a claim from a signed receipt
 * @param {Map<string, object>} index confirmed alignments for the issuer
 * @returns {object|null}
 */
export function translateClaim(claim, index) {
  const note = alignClaim(claim, index);
  if (note.pendingAlignment) return null;
  if (!note.alignedTo) return claim;
  const mapped = { ...claim, concept: note.alignedTo };
  if (note.relation === 'broader' && mapped.result === 'passed') mapped.result = 'partial';
  return mapped;
}

/**
 * Read the `concepts` block of a manifest into the alignments a site declares
 * about its own vocabulary. Anything malformed is skipped rather than thrown:
 * a site with one bad entry still installs.
 *
 * @param {Array<object>} concepts the manifest's `concepts` array
 * @returns {Array<{providerConcept: string, concept: string, relation: string, title: string}>}
 */
export function declaredAlignments(concepts) {
  const out = [];
  for (const entry of Array.isArray(concepts) ? concepts : []) {
    if (!isPlainObject(entry) || !isLocalConcept(entry.id)) continue;
    for (const target of Array.isArray(entry.alignsTo) ? entry.alignsTo : []) {
      if (!isPlainObject(target) || !isRegistryConcept(target.concept)) continue;
      const relation = ALIGNMENT_RELATIONS.includes(target.relation) ? target.relation : 'equivalent';
      out.push({
        providerConcept: entry.id,
        concept: target.concept,
        relation,
        title: typeof entry.title === 'string' ? entry.title : entry.id
      });
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// issuer registry
// ---------------------------------------------------------------------------

/**
 * Join shared/issuers.json with a resolved origins map into the lookup table
 * the vault uses. Pure, so the caller decides how the two JSON documents are
 * loaded (import attribute, fetch, or fs in the seed script).
 *
 * Both arguments are mandatory objects. An empty issuer registry is the worst
 * possible silent failure, since every receipt including the seed ledger would
 * become `unknown-issuer` with nothing thrown, so misuse throws here. Malformed
 * individual entries are still skipped: one bad key must not disable the rest.
 *
 * @param {Record<string, {kid: string, jwk: object}>} issuersJson
 * @param {Record<string, string>} originsMap resolved ORIGINS for this host
 * @returns {Record<string, {origin: string, jwk: object, name: string, id: string}>}
 *   keyed by keyId
 * @throws {TypeError} when either argument is not a plain object
 */
export function buildIssuerMap(issuersJson, originsMap) {
  if (!isPlainObject(issuersJson)) {
    throw new TypeError('buildIssuerMap requires the parsed contents of shared/issuers.json');
  }
  if (!isPlainObject(originsMap)) {
    throw new TypeError('buildIssuerMap requires a resolved origins map, such as ORIGINS');
  }
  const origins = originsMap;
  const map = {};
  for (const [id, entry] of Object.entries(issuersJson)) {
    if (!isPlainObject(entry) || !entry.kid || !isPlainObject(entry.jwk)) continue;
    const origin = id === 'seed' ? SEED_ORIGIN : origins[id];
    if (!origin) continue;
    map[entry.kid] = {
      origin,
      jwk: entry.jwk,
      name: ISSUER_NAMES[id] || id,
      id
    };
  }
  return map;
}

/**
 * CONTRACT DEVIATION (documented): section 5.6 names this `loadIssuers()` with
 * no arguments. It is kept as an alias of the pure `buildIssuerMap` so that
 * this module stays free of JSON imports and runs in Workers and Node without a
 * loader flag. Callers pass the two JSON documents in, and calling it the way
 * the contract spells it, with no arguments, throws rather than handing back an
 * empty registry.
 */
export const loadIssuers = buildIssuerMap;

export { nowIso, sha256, b64url };
