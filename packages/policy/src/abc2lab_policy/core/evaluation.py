"""기본 거부 정책 평가.

규칙을 순서대로 적용하고 첫 거부에서 멈춘다. 어느 규칙도 거부하지 않을 때만 허용한다. 입력
`binding_id`·`view_fingerprint`는 허용·거부 모두에 보존한다. 네트워크·저장·I/O가 없는 순수 함수다.
"""

from __future__ import annotations

from datetime import datetime

from abc2lab_policy.core.model import (
    AuthorizationContext,
    EvaluationRequest,
    IdentityStatus,
    Outcome,
    PolicyEvaluation,
    PolicyReason,
    Purpose,
)

# 사전 인증 없이 평가할 수 있는 목적. 그 외 목적은 전송 전 verified 신원을 요구한다.
_PREAUTH_PURPOSES: frozenset[Purpose] = frozenset({Purpose.AUTHENTICATE, Purpose.IDENTIFY})


def evaluate(
    request: EvaluationRequest,
    authorization: AuthorizationContext,
    now: datetime,
) -> PolicyEvaluation:
    """요청을 등록·범위·프로필·신원에 대해 판정한다(기본 거부).

    Args:
        request: 판정할 요청의 입력 사실.
        authorization: app이 주입한 등록·범위·프로필의 판정 뷰.
        now: 만료 비교 기준이 되는 timezone-aware UTC 시각.

    Returns:
        허용 또는 첫 거부 사유를 담은 판정. 입력 binding을 보존한다.
    """
    denial = _first_denial(request, authorization, now)
    outcome = Outcome.ALLOW if denial is None else Outcome.BLOCK
    reason_codes = (PolicyReason.ALLOWED,) if denial is None else (denial,)
    return PolicyEvaluation(
        outcome=outcome,
        reason_codes=reason_codes,
        run_key=request.run_key,
        request_ref=request.request_ref,
        binding_id=request.binding_id,
        view_fingerprint=request.view_fingerprint,
    )


def _first_denial(
    request: EvaluationRequest,
    authorization: AuthorizationContext,
    now: datetime,
) -> PolicyReason | None:
    """첫 거부 사유를 반환한다. 거부가 없으면 None."""
    if authorization.is_revoked:
        return PolicyReason.AUTHORIZATION_REVOKED
    if _is_expired(authorization.configuration_expires_at, now):
        return PolicyReason.CONFIGURATION_EXPIRED
    if _is_expired(request.binding_expires_at, now):
        return PolicyReason.BINDING_EXPIRED

    operation = authorization.registered_operations.get(request.operation_ref)
    if operation is None:
        return PolicyReason.OPERATION_UNREGISTERED
    if operation.source != request.operation_source:
        return PolicyReason.OPERATION_SOURCE_MISMATCH
    if operation.origin != request.origin:
        return PolicyReason.ORIGIN_MISMATCH
    if operation.method != request.method:
        return PolicyReason.METHOD_MISMATCH
    if request.operation_ref not in authorization.in_scope_operation_refs:
        return PolicyReason.OUT_OF_SCOPE
    if request.purpose not in operation.allowed_purposes:
        return PolicyReason.PURPOSE_NOT_ALLOWED
    if authorization.read_only_profile and operation.is_business_write:
        return PolicyReason.BUSINESS_WRITE_BLOCKED

    needs_verified_identity = request.purpose not in _PREAUTH_PURPOSES
    if needs_verified_identity and request.identity_status is not IdentityStatus.VERIFIED:
        return PolicyReason.IDENTITY_NOT_VERIFIED
    if request.requires_cross_confirmation and not request.has_cross_confirmation:
        return PolicyReason.CROSS_CONFIRMATION_MISSING
    return None


def _is_expired(deadline: datetime | None, now: datetime) -> bool:
    """`deadline`이 있고 `now`가 그 시각 이상이면 만료다. None은 만료로 보지 않는다."""
    return deadline is not None and now >= deadline
