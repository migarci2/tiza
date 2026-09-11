"""nema/0.1 interoperability subset, with Tiza's explicit scope checks."""
from datetime import datetime, timezone
from hashlib import sha256
import json

from .crypto import decode_token, encode, verify_token

ASSERTION = "readiness-assertion"
RECEIPT = "evidence-receipt"
ASSERTION_KEYS = set("type protocol audience purpose requestHash learnerKeyId assertions issuedAt expiresAt vaultKey".split())
RECEIPT_REQUIRED = set("type protocol receiptId issuer keyId subject activity claims issuedAt".split())


def timestamp(value: str) -> datetime:
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if at.tzinfo is None:
        raise ValueError("Timezone required")
    return at


def required_string(obj: dict, key: str):
    if not isinstance(obj.get(key), str) or not obj[key]:
        raise ValueError("Invalid " + key)


def validate_shape(payload: dict, kind: str) -> dict:
    required = ASSERTION_KEYS if kind == ASSERTION else RECEIPT_REQUIRED
    allowed = required if kind == ASSERTION else required | {"conditions", "issuerKey"}
    if kind not in (ASSERTION, RECEIPT) or payload.get("type") != kind or payload.get("protocol") != "nema/0.1":
        raise ValueError("Unexpected protocol or type")
    if not required <= payload.keys() or payload.keys() - allowed:
        raise ValueError("Unexpected or missing fields")
    strings = ("audience", "purpose", "requestHash", "learnerKeyId") if kind == ASSERTION else ("receiptId", "issuer", "keyId", "subject")
    for k in strings:
        required_string(payload, k)
    timestamp(payload["issuedAt"])
    entries = payload.get("assertions" if kind == ASSERTION else "claims")
    if not isinstance(entries, list) or (kind == RECEIPT and not entries) or len(entries) > 100:
        raise ValueError("Invalid claim list")
    fields = ("concept", "ability", "status", "confidence") if kind == ASSERTION else ("concept", "ability", "evidenceType", "result")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid claim")
        for k in fields:
            required_string(entry, k)
        if kind == ASSERTION and entry.keys() - set(fields) - {"alignedTo", "reason"}:
            raise ValueError("Unexpected assertion disclosure")
    if kind == ASSERTION:
        timestamp(payload["expiresAt"])
    elif not isinstance(payload["activity"], dict):
        raise ValueError("Invalid activity")
    else:
        required_string(payload["activity"], "id")
    return payload


def request_hash(request: dict) -> str:
    return "sha256:" + sha256(json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def verify_assertion(token: str, *, audience: str, now: datetime, request: dict | None = None, expected_key: dict | None = None) -> dict:
    if not audience or now.tzinfo is None:
        raise ValueError("Audience and explicit timezone-aware time required")
    payload = validate_shape(decode_token(token)[0], ASSERTION)
    verify_token(token, payload["vaultKey"])
    if payload["audience"] != audience:
        raise ValueError("Wrong audience")
    if timestamp(payload["expiresAt"]) <= now or timestamp(payload["issuedAt"]) > now:
        raise ValueError("Expired or future assertion")
    if timestamp(payload["expiresAt"]) <= timestamp(payload["issuedAt"]):
        raise ValueError("Invalid assertion lifetime")
    expected_subject = "lk_" + encode(sha256((payload["vaultKey"]["x"] + "|" + audience).encode()).digest())[:16]
    if payload["learnerKeyId"] != expected_subject:
        raise ValueError("Subject does not match vault key")
    if expected_key is not None and payload["vaultKey"] != expected_key:
        raise ValueError("Vault key changed; a new link requires consent")
    if request is not None:
        if payload["requestHash"] != request_hash(request) or payload["purpose"] != request["purpose"]:
            raise ValueError("Assertion does not match request")
        allowed = {(r["concept"], r["ability"]) for r in request["requirements"]}
        if any((r["concept"], r["ability"]) not in allowed for r in payload["assertions"]):
            raise ValueError("Assertion exceeds consented scope")
    return payload


def verify_receipt(token: str, issuers: dict, *, subject: str | None = None) -> dict:
    payload = validate_shape(decode_token(token)[0], RECEIPT)
    known = issuers.get(payload["keyId"])
    if known is not None:
        if known["origin"] != payload["issuer"]:
            raise ValueError("Issuer origin mismatch")
        key, trust = known["jwk"], "registered"
    elif payload["keyId"].startswith("self:") and "issuerKey" in payload:
        key, trust = payload["issuerKey"], "self"
    else:
        raise ValueError("Unknown issuer")
    verify_token(token, key)
    if subject is not None and payload["subject"] != subject:
        raise ValueError("Wrong subject")
    return {"payload": payload, "trust": trust}
