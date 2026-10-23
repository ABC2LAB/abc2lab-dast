"""수평 IDOR 보수적 오라클의 단위 테스트. 네트워크·DB·원문 없이 실행한다."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import product

from abc2lab_judge.core import (
    CaseInput,
    CheckState,
    ComparisonFacts,
    ExpectedAccess,
    JudgeReason,
    PolicyAssertion,
    ResolutionState,
    SubjectContext,
    SubjectStatus,
    VerdictValue,
    evaluate_case,
)

_OBSERVED_AT = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)

_POLICY = PolicyAssertion(
    expected_access=ExpectedAccess.DENY,
    sharing=ResolutionState.RESOLVED_NONE,
    delegation=ResolutionState.RESOLVED_NONE,
    has_registered_source=True,
    valid_from=_OBSERVED_AT - timedelta(hours=1),
    valid_until=_OBSERVED_AT + timedelta(hours=1),
)

_SUBJECTS = SubjectContext(
    owner_status=SubjectStatus.VERIFIED,
    evaluated_status=SubjectStatus.VERIFIED,
    owner_subject_ref="subject-a",
    evaluated_subject_ref="subject-b",
)

_FACTS = ComparisonFacts(
    same_resource=CheckState.YES,
    owner_normal_data=CheckState.YES,
    cross_normal_data=CheckState.YES,
    nontrivial_data_match=CheckState.YES,
    reflection_excluded=CheckState.YES,
    template_excluded=CheckState.YES,
)

# 비교가 없을 때의 신호. A·교차 응답이 없으면 모든 비교 신호는 확인 불가다.
_NO_COMPARISON = ComparisonFacts(
    same_resource=CheckState.UNKNOWN,
    owner_normal_data=CheckState.UNKNOWN,
    cross_normal_data=CheckState.UNKNOWN,
    nontrivial_data_match=CheckState.UNKNOWN,
    reflection_excluded=CheckState.UNKNOWN,
    template_excluded=CheckState.UNKNOWN,
)

# _CASE는 (b)(c)가 모두 yes인 강한 근거다. 정책만 바꿔 값이 어떻게 갈리는지 본다.
_CASE = CaseInput(policy=_POLICY, subjects=_SUBJECTS, facts=_FACTS)


def _with_policy(policy: PolicyAssertion) -> CaseInput:
    return replace(_CASE, policy=policy)


def test_confirmed_when_all_three_checks_yes() -> None:
    result = evaluate_case(_CASE, _OBSERVED_AT)
    assert result.value is VerdictValue.CONFIRMED
    assert result.policy_check is CheckState.YES
    assert result.identity_check is CheckState.YES
    assert result.data_check is CheckState.YES


def test_reason_codes_follow_policy_identity_data_order() -> None:
    result = evaluate_case(_CASE, _OBSERVED_AT)
    assert result.reason_codes == (
        JudgeReason.POLICY_DENY_RESOLVED,
        JudgeReason.SUBJECTS_DISTINCT_VERIFIED,
        JudgeReason.DATA_NONTRIVIAL_MATCH,
    )


def test_explicit_allow_with_verified_b_is_allowed() -> None:
    result = evaluate_case(
        _with_policy(replace(_POLICY, expected_access=ExpectedAccess.ALLOW)), _OBSERVED_AT
    )
    assert result.value is VerdictValue.ALLOWED
    assert result.policy_check is CheckState.NO
    # ALLOWED는 허용 사유 하나만 싣는다.
    assert result.reason_codes == (JudgeReason.POLICY_ALLOWS,)


def test_resolved_allow_delegation_with_verified_b_is_allowed() -> None:
    result = evaluate_case(
        _with_policy(replace(_POLICY, delegation=ResolutionState.RESOLVED_ALLOW)), _OBSERVED_AT
    )
    assert result.value is VerdictValue.ALLOWED
    assert result.policy_check is CheckState.NO
    assert result.reason_codes == (JudgeReason.SHARING_OR_DELEGATION_ALLOWS,)


def test_direct_allow_is_not_blocked_by_unknown_sharing() -> None:
    # UNKNOWN 예외는 허용을 더할 수만 있어 검증된 직접 허용을 무효화하지 못한다.
    case = _with_policy(
        replace(_POLICY, expected_access=ExpectedAccess.ALLOW, sharing=ResolutionState.UNKNOWN)
    )
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.ALLOWED
    assert result.reason_codes == (JudgeReason.POLICY_ALLOWS,)


def test_resolved_delegation_allow_overrides_unknown_direct_access() -> None:
    case = _with_policy(
        replace(
            _POLICY,
            expected_access=ExpectedAccess.UNKNOWN,
            delegation=ResolutionState.RESOLVED_ALLOW,
        )
    )
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.ALLOWED
    assert result.reason_codes == (JudgeReason.SHARING_OR_DELEGATION_ALLOWS,)


def test_allowed_needs_no_owner_or_comparison_when_b_verified() -> None:
    # A·비교가 없어 (b)(c)가 UNKNOWN이어도 B가 검증되면 ALLOWED다(서로 다른 축).
    case = CaseInput(
        policy=replace(_POLICY, expected_access=ExpectedAccess.ALLOW),
        subjects=replace(_SUBJECTS, owner_status=SubjectStatus.UNKNOWN, owner_subject_ref=None),
        facts=_NO_COMPARISON,
    )
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.ALLOWED
    assert result.identity_check is CheckState.UNKNOWN
    assert result.data_check is CheckState.UNKNOWN
    assert result.reason_codes == (JudgeReason.POLICY_ALLOWS,)


def test_allow_with_unverified_b_is_undecidable() -> None:
    allow = replace(_POLICY, expected_access=ExpectedAccess.ALLOW)
    for subjects in (
        replace(_SUBJECTS, evaluated_status=SubjectStatus.EXPIRED),
        replace(_SUBJECTS, evaluated_status=SubjectStatus.UNKNOWN),
        replace(_SUBJECTS, evaluated_subject_ref=""),
    ):
        result = evaluate_case(CaseInput(allow, subjects, _FACTS), _OBSERVED_AT)
        assert result.value is VerdictValue.UNDECIDABLE
        assert JudgeReason.SUBJECT_NOT_VERIFIED in result.reason_codes


def test_deny_without_valid_exception_is_never_allowed() -> None:
    weak_data = replace(_CASE, facts=replace(_FACTS, nontrivial_data_match=CheckState.NO))
    for case in (_CASE, weak_data):
        assert evaluate_case(case, _OBSERVED_AT).value is not VerdictValue.ALLOWED


def test_sharing_unknown_with_cross_evidence_is_suspected() -> None:
    result = evaluate_case(
        _with_policy(replace(_POLICY, sharing=ResolutionState.UNKNOWN)), _OBSERVED_AT
    )
    assert result.value is VerdictValue.SUSPECTED
    assert result.policy_check is CheckState.UNKNOWN
    assert JudgeReason.SHARING_OR_DELEGATION_UNKNOWN in result.reason_codes


def test_expected_access_unknown_with_cross_evidence_is_suspected() -> None:
    result = evaluate_case(
        _with_policy(replace(_POLICY, expected_access=ExpectedAccess.UNKNOWN)), _OBSERVED_AT
    )
    assert result.value is VerdictValue.SUSPECTED
    assert result.policy_check is CheckState.UNKNOWN
    assert JudgeReason.EXPECTED_ACCESS_UNKNOWN in result.reason_codes


def test_missing_registered_source_is_undecidable() -> None:
    # (b)(c)가 모두 yes여도 정책 부재만으로는 SUSPECTED가 되지 않는다.
    result = evaluate_case(
        _with_policy(replace(_POLICY, has_registered_source=False)), _OBSERVED_AT
    )
    assert result.value is VerdictValue.UNDECIDABLE
    assert result.identity_check is CheckState.YES
    assert result.data_check is CheckState.YES
    assert JudgeReason.EXPECTED_ACCESS_POLICY_MISSING in result.reason_codes


def test_policy_not_valid_at_judgment_time_is_undecidable() -> None:
    # (b)(c)가 모두 yes여도 기준 시각에 무효인 정책은 UNDECIDABLE이다.
    result = evaluate_case(
        _with_policy(replace(_POLICY, valid_until=_OBSERVED_AT - timedelta(seconds=1))),
        _OBSERVED_AT,
    )
    assert result.value is VerdictValue.UNDECIDABLE
    assert result.policy_check is CheckState.UNKNOWN
    assert JudgeReason.EXPECTED_ACCESS_POLICY_INVALID in result.reason_codes


def test_policy_unknown_with_identity_unknown_is_undecidable() -> None:
    # 정책 내용이 불명이어도 (b)가 확인되지 않으면 SUSPECTED를 열지 않는다.
    case = replace(
        _with_policy(replace(_POLICY, expected_access=ExpectedAccess.UNKNOWN)),
        subjects=replace(_SUBJECTS, owner_status=SubjectStatus.UNKNOWN),
    )
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.UNDECIDABLE
    assert result.identity_check is CheckState.UNKNOWN


def test_policy_unknown_with_data_unknown_is_undecidable() -> None:
    case = replace(
        _with_policy(replace(_POLICY, sharing=ResolutionState.UNKNOWN)),
        facts=replace(_FACTS, nontrivial_data_match=CheckState.UNKNOWN),
    )
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.UNDECIDABLE
    assert result.data_check is CheckState.UNKNOWN


def test_same_subject_is_not_confirmed() -> None:
    case = replace(_CASE, subjects=replace(_SUBJECTS, evaluated_subject_ref="subject-a"))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is not VerdictValue.CONFIRMED
    assert result.identity_check is CheckState.NO
    assert JudgeReason.SUBJECTS_NOT_DISTINCT in result.reason_codes


def test_unverified_owner_reserves_identity() -> None:
    case = replace(_CASE, subjects=replace(_SUBJECTS, owner_status=SubjectStatus.EXPIRED))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.identity_check is CheckState.UNKNOWN
    assert JudgeReason.SUBJECT_NOT_VERIFIED in result.reason_codes


def test_reflection_not_excluded_fails_data() -> None:
    case = replace(_CASE, facts=replace(_FACTS, reflection_excluded=CheckState.NO))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.data_check is CheckState.NO
    assert JudgeReason.DATA_REFLECTION_PRESENT in result.reason_codes


def test_template_not_excluded_fails_data() -> None:
    case = replace(_CASE, facts=replace(_FACTS, template_excluded=CheckState.NO))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.data_check is CheckState.NO
    assert JudgeReason.DATA_TEMPLATE_PRESENT in result.reason_codes


def test_trivial_match_only_fails_data() -> None:
    # HMAC 일치·owner_id 단독·id 반사만으로는 nontrivial 일치가 서지 않는다.
    case = replace(_CASE, facts=replace(_FACTS, nontrivial_data_match=CheckState.NO))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is not VerdictValue.CONFIRMED
    assert result.data_check is CheckState.NO
    assert JudgeReason.DATA_NO_MATCH in result.reason_codes


def test_unverifiable_data_is_undecidable() -> None:
    case = replace(_CASE, facts=replace(_FACTS, nontrivial_data_match=CheckState.UNKNOWN))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.UNDECIDABLE
    assert result.data_check is CheckState.UNKNOWN
    assert JudgeReason.DATA_UNVERIFIABLE in result.reason_codes


def test_each_check_is_required_for_confirmed() -> None:
    weak_policy = _with_policy(replace(_POLICY, expected_access=ExpectedAccess.UNKNOWN))
    weak_identity = replace(_CASE, subjects=replace(_SUBJECTS, evaluated_subject_ref="subject-a"))
    weak_data = replace(_CASE, facts=replace(_FACTS, same_resource=CheckState.NO))
    assert evaluate_case(weak_policy, _OBSERVED_AT).value is not VerdictValue.CONFIRMED
    assert evaluate_case(weak_identity, _OBSERVED_AT).value is not VerdictValue.CONFIRMED
    assert evaluate_case(weak_data, _OBSERVED_AT).value is not VerdictValue.CONFIRMED


def test_deny_without_data_match_is_undecidable() -> None:
    case = replace(_CASE, facts=replace(_FACTS, nontrivial_data_match=CheckState.NO))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.UNDECIDABLE


def test_empty_subject_ref_reserves_identity() -> None:
    case = replace(_CASE, subjects=replace(_SUBJECTS, evaluated_subject_ref=""))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.identity_check is CheckState.UNKNOWN
    assert JudgeReason.SUBJECT_NOT_VERIFIED in result.reason_codes


def test_policy_starting_after_observation_is_undecidable() -> None:
    # 관찰 이후 시작한 정책은 관찰 당시 유효하지 않다.
    result = evaluate_case(
        _with_policy(replace(_POLICY, valid_from=_OBSERVED_AT + timedelta(minutes=1))), _OBSERVED_AT
    )
    assert result.value is VerdictValue.UNDECIDABLE
    assert result.policy_check is CheckState.UNKNOWN
    assert JudgeReason.EXPECTED_ACCESS_POLICY_INVALID in result.reason_codes


def test_policy_valid_at_observation_confirms_despite_later_expiry() -> None:
    # 관찰 당시 유효했으면 이후 만료되더라도 관찰 시각 기준으로 CONFIRMED가 가능하다.
    case = _with_policy(
        replace(
            _POLICY,
            valid_from=_OBSERVED_AT - timedelta(minutes=5),
            valid_until=_OBSERVED_AT + timedelta(minutes=1),
        )
    )
    assert evaluate_case(case, _OBSERVED_AT).value is VerdictValue.CONFIRMED


def test_value_partition_over_every_policy_combination() -> None:
    # 강한 (b)(c)로 정책 조합을 전부 돌린다. 부재·무효는 UNDECIDABLE, SUSPECTED는 내용 불명 두
    # 사유, ALLOWED는 정책 NO, CONFIRMED는 명시 DENY+예외 없음에서만 나온다.
    valid = (_OBSERVED_AT - timedelta(hours=1), _OBSERVED_AT + timedelta(hours=1))
    expired = (_OBSERVED_AT - timedelta(hours=2), _OBSERVED_AT - timedelta(hours=1))
    suspected_reasons = {
        JudgeReason.EXPECTED_ACCESS_UNKNOWN,
        JudgeReason.SHARING_OR_DELEGATION_UNKNOWN,
    }
    for access, sharing, delegation, registered, (start, end) in product(
        ExpectedAccess, ResolutionState, ResolutionState, (True, False), (valid, expired)
    ):
        case = _with_policy(
            replace(
                _POLICY,
                expected_access=access,
                sharing=sharing,
                delegation=delegation,
                has_registered_source=registered,
                valid_from=start,
                valid_until=end,
            )
        )
        result = evaluate_case(case, _OBSERVED_AT)
        policy_reason = result.reason_codes[0]
        if not registered or (start, end) == expired:
            assert result.value is VerdictValue.UNDECIDABLE
            assert policy_reason in {
                JudgeReason.EXPECTED_ACCESS_POLICY_MISSING,
                JudgeReason.EXPECTED_ACCESS_POLICY_INVALID,
            }
        if result.value is VerdictValue.SUSPECTED:
            assert policy_reason in suspected_reasons
        if result.value is VerdictValue.ALLOWED:
            assert result.policy_check is CheckState.NO
        if result.value is VerdictValue.CONFIRMED:
            assert access is ExpectedAccess.DENY
            assert sharing is delegation is ResolutionState.RESOLVED_NONE
