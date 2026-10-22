"""전송 단계 미진입 사유의 공유 계약을 검증한다."""

from abc2lab_contracts.execution import AttemptResult
from abc2lab_contracts.primitives import CaptureStatus, ReasonCode, RunKey, SendStatus


def test_transport_not_entered_reason_wire_value() -> None:
    assert ReasonCode.TRANSPORT_NOT_ENTERED.value == "transport_not_entered"
    assert ReasonCode("transport_not_entered") is ReasonCode.TRANSPORT_NOT_ENTERED


def test_not_sent_attempt_keeps_transport_not_entered_reason() -> None:
    result = AttemptResult(
        run_key=RunKey("org", "target", "env", "run"),
        request_ref="request-1",
        attempt_ref="attempt-1",
        decision_ref="decision-1",
        binding_id="binding-1",
        send_status=SendStatus.NOT_SENT,
        capture_status=CaptureStatus.NOT_APPLICABLE,
        capture_ref=None,
        auth_signal=None,
        audit_links=(),
        reason_codes=(ReasonCode.TRANSPORT_NOT_ENTERED,),
    )
    assert result.reason_codes == (ReasonCode.TRANSPORT_NOT_ENTERED,)
    assert result.send_status is SendStatus.NOT_SENT
    assert result.capture_status is CaptureStatus.NOT_APPLICABLE
