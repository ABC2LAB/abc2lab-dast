"""수평 IDOR 오라클의 내부 도메인 모델.

공개 계약(C4 `Verdict`, C2 공유 타입 `CheckState`·`ExpectedAccessPolicySnapshot`·`IdentityResult`·
C3 `ComparisonSignals`)으로 변환되기 전의 모듈 내부 타입이다. 공개 계약을 대신하거나 사본으로 쓰지
않으며, 원문·캡처 핸들·HMAC 키를 받지 않는다. `adapters`가 저장된 비교 결과·정책 snapshot·신원
결과를 이 모델로 distill하고 이 판정을 `Verdict`로 발행할 책임을 진다.

판정은 보수적이다. (a)(b)(c)가 모두 충족될 때만 CONFIRMED이다. SUSPECTED·ALLOWED·UNDECIDABLE은
C4-B 계약 §2에 따라 (a)의 사유와 (b)(c)의 상태로 가른다(규칙은 `oracle`). 확인하지 못한 것은
UNDECIDABLE이 기본이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CheckState(StrEnum):
    """(a)(b)(c) 각 조건의 확인 상태. 확인하지 못하면 `UNKNOWN`."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class VerdictValue(StrEnum):
    """판정 결과. 보수적 기본값은 `UNDECIDABLE`.

    `ALLOWED`는 검증된 정책상 허용이다. HTTP 성공이나 취약점 부재를 뜻하지 않는다.
    """

    CONFIRMED = "confirmed"
    SUSPECTED = "suspected"
    UNDECIDABLE = "undecidable"
    ALLOWED = "allowed"


class ExpectedAccess(StrEnum):
    """등록 기대 정책이 평가 주체 B에게 부여한 접근."""

    ALLOW = "allow"
    DENY = "deny"
    UNKNOWN = "unknown"


class ResolutionState(StrEnum):
    """공유·위임 예외의 해소 상태. 조회하지 않음을 없음으로 보지 않는다."""

    RESOLVED_NONE = "resolved_none"
    RESOLVED_ALLOW = "resolved_allow"
    UNKNOWN = "unknown"


class SubjectStatus(StrEnum):
    """주체 확인 상태."""

    VERIFIED = "verified"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    MISMATCH = "mismatch"


class JudgeReason(StrEnum):
    """판정 사유 코드. C2/C4 병합 시 contracts `ReasonCode`로 매핑한다."""

    POLICY_DENY_RESOLVED = "policy_deny_resolved"
    POLICY_ALLOWS = "policy_allows"
    SHARING_OR_DELEGATION_ALLOWS = "sharing_or_delegation_allows"
    EXPECTED_ACCESS_POLICY_MISSING = "expected_access_policy_missing"
    EXPECTED_ACCESS_POLICY_INVALID = "expected_access_policy_invalid"
    EXPECTED_ACCESS_UNKNOWN = "expected_access_unknown"
    SHARING_OR_DELEGATION_UNKNOWN = "sharing_or_delegation_unknown"
    SUBJECTS_DISTINCT_VERIFIED = "subjects_distinct_verified"
    SUBJECT_NOT_VERIFIED = "subject_not_verified"
    SUBJECTS_NOT_DISTINCT = "subjects_not_distinct"
    DATA_NONTRIVIAL_MATCH = "data_nontrivial_match"
    DATA_NO_MATCH = "data_no_match"
    DATA_REFLECTION_PRESENT = "data_reflection_present"
    DATA_TEMPLATE_PRESENT = "data_template_present"
    DATA_UNVERIFIABLE = "data_unverifiable"


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """한 조건의 확인 상태와 사유."""

    state: CheckState
    reason: JudgeReason


@dataclass(frozen=True, slots=True)
class PolicyAssertion:
    """등록 기대 접근 정책의 판정용 축약. 등록 출처가 있을 때만 신뢰한다.

    `hint_matches_canonical`은 호출자가 공급한 정책 힌트가 reader가 돌려준 정본과 일치했는지다.
    정본이 이 case의 정책이어도 힌트가 다른(진위는 인증된) 정책이었다면 판정 근거로 쓰지 않는다 —
    명세 §9 "다른 case의 진짜 정책은 UNDECIDABLE + expected_access_policy_invalid".
    """

    expected_access: ExpectedAccess
    sharing: ResolutionState
    delegation: ResolutionState
    has_registered_source: bool
    valid_from: datetime
    valid_until: datetime
    hint_matches_canonical: bool


@dataclass(frozen=True, slots=True)
class SubjectContext:
    """A(소유자)·B(평가) 주체의 확인 상태와 주체 식별자."""

    owner_status: SubjectStatus
    evaluated_status: SubjectStatus
    owner_subject_ref: str | None
    evaluated_subject_ref: str | None


@dataclass(frozen=True, slots=True)
class ComparisonFacts:
    """로컬 비교기가 주입 규칙으로 산출한 비교 신호. 원문·HMAC 키를 포함하지 않는다."""

    same_resource: CheckState
    owner_normal_data: CheckState
    cross_normal_data: CheckState
    nontrivial_data_match: CheckState
    reflection_excluded: CheckState
    template_excluded: CheckState


@dataclass(frozen=True, slots=True)
class CaseInput:
    """한 사례의 판정 입력."""

    policy: PolicyAssertion
    subjects: SubjectContext
    facts: ComparisonFacts


@dataclass(frozen=True, slots=True)
class OracleVerdict:
    """내부 오라클 판정 결과. 발행·감사·revision은 adapter가 담당한다."""

    value: VerdictValue
    policy_check: CheckState
    identity_check: CheckState
    data_check: CheckState
    reason_codes: tuple[JudgeReason, ...]
