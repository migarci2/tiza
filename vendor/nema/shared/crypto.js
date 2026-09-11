// nema: cryptographic primitives shared by every app.
//
// Runs unchanged in browsers, Cloudflare Workers and Node 20+. It only uses
// globalThis.crypto (Web Crypto), TextEncoder and TextDecoder. No imports, no
// dependencies, no JSON imports, so this module can be copied into any bundle
// or served as a static asset.
//
// Signature scheme for the whole protocol: ECDSA over P-256 with SHA-256.
// Web Crypto produces the raw r||s form (64 bytes), which is what we base64url
// encode into a nema token. No DER, no JOSE headers.

const encoder = new TextEncoder();
const decoder = new TextDecoder();

const ALPHABET_REPLACEMENTS = [
  [/\+/g, '-'],
  [/\//g, '_']
];

function toBytes(input) {
  if (input instanceof Uint8Array) return input;
  if (input instanceof ArrayBuffer) return new Uint8Array(input);
  if (ArrayBuffer.isView(input)) {
    return new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
  }
  if (typeof input === 'string') return encoder.encode(input);
  throw new TypeError('expected a string, Uint8Array or ArrayBuffer');
}

function bytesToBinaryString(bytes) {
  // Chunked so that very large payloads do not blow the argument limit.
  let out = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    out += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return out;
}

function subtle() {
  const c = globalThis.crypto;
  if (!c || !c.subtle) {
    throw new Error('Web Crypto is not available in this environment');
  }
  return c.subtle;
}

/**
 * base64url without padding, in both directions.
 */
export const b64url = {
  /**
   * @param {string|Uint8Array|ArrayBuffer} input strings are encoded as UTF-8
   * @returns {string}
   */
  encode(input) {
    const bytes = toBytes(input);
    let out = btoa(bytesToBinaryString(bytes));
    for (const [pattern, replacement] of ALPHABET_REPLACEMENTS) {
      out = out.replace(pattern, replacement);
    }
    return out.replace(/=+$/, '');
  },

  /**
   * @param {string} value base64url text, padding optional
   * @returns {Uint8Array}
   */
  decode(value) {
    if (typeof value !== 'string') {
      throw new TypeError('b64url.decode expects a string');
    }
    if (!/^[A-Za-z0-9_-]*=*$/.test(value)) {
      throw new Error('not base64url');
    }
    let normalized = value.replace(/-/g, '+').replace(/_/g, '/');
    const remainder = normalized.length % 4;
    if (remainder === 1) throw new Error('not base64url');
    if (remainder === 2) normalized += '==';
    else if (remainder === 3) normalized += '=';
    const binary = atob(normalized);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  },

  /**
   * @param {string} value base64url text holding UTF-8 bytes
   * @returns {string}
   */
  decodeToString(value) {
    return decoder.decode(b64url.decode(value));
  }
};

/**
 * Raw SHA-256 digest bytes.
 * @param {string|Uint8Array|ArrayBuffer} input
 * @returns {Promise<Uint8Array>}
 */
export async function sha256Bytes(input) {
  const digest = await subtle().digest('SHA-256', toBytes(input));
  return new Uint8Array(digest);
}

/**
 * Prefixed hex digest, the form used inside protocol objects.
 * @param {string|Uint8Array|ArrayBuffer} input
 * @returns {Promise<string>} "sha256:" followed by 64 lowercase hex characters
 */
export async function sha256(input) {
  const bytes = await sha256Bytes(input);
  let hex = '';
  for (let i = 0; i < bytes.length; i += 1) {
    hex += bytes[i].toString(16).padStart(2, '0');
  }
  return `sha256:${hex}`;
}

const ECDSA_PARAMS = { name: 'ECDSA', namedCurve: 'P-256' };
const ECDSA_SIGN_PARAMS = { name: 'ECDSA', hash: { name: 'SHA-256' } };

function publicJwkOf(jwk) {
  if (!jwk || jwk.kty !== 'EC' || jwk.crv !== 'P-256' || !jwk.x || !jwk.y) {
    throw new Error('expected an EC P-256 public JWK with x and y');
  }
  return { kty: 'EC', crv: 'P-256', x: jwk.x, y: jwk.y };
}

function privateJwkOf(jwk) {
  const pub = publicJwkOf(jwk);
  if (!jwk.d) throw new Error('expected an EC P-256 private JWK with d');
  return { ...pub, d: jwk.d };
}

/**
 * Fresh exportable ECDSA P-256 key pair, as JWKs.
 * @returns {Promise<{ publicJwk: object, privateJwk: object }>}
 */
export async function generateKeyPair() {
  const pair = await subtle().generateKey(ECDSA_PARAMS, true, ['sign', 'verify']);
  const [publicJwk, privateJwk] = await Promise.all([
    subtle().exportKey('jwk', pair.publicKey),
    subtle().exportKey('jwk', pair.privateKey)
  ]);
  return { publicJwk: publicJwkOf(publicJwk), privateJwk: privateJwkOf(privateJwk) };
}

/**
 * @param {object} jwk
 * @returns {Promise<CryptoKey>}
 */
export async function importPublicKey(jwk) {
  return subtle().importKey('jwk', publicJwkOf(jwk), ECDSA_PARAMS, false, ['verify']);
}

/**
 * @param {object} jwk
 * @returns {Promise<CryptoKey>}
 */
export async function importPrivateKey(jwk) {
  return subtle().importKey('jwk', privateJwkOf(jwk), ECDSA_PARAMS, false, ['sign']);
}

/**
 * Sign the UTF-8 bytes of a payload string.
 * @param {object} privateJwk
 * @param {string} payloadString
 * @returns {Promise<string>} base64url of the raw r||s signature
 */
export async function sign(privateJwk, payloadString) {
  if (typeof payloadString !== 'string') {
    throw new TypeError('sign expects the payload as a string');
  }
  const key = await importPrivateKey(privateJwk);
  const signature = await subtle().sign(
    ECDSA_SIGN_PARAMS,
    key,
    encoder.encode(payloadString)
  );
  return b64url.encode(new Uint8Array(signature));
}

/**
 * Verify a signature against the exact payload string that was signed.
 * Never throws: a malformed signature or key resolves to false.
 * @param {object} publicJwk
 * @param {string} payloadString
 * @param {string} sigB64url
 * @returns {Promise<boolean>}
 */
export async function verify(publicJwk, payloadString, sigB64url) {
  try {
    if (typeof payloadString !== 'string') return false;
    const key = await importPublicKey(publicJwk);
    const signature = b64url.decode(sigB64url);
    return await subtle().verify(
      ECDSA_SIGN_PARAMS,
      key,
      signature,
      encoder.encode(payloadString)
    );
  } catch {
    return false;
  }
}

/**
 * Short random identifier, safe inside JSON, URLs and token payloads.
 * @param {string} prefix
 * @param {number} n number of base64url characters after the underscore
 * @returns {string}
 */
export function randomId(prefix, n = 12) {
  const count = Math.max(1, Math.ceil((n * 3) / 4) + 2);
  const bytes = new Uint8Array(count);
  globalThis.crypto.getRandomValues(bytes);
  return `${prefix}_${b64url.encode(bytes).slice(0, n)}`;
}

/**
 * Current time as an ISO 8601 string in UTC.
 * @returns {string}
 */
export function nowIso() {
  return new Date().toISOString();
}
