"""Gateway 전송 결과 상태 머신의 단위 테스트. 네트워크·I/O 없이 실행한다."""

from dataclasses import replace

import pytest
from abc2lab_gateway.core import (
    AttemptOutcome,
    CaptureStatus,
    DecisionCommit,
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


def test_decision_commit_default_is_verified() -> None:
    # 기본값 VERIFIED라 기존 게이트는 그대로 진행한다.
    assert _PROCEED_GATE.decision_commit is DecisionCommit.VERIFIED


def test_invalid_decision_commit_blocks_before_audit() -> None:
    gate = replace(_PROCEED_GATE, decision_commit=DecisionCommit.INVALID, audit_committed=False)
    out = classify_pre_transport(gate)
    assert out is not None
    assert out.send_status is SendStatus.NOT_SENT
    assert out.reason_codes == (GatewayReason.DECISION_UNVERIFIED,)


def test_unknown_decision_commit_blocks() -> None:
    gate = replace(_PROCEED_GATE, decision_commit=DecisionCommit.UNKNOWN)
    out = classify_pre_transport(gate)
    assert out is not None
    assert out.reason_codes == (GatewayReason.DECISION_VERIFICATION_UNKNOWN,)


def test_decision_outcome_block_precedes_commit_check() -> None:
    # 결정 자체가 block이면 commit 검증보다 먼저 policy_blocked로 막는다(§10 순서).
    gate = replace(
        _PROCEED_GATE, decision=DecisionOutcome.BLOCK, decision_commit=DecisionCommit.INVALID
    )
    out = classify_pre_transport(gate)
    assert out is not None
    assert out.reason_codes == (GatewayReason.POLICY_BLOCKED,)


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


def test_gate_block_does_not_override_real_sent() -> None:
    # 게이트가 막아도 실제 전송 관찰(SENT_CAPTURED)이면 sent를 보존하고 모순을 드러낸다.
    gate = replace(_PROCEED_GATE, decision=DecisionOutcome.BLOCK)
    out = classify_attempt(gate, TransportObservation.SENT_CAPTURED)
    assert out.send_status is SendStatus.SENT
    assert out.capture_status is CaptureStatus.CAPTURED
    assert GatewayReason.POLICY_BLOCKED in out.reason_codes
    assert GatewayReason.GATE_CONTRADICTION in out.reason_codes


def test_gate_block_does_not_override_unknown() -> None:
    gate = replace(_PROCEED_GATE, decision=DecisionOutcome.BLOCK)
    out = classify_attempt(gate, TransportObservation.SEND_UNCONFIRMED)
    assert out.send_status is SendStatus.UNKNOWN
    assert GatewayReason.GATE_CONTRADICTION in out.reason_codes


def test_gate_block_with_not_entered_uses_gate_reason() -> None:
    # 전송 미진입이 입증된 경우에만 게이트 사유로 not_sent.
    gate = replace(_PROCEED_GATE, decision=DecisionOutcome.BLOCK)
    out = classify_attempt(gate, TransportObservation.NOT_ENTERED)
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


def test_passed_recheck_with_reason_rejected() -> None:
    with pytest.raises(ValueError):
        RecheckResult(passed=True, reason=GatewayReason.CANCELLED)
