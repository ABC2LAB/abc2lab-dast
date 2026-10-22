"""judge verdict 변환 어댑터의 단위 테스트. 네트워크·I/O 없이 실행한다."""

from __future__ import annotations

import pytest
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


def test_unmapped_reasons_are_skipped() -> None:
    # 계약에 맞는 코드가 없는 사유는 기존 코드로 때우지 않고 건너뛴다(의미 왜곡 방지).
    assert to_contract_reasons((JudgeReason.DATA_NO_MATCH, JudgeReason.DATA_UNVERIFIABLE)) == ()


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


@pytest.mark.xfail(
    reason="미대응 사유에 맞는 contracts ReasonCode 부재 — judge용 사유 코드 추가 대기",
    strict=True,
    raises=ValueError,
)
def test_unmapped_only_undetermined_should_be_publishable(
    undecidable_unmapped_oracle: OracleVerdict, undetermined_context: VerdictContext
) -> None:
    # 데이터 검증 불가(UNDECIDABLE)의 유일한 사유가 미대응이라 wire 사유가 비고, Verdict 생성자가
    # 거부한다. judge 로직 구멍이 아니라 contracts 사유 코드 부재다. 코드가 생기면 xfail을 걷는다.
    verdict = to_verdict(
        undecidable_unmapped_oracle, undetermined_context, producer="judge", event_ref="judge:e1"
    )
    assert verdict.reason_codes != ()
