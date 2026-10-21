"""Gateway 전송 결과 상태 머신의 단위 테스트. 네트워크·I/O 없이 실행한다."""

from dataclasses import replace

import pytest
from abc2lab_gateway.core import (
    AttemptOutcome,
    CaptureStatus,
    DecisionOutcome,
    GatewayReason,
    PreTransportGate,
    RecheckResult,
    SendStatus,
    TransportObservation,
    classify_attempt,
    classify_pre_transport,
    classify_transport,
)

_PROCEED_GATE = PreTransportGate(
    decision=DecisionOutcome.ALLOW,
    audit_committed=True,
    recheck=RecheckResult(passed=True),
    budget_committed=True,
)


def test_gate_allows_proceed_returns_none() -> None:
    assert classify_pre_transport(_PROCEED_GATE) is None


def test_block_decision_is_not_sent() -> None:
    out = classify_pre_transport(replace(_PROCEED_GATE, decision=DecisionOutcome.BLOCK))
    assert out is not None
    assert out.send_status is SendStatus.NOT_SENT
    assert out.capture_status is CaptureStatus.NOT_APPLICABLE
    assert out.reason_codes == (GatewayReason.POLICY_BLOCKED,)


def test_missing_decision_is_not_sent() -> None:
    out = classify_pre_transport(replace(_PROCEED_GATE, decision=DecisionOutcome.MISSING))
    assert out is not None
    assert out.reason_codes == (GatewayReason.DECISION_MISSING,)


def test_uncommitted_audit_blocks_before_transport() -> None:
    out = classify_pre_transport(replace(_PROCEED_GATE, audit_committed=False))
    assert out is not None
    assert out.send_status is SendStatus.NOT_SENT
    assert out.reason_codes == (GatewayReason.AUDIT_COMMIT_FAILED,)


def test_failed_recheck_preserves_reason() -> None:
    recheck = RecheckResult(passed=False, reason=GatewayReason.SESSION_GENERATION_CHANGED)
    out = classify_pre_transport(replace(_PROCEED_GATE, recheck=recheck))
    assert out is not None
    assert out.reason_codes == (GatewayReason.SESSION_GENERATION_CHANGED,)


def test_exhausted_budget_is_not_sent() -> None:
    out = classify_pre_transport(replace(_PROCEED_GATE, budget_committed=False))
    assert out is not None
    assert out.reason_codes == (GatewayReason.BUDGET_EXHAUSTED,)


def test_block_precedes_audit_check() -> None:
    gate = replace(_PROCEED_GATE, decision=DecisionOutcome.BLOCK, audit_committed=False)
    out = classify_pre_transport(gate)
    assert out is not None
    assert out.reason_codes == (GatewayReason.POLICY_BLOCKED,)


def test_transport_not_entered_is_not_sent() -> None:
    out = classify_transport(TransportObservation.NOT_ENTERED)
    assert out.send_status is SendStatus.NOT_SENT
    assert out.capture_status is CaptureStatus.NOT_APPLICABLE
    assert out.reason_codes == (GatewayReason.TRANSPORT_NOT_ENTERED,)


def test_sent_captured_requires_capture_ref_present() -> None:
    out = classify_transport(TransportObservation.SENT_CAPTURED)
    assert out.send_status is SendStatus.SENT
    assert out.capture_status is CaptureStatus.CAPTURED
    assert out.has_capture_ref is True


def test_sent_capture_unavailable_is_sent_without_ref() -> None:
    out = classify_transport(TransportObservation.SENT_CAPTURE_UNAVAILABLE)
    assert out.send_status is SendStatus.SENT
    assert out.capture_status is CaptureStatus.UNAVAILABLE
    assert out.has_capture_ref is False
    assert out.reason_codes == (GatewayReason.CAPTURE_UNAVAILABLE,)


def test_response_overlimit_is_sent_unavailable() -> None:
    out = classify_transport(TransportObservation.SENT_RESPONSE_OVERLIMIT)
    assert out.send_status is SendStatus.SENT
    assert out.capture_status is CaptureStatus.UNAVAILABLE
    assert out.reason_codes == (GatewayReason.RESPONSE_LIMIT_EXCEEDED,)


def test_send_unconfirmed_is_unknown() -> None:
    out = classify_transport(TransportObservation.SEND_UNCONFIRMED)
    assert out.send_status is SendStatus.UNKNOWN
    assert out.capture_status is CaptureStatus.INDETERMINATE
    assert out.has_capture_ref is False
    assert out.reason_codes == (GatewayReason.SEND_ACKNOWLEDGEMENT_LOST,)


def test_attempt_proceeds_to_transport_when_gate_passes() -> None:
    out = classify_attempt(_PROCEED_GATE, TransportObservation.SENT_CAPTURED)
    assert out.send_status is SendStatus.SENT
    assert out.capture_status is CaptureStatus.CAPTURED


def test_attempt_unknown_is_preserved_through_gate() -> None:
    out = classify_attempt(_PROCEED_GATE, TransportObservation.SEND_UNCONFIRMED)
    assert out.send_status is SendStatus.UNKNOWN


def test_attempt_gate_block_ignores_transport_observation() -> None:
    gate = replace(_PROCEED_GATE, decision=DecisionOutcome.BLOCK)
    out = classify_attempt(gate, TransportObservation.SENT_CAPTURED)
    assert out.send_status is SendStatus.NOT_SENT
    assert out.reason_codes == (GatewayReason.POLICY_BLOCKED,)


def test_invalid_send_capture_combination_rejected() -> None:
    with pytest.raises(ValueError):
        AttemptOutcome(SendStatus.SENT, CaptureStatus.NOT_APPLICABLE, has_capture_ref=False)


def test_sent_captured_without_ref_rejected() -> None:
    with pytest.raises(ValueError):
        AttemptOutcome(SendStatus.SENT, CaptureStatus.CAPTURED, has_capture_ref=False)


def test_failed_recheck_requires_reason() -> None:
    with pytest.raises(ValueError):
        RecheckResult(passed=False)


def test_recheck_reason_must_be_a_recheck_reason() -> None:
    with pytest.raises(ValueError):
        RecheckResult(passed=False, reason=GatewayReason.POLICY_BLOCKED)
