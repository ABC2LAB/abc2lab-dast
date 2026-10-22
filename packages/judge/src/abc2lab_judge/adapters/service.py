"""내부 판정을 공개 `Verdict`로 발행하고 자기 감사에 commit·검증하는 제공자 어댑터.

흐름(C4 계약 §3): event_ref 선고정 → `Verdict` 구성 → `verdict_fingerprint` → journal commit →
영수증 → `verify_committed`(저장 내용에서 재계산 대조) → `VerdictProjected`. 공개 호출 포트
(`JudgePort`)와 `JudgeResult` 래퍼는 이번 범위가 아니며, 미래 포트가 아래 예외를 결과로 감싼다.
판정 알고리즘·근거 재검증은 하지 않는다(코어·후속 범위). 전송·저장·판정 상태를 꾸미지 않고 실패는
시끄럽게 올린다.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from uuid import uuid4

from abc2lab_contracts.audit import AuditEventKind, AuditVerifyRequest, VerificationState
from abc2lab_contracts.primitives import ReasonCode, Ref, RunKey
from abc2lab_contracts.projection import VerdictProjected

from abc2lab_judge.adapters.journal import (
    JournalCommitError,
    VerdictJournal,
    verdict_record_binding,
)
from abc2lab_judge.adapters.translation import VerdictContext, to_verdict
from abc2lab_judge.core.model import OracleVerdict

_LOGGER = logging.getLogger(__name__)


def new_event_ref(producer: Ref, run_key: RunKey) -> Ref:
    """다른 판정과 겹치지 않는 새 감사 event_ref를 만든다(commit 전에 고정한다)."""
    return f"{producer}:{run_key.run_ref}:{uuid4().hex}"


class VerdictPublisher:
    """내부 판정을 공개 `Verdict`로 발행하고 commit·검증한 `VerdictProjected`를 낸다."""

    def __init__(
        self,
        journal: VerdictJournal,
        producer: Ref,
        *,
        event_ref_factory: Callable[[Ref, RunKey], Ref] = new_event_ref,
    ) -> None:
        self._journal = journal
        self._producer = producer
        self._new_event_ref = event_ref_factory

    async def publish(self, oracle: OracleVerdict, context: VerdictContext) -> VerdictProjected:
        """판정을 발행하고 저장을 검증한 투영 이벤트를 반환한다.

        Raises:
            ValueError: 미확정 판정인데 공개 사유가 하나도 없다(`Verdict` 생성자가 거부). 계약 사유
                코드 부재를 채움용 코드로 막지 않고 그대로 드러낸다.
            JournalCommitError: commit·검증을 확인하지 못했다. `reason_code`에 계약 사유를 담는다.
        """
        event_ref = self._new_event_ref(self._producer, context.run_key)
        verdict = to_verdict(oracle, context, producer=self._producer, event_ref=event_ref)

        receipt = await self._journal.append(verdict)
        expected = verdict_record_binding(verdict)
        if receipt.run_key != verdict.run_key or receipt.binding != expected:
            _log_failure("receipt mismatch", verdict.verdict_ref, ReasonCode.AUDIT_COMMIT_FAILED)
            raise JournalCommitError(
                "journal returned a receipt for another record",
                reason_code=ReasonCode.AUDIT_COMMIT_FAILED,
            )

        verification = await self._journal.verify_committed(
            AuditVerifyRequest(run_key=verdict.run_key, receipt=receipt, expected=expected)
        )
        verified = (
            verification.run_key == verdict.run_key
            and verification.state is VerificationState.VERIFIED
        )
        if not verified:
            reason = (
                ReasonCode.AUDIT_VERIFICATION_UNKNOWN
                if verification.state is VerificationState.UNKNOWN
                else ReasonCode.AUDIT_COMMIT_FAILED
            )
            _log_failure("verification failed", verdict.verdict_ref, reason)
            raise JournalCommitError("verdict commit verification failed", reason_code=reason)

        _LOGGER.info(
            "judge verdict committed: run=%s verdict=%s revision=%s value=%s",
            verdict.run_key.run_ref,
            verdict.verdict_ref,
            verdict.revision,
            verdict.value,
        )
        return VerdictProjected(
            kind=AuditEventKind.VERDICT,
            event_ref=event_ref,
            run_key=verdict.run_key,
            producer=self._producer,
            source_revision=verdict.revision,
            source_receipt=receipt,
            verdict=verdict,
        )


def _log_failure(stage: str, verdict_ref: Ref, reason: ReasonCode) -> None:
    _LOGGER.error("judge verdict %s: verdict=%s reason=%s", stage, verdict_ref, reason)
