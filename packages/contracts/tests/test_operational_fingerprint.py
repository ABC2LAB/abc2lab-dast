"""Golden and negative tests for the typed C2 operational fingerprints."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict, cast

import pytest
from abc2lab_contracts.audit import AttemptRecord, AuditReceipt, PolicyOutcome, RequestIntentRecord
from abc2lab_contracts.execution import (
    PolicyDecision,
    PolicyDecisionContent,
    PolicyInput,
)
from abc2lab_contracts.fingerprint import (
    _registered_record_envelope,
    attempt_fingerprint,
    canonical_json_bytes,
    identity_content_fingerprint,
    identity_fingerprint,
    policy_decision_content_fingerprint,
    policy_decision_fingerprint,
    policy_input_fingerprint,
    request_intent_fingerprint,
)
from abc2lab_contracts.primitives import SourceVersion
from abc2lab_contracts.session import IdentityContent, IdentityResult


class _Vector(TypedDict):
    id: str
    canonical_utf8: str
    sha256: str


_VECTORS = cast(
    list[_Vector],
    json.loads(
        (
            Path(__file__).resolve().parents[3] / "docs/examples/fingerprint-v1-vectors.json"
        ).read_text(encoding="utf-8")
    )["vectors"],
)


def _vector(vector_id: str) -> _Vector:
    return next(vector for vector in _VECTORS if vector["id"] == vector_id)


def test_policy_input_matches_golden(policy_input: PolicyInput) -> None:
    vector = _vector("policy-input-v1")
    assert policy_input_fingerprint(policy_input) == vector["sha256"]


def test_decision_content_and_final_share_golden(
    decision_content: PolicyDecisionContent, decision: PolicyDecision
) -> None:
    vector = _vector("policy-decision-v1")
    assert policy_decision_content_fingerprint(decision_content) == vector["sha256"]
    assert policy_decision_fingerprint(decision) == vector["sha256"]


def test_identity_content_and_final_share_golden(
    identity_content: IdentityContent, identity: IdentityResult
) -> None:
    vector = _vector("identity-v1")
    assert identity_content_fingerprint(identity_content) == vector["sha256"]
    assert identity_fingerprint(identity) == vector["sha256"]


def test_intent_and_attempt_match_golden(
    intent: RequestIntentRecord, attempt: AttemptRecord
) -> None:
    assert request_intent_fingerprint(intent) == _vector("request-intent-v1")["sha256"]
    assert attempt_fingerprint(attempt) == _vector("attempt-v1")["sha256"]


def test_all_operational_envelopes_match_exact_golden_bytes(
    policy_input: PolicyInput,
    decision: PolicyDecision,
    identity: IdentityResult,
    intent: RequestIntentRecord,
    attempt: AttemptRecord,
) -> None:
    records = (
        ("policy-input-v1", policy_input),
        ("policy-decision-v1", decision),
        ("identity-v1", identity),
        ("request-intent-v1", intent),
        ("attempt-v1", attempt),
    )
    for vector_id, record in records:
        vector = _vector(vector_id)
        assert canonical_json_bytes(_registered_record_envelope(record)) == vector[
            "canonical_utf8"
        ].encode("utf-8")


def test_receipts_are_excluded_but_business_changes_are_not(
    decision: PolicyDecision,
    decision_content: PolicyDecisionContent,
    identity: IdentityResult,
) -> None:
    assert policy_decision_fingerprint(decision) == policy_decision_content_fingerprint(
        decision_content
    )
    changed = replace(decision_content, binding_id="other-binding")
    assert policy_decision_content_fingerprint(changed) != policy_decision_content_fingerprint(
        decision_content
    )
    altered_receipt = replace(decision.audit_receipt, event_ref="other-event", sequence=2)
    assert policy_decision_fingerprint(replace(decision, audit_receipt=altered_receipt)) == (
        policy_decision_fingerprint(decision)
    )
    identity_receipt = replace(
        cast(AuditReceipt, identity.audit_receipt),
        event_ref="other-identity-event",
        sequence=2,
    )
    assert identity_fingerprint(replace(identity, audit_receipt=identity_receipt)) == (
        identity_fingerprint(identity)
    )


def test_content_source_and_enum_changes_change_digest(
    decision_content: PolicyDecisionContent,
) -> None:
    assert policy_decision_content_fingerprint(
        replace(decision_content, policy_version=SourceVersion("policy-demo", "other", 2))
    ) != policy_decision_content_fingerprint(decision_content)
    assert policy_decision_content_fingerprint(
        replace(decision_content, outcome=PolicyOutcome.BLOCK)
    ) != policy_decision_content_fingerprint(decision_content)


def test_wrappers_reject_subclasses_and_unregistered_demo(
    decision_content: PolicyDecisionContent,
) -> None:
    class DecisionChild(PolicyDecisionContent):
        pass

    with pytest.raises(TypeError, match="exact"):
        policy_decision_content_fingerprint(object.__new__(DecisionChild))
    with pytest.raises(ValueError, match="unregistered"):
        from abc2lab_contracts.fingerprint import _registered_record_fingerprint

        _registered_record_fingerprint(object())


def test_wrappers_reject_wrong_kind_raw_enum_and_schema_tampering(
    policy_input: PolicyInput,
    decision: PolicyDecision,
) -> None:
    with pytest.raises(TypeError, match="PolicyInput"):
        policy_input_fingerprint(decision)  # type: ignore[arg-type]
    object.__setattr__(policy_input, "schema_version", "policy_input.v2")
    with pytest.raises(ValueError, match="schema version"):
        policy_input_fingerprint(policy_input)


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [
        ("operation_revision", True),
        ("identity_status", "verified"),
        ("expires_at", datetime(2026, 10, 21)),
        ("scope", {}),
        ("binding_issuer", ""),
    ],
)
def test_operational_wrapper_revalidates_tampered_fields(
    policy_input: PolicyInput, field_name: str, invalid: object
) -> None:
    """컨스트럭터를 우회한 값도 hash 경계에서 다시 검사한다."""
    object.__setattr__(policy_input, field_name, invalid)
    with pytest.raises((TypeError, ValueError)):
        policy_input_fingerprint(policy_input)


def test_missing_nullable_field_is_not_serialized_as_null(policy_input: PolicyInput) -> None:
    object.__delattr__(policy_input, "expected_policy")
    with pytest.raises(TypeError, match="missing"):
        policy_input_fingerprint(policy_input)


def test_operational_wrapper_revalidates_nested_invariants(policy_input: PolicyInput) -> None:
    object.__setattr__(policy_input.budget, "max_attempts", 0)
    with pytest.raises(ValueError, match="positive"):
        policy_input_fingerprint(policy_input)


def test_list_is_not_a_tuple_even_inside_policy_attributes(policy_input: PolicyInput) -> None:
    object.__setattr__(policy_input.policy_attributes, "parameter_names", ["object_id"])
    with pytest.raises(TypeError, match="tuple"):
        policy_input_fingerprint(policy_input)


def test_tuple_order_source_revision_and_utc_offsets(policy_input: PolicyInput) -> None:
    first = replace(
        policy_input,
        policy_attributes=replace(policy_input.policy_attributes, parameter_names=("a", "b")),
    )
    swapped = replace(
        first, policy_attributes=replace(first.policy_attributes, parameter_names=("b", "a"))
    )
    assert policy_input_fingerprint(first) != policy_input_fingerprint(swapped)
    changed_source = replace(
        policy_input,
        scope=replace(policy_input.scope, source=replace(policy_input.scope.source, revision=2)),
    )
    assert policy_input_fingerprint(changed_source) != policy_input_fingerprint(policy_input)
    offset = timezone(timedelta(hours=9))
    same_time = replace(policy_input, expires_at=policy_input.expires_at.astimezone(offset))
    assert policy_input_fingerprint(same_time) == policy_input_fingerprint(policy_input)
