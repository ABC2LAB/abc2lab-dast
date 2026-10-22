"""주입 원본에 대한 view 일관성·교차 실행 대조.

`PolicyInput`에 실린 view(scope·profile·expected_policy·cross_confirmation)는 app이 주입한 원본에서
**선택해 그대로 전달한 값**이어야 한다(S1 §5 132·320행). Host/LLM이 같은 이름의 문자열을 직접 넣어
권한을 얻을 수 없도록, Policy가 주입 원본과 전체 필드·출처·run/자원/동작/계정·유효기간을 재대조한다.
어긋나면 계약 사유 코드로 block한다. 공개 값만 비교하는 순수 함수다.
"""

from __future__ import annotations

from datetime import datetime

from abc2lab_contracts.execution import PolicyIdentityStatus, PolicyInput
from abc2lab_contracts.primitives import Purpose, ReasonCode
from abc2lab_contracts.registration import (
    CrossExecutionConfirmation,
    ExecutionProfileSnapshot,
    ExpectedAccess,
    ExpectedAccessPolicySnapshot,
    ResolutionState,
    ScopeSnapshot,
)


def check_injected_view_consistency(
    request: PolicyInput, scope: ScopeSnapshot, profile: ExecutionProfileSnapshot
) -> ReasonCode | None:
    """view의 scope·profile snapshot이 주입 원본과 전체 필드까지 같은지 확인한다."""
    if request.scope != scope or request.profile != profile:
        return ReasonCode.POLICY_VIEW_MISMATCH
    return None


def check_cross_execution(
    request: PolicyInput,
    expected_policies: tuple[ExpectedAccessPolicySnapshot, ...],
    cross_confirmations: tuple[CrossExecutionConfirmation, ...],
    now: datetime,
) -> tuple[ReasonCode, ...]:
    """교차 실행(access_compare)의 기대 정책·확인을 주입 원본과 대조한다.

    교차가 아닌 요청에 두 값이 실려 있으면 `policy_view_mismatch`로 막는다. 교차 요청은 두 값이
    모두 있고 주입 원본과 일치하며, run·자원·동작·계정이 대응하고, 판정 시각에 유효하고, A/B가 서로
    다른 verified 주체이며, 초기 S1 허용 조합(deny + resolved_none/resolved_none)일 때만 통과한다.
    확인이 아예 없으면 `cross_confirmation_missing`만, 첨부됐으나 주입 원본과 다르면(위조)
    `cross_confirmation_missing`과 `policy_view_mismatch`를 함께 돌려 "없음"과 구분한다. 통과는 빈
    tuple이다.
    """
    policy = request.expected_policy
    confirmation = request.cross_confirmation
    if request.purpose is not Purpose.ACCESS_COMPARE:
        if policy is not None or confirmation is not None:
            return (ReasonCode.POLICY_VIEW_MISMATCH,)
        return ()
    if policy is None or confirmation is None:
        return (ReasonCode.CROSS_CONFIRMATION_MISSING,)

    registry_reason = _policy_against_registry(policy, expected_policies)
    if registry_reason is not None:
        return (registry_reason,)
    if confirmation not in cross_confirmations:
        return (ReasonCode.CROSS_CONFIRMATION_MISSING, ReasonCode.POLICY_VIEW_MISMATCH)

    correspondence_reason = _check_correspondence(request, policy, confirmation, now)
    if correspondence_reason is not None:
        return (correspondence_reason,)
    combination_reason = _check_allowed_combination(policy)
    return () if combination_reason is None else (combination_reason,)


def _policy_against_registry(
    policy: ExpectedAccessPolicySnapshot,
    expected_policies: tuple[ExpectedAccessPolicySnapshot, ...],
) -> ReasonCode | None:
    """같은 policy_ref의 주입 원본을 찾아 전체 필드 일치를 요구한다. 변조는 invalid."""
    original = next(
        (item for item in expected_policies if item.policy_ref == policy.policy_ref), None
    )
    if original is None:
        return ReasonCode.EXPECTED_ACCESS_POLICY_MISSING
    if original != policy:
        return ReasonCode.EXPECTED_ACCESS_POLICY_INVALID
    return None


def _check_correspondence(
    request: PolicyInput,
    policy: ExpectedAccessPolicySnapshot,
    confirmation: CrossExecutionConfirmation,
    now: datetime,
) -> ReasonCode | None:
    """run·자원·동작·계정/주체 대응과 판정 시각 유효성, A/B 구분·검증을 확인한다."""
    resource_ref = request.policy_attributes.resource_ref
    if confirmation.run_key != request.run_key:
        return ReasonCode.POLICY_VIEW_MISMATCH
    if request.operation_ref not in (policy.operation_ref, confirmation.operation_ref):
        return ReasonCode.POLICY_VIEW_MISMATCH
    if policy.operation_ref != confirmation.operation_ref:
        return ReasonCode.POLICY_VIEW_MISMATCH
    if resource_ref is None or resource_ref not in (policy.resource_ref, confirmation.resource_ref):
        return ReasonCode.POLICY_VIEW_MISMATCH
    if policy.resource_ref != confirmation.resource_ref:
        return ReasonCode.POLICY_VIEW_MISMATCH

    owner = request.owner_identity
    if (
        request.identity_status is not PolicyIdentityStatus.VERIFIED
        or owner is None
        or request.subject_ref is None
    ):
        return ReasonCode.IDENTITY_UNKNOWN
    if now >= owner.valid_until:
        return ReasonCode.IDENTITY_UNKNOWN
    if (
        policy.owner_subject_ref == policy.evaluated_subject_ref
        or owner.account_ref == request.account_ref
    ):
        return ReasonCode.IDENTITY_MISMATCH
    if (
        policy.owner_subject_ref != owner.subject_ref
        or policy.evaluated_subject_ref != request.subject_ref
        or confirmation.owner_account_ref != owner.account_ref
        or confirmation.evaluated_account_ref != request.account_ref
    ):
        return ReasonCode.POLICY_VIEW_MISMATCH
    if not policy.valid_from <= now < policy.valid_until or now >= confirmation.valid_until:
        return ReasonCode.EXPECTED_ACCESS_POLICY_INVALID
    return None


def _check_allowed_combination(policy: ExpectedAccessPolicySnapshot) -> ReasonCode | None:
    """초기 S1은 등록된 deny + resolved_none/resolved_none 사례만 실행한다.

    공유·위임이 unknown이면 `sharing_or_delegation_unknown`이다. allow처럼 정상 등록됐더라도 이
    조합 밖인 정책은 **S1 실행 범위 밖**이라는 뜻으로 `expected_access_policy_invalid`로 막는다.
    정책 자체가 잘못됐다는 뜻이 아니라, 초기 S1이 실행하는 사례가 아니라는 의미다.
    """
    if policy.sharing is ResolutionState.UNKNOWN or policy.delegation is ResolutionState.UNKNOWN:
        return ReasonCode.SHARING_OR_DELEGATION_UNKNOWN
    if (
        policy.expected_access is not ExpectedAccess.DENY
        or policy.sharing is not ResolutionState.RESOLVED_NONE
        or policy.delegation is not ResolutionState.RESOLVED_NONE
    ):
        return ReasonCode.EXPECTED_ACCESS_POLICY_INVALID
    return None
