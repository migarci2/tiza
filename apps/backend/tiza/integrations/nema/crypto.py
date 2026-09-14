"""P-256/SHA-256 support for the nema wire contract."""
import base64
import json
import re

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ValueError("Invalid base64url")
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def public_key(jwk: dict) -> ec.EllipticCurvePublicKey:
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256" or "d" in jwk:
        raise ValueError("Expected a public P-256 key")
    x, y = decode(jwk["x"]), decode(jwk["y"])
    if len(x) != 32 or len(y) != 32:
        raise ValueError("Invalid P-256 coordinates")
    return ec.EllipticCurvePublicNumbers(int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()).public_key()


def public_jwk(key: ec.EllipticCurvePrivateKey) -> dict:
    n = key.public_key().public_numbers()
    return {"kty": "EC", "crv": "P-256", "x": encode(n.x.to_bytes(32, "big")), "y": encode(n.y.to_bytes(32, "big"))}


def sign_bytes(payload: bytes, key: ec.EllipticCurvePrivateKey) -> str:
    if not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("Expected P-256")
    r, s = decode_dss_signature(key.sign(payload, ec.ECDSA(hashes.SHA256())))
    return "nema1." + encode(payload) + "." + encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def sign_token(payload: dict, key: ec.EllipticCurvePrivateKey) -> str:
    return sign_bytes(json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode(), key)


def decode_token(token: str) -> tuple[dict, bytes, bytes]:
    if not isinstance(token, str) or len(token) > 65536:
        raise ValueError("Invalid or oversized nema token")
    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] != "nema1":
        raise ValueError("Invalid nema token")
    raw, signature = decode(parts[1]), decode(parts[2])
    def unique_object(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError("Duplicate JSON field")
            result[k] = v
        return result
    payload = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(payload, dict) or len(signature) != 64:
        raise ValueError("Invalid payload or signature")
    return payload, raw, signature


def verify_token(token: str, jwk: dict) -> dict:
    payload, raw, signature = decode_token(token)
    r, s = int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
    public_key(jwk).verify(encode_dss_signature(r, s), raw, ec.ECDSA(hashes.SHA256()))
    return payload
