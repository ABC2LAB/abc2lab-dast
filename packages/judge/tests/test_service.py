"""`VerdictPublisher`의 단위 테스트. 발행·커밋 검증·시끄러운 실패를 확인한다. I/O 없이 실행한다."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from abc2lab_contracts.audit import AuditVerifyRequest, AuditVerifyResult, VerificationState
from abc2lab_contracts.primitives import ReasonCode
from abc2lab_contracts.projection import VerdictProjected
from abc2lab_judge.adapters import (
    InMemoryVerdictJournal,
    JournalCommitError,
    VerdictContext,
    VerdictPublisher,
)
from abc2lab_judge.core.model import OracleVerdict


class _StateJournal(InMemoryVerdictJournal):
    """commit은 하되 검증은 지정 상태를 돌려주는 journal."""

    def __init__(
        self, producer: str, state: VerificationState, *, clock: Callable[[], datetime]
    ) -> None:
        super().__init__(producer, clock=clock)
        self._state = state

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        return AuditVerifyResult(request.run_key, self._state, ())


def _publisher(journal: InMemoryVerdictJournal) -> VerdictPublisher:
    return VerdictPublisher(
        journal, "judge", event_ref_factory=lambda producer, run: f"{producer}:{run.run_ref}:fixed"
    )


@pytest.mark.asyncio
async def test_publish_confirmed_returns_projection(
    publisher: VerdictPublisher,
    journal: InMemoryVerdictJournal,
    confirmed_oracle: OracleVerdict,
    confirmed_context: VerdictContext,
) -> None:
    projected = await publisher.publish(confirmed_oracle, confirmed_context)
    assert isinstance(projected, VerdictProjected)
    assert projected.verdict.verdict_ref == "verdict-1"
    assert projected.event_ref == "judge:run-1:fixed"
    assert projected.producer == "judge"
    assert projected.source_revision == 1
    # 발행한 판정은 journal에 저장돼 있다.
    assert journal.committed(confirmed_context.run_key)[0].receipt == projected.source_receipt


@pytest.mark.asyncio
async def test_publish_undetermined_with_mapped_reason(
    publisher: VerdictPublisher,
    undecidable_mapped_oracle: OracleVerdict,
    undetermined_context: VerdictContext,
) -> None:
    projected = await publisher.publish(undecidable_mapped_oracle, undetermined_context)
    assert projected.verdict.reason_codes == (ReasonCode.EXPECTED_ACCESS_POLICY_MISSING,)


@pytest.mark.asyncio
async def test_publish_unmapped_only_fails_loudly(
    publisher: VerdictPublisher,
    undecidable_unmapped_oracle: OracleVerdict,
    undetermined_context: VerdictContext,
) -> None:
    # 미대응 사유만 남아 wire 사유가 비면 Verdict 생성자가 거부하고, 채움용 코드로 막지 않는다.
    with pytest.raises(ValueError):
        await publisher.publish(undecidable_unmapped_oracle, undetermined_context)


@pytest.mark.asyncio
async def test_publish_raises_on_invalid_verification(
    now: datetime, confirmed_oracle: OracleVerdict, confirmed_context: VerdictContext
) -> None:
    journal = _StateJournal("judge", VerificationState.INVALID, clock=lambda: now)
    with pytest.raises(JournalCommitError) as error:
        await _publisher(journal).publish(confirmed_oracle, confirmed_context)
    assert error.value.reason_code is ReasonCode.AUDIT_COMMIT_FAILED


@pytest.mark.asyncio
async def test_publish_raises_on_unknown_verification(
    now: datetime, confirmed_oracle: OracleVerdict, confirmed_context: VerdictContext
) -> None:
    journal = _StateJournal("judge", VerificationState.UNKNOWN, clock=lambda: now)
    with pytest.raises(JournalCommitError) as error:
        await _publisher(journal).publish(confirmed_oracle, confirmed_context)
    assert error.value.reason_code is ReasonCode.AUDIT_VERIFICATION_UNKNOWN
