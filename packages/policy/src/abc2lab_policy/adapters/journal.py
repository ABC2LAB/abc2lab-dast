"""Policy 결정 journal 포트와 메모리 어댑터.

Policy는 자기 결정을 자기 journal에만 commit하고, 같은 journal이 `verify_committed`로 저장된
기록을 다시 읽어 대조한다(S1 §10). 이 포트는 policy 소유이며 contracts를 바꾸지 않는다. Gateway는
같은 객체를 `AuditVerifier`로 주입받아 결정의 commit을 검증한다.
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
from abc2lab_contracts.execution import PolicyDecisionContent
from abc2lab_contracts.fingerprint import policy_decision_content_fingerprint
from abc2lab_contracts.ports import AuditVerifier
from abc2lab_contracts.primitives import ReasonCode, Ref, RunKey

# 정책 결정은 불변 기록이므로 record_revision은 항상 1이다(S1 §10).
DECISION_RECORD_REVISION = 1


class JournalCommitError(Exception):
    """결정 commit을 확인하지 못했다. `reason_code`에 계약 사유를 담는다."""

    def __init__(
        self, message: str, *, reason_code: ReasonCode = ReasonCode.AUDIT_COMMIT_FAILED
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class PolicyDecisionJournal(AuditVerifier, Protocol):
    """Policy 결정의 commit과 저장 기록 검증을 함께 제공하는 policy 소유 포트.

    구현 계약:
    - `append`: 결정 내용을 내구 commit하고 영수증을 반환한다. 저장 실패·commit 불명을 빈 성공으로
      바꾸지 말고 사유 코드를 담은 `JournalCommitError`로 알린다. 같은 decision_ref에 다른 내용이
      이미 있으면 `idempotency_conflict`로 올린다.
    - `verify_committed`(`AuditVerifier`): 저장 기록을 실제로 다시 읽어 run·영수증·binding과 저장
      내용에서 **재계산한 fingerprint**를 대조한다. 기록을 읽을 수 없으면 예외 대신
      `VerificationState.UNKNOWN`을, 내용이 다르면 사유 코드를 담은 `INVALID`를 반환한다.
    - `asyncio.CancelledError`는 감싸지 않고 전파한다.
    """

    async def append(self, content: PolicyDecisionContent, request_ref: Ref) -> AuditReceipt:
        """결정 내용을 불변으로 commit하고 영수증을 반환한다.

        Raises:
            JournalCommitError: commit을 확인하지 못했거나 같은 decision_ref에 다른 내용이 있다.
        """
        ...


def decision_record_binding(content: PolicyDecisionContent, request_ref: Ref) -> AuditRecordBinding:
    """결정 내용의 업무 필드에서 감사 binding을 계산한다. 영수증 binding을 복사하지 않는다."""
    return AuditRecordBinding(
        event_kind=AuditEventKind.POLICY_DECISION,
        record_ref=content.decision_ref,
        record_revision=DECISION_RECORD_REVISION,
        record_fingerprint=policy_decision_content_fingerprint(content),
        request_ref=request_ref,
        attempt_ref=None,
        binding_id=content.binding_id,
    )


@dataclass(frozen=True, slots=True)
class CommittedDecision:
    """journal에 저장된 결정 내용과 그 영수증."""

    content: PolicyDecisionContent
    receipt: AuditReceipt


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryPolicyDecisionJournal:
    """흐름 테스트용 비내구 메모리 journal.

    프로세스가 끝나면 기록이 사라지므로 app은 이 어댑터를 실제 transport와 연결하지 않는다.
    같은 event loop의 단일 스레드에서 호출하며 `append`의 상태 변경 구간에는 await가 없다.
    """

    def __init__(self, producer: Ref, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._producer = producer
        self._clock = clock
        self._by_event: dict[tuple[RunKey, Ref], CommittedDecision] = {}
        self._by_decision: dict[tuple[RunKey, Ref], CommittedDecision] = {}
        self._sequences: dict[RunKey, int] = {}

    async def append(self, content: PolicyDecisionContent, request_ref: Ref) -> AuditReceipt:
        """결정 내용을 commit한다. 같은 내용의 재commit은 기존 영수증을 반환한다."""
        binding = decision_record_binding(content, request_ref)
        existing = self._by_decision.get((content.run_key, content.decision_ref))
        if existing is not None:
            if existing.receipt.binding == binding:
                return existing.receipt
            raise JournalCommitError(
                "decision_ref already committed with different content",
                reason_code=ReasonCode.IDEMPOTENCY_CONFLICT,
            )
        # run/producer별 sequence는 1부터 1씩 증가한다(S1 §10).
        sequence = self._sequences.get(content.run_key, 0) + 1
        receipt = AuditReceipt(
            run_key=content.run_key,
            producer=self._producer,
            event_ref=f"{self._producer}:{content.run_key.run_ref}:{sequence}",
            sequence=sequence,
            binding=binding,
            committed_at=self._clock(),
        )
        entry = CommittedDecision(content=content, receipt=receipt)
        self._sequences[content.run_key] = sequence
        self._by_event[(content.run_key, receipt.event_ref)] = entry
        self._by_decision[(content.run_key, content.decision_ref)] = entry
        return receipt

    async def verify_committed(self, request: AuditVerifyRequest) -> AuditVerifyResult:
        """저장된 기록을 다시 읽어 run·영수증·binding·재계산 fingerprint를 모두 대조한다."""
        stored = self._by_event.get((request.run_key, request.receipt.event_ref))
        if stored is None or not _matches_stored(stored, request):
            return AuditVerifyResult(
                request.run_key, VerificationState.INVALID, (ReasonCode.SOURCE_UNVERIFIED,)
            )
        return AuditVerifyResult(request.run_key, VerificationState.VERIFIED, ())

    def committed(self, run_key: RunKey) -> tuple[CommittedDecision, ...]:
        """run의 저장된 결정을 sequence 순으로 반환한다."""
        entries = [entry for (key, _), entry in self._by_event.items() if key == run_key]
        return tuple(sorted(entries, key=lambda entry: entry.receipt.sequence))


def _matches_stored(stored: CommittedDecision, request: AuditVerifyRequest) -> bool:
    """영수증 겉모양이 아니라 저장된 내용에서 fingerprint를 다시 계산해 비교한다."""
    recomputed = policy_decision_content_fingerprint(stored.content)
    return (
        stored.receipt.run_key == request.run_key
        and stored.receipt == request.receipt
        and stored.receipt.binding == request.expected
        and recomputed == request.expected.record_fingerprint
    )
