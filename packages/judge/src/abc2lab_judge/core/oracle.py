"""수평 IDOR 보수적 오라클.

(a) 신뢰된 등록 정책이 평가 주체를 명시 금지하고 공유·위임이 모두 해소(none),
(b) A·B가 서로 다른 검증된 주체,
(c) 소유자 객체의 비자명 실데이터가 반사·템플릿 배제 후 교차 응답에 나타남
을 각각 확인한다. 셋이 모두 `yes`일 때만 CONFIRMED이다. HMAC 일치·`owner_id` 단독·id 반사·HTTP
200·공통 템플릿만으로는 (c)를 충족하지 않는다.

나머지 값은 (a)의 상태가 아니라 **사유**로 가른다(C4-B 계약 §2). `CheckState.UNKNOWN`은 정책 부재·
무효·내용 불명을 한데 묶으므로 상태로 분기하면 부재가 SUSPECTED로 새어 나간다.
- 검증된 직접 허용 또는 공유·위임 허용이면 평가 주체 B가 검증됐을 때만 ALLOWED다. A/B 구별·교차
  노출 (b)(c)는 요구하지 않는다(계약 §2.1).
- 등록 정책의 내용이 불명(기대 접근 불명·공유/위임 불명)이고 (b)(c)가 모두 `yes`면 SUSPECTED다.
- 정책이 없거나 기준 시각에 유효하지 않으면 (b)(c)와 무관하게 UNDECIDABLE이다(S1 명세 §9).
- 그 밖에 확인하지 못한 것은 모두 UNDECIDABLE이다.

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

# 검증된 허용 경로. 이 사유의 판정은 평가 주체 B가 검증되면 ALLOWED다.
_ALLOW_POLICY_REASONS: frozenset[JudgeReason] = frozenset(
    {JudgeReason.POLICY_ALLOWS, JudgeReason.SHARING_OR_DELEGATION_ALLOWS}
)

# 등록 정책은 있으나 내용이 불명인 사유. 이때만 (b)(c)가 모두 확인되면 SUSPECTED를 연다. 정책 부재·
# 기준 시각 무효는 넣지 않는다 — 단순 부재로는 SUSPECTED를 만들 수 없다(계약 §2).
_SUSPECTED_POLICY_REASONS: frozenset[JudgeReason] = frozenset(
    {JudgeReason.EXPECTED_ACCESS_UNKNOWN, JudgeReason.SHARING_OR_DELEGATION_UNKNOWN}
)


def check_expected_policy(policy: PolicyAssertion, observed_at: datetime) -> CheckOutcome:
    """(a) 등록 정책이 평가 주체를 명시 금지하고 공유·위임이 모두 해소(none)인지 판정한다.

    유효성은 근거의 관찰 시각 `observed_at` 기준이다. 관찰 이후 시작했거나(valid_from 이후) 관찰
    당시 이미 만료된 정책은 `UNKNOWN`으로 둔다. 허용 경로(직접 ALLOW, 공유·위임 RESOLVED_ALLOW)를
    공유·위임 UNKNOWN보다 먼저 본다. `ResolutionState`에는 제한 상태가 없어 UNKNOWN 예외는 허용을
    더할 수만 있고 이미 검증된 허용을 무효화하지 못한다.
    """
    if not policy.has_registered_source:
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.EXPECTED_ACCESS_POLICY_MISSING)
    if not policy.hint_matches_canonical:
        # 힌트와 정본이 다르면 정본 내용과 무관하게 정책 무효로 보류한다(명세 §9).
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.EXPECTED_ACCESS_POLICY_INVALID)
    if not policy.valid_from <= observed_at < policy.valid_until:
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.EXPECTED_ACCESS_POLICY_INVALID)
    if policy.expected_access is ExpectedAccess.ALLOW:
        return CheckOutcome(CheckState.NO, JudgeReason.POLICY_ALLOWS)

    exceptions = (policy.sharing, policy.delegation)
    if ResolutionState.RESOLVED_ALLOW in exceptions:
        return CheckOutcome(CheckState.NO, JudgeReason.SHARING_OR_DELEGATION_ALLOWS)
    if ResolutionState.UNKNOWN in exceptions:
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.SHARING_OR_DELEGATION_UNKNOWN)
    if policy.expected_access is ExpectedAccess.UNKNOWN:
        return CheckOutcome(CheckState.UNKNOWN, JudgeReason.EXPECTED_ACCESS_UNKNOWN)
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
    """사례를 (a)(b)(c)로 판정한다(보수적). 값은 (a)의 사유와 (b)(c)의 상태로 정한다.

    Args:
        case: 정책·주체·비교 신호를 담은 사례 입력.
        observed_at: 정책 유효성 판정의 기준이 되는 근거 관찰 시각(timezone-aware UTC).

    Returns:
        판정값·세 조건의 CheckState·사유 코드. 사유는 정책·신원·데이터 순서다. ALLOWED는 허용 사유
        하나만 담는다 — A 미검증·비교 없음의 축 사유가 "B 미검증"으로 읽히지 않게 한다.
    """
    policy = check_expected_policy(case.policy, observed_at)
    identity = check_identity(case.subjects)
    data = check_data(case.facts)
    value = _decide_value(policy.reason, identity.state, data.state, case.subjects)
    if value is VerdictValue.ALLOWED:
        reasons: tuple[JudgeReason, ...] = (policy.reason,)
    else:
        reasons = (policy.reason, identity.reason, data.reason)
    return OracleVerdict(
        value=value,
        policy_check=policy.state,
        identity_check=identity.state,
        data_check=data.state,
        reason_codes=reasons,
    )


def _decide_value(
    policy_reason: JudgeReason,
    identity: CheckState,
    data: CheckState,
    subjects: SubjectContext,
) -> VerdictValue:
    cross_verified = identity is CheckState.YES and data is CheckState.YES
    if policy_reason is JudgeReason.POLICY_DENY_RESOLVED:
        return VerdictValue.CONFIRMED if cross_verified else VerdictValue.UNDECIDABLE
    if policy_reason in _ALLOW_POLICY_REASONS:
        if _evaluated_subject_verified(subjects):
            return VerdictValue.ALLOWED
        return VerdictValue.UNDECIDABLE
    if policy_reason in _SUSPECTED_POLICY_REASONS and cross_verified:
        return VerdictValue.SUSPECTED
    # 정책 부재·무효, (b)(c) 미확인, 집합에 없는 사유는 모두 UNDECIDABLE로 둔다(fail-closed).
    return VerdictValue.UNDECIDABLE


def _evaluated_subject_verified(subjects: SubjectContext) -> bool:
    # 평가 주체 B 자신의 검증 여부다. A/B 구별인 (b)와 별개 축이다(계약 §2.1).
    return subjects.evaluated_status is SubjectStatus.VERIFIED and bool(
        subjects.evaluated_subject_ref
    )
