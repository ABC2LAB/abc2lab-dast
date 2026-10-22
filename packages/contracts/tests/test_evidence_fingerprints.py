"""Evidence and Comparison production adapters and fixed independent SHA-256 vectors."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from abc2lab_contracts.evidence import (
    ComparisonPayload,
    ComparisonSignals,
    EvidenceSummary,
    StoreReceipt,
)
from abc2lab_contracts.fingerprint import (
    _registered_record_envelope,
    _registered_record_fingerprint,
    canonical_json_bytes,
    comparison_fingerprint,
    evidence_fingerprint,
)
from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ParameterLocation,
    ReasonCode,
    ResponseClass,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.recipe import RecipeParameter, RegisteredRequestRecipe
from abc2lab_contracts.registration import ComparisonRules

VECTORS = Path(__file__).resolve().parents[3] / "docs/examples/fingerprint-v1-vectors.json"
T = datetime(2026, 10, 21, tzinfo=UTC)
R = RunKey("org", "target", "env", "run")
S = SourceVersion("app", "registration", 1)


def _evidence() -> EvidenceSummary:
    recipe = RegisteredRequestRecipe(
        "poc.v0.1",
        "op-read",
        1,
        "resource-a",
        "binding-a",
        1,
        "GET",
        "${REGISTERED_ORIGIN}",
        "/objects/${RESOURCE_ID}",
        (RecipeParameter("id", ParameterLocation.PATH, "${RESOURCE_ID}"),),
        "fresh_registered_session",
        S,
    )
    return EvidenceSummary(
        R,
        "evidence-owner",
        "attempt-owner",
        "op-read",
        "resource-a",
        "account-owner",
        1,
        "identity-owner",
        ResponseClass.NORMAL,
        200,
        T,
        S,
        AuditLink("evidence-producer", "event-evidence-owner"),
        recipe,
        (),
    )


def _comparison() -> ComparisonPayload:
    return ComparisonPayload(
        R,
        "comparison-a",
        "case-a",
        "resource-a",
        "op-read",
        "evidence-owner",
        "evidence-cross",
        "identity-owner",
        "identity-cross",
        ComparisonSignals(
            CheckState.YES,
            CheckState.YES,
            CheckState.YES,
            CheckState.YES,
            CheckState.UNKNOWN,
            CheckState.YES,
            CheckState.UNKNOWN,
        ),
        ComparisonRules(S, "normalizer", "oracle", "canary"),
    )


@pytest.mark.parametrize(
    "name,record,fn",
    [
        ("evidence-v1-c3", _evidence(), evidence_fingerprint),
        ("comparison-v1-c3", _comparison(), comparison_fingerprint),
    ],
)
def test_production_vectors_match_exact_bytes_and_sha(
    name: str, record: object, fn: object
) -> None:
    obj = json.loads(VECTORS.read_text(encoding="utf-8"))
    vectors = [v for v in obj["vectors"] if v["id"] == name]
    assert len(vectors) == 1
    vector = vectors[0]
    assert vector["validation_path"] == "production_adapter"
    encoded = canonical_json_bytes(_registered_record_envelope(record))
    assert encoded == vector["canonical_utf8"].encode("utf-8")
    assert sha256(encoded).hexdigest() == vector["sha256"]
    assert _registered_record_fingerprint(record) == vector["sha256"]
    assert fn(record) == vector["sha256"]  # type: ignore[operator]


def test_business_field_changes_affect_fingerprint_but_store_receipt_is_separate() -> None:
    evidence = _evidence()
    assert evidence_fingerprint(
        replace(evidence, source_event=AuditLink("x", "event"))
    ) != evidence_fingerprint(evidence)
    assert evidence_fingerprint(
        replace(
            evidence,
            request_recipe=None,
            recipe_reason_codes=(ReasonCode.RECIPE_UNSUPPORTED,),
        )
    ) != evidence_fingerprint(evidence)
    comparison = _comparison()
    changed_rules = ComparisonRules(
        SourceVersion("app", "registration", 2), "normalizer", "oracle", "canary"
    )
    assert comparison_fingerprint(
        replace(comparison, rules=changed_rules)
    ) != comparison_fingerprint(comparison)
    assert comparison_fingerprint(comparison) == comparison_fingerprint(comparison)


def test_operational_registry_rejects_unregistered_receipt() -> None:
    from abc2lab_contracts.evidence import ArtifactKind

    receipt = StoreReceipt(R, "sub", "evidence-owner", ArtifactKind.EVIDENCE, S, T, "a" * 64)
    with pytest.raises(ValueError, match="unregistered"):
        _registered_record_fingerprint(receipt)
    with pytest.raises(TypeError, match="exact EvidenceSummary"):
        evidence_fingerprint(cast(EvidenceSummary, _comparison()))
