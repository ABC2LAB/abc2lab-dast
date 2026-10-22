"""내부 오라클 판정을 공개 C4 `Verdict`로 변환하는 순수 함수들이다.

judge 내부 enum은 소문자이고 공유 `VerdictValue`의 wire 값은 대문자이며 `CheckState`는 값은 같아도
별도 타입이므로, 값 문자열에 기대지 않고 명시 대응표로 변환한다. 판정 사유는 wire에서 뺄 근거,
계약 사유로 대응되는 것, 아직 계약 코드가 없는 것으로 나눈다. 비밀·원문을 담지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from abc2lab_contracts.primitives import (
    AuditLink,
    CheckState,
    ReasonCode,
    Ref,
    Revision,
    RunKey,
    SourceVersion,
)
from abc2lab_contracts.verdict import Verdict, VerdictValue

from abc2lab_judge.core.model import CheckState as JudgeCheckState
from abc2lab_judge.core.model import JudgeReason, OracleVerdict
from abc2lab_judge.core.model import VerdictValue as JudgeVerdictValue

# 내부 소문자 판정값을 wire 대문자로 명시 변환한다(.value 문자열이 달라 직접 변환 불가).
_VALUE_MAP: dict[JudgeVerdictValue, VerdictValue] = {
    JudgeVerdictValue.CONFIRMED: VerdictValue.CONFIRMED,
    JudgeVerdictValue.SUSPECTED: VerdictValue.SUSPECTED,
    JudgeVerdictValue.UNDECIDABLE: VerdictValue.UNDECIDABLE,
}

# 값은 같아도 내부·공개가 별도 타입이라 명시 대응한다.
_CHECK_MAP: dict[JudgeCheckState, CheckState] = {
    JudgeCheckState.YES: CheckState.YES,
    JudgeCheckState.NO: CheckState.NO,
    JudgeCheckState.UNKNOWN: CheckState.UNKNOWN,
}

# CONFIRMED를 뒷받침하는 YES 쪽 근거 사유. 공개 결과(wire)에는 싣지 않는다.
_WIRE_EVIDENCE_DROPPED: frozenset[JudgeReason] = frozenset(
    {
        JudgeReason.POLICY_DENY_RESOLVED,
        JudgeReason.SUBJECTS_DISTINCT_VERIFIED,
        JudgeReason.DATA_NONTRIVIAL_MATCH,
    }
)

# 공개 가능한(YES 근거가 아닌) 모든 판정 사유를 같은 이름의 공개 `ReasonCode`로 대응한다.
# C4-B(#39)로 judge용 사유 9개가 contracts에 추가돼, 비워 뒀던 사유를 전부 여기로 옮겼다.
_REASON_MAP: dict[JudgeReason, ReasonCode] = {
    JudgeReason.EXPECTED_ACCESS_POLICY_MISSING: ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,
    JudgeReason.EXPECTED_ACCESS_POLICY_INVALID: ReasonCode.EXPECTED_ACCESS_POLICY_INVALID,
    JudgeReason.EXPECTED_ACCESS_UNKNOWN: ReasonCode.EXPECTED_ACCESS_UNKNOWN,
    JudgeReason.POLICY_ALLOWS: ReasonCode.POLICY_ALLOWS,
    JudgeReason.SHARING_OR_DELEGATION_ALLOWS: ReasonCode.SHARING_OR_DELEGATION_ALLOWS,
    JudgeReason.SHARING_OR_DELEGATION_UNKNOWN: ReasonCode.SHARING_OR_DELEGATION_UNKNOWN,
    JudgeReason.SUBJECT_NOT_VERIFIED: ReasonCode.SUBJECT_NOT_VERIFIED,
    JudgeReason.SUBJECTS_NOT_DISTINCT: ReasonCode.SUBJECTS_NOT_DISTINCT,
    JudgeReason.DATA_NO_MATCH: ReasonCode.DATA_NO_MATCH,
    JudgeReason.DATA_REFLECTION_PRESENT: ReasonCode.DATA_REFLECTION_PRESENT,
    JudgeReason.DATA_TEMPLATE_PRESENT: ReasonCode.DATA_TEMPLATE_PRESENT,
    JudgeReason.DATA_UNVERIFIABLE: ReasonCode.DATA_UNVERIFIABLE,
}

# 의미가 맞는 공개 코드가 아직 없어 wire에서 비우는 사유. C4-B(#39)가 judge용 9개를 모두 추가해 현재
# 비어 있다. 새 내부 사유가 생겼는데 대응 `ReasonCode`가 없으면 억지로 기존 코드에 맞추지 말고 다시
# 여기에 둔다 — 그 사유만 남은 미확정 판정은 wire 사유가 비어 `Verdict` 생성자가 시끄럽게 거부한다.
_UNMAPPED: frozenset[JudgeReason] = frozenset()


@dataclass(frozen=True, slots=True)
class VerdictContext:
    """내부 판정을 공개 `Verdict`로 발행할 때 더하는 참조 맥락.

    `source_event`는 journal commit에 쓸 event_ref로 발행 직전에 정해지므로 맥락에 담지 않고
    `to_verdict`에 따로 전달한다.
    """

    run_key: RunKey
    verdict_ref: Ref
    revision: Revision
    case_ref: Ref
    oracle_version: SourceVersion
    expected_policy_source: SourceVersion | None = None
    comparison_ref: Ref | None = None
    evidence_refs: tuple[Ref, ...] = field(default_factory=tuple)


def to_verdict_value(value: JudgeVerdictValue) -> VerdictValue:
    """내부 판정값을 공개 wire 판정값으로 바꾼다."""
    return _VALUE_MAP[value]


def to_check_state(state: JudgeCheckState) -> CheckState:
    """내부 확인 상태를 공개 확인 상태로 바꾼다."""
    return _CHECK_MAP[state]


def to_contract_reasons(reasons: tuple[JudgeReason, ...]) -> tuple[ReasonCode, ...]:
    """내부 사유를 공개 `ReasonCode`로 매핑한다. YES 근거·미대응 사유는 제외하고 중복을 없앤다."""
    mapped = [_REASON_MAP[reason] for reason in reasons if reason in _REASON_MAP]
    return tuple(dict.fromkeys(mapped))


def to_verdict(
    oracle: OracleVerdict,
    context: VerdictContext,
    *,
    producer: Ref,
    event_ref: Ref,
) -> Verdict:
    """내부 오라클 판정을 공개 `Verdict`로 조립한다.

    `source_event`는 미리 정한 `event_ref`를 가리킨다(fingerprint에 포함되므로 commit 전에
    고정한다).
    미확정 판정인데 wire 사유가 하나도 남지 않으면(사유가 전부 YES 근거 드롭이면) `Verdict` 생성자가
    `ValueError`로 거부한다. 채움용 코드로 막지 않고 그대로 전파한다.
    """
    return Verdict(
        run_key=context.run_key,
        verdict_ref=context.verdict_ref,
        revision=context.revision,
        case_ref=context.case_ref,
        value=to_verdict_value(oracle.value),
        policy_check=to_check_state(oracle.policy_check),
        identity_check=to_check_state(oracle.identity_check),
        data_check=to_check_state(oracle.data_check),
        expected_policy_source=context.expected_policy_source,
        comparison_ref=context.comparison_ref,
        evidence_refs=context.evidence_refs,
        oracle_version=context.oracle_version,
        source_event=AuditLink(producer=producer, event_ref=event_ref),
        reason_codes=to_contract_reasons(oracle.reason_codes),
    )
