"""검증된 공개 레코드를 오라클 입력(`CaseInput`)과 판정 기준 시각으로 옮기는 순수 함수.

기준 시각 규칙(C4-B 계약 §3):
- 비교가 있으면 정책과 평가 주체 B는 cross 관찰 시각에, 소유자 A는 owner 관찰 시각에 판정한다.
  정책의 유효성은 정본의 유효기간으로만 보고, 현재 정책을 과거 시점에 소급하지 않는다.
- 비교가 없으면 주입된 신뢰 판정 시각 하나에서 판정한다.
- owner/cross 두 시점을 A의 검증 신원 유효기간이 모두 덮지 못하면 같은 자원·데이터 기준선을 보장할
  수 없으므로 기준선 의존 신호의 YES를 UNKNOWN으로 낮춘다.
contracts 값과 내부 enum은 값이 같아도 타입이 달라 명시 대응표로 옮긴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from abc2lab_contracts.evidence import ComparisonSignals
from abc2lab_contracts.primitives import CheckState as WireCheckState
from abc2lab_contracts.registration import ExpectedAccess as WireExpectedAccess
from abc2lab_contracts.registration import ExpectedAccessPolicySnapshot
from abc2lab_contracts.registration import ResolutionState as WireResolutionState
from abc2lab_contracts.session import IdentityResult, IdentityStatus

from abc2lab_judge.adapters.attestation import LoadedComparison
from abc2lab_judge.core.model import (
    CaseInput,
    CheckState,
    ComparisonFacts,
    ExpectedAccess,
    PolicyAssertion,
    ResolutionState,
    SubjectContext,
    SubjectStatus,
)

_ACCESS_MAP: dict[WireExpectedAccess, ExpectedAccess] = {
    WireExpectedAccess.ALLOW: ExpectedAccess.ALLOW,
    WireExpectedAccess.DENY: ExpectedAccess.DENY,
    WireExpectedAccess.UNKNOWN: ExpectedAccess.UNKNOWN,
}

_RESOLUTION_MAP: dict[WireResolutionState, ResolutionState] = {
    WireResolutionState.RESOLVED_NONE: ResolutionState.RESOLVED_NONE,
    WireResolutionState.RESOLVED_ALLOW: ResolutionState.RESOLVED_ALLOW,
    WireResolutionState.UNKNOWN: ResolutionState.UNKNOWN,
}

_CHECK_MAP: dict[WireCheckState, CheckState] = {
    WireCheckState.YES: CheckState.YES,
    WireCheckState.NO: CheckState.NO,
    WireCheckState.UNKNOWN: CheckState.UNKNOWN,
}

# VERIFIED는 기준 시각으로 따로 판정하므로 표에 두지 않는다.
_UNVERIFIED_STATUS_MAP: dict[IdentityStatus, SubjectStatus] = {
    IdentityStatus.UNKNOWN: SubjectStatus.UNKNOWN,
    IdentityStatus.EXPIRED: SubjectStatus.EXPIRED,
    IdentityStatus.MISMATCH: SubjectStatus.MISMATCH,
}


@dataclass(frozen=True, slots=True)
class JudgmentInputs:
    """검증·대조를 마친 한 case의 판정 재료."""

    policy: ExpectedAccessPolicySnapshot | None
    hint_matches_canonical: bool
    owner_identity: IdentityResult | None
    evaluated_identity: IdentityResult | None
    comparison: LoadedComparison | None
    judged_at: datetime


def distill_case(inputs: JudgmentInputs) -> tuple[CaseInput, datetime]:
    """판정 재료를 오라클 입력과 정책 판정 기준 시각으로 바꾼다."""
    comparison = inputs.comparison
    if comparison is None:
        basis = owner_at = inputs.judged_at
        facts = to_comparison_facts(None, baseline_holds=False)
    else:
        owner_at = comparison.owner.observed_at
        basis = comparison.cross.observed_at
        holds = baseline_holds(inputs.owner_identity, owner_at, basis)
        facts = to_comparison_facts(comparison.payload.signals, baseline_holds=holds)
    subjects = SubjectContext(
        owner_status=to_subject_status(inputs.owner_identity, owner_at),
        evaluated_status=to_subject_status(inputs.evaluated_identity, basis),
        owner_subject_ref=_subject_ref(inputs.owner_identity),
        evaluated_subject_ref=_subject_ref(inputs.evaluated_identity),
    )
    policy = to_policy_assertion(
        inputs.policy, hint_matches_canonical=inputs.hint_matches_canonical, at=basis
    )
    return CaseInput(policy=policy, subjects=subjects, facts=facts), basis


def to_policy_assertion(
    policy: ExpectedAccessPolicySnapshot | None, *, hint_matches_canonical: bool, at: datetime
) -> PolicyAssertion:
    """정본 정책을 오라클 정책 축약으로 바꾼다. 정본이 없으면 등록 출처 없음으로 둔다."""
    if policy is None:
        # 정상 부재. 출처가 없으면 오라클이 유효기간을 보지 않으므로 기준 시각을 자리값으로 둔다.
        return PolicyAssertion(
            expected_access=ExpectedAccess.UNKNOWN,
            sharing=ResolutionState.UNKNOWN,
            delegation=ResolutionState.UNKNOWN,
            has_registered_source=False,
            valid_from=at,
            valid_until=at,
            hint_matches_canonical=hint_matches_canonical,
        )
    return PolicyAssertion(
        expected_access=_ACCESS_MAP[policy.expected_access],
        sharing=_RESOLUTION_MAP[policy.sharing],
        delegation=_RESOLUTION_MAP[policy.delegation],
        has_registered_source=True,
        valid_from=policy.valid_from,
        valid_until=policy.valid_until,
        hint_matches_canonical=hint_matches_canonical,
    )


def to_subject_status(identity: IdentityResult | None, at: datetime) -> SubjectStatus:
    """기준 시각 `at`에서 신원의 확인 상태. 유효기간 밖이면 검증된 주체로 보지 않는다."""
    if identity is None:
        return SubjectStatus.UNKNOWN
    if identity.status is not IdentityStatus.VERIFIED:
        return _UNVERIFIED_STATUS_MAP[identity.status]
    if identity.verified_at is None or identity.valid_until is None:
        return SubjectStatus.UNKNOWN
    if at < identity.verified_at:
        return SubjectStatus.UNKNOWN
    if at >= identity.valid_until:
        return SubjectStatus.EXPIRED
    return SubjectStatus.VERIFIED


def baseline_holds(owner: IdentityResult | None, owner_at: datetime, cross_at: datetime) -> bool:
    """A의 검증 신원 유효기간이 owner·cross 두 관찰 시각을 모두 덮는지."""
    if owner is None or owner.status is not IdentityStatus.VERIFIED:
        return False
    if owner.verified_at is None or owner.valid_until is None:
        return False
    return owner.verified_at <= min(owner_at, cross_at) and owner.valid_until > max(
        owner_at, cross_at
    )


def to_comparison_facts(
    signals: ComparisonSignals | None, *, baseline_holds: bool
) -> ComparisonFacts:
    """비교 신호를 오라클 비교 사실로 바꾼다. 비교가 없으면 전부 확인 불가다."""
    if signals is None:
        unknown = CheckState.UNKNOWN
        return ComparisonFacts(unknown, unknown, unknown, unknown, unknown, unknown)
    same_resource = _CHECK_MAP[signals.same_resource]
    owner_normal = _CHECK_MAP[signals.owner_normal_data]
    data_match = _CHECK_MAP[signals.nontrivial_data_match]
    if not baseline_holds:
        same_resource, owner_normal, data_match = (
            _without_yes(same_resource),
            _without_yes(owner_normal),
            _without_yes(data_match),
        )
    return ComparisonFacts(
        same_resource=same_resource,
        owner_normal_data=owner_normal,
        cross_normal_data=_CHECK_MAP[signals.cross_normal_data],
        nontrivial_data_match=data_match,
        reflection_excluded=_CHECK_MAP[signals.reflection_excluded],
        template_excluded=_CHECK_MAP[signals.template_excluded],
    )


def _without_yes(state: CheckState) -> CheckState:
    # 기준선을 보장할 수 없으면 확정(YES)만 보류한다. NO는 그대로 미충족으로 남긴다.
    return CheckState.UNKNOWN if state is CheckState.YES else state


def _subject_ref(identity: IdentityResult | None) -> str | None:
    return None if identity is None else identity.subject_ref
