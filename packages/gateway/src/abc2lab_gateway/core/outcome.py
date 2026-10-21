"""Gateway 전송 결과 분류.

전송 전 게이트(결정 → 감사 commit → 재검사 → 예산)를 순서대로 확인한다. 전송 전 미진입이 입증된
시도만 `not_sent`이다. transport 관찰이 실제 전송(또는 불명)을 가리키면 게이트 판단보다 우선해
`sent`/`unknown`을 보존하고, transport 진입 후 미확정은 `unknown`이며 자동 재전송하지 않는다.
네트워크·I/O 없이 동작하는 순수 함수다.
"""

from __future__ import annotations

from dataclasses import replace

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

    전송이 일어났거나 불명인 관찰(SENT_*/SEND_UNCONFIRMED)은 게이트 판단보다 우선해 실제
    `sent`/`unknown`을 보존한다. 게이트가 막았는데 전송 관찰이 있으면 모순이므로 사유에 드러내되
    상태를 `not_sent`로 내리지 않는다. 관찰이 `NOT_ENTERED`일 때만 게이트의 not_sent 사유를 쓴다.
    """
    gate_block = classify_pre_transport(gate)
    if observation is TransportObservation.NOT_ENTERED:
        return gate_block or _not_sent(GatewayReason.TRANSPORT_NOT_ENTERED)

    outcome = classify_transport(observation)
    if gate_block is None:
        return outcome
    # 모순: 게이트는 막았는데 전송 관찰이 존재한다. 실제 상태를 보존하고 모순을 사유로 남긴다.
    contradiction = gate_block.reason_codes + (GatewayReason.GATE_CONTRADICTION,)
    return replace(outcome, reason_codes=outcome.reason_codes + contradiction)
