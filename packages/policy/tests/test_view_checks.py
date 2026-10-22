"""주입 원본 대조(view 일관성·교차 실행)의 단위 테스트. 네트워크·DB 없이 실행한다."""

from dataclasses import replace
from datetime import datetime, timedelta

from abc2lab_contracts.execution import PolicyInput
from abc2lab_contracts.primitives import ReasonCode
from abc2lab_contracts.registration import (
    CrossExecutionConfirmation,
    ExecutionProfileSnapshot,
    ExpectedAccess,
    ExpectedAccessPolicySnapshot,
    ResolutionState,
    ScopeSnapshot,
)
from abc2lab_policy.adapters import check_cross_execution, check_injected_view_consistency


def test_view_consistency_passes_for_identical_snapshots(
    policy_input: PolicyInput, scope: ScopeSnapshot, profile: ExecutionProfileSnapshot
) -> None:
    assert check_injected_view_consistency(policy_input, scope, profile) is None


def test_view_consistency_blocks_scope_mismatch(
    policy_input: PolicyInput, scope: ScopeSnapshot, profile: ExecutionProfileSnapshot
) -> None:
    tampered = replace(scope, allowed_origins=("https://evil.test",))
    assert (
        check_injected_view_consistency(policy_input, tampered, profile)
        is ReasonCode.POLICY_VIEW_MISMATCH
    )


def test_view_consistency_blocks_profile_mismatch(
    policy_input: PolicyInput, scope: ScopeSnapshot, profile: ExecutionProfileSnapshot
) -> None:
    tampered = replace(profile, allow_redirects=True)
    assert (
        check_injected_view_consistency(policy_input, scope, tampered)
        is ReasonCode.POLICY_VIEW_MISMATCH
    )


def test_non_cross_with_policy_attached_blocks(
    policy_input: PolicyInput, expected_policy: ExpectedAccessPolicySnapshot, now: datetime
) -> None:
    request = replace(policy_input, expected_policy=expected_policy)
    assert check_cross_execution(request, (), (), now) == (ReasonCode.POLICY_VIEW_MISMATCH,)


def test_non_cross_with_confirmation_attached_blocks(
    policy_input: PolicyInput, cross_confirmation: CrossExecutionConfirmation, now: datetime
) -> None:
    request = replace(policy_input, cross_confirmation=cross_confirmation)
    assert check_cross_execution(request, (), (), now) == (ReasonCode.POLICY_VIEW_MISMATCH,)


def test_cross_happy_path_passes(
    cross_policy_input: PolicyInput,
    expected_policy: ExpectedAccessPolicySnapshot,
    cross_confirmation: CrossExecutionConfirmation,
    now: datetime,
) -> None:
    assert (
        check_cross_execution(cross_policy_input, (expected_policy,), (cross_confirmation,), now)
        == ()
    )


def test_absent_confirmation_is_missing_only(
    cross_policy_input: PolicyInput, expected_policy: ExpectedAccessPolicySnapshot, now: datetime
) -> None:
    request = replace(cross_policy_input, cross_confirmation=None)
    assert check_cross_execution(request, (expected_policy,), (), now) == (
        ReasonCode.CROSS_CONFIRMATION_MISSING,
    )


def test_forged_confirmation_is_missing_and_mismatch(
    cross_policy_input: PolicyInput, expected_policy: ExpectedAccessPolicySnapshot, now: datetime
) -> None:
    # 확인이 첨부됐으나 주입 원본에 없는(위조) 경우 "없음"과 구분해 두 사유를 함께 돌려준다.
    assert check_cross_execution(cross_policy_input, (expected_policy,), (), now) == (
        ReasonCode.CROSS_CONFIRMATION_MISSING,
        ReasonCode.POLICY_VIEW_MISMATCH,
    )


def test_unregistered_policy_ref_is_missing(
    cross_policy_input: PolicyInput,
    expected_policy: ExpectedAccessPolicySnapshot,
    cross_confirmation: CrossExecutionConfirmation,
    now: datetime,
) -> None:
    request = replace(
        cross_policy_input, expected_policy=replace(expected_policy, policy_ref="policy-other")
    )
    assert check_cross_execution(request, (expected_policy,), (cross_confirmation,), now) == (
        ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,
    )


def test_tampered_policy_deny_to_allow_is_invalid(
    cross_policy_input: PolicyInput,
    expected_policy: ExpectedAccessPolicySnapshot,
    cross_confirmation: CrossExecutionConfirmation,
    now: datetime,
) -> None:
    tampered = replace(expected_policy, expected_access=ExpectedAccess.ALLOW)
    request = replace(cross_policy_input, expected_policy=tampered)
    assert check_cross_execution(request, (expected_policy,), (cross_confirmation,), now) == (
        ReasonCode.EXPECTED_ACCESS_POLICY_INVALID,
    )


def test_tampered_policy_extended_expiry_is_invalid(
    cross_policy_input: PolicyInput,
    expected_policy: ExpectedAccessPolicySnapshot,
    cross_confirmation: CrossExecutionConfirmation,
    now: datetime,
) -> None:
    extended = replace(expected_policy, valid_until=now + timedelta(days=30))
    request = replace(cross_policy_input, expected_policy=extended)
    assert check_cross_execution(request, (expected_policy,), (cross_confirmation,), now) == (
        ReasonCode.EXPECTED_ACCESS_POLICY_INVALID,
    )


def test_confirmation_for_other_account_breaks_correspondence(
    cross_policy_input: PolicyInput,
    expected_policy: ExpectedAccessPolicySnapshot,
    cross_confirmation: CrossExecutionConfirmation,
    now: datetime,
) -> None:
    # 등록돼 있어도 평가 계정이 요청과 다르면 대응 검사에서 막는다.
    other_account = replace(cross_confirmation, evaluated_account_ref="acct-c")
    request = replace(cross_policy_input, cross_confirmation=other_account)
    assert check_cross_execution(request, (expected_policy,), (other_account,), now) == (
        ReasonCode.POLICY_VIEW_MISMATCH,
    )


def test_confirmation_for_other_resource_breaks_correspondence(
    cross_policy_input: PolicyInput,
    expected_policy: ExpectedAccessPolicySnapshot,
    cross_confirmation: CrossExecutionConfirmation,
    now: datetime,
) -> None:
    other_resource = replace(cross_confirmation, resource_ref="res-2")
    request = replace(cross_policy_input, cross_confirmation=other_resource)
    assert check_cross_execution(request, (expected_policy,), (other_resource,), now) == (
        ReasonCode.POLICY_VIEW_MISMATCH,
    )


def test_unknown_sharing_blocks(
    cross_policy_input: PolicyInput,
    expected_policy: ExpectedAccessPolicySnapshot,
    cross_confirmation: CrossExecutionConfirmation,
    now: datetime,
) -> None:
    unknown = replace(expected_policy, sharing=ResolutionState.UNKNOWN)
    request = replace(cross_policy_input, expected_policy=unknown)
    assert check_cross_execution(request, (unknown,), (cross_confirmation,), now) == (
        ReasonCode.SHARING_OR_DELEGATION_UNKNOWN,
    )


def test_registered_allow_policy_is_not_executed(
    cross_policy_input: PolicyInput,
    expected_policy: ExpectedAccessPolicySnapshot,
    cross_confirmation: CrossExecutionConfirmation,
    now: datetime,
) -> None:
    # 등록 원본이라도 allow(비위반)는 초기 S1 교차 실행 범위 밖이다.
    allow_policy = replace(expected_policy, expected_access=ExpectedAccess.ALLOW)
    request = replace(cross_policy_input, expected_policy=allow_policy)
    assert check_cross_execution(request, (allow_policy,), (cross_confirmation,), now) == (
        ReasonCode.EXPECTED_ACCESS_POLICY_INVALID,
    )
