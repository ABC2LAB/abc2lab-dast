"""judge verdict 변환 어댑터의 단위 테스트. 네트워크·I/O 없이 실행한다."""

from __future__ import annotations

from abc2lab_contracts.primitives import AuditLink, CheckState, ReasonCode
from abc2lab_contracts.verdict import VerdictValue
from abc2lab_judge.adapters import VerdictContext, to_check_state, to_contract_reasons, to_verdict
from abc2lab_judge.adapters.translation import (
    _CHECK_MAP,
    _REASON_MAP,
    _UNMAPPED,
    _VALUE_MAP,
    _WIRE_EVIDENCE_DROPPED,
    to_verdict_value,
)
from abc2lab_judge.core.model import CheckState as JudgeCheckState
from abc2lab_judge.core.model import JudgeReason, OracleVerdict
from abc2lab_judge.core.model import VerdictValue as JudgeVerdictValue


def test_value_map_covers_every_internal_value() -> None:
    assert set(_VALUE_MAP) == set(JudgeVerdictValue)


def test_check_map_covers_every_internal_state() -> None:
    assert set(_CHECK_MAP) == set(JudgeCheckState)


def test_value_conversion_is_uppercase_wire() -> None:
    assert to_verdict_value(JudgeVerdictValue.CONFIRMED) is VerdictValue.CONFIRMED
    assert to_verdict_value(JudgeVerdictValue.UNDECIDABLE) is VerdictValue.UNDECIDABLE
    # 내부 값은 소문자, wire 값은 대문자다(.value 직접 변환이면 깨진다).
    assert JudgeVerdictValue.CONFIRMED.value == "confirmed"
    assert VerdictValue.CONFIRMED.value == "CONFIRMED"


def test_check_conversion() -> None:
    assert to_check_state(JudgeCheckState.YES) is CheckState.YES
    assert to_check_state(JudgeCheckState.NO) is CheckState.NO
    assert to_check_state(JudgeCheckState.UNKNOWN) is CheckState.UNKNOWN


def test_reason_classification_is_exhaustive_and_disjoint() -> None:
    # 새 사유를 추가하면 실행 중 조용히 누락되지 않고 이 테스트가 먼저 실패해야 한다.
    mapped = set(_REASON_MAP)
    assert _WIRE_EVIDENCE_DROPPED | mapped | _UNMAPPED == set(JudgeReason)
    assert _WIRE_EVIDENCE_DROPPED.isdisjoint(mapped)
    assert _WIRE_EVIDENCE_DROPPED.isdisjoint(_UNMAPPED)
    assert mapped.isdisjoint(_UNMAPPED)
    # C4-B(#39)로 공개 코드가 모두 생겨 미대응은 비어 있다. YES 근거가 아닌 사유는 전부 매핑된다.
    assert _UNMAPPED == frozenset()
    assert mapped == set(JudgeReason) - _WIRE_EVIDENCE_DROPPED


def test_yes_evidence_reasons_dropped_from_wire() -> None:
    assert (
        to_contract_reasons(
            (
                JudgeReason.POLICY_DENY_RESOLVED,
                JudgeReason.SUBJECTS_DISTINCT_VERIFIED,
                JudgeReason.DATA_NONTRIVIAL_MATCH,
            )
        )
        == ()
    )


def test_mapped_reasons_and_dedup() -> None:
    reasons = (
        JudgeReason.EXPECTED_ACCESS_POLICY_MISSING,
        JudgeReason.SHARING_OR_DELEGATION_UNKNOWN,
        JudgeReason.EXPECTED_ACCESS_POLICY_MISSING,
    )
    assert to_contract_reasons(reasons) == (
        ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,
        ReasonCode.SHARING_OR_DELEGATION_UNKNOWN,
    )


def test_newly_added_reasons_map_to_same_name_wire_codes() -> None:
    # C4-B 전에는 비워 두던(미대응) 사유들이 이제 같은 이름의 공개 코드로 그대로 나간다.
    assert to_contract_reasons((JudgeReason.DATA_NO_MATCH, JudgeReason.DATA_UNVERIFIABLE)) == (
        ReasonCode.DATA_NO_MATCH,
        ReasonCode.DATA_UNVERIFIABLE,
    )


def test_every_non_evidence_reason_maps_to_identical_name() -> None:
    # YES 근거 드롭을 뺀 모든 JudgeReason은 이름이 같은 ReasonCode로 대응한다(억지 매핑 없음).
    for reason in set(JudgeReason) - _WIRE_EVIDENCE_DROPPED:
        assert _REASON_MAP[reason].name == reason.name


def test_to_verdict_confirmed(
    confirmed_oracle: OracleVerdict, confirmed_context: VerdictContext
) -> None:
    verdict = to_verdict(
        confirmed_oracle, confirmed_context, producer="judge", event_ref="judge:e1"
    )
    assert verdict.value is VerdictValue.CONFIRMED
    assert verdict.policy_check is CheckState.YES
    assert verdict.reason_codes == ()  # YES 근거는 전부 drop, CONFIRMED는 사유 없이 허용
    assert verdict.source_event == AuditLink(producer="judge", event_ref="judge:e1")
    assert verdict.expected_policy_source == confirmed_context.expected_policy_source


def test_to_verdict_undetermined_with_mapped_reason(
    undecidable_mapped_oracle: OracleVerdict, undetermined_context: VerdictContext
) -> None:
    verdict = to_verdict(
        undecidable_mapped_oracle, undetermined_context, producer="judge", event_ref="judge:e1"
    )
    assert verdict.value is VerdictValue.UNDECIDABLE
    assert verdict.reason_codes == (ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,)


def test_data_unverifiable_only_undecidable_is_publishable(
    undecidable_data_unverifiable_oracle: OracleVerdict, undetermined_context: VerdictContext
) -> None:
    # 과거 xfail: 데이터 검증 불가(UNDECIDABLE)의 유일한 wire 사유 DATA_UNVERIFIABLE가 미대응이라
    # Verdict 생성자가 거부했다. C4-B(#39)로 공개 코드가 생겨 이제 정상 발행된다.
    verdict = to_verdict(
        undecidable_data_unverifiable_oracle,
        undetermined_context,
        producer="judge",
        event_ref="judge:e1",
    )
    assert verdict.value is VerdictValue.UNDECIDABLE
    assert verdict.reason_codes == (ReasonCode.DATA_UNVERIFIABLE,)
