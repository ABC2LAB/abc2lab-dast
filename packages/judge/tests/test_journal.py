"""judge verdict journal의 단위 테스트. commit·검증·멱등성·선고정 event_ref를 확인한다."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

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

_OCCURRED_AT = datetime(2026, 10, 22, 12, 30, tzinfo=UTC)


def _verdict(oracle: OracleVerdict, context: VerdictContext, event_ref: str) -> Verdict:
    return to_verdict(oracle, context, producer="judge", event_ref=event_ref)


@pytest.mark.asyncio
async def test_append_assigns_receipt_and_verifies(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    verdict = _verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1")
    receipt = await journal.append(verdict, occurred_at=_OCCURRED_AT)
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
    receipt = await journal.append(verdict, occurred_at=_OCCURRED_AT)
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
    receipt = await journal.append(verdict, occurred_at=_OCCURRED_AT)
    expected = verdict_record_binding(verdict)
    key = (verdict.run_key, verdict.source_event.event_ref)
    tampered = replace(verdict, case_ref="tampered-case")
    journal._by_event[key] = CommittedVerdict(
        verdict=tampered, receipt=receipt, occurred_at=_OCCURRED_AT
    )
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
    first = await journal.append(verdict, occurred_at=_OCCURRED_AT)
    second = await journal.append(verdict, occurred_at=_OCCURRED_AT)
    assert first == second
    assert len(journal.committed(verdict.run_key)) == 1


@pytest.mark.asyncio
async def test_same_revision_different_content_conflicts(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    await journal.append(
        _verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1"), occurred_at=_OCCURRED_AT
    )
    other = _verdict(
        confirmed_oracle, replace(confirmed_context, case_ref="case-2"), "judge:run-1:e2"
    )
    with pytest.raises(JournalCommitError) as error:
        await journal.append(other, occurred_at=_OCCURRED_AT)
    assert error.value.reason_code is ReasonCode.IDEMPOTENCY_CONFLICT


@pytest.mark.asyncio
async def test_new_revision_is_a_new_record(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    first = await journal.append(
        _verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1"), occurred_at=_OCCURRED_AT
    )
    second = await journal.append(
        _verdict(confirmed_oracle, replace(confirmed_context, revision=2), "judge:run-1:e2"),
        occurred_at=_OCCURRED_AT,
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
    await journal.append(
        _verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1"), occurred_at=_OCCURRED_AT
    )
    reused = _verdict(
        confirmed_oracle, replace(confirmed_context, verdict_ref="verdict-2"), "judge:run-1:e1"
    )
    with pytest.raises(JournalCommitError):
        await journal.append(reused, occurred_at=_OCCURRED_AT)


@pytest.mark.asyncio
async def test_occurred_at_is_stored_separately_from_committed_at(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    verdict = _verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1")
    receipt = await journal.append(verdict, occurred_at=_OCCURRED_AT)
    stored = journal.committed(verdict.run_key)[0]
    assert stored.occurred_at == _OCCURRED_AT
    # 감사 발생 시각과 journal commit 시각은 서로 대신하지 않는다.
    assert receipt.committed_at != _OCCURRED_AT


@pytest.mark.asyncio
async def test_latest_revision_tracks_committed_revisions(
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    run_key, verdict_ref = confirmed_context.run_key, confirmed_context.verdict_ref
    assert await journal.latest_revision(run_key, verdict_ref) == 0
    await journal.append(
        _verdict(confirmed_oracle, confirmed_context, "judge:run-1:e1"), occurred_at=_OCCURRED_AT
    )
    second = replace(confirmed_context, revision=2)
    await journal.append(
        _verdict(confirmed_oracle, second, "judge:run-1:e2"), occurred_at=_OCCURRED_AT
    )
    assert await journal.latest_revision(run_key, verdict_ref) == 2
    assert await journal.latest_revision(run_key, "other-verdict") == 0
