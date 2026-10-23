"""Judge verdict 감사 journal 포트와 메모리 어댑터.

Judge는 자기 판정을 자기 journal에만 commit하고, 같은 journal이 `verify_committed`로 저장된 기록을
다시 읽어 **재계산한 fingerprint**와 대조한다(S1 §10, C4 계약 §3). 이 포트는 judge 소유이며
contracts를 바꾸지 않는다. `source_event`가 `verdict_fingerprint`에 포함되므로 event_ref는 commit
전에 정해져야 한다 — 호출자가 발행 직전 event_ref를 정해 `Verdict`에 심고, append는 그 event_ref로
commit한다(policy journal이 append 안에서 event_ref를 만든 것과 반대).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from abc2lab_contracts.audit import (
    AuditEventKind,
    AuditReceipt,
    AuditRecordBinding,
    AuditVerifyRequest,
    AuditVerifyResult,
    VerificationState,
)
from abc2lab_contracts.fingerprint import verdict_fingerprint
from abc2lab_contracts.ports import AuditVerifier
from abc2lab_contracts.primitives import ReasonCode, Ref, RunKey
from abc2lab_contracts.verdict import Verdict


class JournalCommitError(Exception):
    """판정 commit을 확인하지 못했다. `reason_code`에 계약 사유를 담는다."""

    def __init__(
        self, message: str, *, reason_code: ReasonCode = ReasonCode.AUDIT_COMMIT_FAILED
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def verdict_record_binding(verdict: Verdict) -> AuditRecordBinding:
    """판정 내용의 업무 필드에서 감사 binding을 계산한다. 영수증 binding을 복사하지 않는다."""
    return AuditRecordBinding(
        event_kind=AuditEventKind.VERDICT,
        record_ref=verdict.verdict_ref,
        record_revision=verdict.revision,
        record_fingerprint=verdict_fingerprint(verdict),
        request_ref=None,
        attempt_ref=None,
        binding_id=None,
    )


class VerdictJournal(AuditVerifier, Protocol):
    """판정 commit과 저장 기록 검증을 함께 제공하는 judge 소유 포트.

    구현 계약:
    - `append`: `verdict.source_event.event_ref`로 판정을 내구 commit하고 영수증을 반환한다. 저장
      실패·commit 불명을 빈 성공으로 바꾸지 말고 `JournalCommitError`로 알린다. 같은
      `(verdict_ref, revision)`에 다른 내용이 이미 있으면 `idempotency_conflict`로 올린다. 갱신은 새
      revision의 새 기록이며 이전 기록을 덮어쓰지 않는다. 동일 내용의 재commit은 기존 영수증을
      돌려준다.
    - `verify_committed`(`AuditVerifier`): 저장 기록을 다시 읽어 run·영수증·binding과 저장 내용에서
      **재계산한 fingerprint**를 대조한다. 기록을 읽을 수 없으면 `UNKNOWN`, 내용이 다르면 `INVALID`.
    - `asyncio.CancelledError`는 감싸지 않고 전파한다.
    """

    async def append(self, verdict: Verdict, *, occurred_at: datetime) -> AuditReceipt:
        """판정을 불변으로 commit하고 영수증을 반환한다.

        `occurred_at`은 Judge 감사 이벤트의 발생 시각(신뢰 시계 1회 읽기)이다. 근거 관찰 시각이나
        `committed_at`과 다르며 그 값으로 대신하지 않는다.

        Raises:
            JournalCommitError: commit을 확인하지 못했거나 같은 (verdict_ref, revision)에 다른
                내용이 있거나 event_ref를 다른 기록이 이미 썼다.
        """
        ...

    async def latest_revision(self, run_key: RunKey, verdict_ref: Ref) -> int:
        """같은 run의 verdict_ref에 commit된 최고 revision을 반환한다. 없으면 0."""
        ...


@dataclass(frozen=True, slots=True)
class CommittedVerdict:
    """journal에 저장된 판정 내용과 그 영수증."""

    verdict: Verdict
    receipt: AuditReceipt
    occurred_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryVerdictJournal:
    """흐름 테스트용 비내구 메모리 journal.

    프로세스가 끝나면 기록이 사라지므로 app은 이 어댑터를 실제 저장과 연결하지 않는다. 같은 event
    loop의 단일 스레드에서 호출하며 `append`의 상태 변경 구간에는 await가 없다.
    """

    def __init__(self, producer: Ref, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._producer = producer
        self._clock = clock
        self._by_record: dict[tuple[RunKey, Ref, int], CommittedVerdict] = {}
        self._by_event: dict[tuple[RunKey, Ref], CommittedVerdict] = {}
        self._sequences: dict[RunKey, int] = {}

    async def append(self, verdict: Verdict, *, occurred_at: datetime) -> AuditReceipt:
        """판정을 commit한다. 같은 내용의 재commit은 기존 영수증(최초 occurred_at)을 반환한다."""
        event_ref = verdict.source_event.event_ref
        record_key = (verdict.run_key, verdict.verdict_ref, verdict.revision)
        existing = self._by_record.get(record_key)
        if existing is not None:
            if existing.verdict == verdict:
                return existing.receipt
            raise JournalCommitError(
                "verdict revision already committed with different content",
                reason_code=ReasonCode.IDEMPOTENCY_CONFLICT,
            )
        event_key = (verdict.run_key, event_ref)
        if event_key in self._by_event:
            # 다른 기록이 이미 쓴 event_ref다. 선고정한 event id를 재사용할 수 없다.
            raise JournalCommitError("event_ref already committed for another record")
        sequence = self._sequences.get(verdict.run_key, 0) + 1
        receipt = AuditReceipt(
            run_key=verdict.run_key,
            producer=self._producer,
            event_ref=event_ref,
            sequence=sequence,
            binding=verdict_record_binding(verdict),
            committed_at=self._clock(),
        )
        entry = CommittedVerdict(verdict=verdict, receipt=receipt, occurred_at=occurred_at)
        self._sequences[verdict.run_key] = sequence
        self._by_record[record_key] = entry
        self._by_event[event_key] = entry
        return receipt

    async def latest_revision(self, run_key: RunKey, verdict_ref: Ref) -> int:
        """같은 run의 verdict_ref에 commit된 최고 revision을 반환한다. 없으면 0."""
        revisions = [
            revision
            for (key, ref, revision) in self._by_record
            if key == run_key and ref == verdict_ref
        ]
        return max(revisions, default=0)

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        """저장된 판정에서 fingerprint를 재계산해 run·영수증·binding과 대조한다."""
        stored = self._by_event.get((request.run_key, request.receipt.event_ref))
        if stored is None:
            # 기록을 읽지 못한 것은 불일치(INVALID)가 아니라 확인 불가(UNKNOWN)로 보존한다.
            return AuditVerifyResult(
                request.run_key,
                VerificationState.UNKNOWN,
                (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,),
            )
        if not _matches_stored(stored, request):
            return AuditVerifyResult(
                request.run_key, VerificationState.INVALID, (ReasonCode.SOURCE_UNVERIFIED,)
            )
        return AuditVerifyResult(request.run_key, VerificationState.VERIFIED, ())

    def committed(self, run_key: RunKey) -> tuple[CommittedVerdict, ...]:
        """run의 저장된 판정을 sequence 순으로 반환한다."""
        entries = [entry for (key, _), entry in self._by_event.items() if key == run_key]
        return tuple(sorted(entries, key=lambda entry: entry.receipt.sequence))


def _matches_stored(stored: CommittedVerdict, request: AuditVerifyRequest) -> bool:
    """영수증 겉모양이 아니라 저장된 판정에서 fingerprint를 다시 계산해 비교한다."""
    recomputed = verdict_fingerprint(stored.verdict)
    return (
        stored.receipt.run_key == request.run_key
        and stored.receipt == request.receipt
        and stored.receipt.binding == request.expected
        and recomputed == request.expected.record_fingerprint
    )
