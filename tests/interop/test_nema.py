import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from tiza.integrations.nema.crypto import encode, public_jwk, sign_bytes, sign_token, verify_token
from tiza.integrations.nema.protocol import verify_assertion, verify_receipt

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)


def node(script, payload):
    result = subprocess.run(["node", "--input-type=module", "-e", script], input=json.dumps(payload), text=True, capture_output=True, cwd=ROOT, check=True)
    return json.loads(result.stdout)


def test_original_js_and_python_verify_each_others_tokens():
    key = ec.generate_private_key(ec.SECP256R1())
    public = public_jwk(key)
    private = {**public, "d": encode(key.private_numbers().private_value.to_bytes(32, "big"))}
    receipt = {"type": "evidence-receipt", "protocol": "nema/0.1", "receiptId": "rcpt_test", "issuer": "https://tiza.example", "keyId": "self:https://tiza.example", "issuerKey": public, "subject": "lk_test", "activity": {"id": "fraction-1", "version": "1"}, "claims": [{"concept": "tiza:equivalence", "ability": "apply", "evidenceType": "exercise", "result": "pass"}], "conditions": {"hintsUsed": 1, "grader": "deterministic"}, "issuedAt": "2026-09-10T12:00:00Z"}
    # Deliberate whitespace: the foreign verifier must verify original bytes.
    token = sign_bytes(json.dumps(receipt, indent=2).encode(), key)
    output = node("""
      import {readFileSync} from 'node:fs';
      import {verifyReceipt,signToken,buildReadinessRequest,buildAssertionPayload} from './vendor/nema/shared/protocol.js';
      const p=JSON.parse(readFileSync(0,'utf8'));
      const verified=await verifyReceipt(p.token, {});
      const request=buildReadinessRequest({audience:'https://tiza.example', purpose:'Plan next practice', requirements:[{concept:'tiza:equivalence',ability:'apply'}]});
      const assertion=await buildAssertionPayload({request,statuses:[{concept:'tiza:equivalence',ability:'apply',status:'ready',confidence:'low'}],vaultPublicJwk:p.public,now:'2026-09-10T12:00:00Z'});
      console.log(JSON.stringify({verified,token:await signToken(p.receipt,p.private),assertion:await signToken(assertion,p.private),request}));
    """, {"token": token, "receipt": receipt, "private": private, "public": public})
    assert output["verified"]["ok"] and output["verified"]["trust"] == "self"
    assert verify_receipt(output["token"], {}, subject="lk_test")["payload"] == receipt
    assert verify_assertion(output["assertion"], audience="https://tiza.example", now=NOW, request=output["request"])["assertions"][0]["concept"] == "tiza:equivalence"
    for kwargs in [{"audience": "https://wrong.example", "now": NOW}, {"audience": "https://tiza.example", "now": datetime(2027,1,1,tzinfo=timezone.utc)}]:
        with pytest.raises(ValueError):
            verify_assertion(output["assertion"], **kwargs)
    with pytest.raises(ValueError):
        verify_receipt(output["token"], {}, subject="someone-else")
    altered = token[:-10] + ("A" if token[-10] != "A" else "B") + token[-9:]
    with pytest.raises(Exception):
        verify_token(altered, public)


def test_signed_private_disclosures_and_unknown_protocol_rejected():
    key = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(ValueError):
        verify_receipt(sign_token({"type": "evidence-receipt", "protocol": "other"}, key), {})
    with pytest.raises(ValueError):
        verify_token(sign_bytes(b'{"a":1,"a":2}', key), public_jwk(key))
