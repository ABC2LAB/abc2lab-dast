"""준비된 요청, 정책 결정과 전송 결과의 S1 실행 경계 계약이다."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from abc2lab_contracts._validation import (
    ContractRecord,
    require_fingerprint,
    require_positive,
    validate_record,
)
from abc2lab_contracts.audit import AuditReceipt, PolicyOutcome
from abc2lab_contracts.primitives import (
    AuditLink,
    CaptureStatus,
    Purpose,
    ReasonCode,
    Ref,
    RequestParameter,
    ResultStatus,
    Revision,
    RunKey,
    SendStatus,
    SourceVersion,
    UtcTime,
)
from abc2lab_contracts.registration import (
    BudgetSnapshot,
    CrossExecutionConfirmation,
    ExecutionProfileSnapshot,
    ExpectedAccessPolicySnapshot,
    ScopeSnapshot,
)
from abc2lab_contracts.session import AuthSignal, IdentityBindingSummary, SessionHandle

POLICY_INPUT_SCHEMA_VERSION = "policy_input.v1"
PreparedRequestHandle = Ref


class PolicyIdentityStatus(StrEnum):
    """Gateway가 현재 바인딩에서 축약한 정책 평가용 신원 상태다."""

    VERIFIED = "verified"
    UNKNOWN = "unknown"
    ANONYMOUS = "anonymous"


@dataclass(frozen=True, slots=True)
class PrivateHttpRequest(ContractRecord):
    """Gateway 실행 영역에만 전달하는 등록 요청 값이다."""

    origin: str
    method: str
    path: str
    parameters: tuple[RequestParameter, ...]
    timeout_ms: int

    def _validate_invariants(self) -> None:
        require_positive("timeout_ms", self.timeout_ms)


@dataclass(frozen=True, slots=True)
class ExecutionRequest(ContractRecord):
    """WebDiag가 생성한 논리 요청과 등록값을 준비 단계에 전달한다."""

    run_key: RunKey
    request_ref: Ref
    operation_ref: Ref
    operation_revision: Revision
    resource_ref: Ref | None
    resource_binding_ref: Ref | None
    resource_binding_revision: Revision | None
    purpose: Purpose
    http: PrivateHttpRequest
    session: SessionHandle | None
    owner_session: SessionHandle | None
    scope_revision: Revision
    profile_revision: Revision
    expected_policy: ExpectedAccessPolicySnapshot | None
    cross_confirmation: CrossExecutionConfirmation | None


@dataclass(frozen=True, slots=True)
class PolicyAttributes(ContractRecord):
    """실제 파라미터 값을 제외한 등록 구조와 자원 바인딩 view다."""

    registered_path_matches: bool
    parameter_names: tuple[str, ...]
    parameters_match_registration: bool
    resource_ref: Ref | None
    resource_binding_ref: Ref | None
    resource_binding_revision: Revision | None
    resource_owner_subject_ref: Ref | None
    provenance: SourceVersion


@dataclass(frozen=True, slots=True)
class PolicyInput(ContractRecord):
    """Gateway가 불변 요청에서 발행한 비밀 없는 정책 평가 view다."""

    schema_version: str
    run_key: RunKey
    request_ref: Ref
    binding_id: Ref
    binding_issuer: Ref
    expires_at: UtcTime
    origin: str
    method: str
    operation_ref: Ref
    operation_revision: Revision
    purpose: Purpose
    policy_attributes: PolicyAttributes
    account_ref: Ref | None
    session_generation: int | None
    identity_ref: Ref | None
    subject_ref: Ref | None
    identity_status: PolicyIdentityStatus
    owner_identity: IdentityBindingSummary | None
    scope: ScopeSnapshot
    profile: ExecutionProfileSnapshot
    budget: BudgetSnapshot
    expected_policy: ExpectedAccessPolicySnapshot | None
    cross_confirmation: CrossExecutionConfirmation | None

    def _validate_invariants(self) -> None:
        if self.schema_version != POLICY_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported policy input schema version")


@dataclass(frozen=True, slots=True)
class PolicyDecisionContent(ContractRecord):
    """감사 저장 전 fingerprint를 계산할 정책 결정의 불변 내용이다."""

    run_key: RunKey
    decision_ref: Ref
    binding_id: Ref
    evaluated_view_fingerprint: str
    outcome: PolicyOutcome
    policy_version: SourceVersion
    issued_at: UtcTime
    expires_at: UtcTime
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        _validate_decision_content(self)


@dataclass(frozen=True, slots=True)
class PolicyDecision(ContractRecord):
    """Policy 감사 저장 후에만 발행하는 실행 판단이다."""

    run_key: RunKey
    decision_ref: Ref
    binding_id: Ref
    evaluated_view_fingerprint: str
    outcome: PolicyOutcome
    policy_version: SourceVersion
    issued_at: UtcTime
    expires_at: UtcTime
    audit_receipt: AuditReceipt
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        _validate_decision_content(self)

    @classmethod
    def from_content(
        cls, content: PolicyDecisionContent, audit_receipt: AuditReceipt
    ) -> PolicyDecision:
        """저장 전 내용에 받은 영수증을 붙이되 실제 commit 증명을 대신하지 않는다."""
        if type(content) is not PolicyDecisionContent:
            raise TypeError("expected exact policy decision content")
        validate_record(content)
        return cls(
            run_key=content.run_key,
            decision_ref=content.decision_ref,
            binding_id=content.binding_id,
            evaluated_view_fingerprint=content.evaluated_view_fingerprint,
            outcome=content.outcome,
            policy_version=content.policy_version,
            issued_at=content.issued_at,
            expires_at=content.expires_at,
            audit_receipt=audit_receipt,
            reason_codes=content.reason_codes,
        )


def _validate_decision_content(value: PolicyDecisionContent | PolicyDecision) -> None:
    require_fingerprint(value.evaluated_view_fingerprint)
    if value.issued_at >= value.expires_at:
        raise ValueError("policy decision validity interval must be increasing")


@dataclass(frozen=True, slots=True)
class PolicyDecisionResult(ContractRecord):
    """정책 저장 실패를 실행 가능한 결정과 구분하는 결과다."""

    run_key: RunKey
    status: ResultStatus
    decision: PolicyDecision | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.PARTIAL:
            raise ValueError("policy decision result does not support partial")
        if (self.status is ResultStatus.COMPLETE) != (self.decision is not None):
            raise ValueError("policy decision result status/output mismatch")
        if self.decision is not None and self.decision.run_key != self.run_key:
            raise ValueError("policy decision result run mismatch")


@dataclass(frozen=True, slots=True)
class PrepareResult(ContractRecord):
    """전송 없이 준비된 핸들과 동일 요청의 정책 view를 반환한다."""

    run_key: RunKey
    status: ResultStatus
    prepared_handle: PreparedRequestHandle | None
    policy_input: PolicyInput | None
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        if self.status is ResultStatus.PARTIAL:
            raise ValueError("prepare result does not support partial")
        complete = self.status is ResultStatus.COMPLETE
        if complete != (self.prepared_handle is not None) or complete != (
            self.policy_input is not None
        ):
            raise ValueError("prepare result status/output mismatch")
        if self.policy_input is not None and self.policy_input.run_key != self.run_key:
            raise ValueError("prepare result run mismatch")


@dataclass(frozen=True, slots=True)
class ExecuteRequest(ContractRecord):
    """단일 소비 준비 핸들과 저장된 정책 결정을 실행에 전달한다."""

    run_key: RunKey
    request_ref: Ref
    prepared_handle: PreparedRequestHandle
    decision: PolicyDecision | None


@dataclass(frozen=True, slots=True)
class AttemptResult(ContractRecord):
    """실제 전송 상태와 실행 메모리 캡처 참조를 보존하는 결과다."""

    run_key: RunKey
    request_ref: Ref
    attempt_ref: Ref
    decision_ref: Ref | None
    binding_id: Ref | None
    send_status: SendStatus
    capture_status: CaptureStatus
    capture_ref: Ref | None
    auth_signal: AuthSignal | None
    audit_links: tuple[AuditLink, ...]
    reason_codes: tuple[ReasonCode, ...]

    def _validate_invariants(self) -> None:
        valid_pairs = (
            (SendStatus.SENT, CaptureStatus.CAPTURED),
            (SendStatus.SENT, CaptureStatus.UNAVAILABLE),
            (SendStatus.NOT_SENT, CaptureStatus.NOT_APPLICABLE),
            (SendStatus.UNKNOWN, CaptureStatus.INDETERMINATE),
        )
        if (self.send_status, self.capture_status) not in valid_pairs:
            raise ValueError("invalid send and capture status combination")
        if (self.capture_status is CaptureStatus.CAPTURED) != (self.capture_ref is not None):
            raise ValueError("capture reference must exist only for captured status")
