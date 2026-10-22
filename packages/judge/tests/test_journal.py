"""judge verdict journal의 단위 테스트. commit·검증·멱등성·선고정 event_ref를 확인한다."""

from __future__ import annotations

from dataclasses import replace

import pytest
from abc2lab_contracts.audit import AuditVerifyRequest, VerificationState
from abc2lab_contracts.primitives import ReasonCode
from abc2lab_contracts.verdict import Verdict
from abc2lab_judge.adapters import (
    CommittedVerdict,
    InMemoryVerdictJournal,
    JournalCommitError,
    VerdictContext,
    to_verdict,
    verdict_record_binding,
)
from abc2lab_judge.core.model import OracleVerdict


def _verdict(oracle: OracleVerdict, context: VerdictContext, event_ref: str) -> Verdict:
    return to_verdict(oracle, context, producer="judge", event_ref=event_ref)


@pytest.mark.asyncio
async def test_append_assigns_receipt_and_verifies(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    verdict = _verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1")
    receipt = await journal.append(verdict)
    assert receipt.event_ref == verdict.source_event.event_ref == "judge:run-1:e1"
    assert receipt.sequence == 1
    expected = verdict_record_binding(verdict)
    assert receipt.binding == expected
    verification = await journal.verify_committed(
        AuditVerifyRequest(run_key=verdict.run_key, receipt=receipt, expected=expected)
    )
    assert verification.state is VerificationState.VERIFIED


@pytest.mark.asyncio
async def test_verify_unknown_when_event_absent(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    verdict = _verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1")
    receipt = await journal.append(verdict)
    expected = verdict_record_binding(verdict)
    absent = replace(receipt, event_ref="judge:run-1:absent")
    verification = await journal.verify_committed(
        AuditVerifyRequest(run_key=verdict.run_key, receipt=absent, expected=expected)
    )
    assert verification.state is VerificationState.UNKNOWN
    assert verification.reason_codes == (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,)


@pytest.mark.asyncio
async def test_verify_invalid_when_stored_content_tampered(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    # 저장 내용과 영수증이 어긋나게 조작하면, 영수증 복사가 아니라 내용 재계산만이 이를 잡는다.
    verdict = _verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1")
    receipt = await journal.append(verdict)
    expected = verdict_record_binding(verdict)
    key = (verdict.run_key, verdict.source_event.event_ref)
    tampered = replace(verdict, case_ref="tampered-case")
    journal._by_event[key] = CommittedVerdict(verdict=tampered, receipt=receipt)
    verification = await journal.verify_committed(
        AuditVerifyRequest(run_key=verdict.run_key, receipt=receipt, expected=expected)
    )
    assert verification.state is VerificationState.INVALID
    assert verification.reason_codes == (ReasonCode.SOURCE_UNVERIFIED,)


@pytest.mark.asyncio
async def test_same_content_recommit_is_idempotent(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    verdict = _verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1")
    first = await journal.append(verdict)
    second = await journal.append(verdict)
    assert first == second
    assert len(journal.committed(verdict.run_key)) == 1


@pytest.mark.asyncio
async def test_same_revision_different_content_conflicts(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    await journal.append(_verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1"))
    other = _verdict(
        confirmed_oracle, replace(confirmed_context, case_ref="case-2"), "judge:run-1:e2"
    )
    with pytest.raises(JournalCommitError) as error:
        await journal.append(other)
    assert error.value.reason_code is ReasonCode.IDEMPOTENCY_CONFLICT


@pytest.mark.asyncio
async def test_new_revision_is_a_new_record(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    first = await journal.append(_verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1"))
    second = await journal.append(
        _verdict(confirmed_oracle, replace(confirmed_context, revision=2), "judge:run-1:e2")
    )
    assert first.sequence == 1
    assert second.sequence == 2
    assert len(journal.committed(confirmed_context.run_key)) == 2


@pytest.mark.asyncio
async def test_event_ref_reuse_for_other_record_rejected(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    await journal.append(_verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1"))
    reused = _verdict(
        confirmed_oracle, replace(confirmed_context, verdict_ref="verdict-2"), "judge:run-1:e1"
    )
    with pytest.raises(JournalCommitError):
        await journal.append(reused)
