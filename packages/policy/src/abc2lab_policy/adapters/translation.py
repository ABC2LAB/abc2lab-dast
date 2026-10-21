"""C2 실행 경계 타입과 policy 내부 도메인 모델 사이의 변환.

공개 계약(`PolicyInput`·등록 snapshot)을 내부 모델로 distill하고, 내부 판정을 공개 outcome·
`ReasonCode`로 되돌리는 순수 함수들이다. 비밀·원문을 보관하지 않으며, 등록은 app이 주입한 불변
snapshot에서만 온다. 읽기전용은 동작·프로필 허용 목적의 교집합으로 표현한다.
"""

from __future__ import annotations

from datetime import datetime

from abc2lab_contracts.audit import PolicyOutcome
from abc2lab_contracts.execution import PolicyInput
from abc2lab_contracts.primitives import ReasonCode, SourceVersion
from abc2lab_contracts.registration import (
    ExecutionProfileSnapshot,
    OperationRegistration,
    ScopeSnapshot,
)

from abc2lab_policy.core.model import (
    AuthorizationContext,
    EvaluationRequest,
    IdentityStatus,
    Outcome,
    PolicyReason,
    Purpose,
    RegisteredOperation,
)

# 내부 세분화 사유를 공개 `ReasonCode`로 흡수한다. 허용 표식(ALLOWED)은 반환에서 제외한다.
_REASON_MAP: dict[PolicyReason, ReasonCode] = {
    PolicyReason.AUTHORIZATION_REVOKED: ReasonCode.POLICY_BLOCKED,
    PolicyReason.CONFIGURATION_EXPIRED: ReasonCode.SNAPSHOT_EXPIRED,
    PolicyReason.BINDING_EXPIRED: ReasonCode.SNAPSHOT_EXPIRED,
    PolicyReason.OPERATION_UNREGISTERED: ReasonCode.SCOPE_MISMATCH,
    PolicyReason.OPERATION_REF_MISMATCH: ReasonCode.SCOPE_MISMATCH,
    PolicyReason.OPERATION_SOURCE_MISMATCH: ReasonCode.POLICY_VIEW_MISMATCH,
    PolicyReason.ORIGIN_MISMATCH: ReasonCode.SCOPE_MISMATCH,
    PolicyReason.METHOD_MISMATCH: ReasonCode.SCOPE_MISMATCH,
    PolicyReason.OUT_OF_SCOPE: ReasonCode.SCOPE_MISMATCH,
    PolicyReason.PURPOSE_NOT_ALLOWED: ReasonCode.SCOPE_MISMATCH,
    PolicyReason.IDENTITY_NOT_VERIFIED: ReasonCode.IDENTITY_UNKNOWN,
    PolicyReason.CROSS_CONFIRMATION_MISSING: ReasonCode.CROSS_CONFIRMATION_MISSING,
}


def source_version_key(source: SourceVersion) -> str:
    """등록 출처의 비교용 안정 키를 만든다."""
    return f"{source.issuer}:{source.source_ref}:{source.revision}"


def build_evaluation_request(policy_input: PolicyInput, view_fingerprint: str) -> EvaluationRequest:
    """불변 `PolicyInput` view를 내부 평가 입력으로 distill한다.

    `view_fingerprint`는 호출자가 공유 codec으로 계산한 `PolicyInput`의 fingerprint다. 교차 확인
    요구는 내부 규칙(ACCESS_COMPARE)이 강제하므로 플래그로 넘기지 않고, 확인 유무만 전달한다.
    """
    return EvaluationRequest(
        run_key=policy_input.run_key.run_ref,
        request_ref=policy_input.request_ref,
        binding_id=policy_input.binding_id,
        view_fingerprint=view_fingerprint,
        origin=policy_input.origin,
        method=policy_input.method,
        operation_ref=policy_input.operation_ref,
        operation_source=source_version_key(policy_input.policy_attributes.provenance),
        purpose=Purpose(policy_input.purpose.value),
        identity_status=IdentityStatus(policy_input.identity_status.value),
        binding_expires_at=policy_input.expires_at,
        requires_cross_confirmation=False,
        has_cross_confirmation=policy_input.cross_confirmation is not None,
    )


def build_authorization_context(
    scope: ScopeSnapshot,
    profile: ExecutionProfileSnapshot,
    operations: tuple[OperationRegistration, ...],
    *,
    is_revoked: bool = False,
) -> AuthorizationContext:
    """주입된 범위·프로필·동작 등록을 내부 판정 뷰로 distill한다.

    각 동작의 허용 목적은 동작 등록과 실행 프로필의 교집합으로 좁힌다(읽기전용 표현).
    """
    allowed_profile_purposes = frozenset(profile.allowed_purposes)
    registered: dict[str, RegisteredOperation] = {}
    for operation in operations:
        purposes = tuple(
            Purpose(purpose.value)
            for purpose in operation.allowed_purposes
            if purpose in allowed_profile_purposes
        )
        registered[operation.operation_ref] = RegisteredOperation(
            operation_ref=operation.operation_ref,
            source=source_version_key(operation.source),
            origin=operation.origin,
            method=operation.method,
            allowed_purposes=purposes,
        )
    return AuthorizationContext(
        registered_operations=registered,
        in_scope_operation_refs=frozenset(scope.allowed_operation_refs),
        is_revoked=is_revoked,
        configuration_expires_at=_earliest(scope.valid_until, profile.valid_until),
    )


def to_policy_outcome(outcome: Outcome) -> PolicyOutcome:
    """내부 outcome을 공개 계약 outcome으로 바꾼다."""
    return PolicyOutcome(outcome.value)


def to_contract_reasons(reasons: tuple[PolicyReason, ...]) -> tuple[ReasonCode, ...]:
    """내부 사유 코드를 공개 `ReasonCode`로 매핑한다. 허용 표식은 제외한다."""
    return tuple(_REASON_MAP[reason] for reason in reasons if reason is not PolicyReason.ALLOWED)


def _earliest(first: datetime, second: datetime) -> datetime:
    """두 만료 시각 중 이른 쪽을 돌려준다."""
    return first if first <= second else second
