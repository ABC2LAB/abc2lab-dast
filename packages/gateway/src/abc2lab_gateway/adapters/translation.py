"""Gateway 내부 결과와 C2 실행 경계 타입 사이의 변환.

내부 `AttemptOutcome`(§6 상태 머신)을 공개 `AttemptResult`로, 받은 `PolicyDecision`을 게이트
입력 `DecisionOutcome`으로 바꾸는 순수 함수들이다. 내부 `SendStatus`/`CaptureStatus`는 값은 같아도
contracts enum과 별도 타입이라 값으로 변환한다. 비밀·원문·캡처 핸들은 담지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from abc2lab_contracts.audit import PolicyOutcome
from abc2lab_contracts.execution import AttemptResult, PolicyDecision
from abc2lab_contracts.primitives import (
    AuditLink,
    CaptureStatus,
    ReasonCode,
    Ref,
    RunKey,
    SendStatus,
)
from abc2lab_contracts.session import AuthSignal

from abc2lab_gateway.core.model import AttemptOutcome, DecisionOutcome, GatewayReason

# 내부 사유를 공개 `ReasonCode`로 매핑한다. None은 성공 표식처럼 wire에서 뺀다.
# GatewayReason 전부를 덮어야 한다(미등록 시 실행 중 KeyError). 전수 커버는 테스트로 지킨다.
_REASON_MAP: dict[GatewayReason, ReasonCode | None] = {
    GatewayReason.POLICY_BLOCKED: ReasonCode.POLICY_BLOCKED,
    # decision_ref=None으로 Policy 차단 사례와 구분되므로 같은 code를 써도 된다.
    GatewayReason.DECISION_MISSING: ReasonCode.POLICY_BLOCKED,
    GatewayReason.DECISION_UNVERIFIED: ReasonCode.SOURCE_UNVERIFIED,
    GatewayReason.DECISION_VERIFICATION_UNKNOWN: ReasonCode.AUDIT_VERIFICATION_UNKNOWN,
    GatewayReason.AUDIT_COMMIT_FAILED: ReasonCode.AUDIT_COMMIT_FAILED,
    GatewayReason.SESSION_GENERATION_CHANGED: ReasonCode.SESSION_GENERATION_CHANGED,
    GatewayReason.SCOPE_MISMATCH: ReasonCode.SCOPE_MISMATCH,
    GatewayReason.BINDING_MISMATCH: ReasonCode.POLICY_VIEW_MISMATCH,
    GatewayReason.CANCELLED: ReasonCode.CANCELLED,
    GatewayReason.DEADLINE_EXCEEDED: ReasonCode.DEADLINE_EXCEEDED,
    GatewayReason.BUDGET_EXHAUSTED: ReasonCode.BUDGET_EXHAUSTED,
    GatewayReason.CAPTURE_UNAVAILABLE: ReasonCode.CAPTURE_UNAVAILABLE,
    GatewayReason.RESPONSE_LIMIT_EXCEEDED: ReasonCode.RESPONSE_LIMIT_EXCEEDED,
    GatewayReason.SEND_ACKNOWLEDGEMENT_LOST: ReasonCode.SEND_ACKNOWLEDGEMENT_LOST,
    # 게이트가 막았는데 전송된 모순은 Gateway가 자기 불변식을 어긴 것 → internal_error.
    # 게이트 사유와 별도 code라 dedup 후에도 둘 다 남아 감사에서 사라지지 않는다.
    GatewayReason.GATE_CONTRADICTION: ReasonCode.INTERNAL_ERROR,
    GatewayReason.SENT_CAPTURED: None,
    # 게이트를 모두 통과했지만 transport에 들어가지 못한 not_sent의 "안 보낸 이유"(#33).
    GatewayReason.TRANSPORT_NOT_ENTERED: ReasonCode.TRANSPORT_NOT_ENTERED,
}


@dataclass(frozen=True, slots=True)
class AttemptContext:
    """`AttemptResult` 조립에 필요한 run·요청·시도 참조와 감사 연결."""

    run_key: RunKey
    request_ref: Ref
    attempt_ref: Ref
    decision_ref: Ref | None
    binding_id: Ref | None
    capture_ref: Ref | None = None
    auth_signal: AuthSignal | None = None
    audit_links: tuple[AuditLink, ...] = field(default_factory=tuple)


def to_decision_outcome(decision: PolicyDecision | None) -> DecisionOutcome:
    """execute에 전달된 정책 결정을 게이트 입력으로 축약한다.

    None은 `MISSING`이다. `ALLOW`만 명시적으로 `ALLOW`로 두고 그 외 outcome은 모두 `BLOCK`으로
    보낸다(뒤에 outcome 값이 늘어도 fail-open이 되지 않게). 여기서 `ALLOW`는 Gateway의 전송 직전
    재검증 전 주장일 뿐 전송 허가가 아니다.
    """
    if decision is None:
        return DecisionOutcome.MISSING
    if decision.outcome is PolicyOutcome.ALLOW:
        return DecisionOutcome.ALLOW
    return DecisionOutcome.BLOCK


def to_contract_reasons(reasons: tuple[GatewayReason, ...]) -> tuple[ReasonCode, ...]:
    """내부 사유 코드를 공개 `ReasonCode`로 매핑한다. 성공·정보성 사유는 제외한다."""
    mapped = [code for reason in reasons if (code := _REASON_MAP[reason]) is not None]
    return tuple(dict.fromkeys(mapped))


def to_attempt_result(outcome: AttemptOutcome, context: AttemptContext) -> AttemptResult:
    """내부 전송 결과를 공개 `AttemptResult`로 바꾼다.

    capture_ref는 캡처 성공(`outcome.has_capture_ref`)일 때만 동반해야 하며, 그 일관성은
    `AttemptResult`의 불변식이 강제한다(캡처 성공↔capture_ref 존재).
    """
    return AttemptResult(
        run_key=context.run_key,
        request_ref=context.request_ref,
        attempt_ref=context.attempt_ref,
        decision_ref=context.decision_ref,
        binding_id=context.binding_id,
        send_status=SendStatus(outcome.send_status.value),
        capture_status=CaptureStatus(outcome.capture_status.value),
        capture_ref=context.capture_ref,
        auth_signal=context.auth_signal,
        audit_links=context.audit_links,
        reason_codes=to_contract_reasons(outcome.reason_codes),
    )
