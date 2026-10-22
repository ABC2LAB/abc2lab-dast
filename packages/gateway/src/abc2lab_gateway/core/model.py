"""Gateway 전송 결과 상태 머신의 내부 도메인 모델.

C2 실행 경계 타입(`ExecutionRequest`·`PolicyDecision`·`AttemptResult`·`SendStatus`·
`CaptureStatus`)으로 변환되기 전의 모듈 내부 타입이다. 공개 계약을 대신하거나 사본으로 쓰지
않으며, 원문·자격 증명·캡처 핸들을 담지 않는다. C2는 병합됐으며(PR #20), `adapters`가 실제 실행
관찰을 이 모델로 distill하고 `AttemptOutcome`을 `AttemptResult`로 발행할 책임을 진다.

전송 전 미진입이 입증된 시도만 `not_sent`다. transport 진입 후 미확정은 `unknown`이며, `unknown`은
자동 재전송하지 않는다. 허용 조합은 S1 §6의 네 가지뿐이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SendStatus(StrEnum):
    """Gateway가 관찰한 실제 전송 상태."""

    SENT = "sent"
    NOT_SENT = "not_sent"
    UNKNOWN = "unknown"


class CaptureStatus(StrEnum):
    """캡처 결과. 허용 조합은 §6."""

    CAPTURED = "captured"
    UNAVAILABLE = "unavailable"
    NOT_APPLICABLE = "not_applicable"
    INDETERMINATE = "indeterminate"


class DecisionOutcome(StrEnum):
    """execute에 전달된 정책 결정의 축약. `MISSING`은 결정 None."""

    ALLOW = "allow"
    BLOCK = "block"
    MISSING = "missing"


class DecisionCommit(StrEnum):
    """받은 Policy 결정의 저장 commit 검증 결과(§10 ①). Gateway 자기 감사와 별개다."""

    VERIFIED = "verified"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class TransportObservation(StrEnum):
    """transport 단계에서 관찰한 결과. 전송·캡처 입증 상태를 구분한다."""

    NOT_ENTERED = "not_entered"
    SENT_CAPTURED = "sent_captured"
    SENT_CAPTURE_UNAVAILABLE = "sent_capture_unavailable"
    SENT_RESPONSE_OVERLIMIT = "sent_response_overlimit"
    SEND_UNCONFIRMED = "send_unconfirmed"


class GatewayReason(StrEnum):
    """전송 결과 사유 코드. C2 병합 시 contracts `ReasonCode`로 매핑한다."""

    POLICY_BLOCKED = "policy_blocked"
    DECISION_MISSING = "decision_missing"
    DECISION_UNVERIFIED = "decision_unverified"
    DECISION_VERIFICATION_UNKNOWN = "decision_verification_unknown"
    AUDIT_COMMIT_FAILED = "audit_commit_failed"
    SESSION_GENERATION_CHANGED = "session_generation_changed"
    SCOPE_MISMATCH = "scope_mismatch"
    BINDING_MISMATCH = "binding_mismatch"
    CANCELLED = "cancelled"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TRANSPORT_NOT_ENTERED = "transport_not_entered"
    SENT_CAPTURED = "sent_captured"
    CAPTURE_UNAVAILABLE = "capture_unavailable"
    RESPONSE_LIMIT_EXCEEDED = "response_limit_exceeded"
    SEND_ACKNOWLEDGEMENT_LOST = "send_acknowledgement_lost"
    GATE_CONTRADICTION = "gate_contradiction"


# recheck 실패 시 쓸 수 있는 사유. 전송 직전 임계 구역 재검사에서 나온다.
_RECHECK_REASONS: frozenset[GatewayReason] = frozenset(
    {
        GatewayReason.SESSION_GENERATION_CHANGED,
        GatewayReason.SCOPE_MISMATCH,
        GatewayReason.BINDING_MISMATCH,
        GatewayReason.CANCELLED,
        GatewayReason.DEADLINE_EXCEEDED,
    }
)

# §6이 허용하는 (send, capture) 조합과 capture_ref 동반 여부.
_VALID_COMBINATIONS: frozenset[tuple[SendStatus, CaptureStatus, bool]] = frozenset(
    {
        (SendStatus.SENT, CaptureStatus.CAPTURED, True),
        (SendStatus.SENT, CaptureStatus.UNAVAILABLE, False),
        (SendStatus.NOT_SENT, CaptureStatus.NOT_APPLICABLE, False),
        (SendStatus.UNKNOWN, CaptureStatus.INDETERMINATE, False),
    }
)


@dataclass(frozen=True, slots=True)
class RecheckResult:
    """전송 직전 임계 구역 재검사 결과. 실패면 사유를 둔다."""

    passed: bool
    reason: GatewayReason | None = None

    def __post_init__(self) -> None:
        if self.passed and self.reason is not None:
            raise ValueError("통과한 재검사는 사유가 없어야 한다")
        if not self.passed and self.reason is None:
            raise ValueError("실패한 재검사는 사유가 있어야 한다")
        if self.reason is not None and self.reason not in _RECHECK_REASONS:
            raise ValueError(f"재검사 사유가 아니다: {self.reason}")


@dataclass(frozen=True, slots=True)
class PreTransportGate:
    """transport 진입 전 게이트 사실.

    순서(§10): 결정 → 결정 commit 검증 → Gateway 자기 감사 commit → 재검사 → 예산.
    `decision_commit`은 받은 Policy 결정의 저장 검증 결과(§10 ①)이고, `audit_committed`는 Gateway
    자신의 intent 기록 commit(②)이다.
    """

    decision: DecisionOutcome
    audit_committed: bool
    recheck: RecheckResult
    budget_committed: bool
    decision_commit: DecisionCommit = DecisionCommit.VERIFIED


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    """전송 시도의 최종 결과. §6의 네 조합만 허용한다."""

    send_status: SendStatus
    capture_status: CaptureStatus
    has_capture_ref: bool
    reason_codes: tuple[GatewayReason, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        combination = (self.send_status, self.capture_status, self.has_capture_ref)
        if combination not in _VALID_COMBINATIONS:
            raise ValueError(f"허용되지 않은 전송/캡처 조합: {combination}")
