"""gateway 실행 감사 journal 포트와 메모리 어댑터.

Gateway는 전송 전 불변 intent(`RequestIntentRecord`)와 전송 시도 결과(`AttemptRecord`)를 자기
journal에 commit하고, 같은 journal이 `verify_committed`로 저장 내용에서 **fingerprint를 재계산**해
대조한다(§10 ②·⑤). 이 포트는 gateway 소유이며 contracts를 바꾸지 않는다. 원문·자격·캡처 핸들·남은
예산은 담지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from abc2lab_contracts.audit import (
    AttemptRecord,
    AuditEventKind,
    AuditReceipt,
    AuditRecordBinding,
    AuditVerifyRequest,
    AuditVerifyResult,
    RequestIntentRecord,
    VerificationState,
)
from abc2lab_contracts.fingerprint import attempt_fingerprint, request_intent_fingerprint
from abc2lab_contracts.ports import AuditVerifier
from abc2lab_contracts.primitives import ReasonCode, Ref, RunKey


class JournalCommitError(Exception):
    """감사 기록 commit을 확인하지 못했다. `reason_code`에 계약 사유를 담는다."""

    def __init__(
        self, message: str, *, reason_code: ReasonCode = ReasonCode.AUDIT_COMMIT_FAILED
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def intent_record_binding(record: RequestIntentRecord) -> AuditRecordBinding:
    """intent 내용에서 감사 binding을 계산한다(record_ref=attempt_ref, revision=1)."""
    return AuditRecordBinding(
        event_kind=AuditEventKind.REQUEST_INTENT,
        record_ref=record.attempt_ref,
        record_revision=1,
        record_fingerprint=request_intent_fingerprint(record),
        request_ref=record.request_ref,
        attempt_ref=record.attempt_ref,
        binding_id=record.binding_id,
    )


def attempt_record_binding(record: AttemptRecord) -> AuditRecordBinding:
    """attempt 내용에서 감사 binding을 계산한다(ATTEMPT: record_ref=attempt_ref=attempt_ref)."""
    return AuditRecordBinding(
        event_kind=AuditEventKind.ATTEMPT,
        record_ref=record.attempt_ref,
        record_revision=record.revision,
        record_fingerprint=attempt_fingerprint(record),
        request_ref=record.request_ref,
        attempt_ref=record.attempt_ref,
        binding_id=record.binding_id,
    )


class GatewayJournal(AuditVerifier, Protocol):
    """intent·attempt commit과 저장 기록 검증을 함께 제공하는 gateway 소유 포트.

    구현 계약: `append_intent`/`append_attempt`는 기록을 내구 commit하고 영수증을 반환한다. 저장
    실패·commit 불명을 빈 성공으로 바꾸지 말고 `JournalCommitError`로 알린다. `verify_committed`는
    저장 기록을 다시 읽어 run·영수증·binding과 저장 내용에서 재계산한 fingerprint를 대조한다.
    `asyncio.CancelledError`는 감싸지 않고 전파한다.
    """

    async def append_intent(self, record: RequestIntentRecord) -> AuditReceipt:
        """전송 전 intent를 불변으로 commit한다."""
        ...

    async def append_attempt(self, record: AttemptRecord) -> AuditReceipt:
        """전송 시도 결과를 불변으로 commit한다."""
        ...


@dataclass(frozen=True, slots=True)
class _Committed:
    fingerprint: str
    binding: AuditRecordBinding
    receipt: AuditReceipt


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryGatewayJournal:
    """흐름 테스트용 비내구 메모리 journal. 같은 loop의 단일 스레드에서 호출한다."""

    def __init__(self, producer: Ref, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._producer = producer
        self._clock = clock
        self._by_event: dict[tuple[RunKey, Ref], _Committed] = {}
        self._sequences: dict[RunKey, int] = {}

    async def append_intent(self, record: RequestIntentRecord) -> AuditReceipt:
        """intent를 commit한다. 같은 attempt의 재commit은 기존 영수증을 반환한다."""
        event_ref = f"{self._producer}:{record.run_key.run_ref}:intent:{record.attempt_ref}"
        return self._commit(
            record.run_key,
            event_ref,
            request_intent_fingerprint(record),
            intent_record_binding(record),
        )

    async def append_attempt(self, record: AttemptRecord) -> AuditReceipt:
        """attempt를 commit한다. 같은 (attempt, revision) 재commit은 기존 영수증을 반환한다."""
        run_ref = record.run_key.run_ref
        event_ref = f"{self._producer}:{run_ref}:attempt:{record.attempt_ref}:{record.revision}"
        return self._commit(
            record.run_key, event_ref, attempt_fingerprint(record), attempt_record_binding(record)
        )

    def _commit(
        self, run_key: RunKey, event_ref: Ref, fingerprint: str, binding: AuditRecordBinding
    ) -> AuditReceipt:
        existing = self._by_event.get((run_key, event_ref))
        if existing is not None:
            if existing.fingerprint == fingerprint and existing.binding == binding:
                return existing.receipt
            raise JournalCommitError(
                "audit event already committed with different content",
                reason_code=ReasonCode.IDEMPOTENCY_CONFLICT,
            )
        sequence = self._sequences.get(run_key, 0) + 1
        receipt = AuditReceipt(
            run_key=run_key,
            producer=self._producer,
            event_ref=event_ref,
            sequence=sequence,
            binding=binding,
            committed_at=self._clock(),
        )
        self._sequences[run_key] = sequence
        self._by_event[(run_key, event_ref)] = _Committed(fingerprint, binding, receipt)
        return receipt

    def committed_count(self, run_key: RunKey) -> int:
        """run에 commit된 감사 이벤트 수(intent+attempt). 테스트 보조용이다."""
        return sum(1 for (run, _event) in self._by_event if run == run_key)

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        """저장된 기록의 재계산 fingerprint·binding·영수증을 대조한다."""
        stored = self._by_event.get((request.run_key, request.receipt.event_ref))
        if stored is None:
            return AuditVerifyResult(
                request.run_key, VerificationState.UNKNOWN, (ReasonCode.AUDIT_VERIFICATION_UNKNOWN,)
            )
        matches = (
            stored.receipt == request.receipt
            and stored.binding == request.expected
            and stored.fingerprint == request.expected.record_fingerprint
        )
        if not matches:
            return AuditVerifyResult(
                request.run_key, VerificationState.INVALID, (ReasonCode.SOURCE_UNVERIFIED,)
            )
        return AuditVerifyResult(request.run_key, VerificationState.VERIFIED, ())
