"""Gateway 전송 결과 분류.

전송 전 게이트(결정 → 감사 commit → 재검사 → 예산)를 순서대로 확인해 하나라도 막히면
`not_sent`로 끝낸다. 게이트를 모두 통과하면 transport 관찰로 최종 결과를 분류한다. 전송 전
미진입이 입증된 시도만 `not_sent`이고, transport 진입 후 미확정은 `unknown`이며 자동 재전송하지
않는다. 네트워크·I/O 없이 동작하는 순수 함수다.
"""

from __future__ import annotations

from abc2lab_gateway.core.model import (
    AttemptOutcome,
    CaptureStatus,
    DecisionOutcome,
    GatewayReason,
    PreTransportGate,
    SendStatus,
    TransportObservation,
)


def _not_sent(reason: GatewayReason) -> AttemptOutcome:
    """전송 미진입이 입증된 결과를 만든다."""
    return AttemptOutcome(
        send_status=SendStatus.NOT_SENT,
        capture_status=CaptureStatus.NOT_APPLICABLE,
        has_capture_ref=False,
        reason_codes=(reason,),
    )


def classify_pre_transport(gate: PreTransportGate) -> AttemptOutcome | None:
    """전송 전 게이트를 순서대로 확인한다.

    Returns:
        게이트가 막으면 `not_sent` 결과, 모두 통과하면 None(transport로 진행).
    """
    if gate.decision is DecisionOutcome.BLOCK:
        return _not_sent(GatewayReason.POLICY_BLOCKED)
    if gate.decision is DecisionOutcome.MISSING:
        return _not_sent(GatewayReason.DECISION_MISSING)
    if not gate.audit_committed:
        return _not_sent(GatewayReason.AUDIT_COMMIT_FAILED)
    if not gate.recheck.passed:
        # RecheckResult 불변식상 실패면 사유가 존재한다.
        assert gate.recheck.reason is not None
        return _not_sent(gate.recheck.reason)
    if not gate.budget_committed:
        return _not_sent(GatewayReason.BUDGET_EXHAUSTED)
    return None


def classify_transport(observation: TransportObservation) -> AttemptOutcome:
    """transport 관찰을 §6의 허용 조합으로 분류한다."""
    if observation is TransportObservation.NOT_ENTERED:
        return _not_sent(GatewayReason.TRANSPORT_NOT_ENTERED)
    if observation is TransportObservation.SENT_CAPTURED:
        return AttemptOutcome(
            send_status=SendStatus.SENT,
            capture_status=CaptureStatus.CAPTURED,
            has_capture_ref=True,
            reason_codes=(GatewayReason.SENT_CAPTURED,),
        )
    if observation is TransportObservation.SENT_CAPTURE_UNAVAILABLE:
        return AttemptOutcome(
            send_status=SendStatus.SENT,
            capture_status=CaptureStatus.UNAVAILABLE,
            has_capture_ref=False,
            reason_codes=(GatewayReason.CAPTURE_UNAVAILABLE,),
        )
    if observation is TransportObservation.SENT_RESPONSE_OVERLIMIT:
        return AttemptOutcome(
            send_status=SendStatus.SENT,
            capture_status=CaptureStatus.UNAVAILABLE,
            has_capture_ref=False,
            reason_codes=(GatewayReason.RESPONSE_LIMIT_EXCEEDED,),
        )
    return AttemptOutcome(
        send_status=SendStatus.UNKNOWN,
        capture_status=CaptureStatus.INDETERMINATE,
        has_capture_ref=False,
        reason_codes=(GatewayReason.SEND_ACKNOWLEDGEMENT_LOST,),
    )


def classify_attempt(gate: PreTransportGate, observation: TransportObservation) -> AttemptOutcome:
    """게이트와 transport 관찰로 시도의 최종 결과를 낸다.

    게이트가 막으면 `not_sent`로 끝내고 transport 관찰은 보지 않는다. 통과하면 관찰을 분류한다.
    """
    return classify_pre_transport(gate) or classify_transport(observation)
