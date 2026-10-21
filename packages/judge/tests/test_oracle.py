"""수평 IDOR 보수적 오라클의 단위 테스트. 네트워크·DB·원문 없이 실행한다."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

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

_CASE = CaseInput(policy=_POLICY, subjects=_SUBJECTS, facts=_FACTS)


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


def test_explicit_allow_policy_is_not_confirmed() -> None:
    case = replace(_CASE, policy=replace(_POLICY, expected_access=ExpectedAccess.ALLOW))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is not VerdictValue.CONFIRMED
    assert result.policy_check is CheckState.NO
    assert JudgeReason.POLICY_ALLOWS in result.reason_codes


def test_resolved_allow_delegation_is_not_confirmed() -> None:
    case = replace(_CASE, policy=replace(_POLICY, delegation=ResolutionState.RESOLVED_ALLOW))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.policy_check is CheckState.NO
    assert JudgeReason.SHARING_OR_DELEGATION_ALLOWS in result.reason_codes


def test_sharing_unknown_is_undecidable() -> None:
    case = replace(_CASE, policy=replace(_POLICY, sharing=ResolutionState.UNKNOWN))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.UNDECIDABLE
    assert result.policy_check is CheckState.UNKNOWN
    assert JudgeReason.SHARING_OR_DELEGATION_UNKNOWN in result.reason_codes


def test_missing_registered_source_is_undecidable() -> None:
    case = replace(_CASE, policy=replace(_POLICY, has_registered_source=False))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.UNDECIDABLE
    assert JudgeReason.EXPECTED_ACCESS_POLICY_MISSING in result.reason_codes


def test_policy_not_valid_at_judgment_time_is_undecidable() -> None:
    case = replace(_CASE, policy=replace(_POLICY, valid_until=_OBSERVED_AT - timedelta(seconds=1)))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.policy_check is CheckState.UNKNOWN
    assert JudgeReason.EXPECTED_ACCESS_POLICY_INVALID in result.reason_codes


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
    weak_policy = replace(_CASE, policy=replace(_POLICY, expected_access=ExpectedAccess.UNKNOWN))
    weak_identity = replace(_CASE, subjects=replace(_SUBJECTS, evaluated_subject_ref="subject-a"))
    weak_data = replace(_CASE, facts=replace(_FACTS, same_resource=CheckState.NO))
    assert evaluate_case(weak_policy, _OBSERVED_AT).value is not VerdictValue.CONFIRMED
    assert evaluate_case(weak_identity, _OBSERVED_AT).value is not VerdictValue.CONFIRMED
    assert evaluate_case(weak_data, _OBSERVED_AT).value is not VerdictValue.CONFIRMED


def test_concrete_anomaly_promotes_unconfirmed_to_suspected() -> None:
    # 확인 불가가 없고(모두 결정됨) 미충족 + 명시 이상이면 SUSPECTED.
    facts = replace(_FACTS, nontrivial_data_match=CheckState.NO)
    case = replace(_CASE, facts=facts, has_concrete_anomaly=True)
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.SUSPECTED


def test_default_unconfirmed_without_anomaly_is_undecidable() -> None:
    case = replace(_CASE, facts=replace(_FACTS, nontrivial_data_match=CheckState.NO))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.UNDECIDABLE


def test_unknown_outranks_concrete_anomaly() -> None:
    # 확인 불가(정책 부재)는 명시 이상 신호가 있어도 UNDECIDABLE이 우선한다.
    case = replace(
        _CASE,
        policy=replace(_POLICY, has_registered_source=False),
        has_concrete_anomaly=True,
    )
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.value is VerdictValue.UNDECIDABLE
    assert result.policy_check is CheckState.UNKNOWN


def test_empty_subject_ref_reserves_identity() -> None:
    case = replace(_CASE, subjects=replace(_SUBJECTS, evaluated_subject_ref=""))
    result = evaluate_case(case, _OBSERVED_AT)
    assert result.identity_check is CheckState.UNKNOWN
    assert JudgeReason.SUBJECT_NOT_VERIFIED in result.reason_codes


def test_policy_starting_after_observation_is_undecidable() -> None:
    # 관찰 이후 시작한 정책은 관찰 당시 유효하지 않다.
    policy = replace(_POLICY, valid_from=_OBSERVED_AT + timedelta(minutes=1))
    result = evaluate_case(replace(_CASE, policy=policy), _OBSERVED_AT)
    assert result.policy_check is CheckState.UNKNOWN
    assert JudgeReason.EXPECTED_ACCESS_POLICY_INVALID in result.reason_codes


def test_policy_valid_at_observation_confirms_despite_later_expiry() -> None:
    # 관찰 당시 유효했으면 이후 만료되더라도 관찰 시각 기준으로 CONFIRMED가 가능하다.
    policy = replace(
        _POLICY,
        valid_from=_OBSERVED_AT - timedelta(minutes=5),
        valid_until=_OBSERVED_AT + timedelta(minutes=1),
    )
    result = evaluate_case(replace(_CASE, policy=policy), _OBSERVED_AT)
    assert result.value is VerdictValue.CONFIRMED
