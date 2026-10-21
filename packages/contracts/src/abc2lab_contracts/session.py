"""WebDiag 신원 snapshot과 Gateway 실행 전용 세션 context 계약이다."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from abc2lab_contracts._validation import ContractRecord, validate_record
from abc2lab_contracts.audit import AuditReceipt
from abc2lab_contracts.primitives import (
    AttemptSummary,
    ReasonCode,
    Ref,
    ResultStatus,
    RunKey,
    UtcTime,
)


class SessionState(StrEnum):
    """WebDiag가 단일 소유하는 세션 상태다."""

    NOT_READY = "not_ready"
    AUTHENTICATING = "authenticating"
    CONFIRMED = "confirmed"
    UNAVAILABLE = "unavailable"
    EXPIRY_SUSPECTED = "expiry_suspected"
    RECOVERING = "recovering"
    CLOSED = "closed"


class IdentityStatus(StrEnum):
    """Policy의 축약 상태와 구분되는 실제 신원 확인 결과다."""

    VERIFIED = "verified"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    MISMATCH = "mismatch"


class AuthSignalKind(StrEnum):
    """등록된 추출 규칙이 관찰한 인증 신호 종류다."""

    LOGIN_RESULT = "login_result"
    IDENTITY = "identity"
    EXPIRY = "expiry"


class AuthSignalState(StrEnum):
    """원문을 공개하지 않는 인증 신호의 확인 상태다."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SessionHandle(ContractRecord):
    """계정과 generation에 귀속된 실행 세션 참조다."""

    session_ref: Ref
    run_key: RunKey
    account_ref: Ref
    generation: int
    expires_at: UtcTime


@dataclass(frozen=True, slots=True)
class SessionResult(ContractRecord):
    """인증 시도의 요약을 보존하는 세션 확보 결과다."""

    run_key: RunKey
    status: ResultStatus
    session: SessionHandle | None
    session_state: SessionState
    attempt_summaries: tuple[AttemptSummary, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.PARTIAL:
            raise ValueError("session result does not support partial")
        if self.status is ResultStatus.COMPLETE:
            if self.session is None or self.session_state is not SessionState.CONFIRMED:
                raise ValueError("complete session result requires a confirmed session")
            if self.session.run_key != self.run_key:
                raise ValueError("session result run mismatch")
        elif self.session is not None:
            raise ValueError("failed session result cannot publish a session")
        elif self.session_state is SessionState.CONFIRMED:
            raise ValueError("failed session result cannot claim confirmed state")


@dataclass(frozen=True, slots=True)
class IdentityContent(ContractRecord):
    """identity 감사 저장 전에만 쓰는 영수증 없는 불변 확인 내용이다."""

    run_key: RunKey
    identity_ref: Ref | None
    status: IdentityStatus
    session_ref: Ref
    account_ref: Ref
    generation: int
    subject_ref: Ref | None
    evidence_ref: Ref | None
    verified_at: UtcTime | None
    valid_until: UtcTime | None
    attempt_summaries: tuple[AttemptSummary, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        _validate_identity_content(self)


@dataclass(frozen=True, slots=True)
class IdentityResult(ContractRecord):
    """저장된 근거와 감사를 동반하는 상세 주체 확인 결과다."""

    run_key: RunKey
    identity_ref: Ref | None
    status: IdentityStatus
    session_ref: Ref
    account_ref: Ref
    generation: int
    subject_ref: Ref | None
    evidence_ref: Ref | None
    verified_at: UtcTime | None
    valid_until: UtcTime | None
    audit_receipt: AuditReceipt | None
    attempt_summaries: tuple[AttemptSummary, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        _validate_identity_content(self)
        if self.status is IdentityStatus.VERIFIED and self.audit_receipt is None:
            raise ValueError("verified identity requires audit receipt")

    @classmethod
    def from_content(
        cls, content: IdentityContent, audit_receipt: AuditReceipt | None
    ) -> IdentityResult:
        """확인 내용에 감사 영수증을 붙이고 verified의 필수 조건을 검사한다."""
        if type(content) is not IdentityContent:
            raise TypeError("expected exact identity content")
        validate_record(content)
        return cls(
            run_key=content.run_key,
            identity_ref=content.identity_ref,
            status=content.status,
            session_ref=content.session_ref,
            account_ref=content.account_ref,
            generation=content.generation,
            subject_ref=content.subject_ref,
            evidence_ref=content.evidence_ref,
            verified_at=content.verified_at,
            valid_until=content.valid_until,
            audit_receipt=audit_receipt,
            attempt_summaries=content.attempt_summaries,
            reason_codes=content.reason_codes,
        )


def _validate_identity_content(value: IdentityContent | IdentityResult) -> None:
    if value.status is IdentityStatus.VERIFIED and any(
        item is None
        for item in (
            value.identity_ref,
            value.subject_ref,
            value.evidence_ref,
            value.verified_at,
            value.valid_until,
        )
    ):
        raise ValueError("verified identity requires evidence and validity")
    if (
        value.verified_at is not None
        and value.valid_until is not None
        and value.verified_at >= value.valid_until
    ):
        raise ValueError("identity validity interval must be increasing")


@dataclass(frozen=True, slots=True)
class IdentityBindingSummary(ContractRecord):
    """검증된 신원의 비밀 없는 Policy view다."""

    identity_ref: Ref
    session_ref: Ref
    account_ref: Ref
    subject_ref: Ref
    generation: int
    verified_at: UtcTime
    valid_until: UtcTime

    def _validate_invariants(self) -> None:
        if self.verified_at >= self.valid_until:
            raise ValueError("identity validity interval must be increasing")


@dataclass(frozen=True, slots=True)
class SessionBinding(ContractRecord):
    """같은 event loop에서 원자 교체해 즉시 읽는 불변 snapshot이다."""

    session: SessionHandle
    state: SessionState
    identity: IdentityResult | None
    transport_context_ref: Ref
    cancelled: bool

    def _validate_invariants(self) -> None:
        if self.state is SessionState.CONFIRMED:
            if self.identity is None or self.identity.status is not IdentityStatus.VERIFIED:
                raise ValueError("confirmed binding requires verified identity")
        if self.identity is not None and (
            self.identity.run_key != self.session.run_key
            or self.identity.session_ref != self.session.session_ref
            or self.identity.account_ref != self.session.account_ref
            or self.identity.generation != self.session.generation
        ):
            raise ValueError("session identity binding mismatch")


@dataclass(frozen=True, slots=True)
class SessionBindingResult(ContractRecord):
    """없는 세션을 익명으로 바꾸지 않는 동기 읽기 결과다."""

    run_key: RunKey
    status: ResultStatus
    binding: SessionBinding | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.PARTIAL:
            raise ValueError("session binding result does not support partial")
        if (self.status is ResultStatus.COMPLETE) != (self.binding is not None):
            raise ValueError("session binding result status/output mismatch")
        if self.binding is not None and self.binding.session.run_key != self.run_key:
            raise ValueError("session binding result run mismatch")


@dataclass(frozen=True, slots=True)
class AuthSignal(ContractRecord):
    """Gateway 등록 규칙으로 추출한 비밀 없는 인증 신호다."""

    kind: AuthSignalKind
    state: AuthSignalState
    subject_ref: Ref | None


@dataclass(frozen=True, slots=True)
class SessionContextRequest(ContractRecord):
    """로그인이나 전송 없이 격리된 context를 할당하는 요청이다."""

    run_key: RunKey
    session_ref: Ref
    account_ref: Ref
    generation: int
    auth_profile_ref: Ref


@dataclass(frozen=True, slots=True)
class SessionContextResult(ContractRecord):
    """Gateway가 소유하는 실행 context 참조의 할당 결과다."""

    run_key: RunKey
    status: ResultStatus
    transport_context_ref: Ref | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.PARTIAL:
            raise ValueError("session context result does not support partial")
        if (self.status is ResultStatus.COMPLETE) != (self.transport_context_ref is not None):
            raise ValueError("session context result status/output mismatch")


@dataclass(frozen=True, slots=True)
class SessionContextCloseRequest(ContractRecord):
    """알려진 전송 상태를 유지하며 context를 종료하는 요청이다."""

    run_key: RunKey
    transport_context_ref: Ref
