# Reuse and interoperability

Upstream: `migarci2/nema`, commit `6f630aff03f20e74b55406bc13b2b36433dc491b`, MIT, copyright 2026 Miguel Garcia. Files under `vendor/nema` preserve source and notices. No issuer keys, private vaults, branding, cooking courses, marketing pages or extension bundle are imported.

| Source | Tiza implementation | Verification |
|---|---|---|
| `shared/inference.js` | `learning/state.py` and `learning/nema_needs.py` preserve derivation, implicit repetition and discrete needs; `learning/policy.py` adds Tiza assignment rules | Original-JS generated state and needs fixtures under `tests/parity` |
| `shared/concepts.json` | Reference catalog used only for parity | New 12-concept fractions catalog under `curricula/fractions` |
| `shared/crypto.js` | `integrations/nema/crypto.py` using cryptography | JavaScript verifies Python signatures and Python verifies JavaScript |
| `shared/protocol.js` | `integrations/nema/protocol.py`, readiness and receipts | Shape, scope, audience, expiry, subject and negative tests |
| Ledger/derived state separation | Append-only `EvidenceEvent`, teacher revisions | API evidence/idempotency tests |

The compatibility format stays `nema1.<payload>.<signature>` and `nema/0.1`. Python converts DER ECDSA signatures to raw `r || s` and verifies the original UTF-8 JSON bytes. Keys are new Tiza deployment configuration, never copied. The Python adapter deliberately rejects additional disclosure fields and ambiguous JSON, beyond the upstream minimum, at the Tiza trust boundary.

Readiness has its own authenticated, expiring request and grant. It does not copy a vault ledger or grant access to a browser. Receipt export retains the evaluator and assistance conditions. A teacher cannot export for a learner. Registration and concept alignment remain explicit compatibility steps; a mathematically valid Tiza fraction curriculum is not automatically a nema-recognized catalog.

The original `protocol.js` contains one NUL byte in a string key separator; the vendored file is byte-identical, not damaged. SHA-256: `aaa9e8cbfcb3ec75a825706cc911619e7b6aee3c310d5c2d8987ca61b24a1f58`.
