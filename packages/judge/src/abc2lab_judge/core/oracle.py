"""수평 IDOR 보수적 오라클.

(a) 신뢰된 등록 정책이 평가 주체를 명시 금지하고 공유·위임이 모두 해소(none),
(b) A·B가 서로 다른 검증된 주체,
(c) 소유자 객체의 비자명 실데이터가 반사·템플릿 배제 후 교차 응답에 나타남
을 각각 확인한다. 셋이 모두 `yes`일 때만 CONFIRMED이다. 하나라도 `unknown`(확인 불가)이면
UNDECIDABLE이 우선하며, 전부 확인됐으나 미충족이면서 명시 이상 신호가 있을 때만
SUSPECTED(허용 범위는 팀 합의 전 잠정)다. HMAC 일치·`owner_id` 단독·id 반사·HTTP 200·공통
템플릿만으로는 (c)를 충족하지 않는다.

정책·주체 유효성은 **근거의 관찰 시각(`observed_at`)** 기준으로 판정하며, 판정 시각 TTL 경과만으로
당시 유효했던 근거를 버리지 않는다. 네트워크·저장·원문 없이 동작하는 순수 함수다.
"""

from __future__ import annotations

from datetime import datetime

from abc2lab_judge.core.model import (
    CaseInput,
    CheckOutcome,
    CheckState,
    ComparisonFacts,
    ExpectedAccess,
    JudgeReason,
    OracleVerdict,
    PolicyAssertion,
    ResolutionState,
    SubjectContext,
    SubjectStatus,
    VerdictValue,
)


def check_expected_policy(policy: PolicyAssertion, observed_at: datetime) -> CheckOutcome:
    """(a) 등록 정책이 평가 주체를 명시 금지하고 공유·위임이 모두 해소(none)인지 판정한다.

    유효성은 근거의 관찰 시각 `observed_at` 기준이다. 관찰 이후 시작했거나(valid_from 이후) 관찰
    당시 이미 만료된 정책은 `UNKNOWN`으로 둔다.
    """
    if not policy.has_registered_source:
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.EXPECTED_ACCESS_POLICY_MISSING)
    if not policy.valid_from <= observed_at < policy.valid_until:
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.EXPECTED_ACCESS_POLICY_INVALID)

    sharing_unknown = policy.sharing is ResolutionState.UNKNOWN
    delegation_unknown = policy.delegation is ResolutionState.UNKNOWN
    if sharing_unknown or delegation_unknown:
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.SHARING_OR_DELEGATION_UNKNOWN)
    if policy.expected_access is ExpectedAccess.UNKNOWN:
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.EXPECTED_ACCESS_UNKNOWN)
    if policy.expected_access is ExpectedAccess.ALLOW:
        return CheckOutcome(CheckState.NO, JudgeReason.POLICY_ALLOWS)

    sharing_allows = policy.sharing is ResolutionState.RESOLVED_ALLOW
    delegation_allows = policy.delegation is ResolutionState.RESOLVED_ALLOW
    if sharing_allows or delegation_allows:
        return CheckOutcome(CheckState.NO, JudgeReason.SHARING_OR_DELEGATION_ALLOWS)
    return CheckOutcome(CheckState.YES, JudgeReason.POLICY_DENY_RESOLVED)


def check_identity(subjects: SubjectContext) -> CheckOutcome:
    """(b) A·B가 모두 verified이고 서로 다른 주체인지 판정한다. 만료·불명은 유보."""
    if subjects.owner_status is not SubjectStatus.VERIFIED:
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.SUBJECT_NOT_VERIFIED)
    if subjects.evaluated_status is not SubjectStatus.VERIFIED:
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.SUBJECT_NOT_VERIFIED)
    if not subjects.owner_subject_ref or not subjects.evaluated_subject_ref:
        # None·빈 문자열 주체 참조는 검증된 주체로 인정하지 않는다.
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.SUBJECT_NOT_VERIFIED)
    if subjects.owner_subject_ref == subjects.evaluated_subject_ref:
        return CheckOutcome(CheckState.NO, JudgeReason.SUBJECTS_NOT_DISTINCT)
    return CheckOutcome(CheckState.YES, JudgeReason.SUBJECTS_DISTINCT_VERIFIED)


def check_data(facts: ComparisonFacts) -> CheckOutcome:
    """(c) 소유자 객체의 비자명 실데이터가 반사·템플릿 배제 후 교차 응답에 나타나는지 판정한다."""
    if facts.reflection_excluded is CheckState.NO:
        return CheckOutcome(CheckState.NO, JudgeReason.DATA_REFLECTION_PRESENT)
    if facts.template_excluded is CheckState.NO:
        return CheckOutcome(CheckState.NO, JudgeReason.DATA_TEMPLATE_PRESENT)
    if facts.nontrivial_data_match is CheckState.NO:
        return CheckOutcome(CheckState.NO, JudgeReason.DATA_NO_MATCH)

    required = (
        facts.same_resource,
        facts.owner_normal_data,
        facts.cross_normal_data,
        facts.nontrivial_data_match,
        facts.reflection_excluded,
        facts.template_excluded,
    )
    if any(state is CheckState.NO for state in required):
        return CheckOutcome(CheckState.NO, JudgeReason.DATA_NO_MATCH)
    if any(state is CheckState.UNKNOWN for state in required):
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.DATA_UNVERIFIABLE)
    return CheckOutcome(CheckState.YES, JudgeReason.DATA_NONTRIVIAL_MATCH)


def evaluate_case(case: CaseInput, observed_at: datetime) -> OracleVerdict:
    """사례를 (a)(b)(c)로 판정한다(보수적). 셋이 모두 yes일 때만 CONFIRMED.

    Args:
        case: 정책·주체·비교 신호와 SUSPECTED 잠정 게이트를 담은 사례 입력.
        observed_at: 정책 유효성 판정의 기준이 되는 근거 관찰 시각(timezone-aware UTC).

    Returns:
        판정값·세 조건의 CheckState·사유 코드. 사유 코드는 정책·신원·데이터 순서다.
    """
    policy = check_expected_policy(case.policy, observed_at)
    identity = check_identity(case.subjects)
    data = check_data(case.facts)
    checks = (policy, identity, data)

    any_unknown = any(outcome.state is CheckState.UNKNOWN for outcome in checks)
    if all(outcome.state is CheckState.YES for outcome in checks):
        value = VerdictValue.CONFIRMED
    elif any_unknown:
        # 확인 불가(정책 부재·유효성 불명·자료 미검증)는 SUSPECTED보다 UNDECIDABLE이 우선한다.
        value = VerdictValue.UNDECIDABLE
    elif case.has_concrete_anomaly:
        value = VerdictValue.SUSPECTED
    else:
        value = VerdictValue.UNDECIDABLE
    return OracleVerdict(
        value=value,
        policy_check=policy.state,
        identity_check=identity.state,
        data_check=data.state,
        reason_codes=tuple(outcome.reason for outcome in checks),
    )
