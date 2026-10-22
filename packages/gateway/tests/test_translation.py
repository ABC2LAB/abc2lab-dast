"""Gateway C2 변환 어댑터의 단위 테스트. 네트워크·I/O 없이 실행한다."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from abc2lab_contracts.audit import (
    AuditEventKind,
    AuditReceipt,
    AuditRecordBinding,
    PolicyOutcome,
)
from abc2lab_contracts.execution import PolicyDecision
from abc2lab_contracts.primitives import (
    AuditLink,
    CaptureStatus,
    ReasonCode,
    RunKey,
    SendStatus,
    SourceVersion,
)
from abc2lab_gateway.adapters import (
    AttemptContext,
    to_attempt_result,
    to_contract_reasons,
    to_decision_outcome,
)
from abc2lab_gateway.core import (
    DecisionOutcome,
    GatewayReason,
    TransportObservation,
    classify_transport,
)

_NOW = datetime(2026, 10, 22, 12, 0, 0, tzinfo=UTC)
_RUN_KEY = RunKey(organization_ref="org", target_ref="tgt", environment_ref="env", run_ref="run-1")
_SOURCE = SourceVersion(issuer="iss", source_ref="policy-rules", revision=1)


_BASE_CONTEXT = AttemptContext(
    run_key=_RUN_KEY,
    request_ref="request-1",
    attempt_ref="attempt-1",
    decision_ref="decision-1",
    binding_id="binding-1",
)


def _decision(outcome: PolicyOutcome) -> PolicyDecision:
    binding = AuditRecordBinding(
        event_kind=AuditEventKind.POLICY_DECISION,
        record_ref="decision-1",
        record_revision=1,
        record_fingerprint="a" * 64,
        request_ref="request-1",
        attempt_ref=None,
        binding_id="binding-1",
    )
    receipt = AuditReceipt(
        run_key=_RUN_KEY,
        producer="policy",
        event_ref="policy:run-1:1",
        sequence=1,
        binding=binding,
        committed_at=_NOW,
    )
    return PolicyDecision(
        run_key=_RUN_KEY,
        decision_ref="decision-1",
        binding_id="binding-1",
        evaluated_view_fingerprint="a" * 64,
        outcome=outcome,
        policy_version=_SOURCE,
        issued_at=_NOW,
        expires_at=_NOW + timedelta(minutes=10),
        audit_receipt=receipt,
        reason_codes=(),
    )


def test_decision_outcome_none_is_missing() -> None:
    assert to_decision_outcome(None) is DecisionOutcome.MISSING


def test_decision_outcome_allow_and_block() -> None:
    assert to_decision_outcome(_decision(PolicyOutcome.ALLOW)) is DecisionOutcome.ALLOW
    assert to_decision_outcome(_decision(PolicyOutcome.BLOCK)) is DecisionOutcome.BLOCK


def test_reason_mapping_and_dedup() -> None:
    reasons = (
        GatewayReason.SESSION_GENERATION_CHANGED,
        GatewayReason.BUDGET_EXHAUSTED,
        GatewayReason.DECISION_MISSING,
        GatewayReason.POLICY_BLOCKED,
    )
    assert to_contract_reasons(reasons) == (
        ReasonCode.SESSION_GENERATION_CHANGED,
        ReasonCode.BUDGET_EXHAUSTED,
        ReasonCode.POLICY_BLOCKED,
    )


def test_informational_reasons_are_dropped() -> None:
    dropped = (GatewayReason.SENT_CAPTURED, GatewayReason.TRANSPORT_NOT_ENTERED)
    assert to_contract_reasons(dropped) == ()


def test_gate_contradiction_maps_to_view_mismatch() -> None:
    assert to_contract_reasons((GatewayReason.GATE_CONTRADICTION,)) == (
        ReasonCode.POLICY_VIEW_MISMATCH,
    )


def test_sent_captured_requires_capture_ref() -> None:
    outcome = classify_transport(TransportObservation.SENT_CAPTURED)
    result = to_attempt_result(outcome, replace(_BASE_CONTEXT, capture_ref="capture-1"))
    assert result.send_status is SendStatus.SENT
    assert result.capture_status is CaptureStatus.CAPTURED
    assert result.capture_ref == "capture-1"
    assert result.reason_codes == ()


def test_captured_outcome_without_ref_rejected() -> None:
    outcome = classify_transport(TransportObservation.SENT_CAPTURED)
    with pytest.raises(ValueError):
        to_attempt_result(outcome, _BASE_CONTEXT)


def test_capture_ref_without_captured_outcome_rejected() -> None:
    outcome = classify_transport(TransportObservation.SEND_UNCONFIRMED)
    with pytest.raises(ValueError):
        to_attempt_result(outcome, replace(_BASE_CONTEXT, capture_ref="capture-1"))


def test_unknown_outcome_maps_to_indeterminate() -> None:
    outcome = classify_transport(TransportObservation.SEND_UNCONFIRMED)
    result = to_attempt_result(outcome, _BASE_CONTEXT)
    assert result.send_status is SendStatus.UNKNOWN
    assert result.capture_status is CaptureStatus.INDETERMINATE
    assert result.capture_ref is None
    assert result.reason_codes == (ReasonCode.SEND_ACKNOWLEDGEMENT_LOST,)


def test_not_sent_outcome_preserves_links() -> None:
    outcome = classify_transport(TransportObservation.NOT_ENTERED)
    links = (AuditLink(producer="gateway", event_ref="event-1"),)
    result = to_attempt_result(outcome, replace(_BASE_CONTEXT, audit_links=links))
    assert result.send_status is SendStatus.NOT_SENT
    assert result.capture_status is CaptureStatus.NOT_APPLICABLE
    assert result.audit_links == links
    assert result.reason_codes == ()
